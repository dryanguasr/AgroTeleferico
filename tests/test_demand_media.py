#!/usr/bin/env python3
"""Local media contracts; no ROS, Gazebo or live sensors are exercised here."""
from pathlib import Path
import importlib
import io
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from validate_demand_native import (demand_inputs, configure_demand_world, in_video_window,
                                    validate_window, validate_recording_window,
                                    cli_command, compare_csv, CSV_FILES)
from compose_telemetry_hud import Timeline
from compose_demand_hud import (DEMAND_FIELDS, DemandHud, demand_snapshot,
                                electrical_estimate_wh, validate_capture_times, POLICIES)
from PIL import Image


def state(time=600, policy=0):
    row = {key: 0. for key in DEMAND_FIELDS}
    row.update(time_s=float(time), policy=float(policy), phase=1.,
               slack_up_s=-1., slack_down_s=-1., next_dispatch_s=-1.,
               inventory_lower_kg=10., inventory_upper_kg=10.)
    return row


class DemandMediaTests(unittest.TestCase):
    def test_window_is_half_open_and_floating_tolerant(self):
        self.assertFalse(in_video_window(599.8, 600, 1200))
        self.assertTrue(in_video_window(600 - 1e-10, 600, 1200))
        self.assertTrue(in_video_window(1199.8, 600, 1200))
        self.assertFalse(in_video_window(1200 - 1e-10, 600, 1200))
        self.assertTrue(in_video_window(20, 0, None))

    def test_invalid_window(self):
        for args in [(-1, 1200, 1200), (600, 600, 1200), (600, 1201, 1200),
                     (float('nan'), 1200, 1200), (600, None, 600)]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                validate_window(*args)
        validate_window(600, 1200, 1200)

    def test_exact_ticks_not_just_count(self):
        times = [600 + index/5 for index in range(3000)]
        validate_capture_times(times)
        for mutated in [times[:-1], [stamp+.04 for stamp in times], times[:10]+times[11:]+[1200.]]:
            with self.assertRaises(ValueError):
                validate_capture_times(mutated)

    def test_short_probe_sensor_start(self):
        times = [.04] + [index/5 for index in range(1, 100)]
        validate_recording_window(times, 0, 20)
        validate_recording_window([600+index/5 for index in range(3000)], 600, 1200)
        for mutated in [times[:-1], times[:10]+times[11:]+[20.], [stamp+.04 for stamp in times]]:
            with self.assertRaises(ValueError):
                validate_recording_window(mutated, 0, 20)

    def test_historical_world_is_untouched(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'world.sdf'
            content = '<sdf><world name="x"/></sdf>'
            path.write_text(content)
            configure_demand_world(path, None)
            self.assertEqual(path.read_text(), content)
        self.assertIsNone(demand_inputs(None, None, None, None))

    def test_complete_inputs_and_exact_sdf_tags(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            paths = []
            for name in ('orders.csv', 'dispatch.params', 'predictor.csv'):
                path = root/name
                path.write_text('test')
                paths.append(path)
            inputs = demand_inputs(paths[0], paths[1], 'D', paths[2])
            world = root/'world.sdf'
            world.write_text('<sdf><world name="x"><plugin name="agro::LoopSystem"><mode>central_only</mode></plugin></world></sdf>')
            configure_demand_world(world, inputs)
            configure_demand_world(world, inputs)
            plugin = ET.parse(world).find("world/plugin")
            for key, value in inputs.items():
                self.assertEqual(plugin.findtext(key), value)
                self.assertEqual(len(plugin.findall(key)), 1)
            self.assertEqual(plugin.findtext('mode'), 'central_only')
            command = cli_command('cli', 'core.params', 'new-output', inputs)
            self.assertNotIn('--compact', command)
            self.assertIn('--no-wind', command)
            self.assertEqual(command[command.index('--policy')+1], 'D')

    def test_partial_or_missing_inputs_rejected(self):
        with self.assertRaises(ValueError):
            demand_inputs('a.csv', None, 'A', None)
        with self.assertRaises(ValueError):
            demand_inputs('missing.csv', 'missing.params', 'E', 'missing.csv')
        with self.assertRaises(ValueError):
            demand_inputs('missing.csv', 'missing.params', 'A', 'missing.csv')

    def test_parity_includes_demand_telemetry(self):
        with tempfile.TemporaryDirectory() as folder:
            a, b = Path(folder)/'a', Path(folder)/'b'
            a.mkdir(); b.mkdir()
            for name in CSV_FILES+('demand_status.csv',):
                (a/name).write_text('time_s,value\n0,1\n')
                (b/name).write_text('time_s,value\n0,1\n')
            self.assertTrue(all(entry['identical'] for entry in compare_csv(a, b).values()))
            (b/'demand_status.csv').write_text('time_s,value\n0,2\n')
            self.assertFalse(compare_csv(a, b)['demand_status.csv']['identical'])

    def test_causal_demand_sample(self):
        before, future = state(600), state(600.05)
        future['queue_up'] = 9
        timeline = Timeline([before, future])
        row, lag = demand_snapshot(timeline, 600.04, 0)
        self.assertEqual(row['queue_up'], 0)
        self.assertAlmostEqual(lag, .04)
        with self.assertRaises(ValueError):
            demand_snapshot(timeline, 599.99, 0)
        with self.assertRaises(ValueError):
            demand_snapshot(timeline, 600.2, 0)

    def test_wrong_policy_phase_and_mass_rejected(self):
        for key, value in [('policy', 2), ('phase', 7), ('queue_up', .2),
                           ('operator_lower', 2), ('useful_1_kg', 11), ('aux_0_kg', -1)]:
            row = state()
            row[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                demand_snapshot(Timeline([row]), 600, 0)

    def test_incomplete_schema_rejected(self):
        row = state()
        del row['early_upper_kg']
        with self.assertRaises(ValueError):
            demand_snapshot(Timeline([row]), 600, 0)

    def test_hypothetical_electricity_has_no_recovery_credit(self):
        self.assertAlmostEqual(electrical_estimate_wh(850, 600), 4000/3600)
        self.assertEqual(electrical_estimate_wh(0, 0), 0)

    def test_all_four_hud_layouts_render(self):
        overview = Image.new('RGB', (1280, 800), '#8eb4cc')
        values = {'global': [{'speed_m_s': .2, 'power_W': -2,
                             'drive_positive_J': 100., 'drive_absorbed_J': 150., 'residual_J': 2.}],
                  'carriers': [{'id': 0, 'swing_x_rad': .01, 'swing_y_rad': .02},
                               {'id': 1, 'swing_x_rad': 0., 'swing_y_rad': .01}],
                  'cables': [{'max_tension_N': 350.}, {'max_tension_N': 360.}]}
        for policy in POLICIES:
            row = state(policy=policy)
            row.update(queue_up=3., queue_down=2., slack_up_s=-100., slack_down_s=300.,
                       delivered_orders=12., late_orders=2., useful_0_kg=8., aux_0_kg=2.,
                       next_dispatch_s=630., operator_lower=1.)
            frame = DemandHud(policy).draw(overview, overview, 600, values, row, {'demand': .04})
            self.assertEqual(frame.size, (1920, 1080))
            self.assertEqual(frame.mode, 'RGB')

    def test_encoder_timeout_is_reaped_and_recorded(self):
        package = types.ModuleType('ament_index_python.packages')
        package.get_package_prefix = Mock(side_effect=AssertionError('Must not query ROS in unit test'))
        with patch.dict(sys.modules, {'ament_index_python': types.ModuleType('ament_index_python'),
                                      'ament_index_python.packages': package}):
            capture = importlib.import_module('capture_loop')
        encoder = Mock()
        encoder.stdin = io.BytesIO()
        encoder.poll.side_effect = [None, 0]
        encoder.wait.side_effect = [subprocess.TimeoutExpired('ffmpeg', 30), 0]
        encoder.returncode = 0
        errors = []
        capture.finish_encoder(encoder, 'Overview', errors)
        self.assertTrue(encoder.stdin.closed)
        encoder.terminate.assert_called_once()
        encoder.kill.assert_not_called()
        self.assertEqual(len(errors), 1)


if __name__ == '__main__':
    unittest.main()
