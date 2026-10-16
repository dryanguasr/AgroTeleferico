"""Reject invalid resource evidence without starting Gazebo or any child process."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from run_loop_guarded import read_host_memory


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


if __name__ == '__main__':
    unittest.main()
