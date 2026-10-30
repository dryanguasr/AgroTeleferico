#!/usr/bin/env python3
"""Explicit guarded Harmonic lifecycle/parity test; never part of default CTest.

Run in the sourced ROS environment with a fresh Windows host-memory feed.
This checks the shared reduced model and transport lifecycle, not native contact.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
import traceback
import uuid
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from generate_ballasted import generate
from supervision import read_host_memory, tree_rss

CSV_FILES = ('global.csv', 'carriers.csv', 'cables.csv', 'bases.csv', 'geometry.csv')
WORLD_STEP = .02
CORE_STEP = .001
VISUAL_PERIOD = .1


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compare_csv(left, right):
    files = {}
    for name in CSV_FILES:
        a, b = (Path(left)/name).read_bytes(), (Path(right)/name).read_bytes()
        files[name] = {'cli_sha256': hashlib.sha256(a).hexdigest(),
                       'gazebo_sha256': hashlib.sha256(b).hexdigest(),
                       'cli_rows': len(a.splitlines())-1,
                       'gazebo_rows': len(b.splitlines())-1,
                       'exactly_equal': a == b and len(a.splitlines()) > 1}
    return {'files': files, 'passed': all(item['exactly_equal'] for item in files.values())}


def group_members(pgid):
    rows = subprocess.check_output(['ps', '-eo', 'pid=,pgid=,stat=,args='], text=True)
    members = []
    for row in rows.splitlines():
        parts = row.split(None, 3)
        if len(parts) >= 3 and int(parts[1]) == pgid and not parts[2].startswith('Z'):
            members.append({'pid': int(parts[0]), 'state': parts[2],
                            'command': parts[3] if len(parts) > 3 else ''})
    return members


def cleanup_group(process):
    """Only signal the new session created for this test's subprocess."""
    actions = []
    for sig, grace in ((signal.SIGINT, 5), (signal.SIGTERM, 3), (signal.SIGKILL, 2)):
        if not group_members(process.pid):
            break
        try:
            os.killpg(process.pid, sig)
            actions.append(signal.Signals(sig).name)
        except ProcessLookupError:
            break
        deadline = time.monotonic()+grace
        while time.monotonic() < deadline and group_members(process.pid):
            process.poll()
            time.sleep(.1)
    if process.poll() is None:
        process.wait(timeout=2)
    return {'pid': process.pid, 'signals': actions,
            'remaining_group_members': group_members(process.pid),
            'exit_code': process.returncode}


