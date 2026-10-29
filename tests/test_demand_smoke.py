"""Fail closed before launching workloads, preserve prior output directories."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import run_demand_smoke as smoke


class Admission(unittest.TestCase):
    def test_linux_feed_rejects_wsl(self):
        with patch.object(smoke.platform, 'release', return_value='6.6-microsoft-standard-WSL2'):
            with self.assertRaisesRegex(RuntimeError, 'Windows supervisor'):
                smoke.linux_sample()

    def test_low_memory_never_starts_subprocess(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)/'new'
            with patch.object(sys, 'argv', ['smoke', '--output', str(out), '--host-memory', str(Path(temp)/'feed.json')]), \
                 patch.object(smoke, 'read_host_memory', return_value=6.9), \
                 patch.object(smoke.subprocess, 'Popen') as launch:
                with self.assertRaisesRegex(RuntimeError, '7 GiB'):
                    smoke.main()
                launch.assert_not_called()
            self.assertFalse(json.loads((out/'smoke.json').read_text())['passed'])

    def test_existing_evidence_is_never_reused(self):
        with tempfile.TemporaryDirectory() as temp:
            marker = Path(temp)/'smoke.json'
            marker.write_text('preserved')
            with patch.object(sys, 'argv', ['smoke', '--output', temp, '--host-memory', str(Path(temp)/'feed.json')]):
                with self.assertRaises(FileExistsError):
                    smoke.main()
            self.assertEqual(marker.read_text(), 'preserved')


if __name__ == '__main__':
    unittest.main()
