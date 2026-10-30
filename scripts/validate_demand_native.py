#!/usr/bin/env python3
"""Guarded full-run Gazebo/CLI demand parity; explicit integration test only."""
import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import time
import uuid
import xml.etree.ElementTree as ET


CSV_FILES = ('global.csv', 'carriers.csv', 'cables.csv', 'bases.csv', 'geometry.csv')
DEMAND_TAGS = {'demand': 'demand', 'dispatch_config': 'dispatch_config',
               'policy': 'policy', 'predictor': 'predictor'}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def demand_inputs(demand, dispatch_config, policy, predictor):
    supplied = (demand, dispatch_config, policy, predictor)
    if not any(value is not None for value in supplied):
        return None
    if not all(value is not None for value in supplied):
        raise ValueError('Demand mode requires --demand, --dispatch-config, --policy and --predictor')
    if policy not in 'ABCD' or len(policy) != 1:
        raise ValueError('Policy must be A, B, C or D')
    values = {'policy': policy}
    for key, value in [('demand', demand), ('dispatch_config', dispatch_config), ('predictor', predictor)]:
        path = Path(value).resolve()
        if not path.is_file():
            raise ValueError(f'Missing {key}: {path}')
        values[key] = str(path)
    return values


def configure_demand_world(world, inputs):
    """Only add explicit demand inputs; historical SDF remains unchanged otherwise."""
    if inputs is None:
        return
    tree = ET.parse(world)
    root = tree.getroot().find('world')
    plugin = root.find("plugin[@name='agro::LoopSystem']")
    if plugin is None:
        raise ValueError('Missing AgroLoopSystem plugin')
    for key, tag in DEMAND_TAGS.items():
        value = plugin.find(tag)
        if value is None:
            value = ET.SubElement(plugin, tag)
        value.text = inputs[key]
    tree.write(world, encoding='unicode')


def in_video_window(stamp, start, end):
    # Sensors stamp exact decimal ticks with floating representation noise.
    return stamp >= start - 1e-7 and (end is None or stamp < end - 1e-7)


def validate_window(start, end, until):
    if not all(math.isfinite(v) for v in (start, until)) or start < 0 or until <= start:
        raise ValueError('Require finite 0 <= video-start < until')
    if end is not None and (not math.isfinite(end) or not start < end <= until):
        raise ValueError('Require video-start < video-end <= until')


def cli_command(binary, params, output, inputs):
    command = [str(binary), '--config', str(params), '--output', str(output),
               '--mode', 'central_only', '--no-wind']
    for key, flag in [('demand', '--demand'), ('dispatch_config', '--dispatch-config'),
                      ('policy', '--policy'), ('predictor', '--predictor')]:
        command += [flag, inputs[key]]
    return command


def compare_csv(native, reference):
    result = {}
    for name in CSV_FILES + ('demand_status.csv',):
        left, right = Path(native)/name, Path(reference)/name
        a, b = left.read_bytes(), right.read_bytes()
        result[name] = {'identical': a == b and len(a.splitlines()) > 1,
                        'native_sha256': hashlib.sha256(a).hexdigest(),
                        'reference_sha256': hashlib.sha256(b).hexdigest(),
                        'rows': len(a.splitlines()) - 1}
    return result


def stop_owned(process):
    actions = []
    if process is None:
        return actions
    for sig, grace in ((signal.SIGINT, 10), (signal.SIGTERM, 3), (signal.SIGKILL, 3)):
        if process.poll() is not None:
            break
        try:
            os.killpg(process.pid, sig)
            actions.append(signal.Signals(sig).name)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            pass
    return actions