def run(args):
    out = Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    statuses, stats, callback_errors, processes = [], [], [], []
    checks = {}
    result = {'scope': 'Live shared reduced model; no native wheel/cable contact or structural certification',
              'passed': False, 'checks': checks, 'phase': 'admission'}
    stop_monitor = threading.Event()
    monitor_errors = []
    lock = threading.Lock()
    trace_file = (out/'trace.jsonl').open('w')
    resources_file = (out/'resources.jsonl').open('w')
    trace_closed = False
    monitor = None
    process = None
    node = None

    def trace(kind, value):
        with lock:
            if not trace_closed:
                trace_file.write(json.dumps({'wall_s': time.monotonic()-started,
                                             'kind': kind, 'value': value})+'\n')
                trace_file.flush()

    def monitor_resources():
        while not stop_monitor.is_set():
            try:
                free = read_host_memory(args.host_memory)
                rss, pids = tree_rss(os.getpid())
                sample = {'wall_s': time.monotonic()-started, 'host_free_gib': free,
                          'tree_rss_gib': rss, 'pids': pids}
                resources_file.write(json.dumps(sample)+'\n')
                resources_file.flush()
                if free < 5:
                    raise RuntimeError('Host free memory below 5 GiB stop threshold')
                if (out.parent/'STOP_REQUESTED').exists():
                    raise RuntimeError('Explicit STOP_REQUESTED observed')
                if time.monotonic()-started > args.timeout:
                    raise TimeoutError('Overall lifecycle timeout exceeded')
            except BaseException as exc:
                monitor_errors.append(repr(exc))
                trace('resource_stop', repr(exc))
                for child in list(processes):
                    try:
                        os.killpg(child.pid, signal.SIGINT)
                    except ProcessLookupError:
                        pass
                return
            stop_monitor.wait(1)

    def healthy():
        if monitor_errors:
            raise RuntimeError('Resource monitor stopped test: '+monitor_errors[0])
        if callback_errors:
            raise RuntimeError('Transport callback failed: '+callback_errors[0])
        if time.monotonic()-started > args.timeout:
            raise TimeoutError('Overall lifecycle timeout exceeded')

    def wait_for(label, predicate, timeout=30, require_running=True):
        deadline = min(started+args.timeout, time.monotonic()+timeout)
        while True:
            healthy()
            if predicate():
                trace('condition_met', label)
                return
            if require_running and process is not None and process.poll() is not None:
                raise RuntimeError(f'Gazebo exited while waiting for {label}: {process.returncode}')
            if time.monotonic() > deadline:
                raise TimeoutError('Condition timed out: '+label)
            time.sleep(.05)

    def settle(seconds):
        end = time.monotonic()+seconds
        while time.monotonic() < end:
            healthy()
            time.sleep(min(.05, max(0, end-time.monotonic())))

    def check(name, passed, observation=None):
        checks[name] = bool(passed)
        trace('check', {'name': name, 'passed': bool(passed), 'observation': observation})
        if not passed:
            raise AssertionError(name)

    try:
        if not math.isfinite(args.timeout) or args.timeout <= 0:
            raise ValueError('--timeout must be finite and positive')
        first_free = read_host_memory(args.host_memory)
        trace('admission', {'host_free_gib': first_free, 'required_gib': 9})
        if first_free < 9:
            raise RuntimeError('Admission requires at least 9 GiB fresh host free memory')
        os.environ['GZ_PARTITION'] = 'agro_ballasted_lifecycle_'+uuid.uuid4().hex
        from ament_index_python.packages import get_package_prefix
        prefix = Path(get_package_prefix('agro_teleferico'))
        plugin = prefix/'lib/libAgroLoopSystem.so'
        binary = prefix/'lib/agro_teleferico/agro_loop_cli'
        os.environ['GZ_SIM_SYSTEM_PLUGIN_PATH'] = str(prefix/'lib')
        from gz.transport13 import Node
        from gz.msgs10.stringmsg_pb2 import StringMsg
        from gz.msgs10.world_stats_pb2 import WorldStatistics
        from gz.msgs10.world_control_pb2 import WorldControl
        from gz.msgs10.server_control_pb2 import ServerControl
        from gz.msgs10.boolean_pb2 import Boolean

        world = generate('ladera_agricola', out/'pilot', dt=CORE_STEP,
                         shape_period=.01, calm=True, stop_at_end=False,
                         variant='revised_supports')
        params = world.parent/'loop.params'
        native = world.parent/'gazebo'
        sdf = ET.parse(world).getroot().find('world')
        system = sdf.find("plugin[@name='agro::LoopSystem']")
        effective = {}
        for line in params.read_text().splitlines():
            fields = line.split()
            if len(fields) == 2 and not fields[0].startswith('#'):
                effective[fields[0]] = float(fields[1])
        check('effective_case_parameters', effective['dt'] == CORE_STEP
              and effective['shape_period'] == .01
              and effective['visual_period'] == VISUAL_PERIOD
              and effective['single_span'] == 1
              and float(sdf.findtext('physics/max_step_size')) == WORLD_STEP
              and system.findtext('mode') == 'central_only'
              and system.findtext('gust') == 'false'
              and system.findtext('stop_at_end') == 'false'
              and Path(system.findtext('params')) == params
              and Path(system.findtext('output')) == native)
        sources = [Path(__file__), ROOT/'src/loop_system.cpp', ROOT/'src/loop_cli.cpp',
                   *sorted((ROOT/'include/agro').glob('loop*.hpp')),
                   ROOT/'scripts/generate_ballasted.py', ROOT/'scripts/generate_loop.py',
                   ROOT/'scripts/run_loop_guarded.py', ROOT/'config/loop.yaml',
                   ROOT/'config/ballasted_revised_supports.json', ROOT/'config/ladera_agricola.json']
        provenance = {'captured_before_launch': True, 'partition': os.environ['GZ_PARTITION'],
                      'scenario': 'ladera_agricola', 'variant': 'revised_supports',
                      'dt': CORE_STEP, 'shape_period': .01, 'gust': False,
                      'world_step': WORLD_STEP, 'visual_period': VISUAL_PERIOD,
                      'plugin': {'path': str(plugin), 'sha256': sha256(plugin)},
                      'cli': {'path': str(binary), 'sha256': sha256(binary)},
                      'world_sha256': sha256(world), 'params_sha256': sha256(params),
                      'source_sha256': {str(p.relative_to(ROOT)): sha256(p) for p in sources},
                      'git_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                      'git_status': subprocess.check_output(['git', 'status', '--short'], cwd=ROOT, text=True)}
        (out/'provenance.json').write_text(json.dumps(provenance, indent=2))
        node = Node()

        def on_status(message):
            try:
                value = json.loads(message.data)
                if not math.isfinite(value['time_s']):
                    raise ValueError('Nonfinite status time')
                statuses.append(value)
                trace('status', value)
            except Exception as exc:
                callback_errors.append(repr(exc))
                trace('callback_error', repr(exc))

        def on_stats(message):
            value = {'time_s': message.sim_time.sec+message.sim_time.nsec*1e-9,
                     'paused': message.paused, 'iterations': message.iterations}
            stats.append(value)
            trace('world_stats', value)

        check('subscriptions_created', node.subscribe(StringMsg, '/agro_loop/status', on_status)
              and node.subscribe(WorldStatistics, '/world/agro_loop/stats', on_stats))

        def request(service, message, request_type, timeout_ms=2000):
            healthy()
            trace('request', {'service': service, 'message': str(message), 'timeout_ms': timeout_ms})
            ok, response = node.request(service, message, request_type, Boolean, timeout_ms)
            accepted = bool(ok and response.data)
            trace('response', {'service': service, 'transport_ok': bool(ok), 'accepted': accepted})
            if not accepted:
                raise RuntimeError('Control request was not acknowledged: '+service)
            healthy()

        def control(message):
            request('/world/agro_loop/control', message, WorldControl)

        def at_world(target):
            return bool(stats and stats[-1]['paused'] and abs(stats[-1]['time_s']-target) < 1e-8)

        def check_status_lag(label, target, after=0):
            wait_for(label, lambda: len(statuses) > after
                     and -1e-8 <= target-statuses[-1]['time_s'] <= VISUAL_PERIOD+1e-8)
            lag = target-statuses[-1]['time_s']
            check(label, True, {'world_time_s': target, 'status_time_s': statuses[-1]['time_s'],
                                'publication_lag_s': lag, 'allowed_lag_s': VISUAL_PERIOD})

        # Recheck immediately before starting the sole native process.
        launch_free = read_host_memory(args.host_memory)
        trace('launch_admission', {'host_free_gib': launch_free, 'required_gib': 9})
        if launch_free < 9:
            raise RuntimeError('Launch admission fell below 9 GiB')
        result['phase'] = 'initial_paused_world'
        with (out/'process.log').open('w') as process_log:
            command = ['gz', 'sim', '-s', str(world)]
            process = subprocess.Popen(command, stdout=process_log, stderr=subprocess.STDOUT,
                                       start_new_session=True)
            processes.append(process)
            (out/'process.json').write_text(json.dumps({'pid': process.pid, 'command': command,
                                                       'partition': os.environ['GZ_PARTITION']}, indent=2))
            monitor = threading.Thread(target=monitor_resources, daemon=True)
            monitor.start()
            wait_for('paused startup at zero', lambda: at_world(0))
            check('starts_paused_at_zero', True)
            result['phase'] = 'first_200_steps'
            control(WorldControl(pause=True, multi_step=200))
            wait_for('200 world steps reach 4 s and pause', lambda: at_world(4))
            check_status_lag('status_near_4_seconds', 4)
            settle(.3)
            paused_world, paused_core = stats[-1]['time_s'], statuses[-1]['time_s']
            settle(1)
            check('pause_stops_world_and_core', stats[-1]['time_s'] == paused_world
                  and statuses[-1]['time_s'] == paused_core)
            result['phase'] = 'next_10_steps'
            control(WorldControl(pause=True, multi_step=10))
            wait_for('10 more world steps reach 4.2 s and pause', lambda: at_world(4.2))
            check_status_lag('status_near_4_2_seconds', 4.2)

            result['phase'] = 'cli_reference'
            cli_command = [str(binary), '--config', str(params), '--output', str(out/'cli'),
                           '--mode', 'central_only', '--no-wind', '--until', '4.1995']
            trace('cli_command', cli_command)
            with (out/'cli.log').open('w') as cli_log:
                cli = subprocess.Popen(cli_command, stdout=cli_log, stderr=subprocess.STDOUT,
                                       start_new_session=True)
                processes.append(cli)
                wait_for('CLI reference finished', lambda: cli.poll() is not None)
                check('cli_exit_zero', cli.returncode == 0)
            cli_summary = json.loads((out/'cli/summary.json').read_text())
            check('cli_terminal_time_4_2', cli_summary['status'] == 'partial_requested'
                  and abs(cli_summary['simulated_s']-4.2) < 1e-9)

            result['phase'] = 'reset_and_preserved_segment_parity'
            reset_status_index = len(statuses)
            reset = WorldControl(pause=True)
            reset.reset.all = True
            control(reset)
            wait_for('reset preserves old summary and resets world clock',
                     lambda: (native/'summary.json').exists() and at_world(0))
            # Reset calls Log.finish: only now are all five pre-reset CSVs flushed.
            first = json.loads((native/'summary.json').read_text())
            result['pre_reset_summary'] = first
            check('reset_preserves_terminal_state_4_2', first['status'] == 'reset_interrupted'
                  and abs(first['simulated_s']-4.2) < 1e-9
                  and first['final_q_m'] == cli_summary['final_q_m'])
            check('both_carriers_loaded_before_reset', first['loaded_kg'] == 15
                  and first['unloaded_kg'] == 0)
            parity = compare_csv(out/'cli', native)
            parity['scope'] = 'Pre-reset 4.2 s segment; compare after Reset flushes logs, before stepping reset_1'
            parity['same_events'] = first['events'] == cli_summary['events']
            parity['same_mode_and_wind'] = (first['mode'], first['gust_enabled']) == ('central_only', False)
            parity['passed'] = parity['passed'] and parity['same_events'] and parity['same_mode_and_wind']
            (out/'parity.json').write_text(json.dumps(parity, indent=2))
            check('five_pre_reset_csvs_exactly_equal', parity['passed'])
            check('reset_1_created', (native/'reset_1').is_dir())

            result['phase'] = 'reset_50_steps_then_resume'
            control(WorldControl(pause=True, multi_step=50))
            wait_for('50 post-reset steps reach 1 s and pause', lambda: at_world(1))
            check_status_lag('reset_core_clock_near_1_second', 1, reset_status_index)
            control(WorldControl(pause=False))
            wait_for('resume advances world and core', lambda: stats[-1]['time_s'] >= 1.2
                     and statuses[-1]['time_s'] > 1)
            check('resume_advances_world_and_core', True)
            control(WorldControl(pause=True))
            wait_for('resume is paused again', lambda: stats[-1]['paused'])
            settle(.3)
            terminal_world = stats[-1]['time_s']
            check_status_lag('final_status_lag', terminal_world, reset_status_index)
            result['terminal_world_s'] = terminal_world
            result['phase'] = 'server_stop'
            request('/server_control', ServerControl(stop=True), ServerControl, 5000)
            check('server_stop_acknowledged', True)
            wait_for('Gazebo exits after stop acknowledgement', lambda: process.poll() is not None,
                     timeout=20, require_running=False)
            check('gazebo_clean_exit', process.returncode == 0)
            second = json.loads((native/'reset_1/summary.json').read_text())
            result['post_reset_summary'] = second
            check('reset_segment_terminal_state_saved', second['status'] == 'interrupted'
                  and abs(second['simulated_s']-terminal_world) < 1e-8)
            result['phase'] = 'finished'
    except BaseException as exc:
        result['failure'] = {'observed': repr(exc), 'traceback': traceback.format_exc(),
                             'cause_hypothesis': None}
        trace('failure', result['failure'])
    finally:
        stop_monitor.set()
        if monitor is not None:
            monitor.join(timeout=3)
        cleanup = []
        for child in reversed(processes):
            try:
                cleanup.append(cleanup_group(child))
            except BaseException as exc:
                cleanup.append({'pid': child.pid, 'cleanup_error': repr(exc)})
        result['cleanup'] = cleanup
        checks['no_owned_processes_remaining'] = all(
            not item.get('remaining_group_members') and 'cleanup_error' not in item for item in cleanup)
        result['resource_errors'] = monitor_errors
        result['callback_errors'] = callback_errors
        result['statuses'] = statuses
        result['world_stats'] = stats
        result['wall_s'] = time.monotonic()-started
        result['gazebo_exit_code'] = process.returncode if process is not None else None
        result['passed'] = bool(checks) and all(checks.values()) and not any(
            (result.get('failure'), monitor_errors, callback_errors))
        with lock:
            trace_closed = True
            trace_file.close()
        resources_file.close()
        (out/'checks.json').write_text(json.dumps(result, indent=2))
    print(json.dumps({'passed': result['passed'], 'phase': result['phase'],
                      'checks': checks, 'failure': result.get('failure')}, indent=2), flush=True)
    return 0 if result['passed'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, help='New evidence directory; existing paths are rejected')
    parser.add_argument('--host-memory', required=True, help='Fresh Windows JSON feed, refreshed every second')
    parser.add_argument('--timeout', type=float, default=120, help='Overall wall-clock timeout in seconds')
    return run(parser.parse_args())


if __name__ == '__main__':
    raise SystemExit(main())
