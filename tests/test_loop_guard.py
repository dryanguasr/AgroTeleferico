"""Check admission and effective case inputs without starting ROS/Gazebo."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from run_loop_guarded import read_host_memory, prepare_case
from generate_ballasted import config as pilot_config


class HostMemory(unittest.TestCase):
    def read_sample(self, sample):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'memory.json'
            path.write_text(json.dumps(sample), encoding='utf-8-sig')
            return read_host_memory(path, now=100)

    def test_fresh_sample_with_bom(self):
        self.assertEqual(self.read_sample({'unix_s':99,'free_gib':7.5}),7.5)

    def test_drvfs_transient_is_retried_but_stale_evidence_rejected(self):
        with patch.object(Path, 'read_text', side_effect=[OSError(61, 'No data available'), '{"unix_s":99,"free_gib":12}']), patch('run_loop_guarded.time.sleep'):
            self.assertEqual(read_host_memory('unused', now=100), 12)
        with patch.object(Path, 'read_text', side_effect=[OSError(61, 'No data available'), '{"unix_s":80,"free_gib":12}']), patch('run_loop_guarded.time.sleep'), self.assertRaises(RuntimeError):
            read_host_memory('unused', now=100)

    def test_repeated_io_failure_stops_after_three_attempts(self):
        with patch.object(Path, 'read_text', side_effect=OSError(61, 'No data available')) as reader, patch('run_loop_guarded.time.sleep'), self.assertRaises(OSError):
            try:
                read_host_memory('unused', now=100)
            finally:
                self.assertEqual(reader.call_count, 3)

    def test_invalid_evidence_fails_closed(self):
        samples = [
            {'unix_s':84,'free_gib':12},
            {'unix_s':106,'free_gib':12},
            {'unix_s':99,'free_gib':float('nan')},
            {'unix_s':99,'free_gib':float('inf')},
            {'unix_s':99,'free_gib':-1},
            {'unix_s':99,'free_gib':True},
            {'unix_s':99,'free_gib':12,'error':'CIM failed'},
        ]
        for sample in samples:
            with self.subTest(sample=sample), self.assertRaises(RuntimeError):
                self.read_sample(sample)


class CasePreparation(unittest.TestCase):
    cases = (
        ('central_gust', .002, .02, True),
        ('hybrid_gust', .002, .02, True),
        ('hybrid_calm', .002, .02, False),
        ('hybrid_half_dt', .001, .02, True),
        ('hybrid_half_shape', .002, .01, True),
    )

    def test_ballasted_options_reach_generator(self):
        for case, dt, shape_period, gust in self.cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                out = Path(directory)
                expected_world = out/'pilot/generated/world.sdf'
                with patch('generate_ballasted.generate', return_value=expected_world) as generate:
                    world, config = prepare_case(out, case, 'ladera_agricola')
                generate.assert_called_once_with(
                    'ladera_agricola', out/'pilot', dt=dt, shape_period=shape_period,
                    calm=not gust, stop_at_end=True, variant='revised_supports')
                self.assertEqual(world, expected_world)
                recorded = yaml.safe_load(config.read_text())
                self.assertEqual((recorded['dt'], recorded['shape_period']), (dt, shape_period))

    def test_effective_ballasted_inputs_agree(self):
        # Actual file generation, no simulation: check the input the plugin will
        # read as well as the supervisor record and human-readable metadata.
        for case, dt, shape_period, gust in self.cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                out = Path(directory)
                world, config = prepare_case(out, case, 'ladera_agricola')
                recorded = yaml.safe_load(config.read_text())
                pilot_input = yaml.safe_load((out/'pilot/input.yaml').read_text())
                metadata = json.loads((world.parent/'metadata.json').read_text())
                self.assertEqual(recorded, pilot_input)
                self.assertEqual(recorded, metadata['core'])
                self.assertEqual((recorded['dt'], recorded['shape_period']), (dt, shape_period))
                self.assertEqual(metadata['scenario']['gust'], gust)
                self.assertEqual(metadata['scenario']['equipment_variant'], 'revised_supports')
                plugin = ET.parse(world).getroot().find("world/plugin[@name='agro::LoopSystem']")
                self.assertEqual(plugin.findtext('gust'), str(gust).lower())
                self.assertEqual(plugin.findtext('mode'), 'central_only')
                self.assertEqual(plugin.findtext('stop_at_end'), 'true')
                params = Path(plugin.findtext('params'))
                self.assertEqual(params, world.parent/'loop.params')
                effective = {}
                for line in params.read_text().splitlines():
                    if not line or line.startswith('#'):
                        continue
                    key, *values = line.split()
                    if key == 'terrain':
                        self.assertEqual(int(values[0]), len(recorded['terrain']))
                        coords = list(map(float, values[1:]))
                        effective[key] = [coords[i:i+2] for i in range(0, len(coords), 2)]
                    else:
                        effective[key] = float(values[0])
                self.assertEqual(effective, recorded)

    def test_variants_and_patio_alias_preserve_selection(self):
        # Previous positional callers keep their variant argument in position 5.
        for variant in ('baseline', 'compact_candidate', 'revised_supports'):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as directory:
                out = Path(directory)
                expected, _, _ = pilot_config('buitrago_patio', None, None, False, variant)
                with patch('generate_ballasted.generate', return_value=out/'world.sdf') as generate:
                    _, config = prepare_case(out, 'central_gust', 'buitrago_patio', variant)
                self.assertEqual(yaml.safe_load(config.read_text()), expected)
                self.assertEqual(generate.call_args.kwargs['variant'], variant)
        patio, _, _ = pilot_config('buitrago_patio')
        pisos, _, _ = pilot_config('buitrago_entre_pisos')
        self.assertEqual(patio, pisos)
        self.assertEqual(patio['terrain'], [[0, 0], [8.6, 3.2]])

    def test_historical_loop_options_are_preserved(self):
        for case, dt, shape_period, gust in self.cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                out = Path(directory)
                with patch('run_loop_guarded.read_config', return_value={'dt': .002, 'shape_period': .02}), \
                        patch('run_loop_guarded.generate', return_value=out/'world.sdf') as generate:
                    _, config = prepare_case(out, case)
                self.assertEqual(yaml.safe_load(config.read_text()), {'dt': dt, 'shape_period': shape_period})
                generate.assert_called_once_with(
                    config, out/'generated',
                    mode='central_only' if case == 'central_gust' else 'central_local',
                    gust=gust, stop_at_end=True)


if __name__ == '__main__':
    unittest.main()