def validate_recording_window(times, start, end):
    """Strict coverage, allowing the initial sensor's first tick after world zero."""
    if not times or any(not math.isfinite(stamp) for stamp in times):
        raise ValueError('Empty or nonfinite camera timestamps')
    if any(b <= a or b-a > .201 for a, b in zip(times, times[1:])):
        raise ValueError('Missing/duplicate camera timestamps')
    if any(not in_video_window(stamp, start, end) for stamp in times):
        raise ValueError('Camera timestamp outside requested half-open window')
    if len(times) != round((end-start)*5):
        raise ValueError('Camera frame count does not cover requested 5 Hz window')
    if start == 0:
        if not 0 <= times[0] < .201:
            raise ValueError('Initial sensor tick missing')
    elif abs(times[0]-start) > 1e-6:
        raise ValueError('First sensor tick missing')
    if abs(times[-1]-(end-.2)) > 1e-6:
        raise ValueError('Final included sensor tick missing')


def verify_capture(args):
    """Verify an existing live partial capture, then run a matching CLI prefix."""
    from ament_index_python.packages import get_package_prefix
    from compose_telemetry_hud import camera_times, probe, decode_strict
    from supervision import read_host_memory, tree_rss
    capture, out = args.capture.resolve(), args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    prefix = Path(get_package_prefix('agro_teleferico'))
    binary, plugin = prefix/'lib/agro_teleferico/agro_loop_cli', prefix/'lib/libAgroLoopSystem.so'
    started = time.monotonic()
    process = None
    result = {'schema': 'agro-demand-capture-verification-v1', 'passed': False,
              'scope': 'Live camera prefix and shared-core parity, not a complete service or independent physics',
              'capture': str(capture), 'checks': {}, 'errors': [], 'admission_samples': []}

    def check(name, value):
        result['checks'][name] = bool(value)
        if not value:
            raise ValueError('Capture check failed: ' + name)

    try:
        metadata = json.loads((capture/'capture.json').read_text())
        provenance = json.loads((capture/'provenance.json').read_text())
        native = capture/'pilot/generated/gazebo'
        params = native.parent/'loop.params'
        terminal = json.loads((native/'summary.json').read_text())
        inputs = provenance['demand_inputs']
        inputs = demand_inputs(inputs['demand'], inputs['dispatch_config'], inputs['policy'], inputs['predictor'])
        result.update(policy=inputs['policy'], inputs=inputs)
        check('clean_capture', metadata['gazebo_exit_code'] == 0 and not metadata['errors'])
        check('live_cameras', metadata['live_gazebo_sensor'] and not metadata['replay'])
        check('stop_acknowledged', metadata['stop_requested'] and metadata['stop_acknowledged'])
        check('same_policy', metadata['policy'] == inputs['policy'])
        check('plugin_unchanged', sha256(plugin) == provenance['plugin_sha256'])
        for key in ('demand', 'dispatch_config', 'predictor'):
            check(key+'_unchanged', sha256(inputs[key]) == provenance['demand_input_sha256'][key])
        window = metadata['recording_window_s']
        if window[1] is None:
            raise ValueError('Demand capture verification requires explicit exclusive video-end')
        result['recording_window_s'] = window
        overview = camera_times(capture/'frame_times_overview.csv')
        follow = camera_times(capture/'frame_times_follow.csv')
        validate_recording_window(overview, *window)
        validate_recording_window(follow, *window)
        check('cameras_synchronized', overview == follow)
        result['videos'] = {}
        for name in ('gazebo.mp4', 'follow.mp4'):
            video = probe(capture/name)
            decode_strict(capture/name)
            check(name+'_frames', int(video['nb_read_frames']) == len(overview))
            check(name+'_format', video['width'] == 1280 and video['height'] == 800
                  and video['r_frame_rate'] == '20/1')
            result['videos'][name] = {'probe': video, 'sha256': sha256(capture/name), 'strict_decode': True}
        samples = [json.loads(line) for line in (capture/'resources.jsonl').read_text().splitlines()]
        check('resource_samples_present', bool(samples))
        result['min_host_free_gib'] = min(row['host_free_gib'] for row in samples)
        result['peak_tree_rss_gib'] = max(row['tree_rss_gib'] for row in samples)
        check('reserve_preserved', result['min_host_free_gib'] >= 5)
        effective = {}
        for line in params.read_text().splitlines():
            columns = line.split()
            if len(columns) == 2 and not columns[0].startswith('#'):
                effective[columns[0]] = float(columns[1])
        stop_time = float(terminal['simulated_s'])
        check('core_covers_capture', stop_time >= window[1])
        command = cli_command(binary, params, out/'reference', inputs)
        command += ['--until', str(stop_time-effective['dt']/2)]
        result.update(actual_core_stop_s=stop_time, reference_command=command)
        paths = [binary, plugin, params, capture/'capture.json', capture/'provenance.json',
                 Path(inputs['demand']), Path(inputs['dispatch_config']), Path(inputs['predictor'])]
        result['source_sha256'] = {str(path): sha256(path) for path in paths}
        for index in range(2):
            free = read_host_memory(args.host_memory)
            result['admission_samples'].append({'free_gib': free, 'wall_s': time.monotonic()-started})
            if free < 6:
                raise RuntimeError('CLI reference admission requires 6 GiB host free memory')
            if index == 0:
                time.sleep(5)
        with (out/'reference.log').open('w') as log, (out/'resources.jsonl').open('w') as resource_log:
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            while process.poll() is None:
                free = read_host_memory(args.host_memory)
                rss, pids = tree_rss(os.getpid())
                resource_log.write(json.dumps({'wall_s': time.monotonic()-started, 'host_free_gib': free,
                                               'tree_rss_gib': rss, 'pids': pids})+'\n')
                resource_log.flush()
                if free < 5 or (out.parent/'STOP_REQUESTED').exists():
                    raise RuntimeError('Preventive reference stop')
                if time.monotonic()-started > args.timeout:
                    raise TimeoutError('Reference timeout')
                time.sleep(.5)
        result['reference_exit_code'] = process.returncode
        check('reference_exit', process.returncode == 0)
        result['parity'] = compare_csv(native, out/'reference')
        check('six_csv_exactly_equal', all(value['identical'] for value in result['parity'].values()))
        reference = json.loads((out/'reference/summary.json').read_text())
        check('same_stop_time', reference['simulated_s'] == terminal['simulated_s'])
        check('source_unchanged', all(sha256(path) == value for path, value in result['source_sha256'].items()))
        result['passed'] = True
    except BaseException as exc:
        result['errors'].append(repr(exc))
        raise
    finally:
        result['cleanup_signals'] = stop_owned(process)
        result['wall_s'] = time.monotonic()-started
        (out/'validation.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({'passed': result['passed'], 'policy': result['policy'], 'frames': len(overview)}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--demand', type=Path)
    parser.add_argument('--dispatch-config', type=Path)
    parser.add_argument('--policy', choices=list('ABCD'))
    parser.add_argument('--predictor', type=Path)
    parser.add_argument('--capture', type=Path, help='Verify existing partial demand capture instead of starting Gazebo')
    parser.add_argument('--host-memory', type=Path, required=True)
    parser.add_argument('--timeout', type=float, default=900)
    args = parser.parse_args()
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error('--timeout must be finite and positive')
    if args.capture:
        if any(value is not None for value in (args.demand, args.dispatch_config, args.policy, args.predictor)):
            parser.error('--capture infers demand inputs from provenance; omit explicit demand flags')
        verify_capture(args)
        return
    inputs = demand_inputs(args.demand, args.dispatch_config, args.policy, args.predictor)
    if inputs is None:
        parser.error('Native execution requires demand inputs, or use --capture')
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    from ament_index_python.packages import get_package_prefix
    from generate_ballasted import generate
    from supervision import read_host_memory, tree_rss
    prefix = Path(get_package_prefix('agro_teleferico'))
    binary, plugin = prefix/'lib/agro_teleferico/agro_loop_cli', prefix/'lib/libAgroLoopSystem.so'
    os.environ['GZ_SIM_SYSTEM_PLUGIN_PATH'] = str(prefix/'lib')
    os.environ['GZ_PARTITION'] = 'agro_demand_native_' + uuid.uuid4().hex
    result = {'schema': 'agro-demand-native-v1', 'passed': False, 'policy': args.policy,
              'scope': 'Shared-core execution parity, not independent physical validation',
              'inputs': inputs, 'admission_samples': [], 'processes': [], 'errors': []}
    started = time.monotonic()
    process = None
    try:
        for index in range(2):
            free = read_host_memory(args.host_memory)
            result['admission_samples'].append({'free_gib': free, 'wall_s': time.monotonic() - started})
            if free < 7:
                raise RuntimeError('Native admission requires 7 GiB host free memory')
            if index == 0:
                time.sleep(5)
        world = generate('buitrago_patio', out/'pilot', calm=True, stop_at_end=True,
                         variant='revised_supports')
        configure_demand_world(world, inputs)
        params, native = world.parent/'loop.params', world.parent/'gazebo'
        source_paths = [Path(__file__), binary, plugin, world, params]
        source_paths += [Path(inputs[key]) for key in ('demand', 'dispatch_config', 'predictor')]
        source_paths += [Path(inputs['predictor']+'.manifest')]
        result['source_sha256'] = {str(path): sha256(path) for path in source_paths}
        result['partition'] = os.environ['GZ_PARTITION']
        with (out/'resources.jsonl').open('w') as resources:
            def run(command, filename):
                nonlocal process
                with (out/filename).open('w') as log:
                    process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                               start_new_session=True)
                    entry = {'command': command, 'pid': process.pid}
                    result['processes'].append(entry)
                    while process.poll() is None:
                        free = read_host_memory(args.host_memory)
                        rss, pids = tree_rss(os.getpid())
                        resources.write(json.dumps({'wall_s': time.monotonic() - started,
                                                    'host_free_gib': free, 'tree_rss_gib': rss,
                                                    'pids': pids}) + '\n')
                        resources.flush()
                        if free < 5 or (out.parent/'STOP_REQUESTED').exists():
                            raise RuntimeError('Preventive stop: reserve or explicit request')
                        if time.monotonic() - started > args.timeout:
                            raise TimeoutError('Native validation timeout')
                        time.sleep(.5)
                    entry['exit_code'] = process.returncode
                    if process.returncode != 0:
                        raise RuntimeError(f'Process exited {process.returncode}: {filename}')
            run(['gz', 'sim', '-s', '-r', '-v', '3', str(world)], 'gazebo.log')
            result['native_summary'] = json.loads((native/'summary.json').read_text())
            if result['native_summary']['status'] != 'completed':
                raise RuntimeError('Native run did not complete')
            result['demand_summary'] = json.loads((native/'demand_summary.json').read_text())
            if not result['demand_summary']['completed'] or not result['demand_summary']['comparable']:
                raise RuntimeError('Native demand run did not reach a comparable terminal state')
            run(cli_command(binary, params, out/'reference', inputs), 'reference.log')
        result['parity'] = compare_csv(native, out/'reference')
        result['source_unchanged'] = all(sha256(path) == value for path, value in result['source_sha256'].items())
        result['passed'] = result['source_unchanged'] and all(v['identical'] for v in result['parity'].values())
        if not result['passed']:
            raise RuntimeError('Demand native/CLI parity or provenance failed')
    except BaseException as exc:
        result['errors'].append(repr(exc))
        raise
    finally:
        result['cleanup_signals'] = stop_owned(process)
        result['wall_s'] = time.monotonic() - started
        (out/'validation.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({'passed': result['passed'], 'policy': args.policy, 'wall_s': result['wall_s']}))


if __name__ == '__main__':
    main()
