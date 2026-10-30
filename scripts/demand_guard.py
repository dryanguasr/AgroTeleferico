#!/usr/bin/env python3
"""Run one explicitly described demand task with fresh host-memory supervision."""
import argparse
import base64
import json
import os
from pathlib import Path
import signal
import subprocess
import time

from supervision import read_host_memory, tree_rss


def process_identity(pid):
    try:
        fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
        return None if fields[0] == 'Z' else fields[19]
    except (FileNotFoundError, ProcessLookupError):
        return None


def live_owned(identities):
    return [pid for pid, started in identities.items()
            if started is not None and process_identity(pid) == started]


def signal_group(pid, signum):
    try:
        os.killpg(pid, signum)
    except ProcessLookupError:
        pass


def cleanup_owned(identities, actions):
    for sig, seconds in ((signal.SIGTERM, 5), (signal.SIGKILL, 3)):
        for pid in live_owned(identities):
            try:
                os.kill(pid, sig)
                actions.append({'signal': signal.Signals(sig).name, 'pid': pid})
            except ProcessLookupError:
                pass
        deadline = time.monotonic() + seconds
        while live_owned(identities) and time.monotonic() < deadline:
            time.sleep(.1)
    return live_owned(identities)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task-base64', required=True)
    parser.add_argument('--host-memory', type=Path, required=True)
    args = parser.parse_args()
    task = json.loads(base64.b64decode(args.task_base64).decode('utf-8-sig'))
    command = task['argv']
    if not isinstance(command, list) or not command or any(not isinstance(x, str) or not x or '\0' in x for x in command):
        raise ValueError('Task argv must be a nonempty list of nonempty strings')
    minimum = float(task['minimum_free_gib'])
    if minimum not in (6., 7., 7.5, 8., 9., 10.):
        raise ValueError('Admission must be 6/7/7.5 GiB for CLI/native/headless video or stricter 9/10')
    timeout = float(task.get('timeout_s', 86400))
    if not 0 < timeout <= 172800:
        raise ValueError('Task timeout outside (0,172800] seconds')
    directory = args.host_memory.resolve().parent
    if read_host_memory(args.host_memory) < minimum:
        raise RuntimeError('Fresh host admission below task minimum')
    # Placeholders are replaced as individual argv entries, never shell text.
    command = [str(args.host_memory.resolve()) if x == '{host_memory}' else x for x in command]
    (directory / 'task.json').write_text(json.dumps({**task, 'argv': command}, indent=2))
    started = time.monotonic()
    reason = None
    stop_started = None
    peak_rss = 0.
    free_min = read_host_memory(args.host_memory)
    signal_request = []
    def request_stop(signum, frame):
        signal_request.append(signum)
    previous = {sig: signal.signal(sig, request_stop) for sig in (signal.SIGINT, signal.SIGTERM)}
    process = None
    escalations = []
    identities, descendant_actions = {}, []
    remaining = []
    try:
        with (directory / 'task.stdout.log').open('w') as stdout, (directory / 'task.stderr.log').open('w') as stderr, (directory / 'resources.jsonl').open('w') as resources:
            process = subprocess.Popen(command, stdout=stdout, stderr=stderr, start_new_session=True)
            (directory / 'process.json').write_text(json.dumps({'pid': process.pid, 'pgid': process.pid, 'argv': command}))
            while process.poll() is None:
                elapsed = time.monotonic() - started
                try:
                    free = read_host_memory(args.host_memory)
                    rss, pids = tree_rss(process.pid)
                    for pid in pids:
                        identity = process_identity(pid)
                        if identity is not None:
                            identities[pid] = identity
                    free_min = min(free_min, free)
                    peak_rss = max(peak_rss, rss)
                    resources.write(json.dumps({'wall_s': elapsed, 'free_gib': free, 'tree_rss_gib': rss, 'pids': pids}) + '\n')
                    resources.flush()
                    if free < 5:
                        reason = reason or 'host_memory_below_5_gib'
                except Exception as exc:
                    reason = reason or f'monitor_error:{type(exc).__name__}:{exc}'
                if elapsed > timeout:
                    reason = reason or 'wall_timeout'
                if signal_request:
                    reason = reason or 'signal_requested'
                if (directory / 'STOP_REQUESTED').exists():
                    reason = reason or 'supervisor_stop_requested'
                if reason and stop_started is None:
                    stop_started = time.monotonic()
                    (directory / 'STOP_REQUESTED').write_text(reason)
                    signal_group(process.pid, signal.SIGINT)
                    escalations.append('SIGINT')
                if stop_started is not None:
                    delay = time.monotonic() - stop_started
                    if delay > 30 and 'SIGTERM' not in escalations:
                        signal_group(process.pid, signal.SIGTERM)
                        escalations.append('SIGTERM')
                    if delay > 40 and 'SIGKILL' not in escalations:
                        signal_group(process.pid, signal.SIGKILL)
                        escalations.append('SIGKILL')
                time.sleep(.5)
            code = process.wait()
    finally:
        if process is not None and process.poll() is None:
            signal_group(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                signal_group(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
        if live_owned(identities):
            reason = reason or 'owned_descendants_remained_after_exit'
            remaining = cleanup_owned(identities, descendant_actions)
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        (directory / 'guard_summary.json').write_text(json.dumps({
            'exit_code': process.returncode if process else None,
            'reason': reason, 'wall_s': time.monotonic() - started,
            'min_host_free_gib': free_min, 'peak_tree_rss_gib': peak_rss,
            'escalations': escalations, 'reserve_gib': 4,
            'descendant_cleanup': descendant_actions, 'remaining_owned_pids': remaining,
        }, indent=2))
    return 1 if reason else code


if __name__ == '__main__':
    raise SystemExit(main())
