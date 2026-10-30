#!/usr/bin/env python3
"""Brief real ROS/Gazebo contract smoke, guarded by fresh Windows memory samples.

Run explicitly after sourcing ROS and the rebuilt workspace. Each output must
be new. This records observed command effects; no command-ID receipts exist.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import time
import traceback
import uuid

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_NODES = ('gz', 'parameter_bridge', 'agro_telemetry_bridge', 'ros_interface.py')


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False), encoding='utf-8')


def event(stream, **fields):
    stream.write(json.dumps({'unix_s': time.time(), 'monotonic_s': time.monotonic(), **fields}, allow_nan=False)+'\n')
    stream.flush()


def parse_launch_log(text):
    """Extract actual child outcomes; absence of a termination line is unknown."""
    text = re.sub(r'\x1b\[[0-9;]*m', '', text)
    outcomes = {}
    for name, pid in re.findall(r'\[([^\[\]]+)\]: process started with pid \[(\d+)\]', text):
        outcomes[name] = {'pid': int(pid), 'exit_code': None, 'termination': 'unknown'}
    for name, pid in re.findall(r'\[([^\[\]]+)\]: process has finished cleanly \[pid (\d+)\]', text):
        outcomes[name] = {'pid': int(pid), 'exit_code': 0, 'termination': 'clean'}
    for name, pid, code in re.findall(r'\[([^\[\]]+)\]: process has died \[pid (\d+), exit code (-?\d+)', text):
        outcomes[name] = {'pid': int(pid), 'exit_code': int(code), 'termination': 'died'}
    return outcomes


def node_outcome(outcomes, executable):
    return [value for name, value in outcomes.items() if re.sub(r'-\d+$', '', name) == executable]


def process_identity(pid):
    """Linux PID start time guards cleanup against PID reuse; zombies are done."""
    try:
        fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
        return None if fields[0] == 'Z' else fields[19]
    except (FileNotFoundError, ProcessLookupError):
        return None


def live_owned(identities):
    return [pid for pid, start in identities.items() if start is not None and process_identity(pid) == start]


def signal_owned(identities, signum, actions):
    for pid in live_owned(identities):
        try:
            os.kill(pid, signum)
            actions.append({'action': signal.Signals(signum).name, 'target': 'owned_pid', 'pid': pid})
        except ProcessLookupError:
            pass


def stop_launch(process, identities, actions):
    """Let launch coordinate one SIGINT, then escalate only identified children."""
    if process.poll() is None:
        process.send_signal(signal.SIGINT)
        actions.append({'action': 'SIGINT', 'target': 'launch_coordinator', 'pid': process.pid})
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            process.send_signal(signal.SIGTERM)
            actions.append({'action': 'SIGTERM', 'target': 'launch_coordinator', 'pid': process.pid})
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
    # Include descendants observed before shutdown even if launch has exited.
    remaining = live_owned(identities)
    if remaining:
        signal_owned(identities, signal.SIGTERM, actions)
        deadline = time.monotonic()+5
        while live_owned(identities) and time.monotonic() < deadline:
            time.sleep(.1)
    if live_owned(identities):
        signal_owned(identities, signal.SIGKILL, actions)
    if process.poll() is None:
        process.wait(timeout=5)
    deadline = time.monotonic()+3
    while live_owned(identities) and time.monotonic() < deadline:
        time.sleep(.1)
    return live_owned(identities)


class Watchdog:
    def __init__(self, memory, directory, read_memory, tree_rss, timeout=120):
        self.memory, self.directory = memory, directory
        self.read_memory, self.tree_rss = read_memory, tree_rss
        self.started = time.monotonic()
        self.timeout = timeout
        self.process = None
        self.identities = {}
        self.stop = threading.Event()
        self.reason = None
        self.minimum = None
        self.peak = 0.
        self.thread = threading.Thread(target=self.run, daemon=True)

    def capture_owned(self):
        if self.process is None or self.process.poll() is not None:
            return 0., []
        rss, pids = self.tree_rss(self.process.pid)
        for pid in pids:
            identity = process_identity(pid)
            if identity is not None:
                self.identities[pid] = identity
        return rss, pids

    def run(self):
        with (self.directory/'resources.jsonl').open('w', encoding='utf-8') as samples:
            while not self.stop.is_set():
                try:
                    free = self.read_memory(self.memory)
                    rss, pids = self.capture_owned()
                    self.minimum = free if self.minimum is None else min(self.minimum, free)
                    self.peak = max(self.peak, rss)
                    event(samples, host_free_gib=free, tree_rss_gib=rss, pids=pids)
                    if free < 5:
                        raise RuntimeError('host_below_5_gib_stop_margin_for_4_gib_reserve')
                    if (self.directory.parent/'STOP_REQUESTED').exists() or (self.memory.parent/'STOP_REQUESTED').exists():
                        raise RuntimeError('explicit_stop_request')
                    if time.monotonic()-self.started > self.timeout:
                        raise RuntimeError(f'scenario_timeout_{self.timeout:g}_s')
                except BaseException as error:
                    self.reason = repr(error)
                    event(samples, error=self.reason)
                    return
                self.stop.wait(1)

    def check(self):
        if self.reason is not None:
            raise RuntimeError(self.reason)
        if time.monotonic()-self.started > self.timeout:
            raise TimeoutError(f'scenario_timeout_{self.timeout:g}_s')

    def close(self):
        self.stop.set()
        self.thread.join(timeout=3)
        if self.thread.is_alive():
            raise RuntimeError('memory_watchdog_did_not_finish')


def admission(memory, directory, read_memory):
    record = {'minimum_gib': 9, 'reserve_gib': 4, 'stop_below_gib': 5,
              'separation_s': 5, 'samples': [], 'admitted': False}
    try:
        for index in range(2):
            if index:
                time.sleep(5)
            free = read_memory(memory)
            record['samples'].append({'unix_s': time.time(), 'free_gib': free})
            if free < 9:
                raise RuntimeError('Admission requires 9 GiB of fresh host free memory')
        record['admitted'] = True
    except BaseException as error:
        record['error'] = repr(error)
        raise
    finally:
        write_json(directory/'admission.json', record)


def validate_row(data):
    return len(data) == 50 and all(math.isfinite(value) for value in data) and 0 <= data[0] < 2**31


def target_matches(data, scenario):
    if scenario == 'single':
        return abs(data[13]-12.) < 1e-6
    return all(abs(value-expected) < 1e-6 for value, expected in zip(data[13:19], (10.2, 0., 7.68, 0., 0., 0.)))


def run_scenario(scenario, directory, memory, domain, read_memory, tree_rss, timeout=120):
    directory.mkdir()
    result = {'scenario': scenario, 'passed': False, 'checks': {}, 'errors': [],
              'launch_exit_code': None, 'node_outcomes': {}, 'shutdown_actions': [],
              'meaning': 'Observed command effects; no command-ID acknowledgement exists.'}
    process = None
    node = None
    ros = None
    watchdog = None
    state = {'count': 0, 'latest': None, 'typed_pose_count': 0, 'invalid_rows': 0, 'backward_rows': 0}
    log_path = directory/'launch.log'
    try:
        admission(memory, directory, read_memory)
        watchdog = Watchdog(memory, directory, read_memory, tree_rss, timeout)
        watchdog.thread.start()
        partition = 'agro_ros_smoke_'+scenario+'_'+uuid.uuid4().hex
        os.environ.update(GZ_PARTITION=partition, ROS_DOMAIN_ID=str(domain), RCUTILS_COLORIZED_OUTPUT='0')
        import rclpy as ros
        from geometry_msgs.msg import PoseStamped
        from std_msgs.msg import Float64MultiArray, Float64
        ros.init()
        name = 'agro_ros_smoke_'+uuid.uuid4().hex[:12]
        node = ros.create_node(name)
        discovery_deadline = time.monotonic()+2
        while time.monotonic() < discovery_deadline:
            watchdog.check()
            ros.spin_once(node, timeout_sec=.05)
        peers = [(n, namespace) for n, namespace in node.get_node_names_and_namespaces() if n != name]
        result['prelaunch_graph'] = peers
        result['checks']['domain_observed_empty'] = not peers
        if peers:
            raise RuntimeError(f'ROS domain {domain} already has nodes: {peers}')
        # The empty discovery window is evidence, not a reservation against
        # another process joining the domain later.
        command = ['ros2', 'launch', 'agro_teleferico', 'pilot.launch.py',
                   f'scenario:={scenario}', 'gui:=false', f'output:={directory}/telemetry.csv']
        result.update(command=command, partition=partition, ros_domain_id=domain)
        with log_path.open('w', encoding='utf-8') as log, \
                (directory/'telemetry.jsonl').open('w', encoding='utf-8') as raw, \
                (directory/'typed_pose.jsonl').open('w', encoding='utf-8') as poses, \
                (directory/'commands.jsonl').open('w', encoding='utf-8') as commands:
            def receive(message):
                data = list(message.data)
                valid = validate_row(data)
                event(raw, sequence=state['count']+1, valid=valid,
                      data=[value if math.isfinite(value) else str(value) for value in data])
                state['count'] += 1
                if not valid:
                    state['invalid_rows'] += 1
                    return
                if state['latest'] is not None and data[0] < state['latest'][0]:
                    state['backward_rows'] += 1
                state['latest'] = data

            def receive_pose(message):
                p, q, stamp = message.pose.position, message.pose.orientation, message.header.stamp
                event(poses, frame_id=message.header.frame_id, sec=stamp.sec, nanosec=stamp.nanosec,
                      position=[p.x, p.y, p.z], quaternion_xyzw=[q.x, q.y, q.z, q.w])
                state['typed_pose_count'] += 1

            node.create_subscription(Float64MultiArray, '/agro/telemetry', receive, 10)
            node.create_subscription(PoseStamped, '/agro/pose', receive_pose, 10)
            cart_pub = node.create_publisher(Float64, '/agro/goal_x', 10)
            pose_pub = node.create_publisher(PoseStamped, '/agro/target_pose', 10)
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            watchdog.process = process
            watchdog.capture_owned()
            write_json(directory/'process.json', {'pid': process.pid, 'command': command, 'partition': partition, 'ros_domain_id': domain})

            def wait_effect(predicate, label, publish=None):
                deadline = time.monotonic()+30
                next_publish = 0.
                baseline_count = state['count']
                baseline_time = state['latest'][0] if state['latest'] is not None else -1.
                while time.monotonic() < deadline:
                    watchdog.check()
                    if process.poll() is not None:
                        raise RuntimeError(f'Launch exited early with code {process.returncode}')
                    now = time.monotonic()
                    if publish is not None and now >= next_publish:
                        publish()
                        next_publish = now+.2
                    ros.spin_once(node, timeout_sec=.05)
                    latest = state['latest']
                    if latest is not None and state['count'] > baseline_count and latest[0] > baseline_time and predicate(latest):
                        observation = {'time_s': latest[0], 'raw_sequence': state['count'],
                                       'target': latest[13:19], 'rejected': latest[24]}
                        event(commands, effect=label, **observation)
                        return observation
                raise TimeoutError(f'{label}: no effect observed in 30 s')

            wait_effect(lambda d: d[0] >= 1 and state['typed_pose_count'] > 0, 'telemetry_ready')
            result['checks']['typed_pose_observed'] = state['typed_pose_count'] > 0
            command_sequence = 0

            def publish_goal(rejected=False):
                nonlocal command_sequence
                command_sequence += 1
                if scenario == 'single':
                    value = 100. if rejected else 12.
                    cart_pub.publish(Float64(data=value))
                    payload = {'x': value}
                    topic = '/agro/goal_x'
                else:
                    goal = PoseStamped()
                    goal.header.frame_id = 'world'
                    goal.pose.position.x = 100. if rejected else 10.2
                    goal.pose.position.z = 7.68
                    goal.pose.orientation.w = 1.
                    pose_pub.publish(goal)
                    payload = {'frame_id': 'world', 'position': [goal.pose.position.x, 0., 7.68], 'quaternion_xyzw': [0., 0., 0., 1.]}
                    topic = '/agro/target_pose'
                event(commands, command_sequence_local=command_sequence, topic=topic, payload=payload,
                      expected='rejected' if rejected else 'accepted', latest_sim_time_s=state['latest'][0])

            result['accepted_effect'] = wait_effect(lambda d: target_matches(d, scenario), 'accepted_target', publish_goal)
            previous = state['latest'][24]
            result['rejected_effect'] = wait_effect(lambda d: d[24] > previous and target_matches(d, scenario),
                                                   'rejected_target_preserved', lambda: publish_goal(True))
            result['checks'].update(accepted_target_effect=True, rejected_counter_increased=True, rejected_target_preserved=True)
            watchdog.check()
    except BaseException as error:
        result['errors'].append(repr(error))
        (directory/'error.txt').write_text(traceback.format_exc(), encoding='utf-8')
    finally:
        if process is not None:
            try:
                watchdog.capture_owned()
            except BaseException as error:
                result['errors'].append('final_process_sample: '+repr(error))
            try:
                result['remaining_owned_pids'] = stop_launch(process, watchdog.identities.copy(), result['shutdown_actions'])
            except BaseException as error:
                result['errors'].append('launch_cleanup: '+repr(error))
            result['launch_exit_code'] = process.poll()
        if node is not None:
            try:
                node.destroy_node()
            except BaseException as error:
                result['errors'].append('test_node_cleanup: '+repr(error))
        if ros is not None:
            try:
                ros.try_shutdown()
            except BaseException as error:
                result['errors'].append('test_ros_cleanup: '+repr(error))
        if watchdog is not None:
            try:
                watchdog.close()
            except BaseException as error:
                result['errors'].append(repr(error))
            result.update(min_host_free_gib=watchdog.minimum, peak_tree_rss_gib=watchdog.peak, guard_reason=watchdog.reason)
            if watchdog.reason is not None:
                result['errors'].append(watchdog.reason)
        text = log_path.read_text(encoding='utf-8', errors='replace') if log_path.exists() else ''
        outcomes = parse_launch_log(text)
        result['node_outcomes'] = outcomes
        result['checks'].update(
            launch_exit_zero=result['launch_exit_code'] == 0,
            all_expected_nodes_exit_zero=all(len(node_outcome(outcomes, name)) == 1 and node_outcome(outcomes, name)[0]['exit_code'] == 0 for name in EXPECTED_NODES),
            adapter_exit_zero=len(node_outcome(outcomes, 'ros_interface.py')) == 1 and node_outcome(outcomes, 'ros_interface.py')[0]['exit_code'] == 0,
            no_double_shutdown='rcl_shutdown already called' not in text,
            no_traceback='Traceback (most recent call last)' not in text,
            no_cleanup_escalation=all(action['action'] == 'SIGINT' and action['target'] == 'launch_coordinator' for action in result['shutdown_actions']),
            no_owned_processes_left=process is not None and result.get('remaining_owned_pids') == [],
            raw_telemetry_valid=state['count'] > 0 and state['invalid_rows'] == 0,
            raw_time_nondecreasing=state['count'] > 0 and state['backward_rows'] == 0)
        result['telemetry_counts'] = {key: value for key, value in state.items() if key != 'latest'}
        result['passed'] = not result['errors'] and all(result['checks'].values())
        write_json(directory/'summary.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='New evidence directory; existing paths are refused')
    parser.add_argument('--host-memory', type=Path, required=True, help='Windows host JSON refreshed at least every 15 s')
    parser.add_argument('--ros-domain-id', type=int, required=True, help='Unused domain 0..232; checked with a two-second discovery window')
    parser.add_argument('--timeout', type=float, default=120, help='Maximum monitored wall seconds per scenario (default: 120)')
    args = parser.parse_args()
    if not 0 <= args.ros_domain_id <= 232:
        parser.error('--ros-domain-id must be in [0,232]')
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error('--timeout must be positive and finite')
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    summary = {'schema': 'agro-ros-smoke-v1', 'passed': False, 'scenarios': [], 'errors': [],
               'scope': 'Historical AgroCableSystem ROS contract and process lifecycle; not structural or physical validation.'}
    try:
        sys.path.insert(0, str(ROOT/'scripts'))
        from supervision import read_host_memory, tree_rss
        sources = [Path(__file__), ROOT/'scripts/ros_interface.py', ROOT/'src/system.cpp', ROOT/'src/telemetry_bridge.cpp', ROOT/'launch/pilot.launch.py']
        write_json(out/'provenance.json', {'source_sha256': {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources},
                                         'ros_domain_id': args.ros_domain_id, 'host_memory': str(args.host_memory.resolve())})
        for scenario in ('single', 'spider'):
            result = run_scenario(scenario, out/scenario, args.host_memory.resolve(), args.ros_domain_id, read_host_memory, tree_rss, args.timeout)
            summary['scenarios'].append({'scenario': scenario, 'passed': result['passed'], 'summary': str(out/scenario/'summary.json')})
            if not result['passed']:
                break
        summary['passed'] = len(summary['scenarios']) == 2 and all(case['passed'] for case in summary['scenarios'])
    except BaseException as error:
        summary['errors'].append(repr(error))
        (out/'error.txt').write_text(traceback.format_exc(), encoding='utf-8')
    finally:
        write_json(out/'summary.json', summary)
    print(json.dumps(summary, indent=2), flush=True)
    return 0 if summary['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
