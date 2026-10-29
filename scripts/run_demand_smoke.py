#!/usr/bin/env python3
"""One fixed demand replica, fresh calibration, native parity and independent audit."""
import argparse
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import threading
import time

from generate_ballasted import generate
from run_loop_guarded import read_host_memory
from validate_demand_native import sha256, stop_owned
from audit_demand_outputs import audit_run


def linux_sample():
    if 'microsoft' in platform.release().lower():
        raise RuntimeError('WSL requires --host-memory from the Windows supervisor')
    values = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
    return {'unix_s': time.time(), 'free_gib': int(values['MemAvailable'].split()[0])/1024**2}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    memory = parser.add_mutually_exclusive_group(required=True)
    memory.add_argument('--host-memory', type=Path)
    memory.add_argument('--linux-host', action='store_true', help='Dedicated native Linux host, never WSL')
    args = parser.parse_args()
    if args.linux_host:
        linux_sample()  # Reject WSL before creating any output.
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    feed = args.host_memory.resolve() if args.host_memory else out/'host_memory.json'
    done = threading.Event()
    thread = None
    result = {'schema': 'agro-demand-smoke-v1', 'passed': False, 'policy': 'C',
              'scope': 'Fixed integration regression; not a statistical campaign or physical validation'}

    def sample():
        try:
            value = linux_sample()
        except Exception as exc:
            value = {'unix_s': time.time(), 'free_gib': 0, 'error': repr(exc)}
        temporary = feed.with_suffix('.tmp')
        temporary.write_text(json.dumps(value))
        temporary.replace(feed)

    def feed_loop():
        while not done.wait(.5):
            sample()

    def run(command, label, timeout):
        process = None
        started = time.monotonic()
        entry = {'command': command}
        result.setdefault('processes', {})[label] = entry
        try:
            if read_host_memory(feed) < 7:
                raise RuntimeError('Admission requires 7 GiB free')
            with (out/(label+'.log')).open('x') as log:
                process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                while process.poll() is None:
                    if read_host_memory(feed) < 5 or (feed.parent/'STOP_REQUESTED').exists():
                        raise RuntimeError('Preventive memory/explicit stop')
                    if time.monotonic()-started > timeout:
                        raise TimeoutError(label)
                    time.sleep(.5)
                entry['exit_code'] = process.returncode
                if process.returncode:
                    raise RuntimeError(f'{label} failed; inspect {label}.log')
        finally:
            entry['cleanup_signals'] = stop_owned(process)
            entry['wall_s'] = time.monotonic()-started

    try:
        if args.linux_host:
            sample()
            thread = threading.Thread(target=feed_loop, daemon=True)
            thread.start()
        result['admission'] = [read_host_memory(feed)]
        if result['admission'][0] < 7:
            raise RuntimeError('Admission requires 7 GiB free')
        time.sleep(5)
        result['admission'].append(read_host_memory(feed))
        if result['admission'][1] < 7:
            raise RuntimeError('Second admission below 7 GiB')
        from ament_index_python.packages import get_package_prefix, get_package_share_directory
        prefix = Path(get_package_prefix('agro_teleferico'))
        binary = prefix/'lib/agro_teleferico/agro_loop_cli'
        config = json.loads((Path(get_package_share_directory('agro_teleferico'))/'config/demand_pilot.json').read_text())
        world = generate('buitrago_patio', out/'preparation', calm=True, variant='revised_supports')
        params = world.parent/'loop.params'
        # Disable early goods staging in this fixture so the second known order
        # must travel on the return leg. Auxiliary modules remain enabled.
        settings = dict(config['dispatch'], horizon_s=90, max_time_s=900, early_capacity_kg=0)
        dispatch = out/'dispatch.params'
        dispatch.write_text(''.join(f'{key} {value}\n' for key, value in settings.items()))
        requests = out/'requests.csv'
        requests.write_text('id,known_s,requested_s,deadline_s,origin,mass_kg,load_s,unload_s\n'
                            'up,0,0,500,0,8,20,20\ndown,0,70,500,1,8,20,20\n')
        run([str(binary), '--config', str(params), '--output', str(out/'calibration'), '--build-predictor'], 'calibration', 300)
        predictor = out/'calibration/predictor.csv'
        bound = [params, dispatch, requests, predictor, binary, Path(__file__)]
        result['input_sha256'] = {str(path): sha256(path) for path in bound}
        run([sys.executable, str(Path(__file__).with_name('validate_demand_native.py')),
             '--output', str(out/'native'), '--demand', str(requests), '--dispatch-config', str(dispatch),
             '--policy', 'C', '--predictor', str(predictor), '--host-memory', str(feed), '--timeout', '180'], 'validation', 200)
        validation = json.loads((out/'native/validation.json').read_text())
        if sha256(out/'native/pilot/generated/loop.params') != sha256(params):
            raise RuntimeError('Calibration and native physics parameters differ')
        audits = {}
        for label, folder in [('gazebo', out/'native/pilot/generated/gazebo'), ('cli', out/'native/reference')]:
            audits[label] = audit_run(requests, folder, 'C')
            (out/(label+'_audit.json')).write_text(json.dumps(audits[label], indent=2))
        summary = validation['demand_summary']
        result['checks'] = {
            'native_parity': validation['passed'],
            'independent_audits': all(a['passed'] for a in audits.values()),
            'two_deliveries': summary['orders_delivered'] == 2,
            'buffers_exercised': summary['buffer_moves_kg'] > 0,
            'inputs_unchanged': all(sha256(path) == digest for path, digest in result['input_sha256'].items()),
        }
        result['metrics'] = summary
        result['passed'] = all(result['checks'].values())
        if not result['passed']:
            raise RuntimeError('Demand smoke acceptance failed')
    except BaseException as exc:
        result['error'] = repr(exc)
        raise
    finally:
        done.set()
        if thread:
            thread.join(timeout=2)
        (out/'smoke.json').write_text(json.dumps(result, indent=2))
    print(json.dumps({'passed': True, 'output': str(out), 'checks': result['checks']}))


if __name__ == '__main__':
    main()
