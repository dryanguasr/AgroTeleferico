"""HUD synchronization/drawing/cleanup tests; no simulation or encoder starts."""
from collections import defaultdict
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import Mock
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from compose_telemetry_hud import Timeline, require_synchronized_cameras, Hud, stop_processes


class PreviousSample(unittest.TestCase):
    def test_never_reads_future_or_interpolates(self):
        timeline = Timeline([{'time_s': 0, 'x': 10}, {'time_s': .05, 'x': 20},
                             {'time_s': .10, 'x': 30}])
        self.assertEqual(timeline.previous(.049)[0][0]['x'], 10)
        self.assertEqual(timeline.previous(.05)[0][0]['x'], 20)
        self.assertEqual(timeline.previous(.099)[0][0]['x'], 20)
        self.assertAlmostEqual(timeline.previous(.099)[1], .049)

    def test_missing_and_stale_samples_fail(self):
        timeline = Timeline([{'time_s': .05, 'x': 20}])
        for stamp in (0, .04, .102):
            with self.subTest(stamp=stamp), self.assertRaises(ValueError):
                timeline.previous(stamp)
        self.assertAlmostEqual(timeline.previous(.101)[1], .051)

    def test_preserves_identities_and_accepts_identical_final_flush(self):
        rows = [{'time_s': .1, 'id': 0, 'x': 1}, {'time_s': .1, 'id': 1, 'x': 2}]
        timeline = Timeline(rows + rows, ('id',))
        self.assertEqual(len(timeline.previous(.1)[0]), 2)
        with self.assertRaises(ValueError):
            Timeline(rows + [{'time_s': .1, 'id': 0, 'x': 5}], ('id',))

    def test_invalid_order_and_nonfinite_values_fail(self):
        for rows in ([{'time_s': 1}, {'time_s': 0}],
                     [{'time_s': 0, 'x': float('nan')}], []):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                Timeline(rows)

    def test_camera_mismatch_and_missing_frames_fail(self):
        require_synchronized_cameras([.04, .2, .4], [.04, .2, .4])
        for overview, follow in (([.04, .2], [.04, .21]),
                                 ([.04, .2], [.04]),
                                 ([.04, .4], [.04, .4])):
            with self.subTest(overview=overview, follow=follow), self.assertRaises(ValueError):
                require_synchronized_cameras(overview, follow)


class DrawingAndCleanup(unittest.TestCase):
    def test_draw_progress_from_zero_to_full_without_invalid_rectangles(self):
        hud = Hud({'scenario': {'name': 'Prueba sintética'}, 'core': {'max_tension': 4000}},
                  {'reference_loop_m': 25}, 0)
        blank = Image.new('RGB', (1280, 800))
        values = {'global': [defaultdict(float)],
                  'carriers': [defaultdict(float, id=i) for i in (0, 1)],
                  'bases': [defaultdict(float, station=i) for i in (0, 1)],
                  'cables': [{'max_tension_N': 200.}]}
        for progress in (0, 1e-15, .0001, .001, 1):
            with self.subTest(progress=progress):
                values['global'][0]['q_m'] = 25 * progress
                image = hud.draw(blank, blank, 0, values, {'global': 0})
                self.assertEqual(image.size, (1920, 1080))
                if progress == 1:
                    self.assertEqual(image.getpixel((1871, 242)), (87, 212, 232))

    def test_cleanup_closes_pipes_then_kills_timed_out_processes(self):
        processes = [Mock(pid=10), Mock(pid=11)]
        for process in processes:
            process.poll.return_value = None
            process.wait.side_effect = [subprocess.TimeoutExpired('ffmpeg', 2), 0]
        self.assertEqual(stop_processes(processes), [])
        for process in processes:
            process.stdout.close.assert_called_once()
            process.stdin.close.assert_called_once()
            process.terminate.assert_called_once()
            process.kill.assert_called_once()
            self.assertEqual([call.kwargs['timeout'] for call in process.wait.call_args_list], [2, 5])
            names = [call[0] for call in process.mock_calls]
            self.assertLess(names.index('stdout.close'), names.index('terminate'))
            self.assertLess(names.index('stdin.close'), names.index('terminate'))

    def test_cleanup_failure_does_not_mask_original_or_skip_other_process(self):
        stuck, second = Mock(pid=10), Mock(pid=11)
        stuck.poll.return_value = second.poll.return_value = None
        stuck.wait.side_effect = subprocess.TimeoutExpired('ffmpeg', 2)
        second.wait.return_value = 0
        original = ValueError('original drawing failure')
        with self.assertRaises(ValueError) as caught:
            try:
                raise original
            finally:
                errors = stop_processes((stuck, second))
        self.assertIs(caught.exception, original)
        self.assertTrue(errors)
        stuck.kill.assert_called_once()
        second.terminate.assert_called_once()
        second.wait.assert_called_once_with(timeout=2)


if __name__ == '__main__':
    unittest.main()
