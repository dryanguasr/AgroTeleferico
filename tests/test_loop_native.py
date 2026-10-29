#!/usr/bin/env python3
"""Live Harmonic lifecycle checks; run explicitly in a sourced ROS environment."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from generate_loop import generate
from generate_ballasted import generate as generate_ballasted


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--scenario', choices=('ballasted', 'loop'), default='ballasted')
    args = parser.parse_args()
    out = Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=False)
    os.environ['GZ_PARTITION'] = 'agro_loop_lifecycle_' + uuid.uuid4().hex
    from ament_index_python.packages import get_package_prefix
    os.environ['GZ_SIM_SYSTEM_PLUGIN_PATH'] = str(Path(get_package_prefix('agro_teleferico'))/'lib')
    from gz.transport13 import Node
    from gz.msgs10.stringmsg_pb2 import StringMsg
    from gz.msgs10.world_stats_pb2 import WorldStatistics
    from gz.msgs10.world_control_pb2 import WorldControl
    from gz.msgs10.server_control_pb2 import ServerControl
    from gz.msgs10.boolean_pb2 import Boolean

    node = Node()
    statuses, stats = [], []
    node.subscribe(StringMsg, '/agro_loop/status', lambda msg: statuses.append(json.loads(msg.data)))
    node.subscribe(WorldStatistics, '/world/agro_loop/stats', lambda msg: stats.append((msg.sim_time.sec+msg.sim_time.nsec*1e-9, msg.paused)))
    # CI exercises the current two-carrier platform. The nine-post extension
    # remains an explicit opt-in and is not resumed by this lifecycle test.
    if args.scenario == 'ballasted':
        world = generate_ballasted('buitrago_patio', out/'pilot', calm=True, stop_at_end=False)
    else:
        world = generate(Path(__file__).resolve().parents[1]/'config/loop.yaml', out/'generated')
    import xml.etree.ElementTree as ET
    world_step = float(ET.parse(world).findtext('.//physics/max_step_size'))
    native = world.parent/'gazebo'
    checks = {}
    requests = []

    def wait_for(predicate, timeout=45):
        deadline = time.monotonic()+timeout
        while not predicate():
            if time.monotonic() > deadline:
                raise TimeoutError('Lifecycle condition timed out')
            if process.poll() is not None:
                raise RuntimeError(f'Gazebo exited early: {process.returncode}')
            time.sleep(.05)

    def control(request):
        ok, response = node.request('/world/agro_loop/control', request, WorldControl, Boolean, 15000)
        requests.append({'request': str(request), 'transport_ok': ok, 'response': bool(response.data)})
        if not ok or not response.data:
            raise RuntimeError('World control was not acknowledged')

    with (out/'process.log').open('w') as log:
        process = subprocess.Popen(['gz', 'sim', '-s', '-r', str(world)], stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            wait_for(lambda: statuses and statuses[-1]['time_s'] >= 2 and stats)
            checks['status_published'] = True
            control(WorldControl(pause=True))
            wait_for(lambda: stats[-1][1])
            time.sleep(.3)
            paused_time, core_time = stats[-1][0], statuses[-1]['time_s']
            time.sleep(1)
            checks['pause_stops_world_and_core'] = stats[-1][0] == paused_time and statuses[-1]['time_s'] == core_time
            old_count = len(statuses)
            control(WorldControl(pause=True, multi_step=10))
            wait_for(lambda: len(statuses) > old_count)
            # Service acknowledgement queues the request; wait for all ten
            # iterations before reset, otherwise remaining steps re-pause it.
            wait_for(lambda: stats[-1][1] and stats[-1][0] >= paused_time+10*world_step-1e-6)
            checks['manual_step_advances_core'] = statuses[-1]['time_s'] > core_time
            request = WorldControl(pause=True)
            request.reset.all = True
            control(request)
            # The old summary is written inside Reset, before the server has
            # finished resetting. Wait for a fresh zero-clock paused sample.
            wait_for(lambda: (native/'summary.json').exists() and stats[-1][1] and abs(stats[-1][0]) < 1e-9)
            first = json.loads((native/'summary.json').read_text())
            checks['reset_preserves_interrupted_run'] = first['status'] == 'reset_interrupted'
            old_count = len(statuses)
            control(WorldControl(pause=True, multi_step=50))
            wait_for(lambda: stats[-1][1] and abs(stats[-1][0]-50*world_step) < 1e-6 and len(statuses) > old_count)
            checks['reset_restarts_core_clock'] = statuses[old_count]['time_s'] < core_time
            control(WorldControl(pause=False))
            wait_for(lambda: stats[-1][0] > 50*world_step and statuses[-1]['time_s'] > 50*world_step)
            ok, response = node.request('/server_control', ServerControl(stop=True), ServerControl, Boolean, 5000)
            checks['stop_acknowledged'] = ok and response.data
            process.wait(timeout=25)
            checks['clean_exit'] = process.returncode == 0
            reset = json.loads((native/'reset_1/summary.json').read_text())
            checks['reset_writes_separate_complete_files'] = reset['status'] == 'interrupted' and reset['simulated_s'] >= 1
        except Exception as exc:
            checks['error'] = repr(exc)
            raise
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGINT)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
            (out/'checks.json').write_text(json.dumps({'checks': checks, 'requests': requests, 'scenario': args.scenario, 'passed': bool(checks) and all(value is True for value in checks.values()), 'statuses': statuses, 'world_stats': stats, 'gazebo_exit_code': process.returncode}, indent=2))
    if not all(value is True for value in checks.values()):
        raise RuntimeError('Lifecycle checks failed')
    print(json.dumps(checks, indent=2))


if __name__ == '__main__':
    main()
