#!/usr/bin/env python3
"""Scoped process cleanup must never signal a reused or unobserved PID."""
from pathlib import Path
import signal
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import demand_guard as guard


class GuardTests(unittest.TestCase):
    def test_reused_pid_is_not_owned(self):
        with patch.object(guard, 'process_identity', side_effect=lambda pid: {11: 'old', 12: 'new'}.get(pid)):
            self.assertEqual(guard.live_owned({11: 'old', 12: 'old', 13: None}), [11])

    def test_group_disappearing_during_signal_is_normal(self):
        with patch.object(guard.os, 'killpg', side_effect=ProcessLookupError):
            guard.signal_group(123, signal.SIGTERM)

    def test_cleanup_signals_only_observed_same_identity(self):
        live = {11: 'same', 12: 'reused'}
        calls = []
        def kill(pid, sig):
            calls.append((pid, sig))
            live.pop(pid, None)
        with patch.object(guard, 'process_identity', side_effect=lambda pid: live.get(pid)), patch.object(guard.os, 'kill', side_effect=kill):
            actions = []
            self.assertEqual(guard.cleanup_owned({11: 'same', 12: 'previous'}, actions), [])
        self.assertEqual(calls, [(11, signal.SIGTERM)])
        self.assertEqual(actions, [{'signal': 'SIGTERM', 'pid': 11}])
        self.assertEqual(live, {12: 'reused'})

    def test_zombie_and_missing_are_finished(self):
        fields = ['Z'] + ['0'] * 18 + ['31415']
        with patch.object(Path, 'read_text', return_value='5 (name with spaces) ' + ' '.join(fields)):
            self.assertIsNone(guard.process_identity(5))
        fields[0] = 'S'
        with patch.object(Path, 'read_text', return_value='5 (name with spaces) ' + ' '.join(fields)):
            self.assertEqual(guard.process_identity(5), '31415')
        with patch.object(Path, 'read_text', side_effect=FileNotFoundError):
            self.assertIsNone(guard.process_identity(5))


if __name__ == '__main__':
    unittest.main()
