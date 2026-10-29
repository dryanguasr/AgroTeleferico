#!/usr/bin/env python3
"""Frozen paired demand inputs and sequential, memory-guarded campaign execution.

Generating inputs does not run the simulator. Synthetic assumptions are kept in
the frozen JSON beside the inputs; policies consume the same CSV bytes.
"""
import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import random
import shutil
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
POLICIES = ('A', 'B', 'C', 'D')
DEMAND_FIELDS = ('id', 'known_s', 'requested_s', 'deadline_s', 'origin',
                 'mass_kg', 'load_s', 'unload_s')


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                    allow_nan=False) + '\n', encoding='utf-8')
    temporary.replace(path)


def finite_number(value, label, minimum=0):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < minimum:
        raise ValueError(f'{label} must be finite and >= {minimum}')
    return value


def probabilities(values, weights, label):
    if not isinstance(values, list) or not values or len(values) != len(weights):
        raise ValueError(f'{label} values and weights must have equal nonzero length')
    for value in values:
        finite_number(value, label)
    for weight in weights:
        finite_number(weight, label + ' probability')
    if not math.isclose(sum(weights), 1, rel_tol=0, abs_tol=1e-12):
        raise ValueError(f'{label} probabilities must sum to one')


def validate_config(config):
    if config.get('schema') != 'agro-demand-pilot-v1':
        raise ValueError('Unsupported demand pilot schema')
    if config.get('policies') != list(POLICIES):
        raise ValueError('The paired pilot requires policies A, B, C, D in order')
    demand = config['demand']
    if not isinstance(demand['seeds'], int) or isinstance(demand['seeds'], bool) or demand['seeds'] < 1:
        raise ValueError('seeds must be a positive integer')
    for key in ('horizon_s', 'alternating_block_s'):
        finite_number(demand[key], key, 1e-12)
    for rate in demand['rates_per_hour']:
        finite_number(rate, 'rate', 1e-12)
    if not demand['rates_per_hour'] or len(set(demand['rates_per_hour'])) != len(demand['rates_per_hour']):
        raise ValueError('rates must be nonempty and unique')
    if not demand['patterns'] or len(set(demand['patterns'])) != len(demand['patterns']) or not set(demand['patterns']) <= {'balanced', 'alternating'}:
        raise ValueError('patterns must be unique balanced/alternating selectors')
    if len(demand['alternating_up_probabilities']) != 2:
        raise ValueError('alternating demand needs two directional probabilities')
    for value in [*demand['alternating_up_probabilities'], demand['advance_notice_fraction']]:
        if not 0 <= finite_number(value, 'probability') <= 1:
            raise ValueError('probability outside [0,1]')
    finite_number(demand['advance_notice_s'], 'advance_notice_s')
    finite_number(demand['handling_s_per_kg'], 'handling_s_per_kg')
    probabilities(demand['mass_kg'], demand['mass_probabilities'], 'mass')
    probabilities(demand['deadline_slack_s'], demand['deadline_probabilities'], 'deadline')
    if min(demand['mass_kg']) <= 0 or min(demand['deadline_slack_s']) <= 0:
        raise ValueError('mass and deadline slack must be positive')
    triangle = demand['handling_triangle_s']
    values = [finite_number(triangle[key], key, 1e-12) for key in ('minimum', 'mode', 'maximum')]
    if not values[0] <= values[1] <= values[2] or values[0] == values[2]:
        raise ValueError('invalid handling triangle')
    runner = config['runner']
    if (runner['admission_gib'], runner['admission_samples'], runner['admission_separation_s'],
            runner['stop_below_gib'], runner['reserve_gib']) != (6, 2, 5, 5, 4):
        raise ValueError('The measured CLI profile requires admission/stop/reserve of 6/5/4 GiB')
    finite_number(runner['timeout_s'], 'timeout_s', 1)
    finite_number(runner['poll_s'], 'poll_s', 0.01)
    if runner['poll_s'] > 1:
        raise ValueError('host memory must be checked at least once per second')
    analysis = config['analysis']
    if analysis['bootstrap_replicates'] != 10000 or analysis['confidence_level'] != .95:
        raise ValueError('Pilot analysis uses 10000 bootstrap replicates and 95% confidence')
    dispatch = config['dispatch']
    for key, value in dispatch.items():
        finite_number(value, key)
    if dispatch['horizon_s'] != demand['horizon_s'] or dispatch['max_time_s'] <= dispatch['horizon_s']:
        raise ValueError('Dispatch and demand horizons disagree')
    if max(demand['mass_kg']) > dispatch['capacity_kg']:
        raise ValueError('A useful order exceeds experimental carrying capacity')
    if not 0 < dispatch['operator_open_s'] <= dispatch['operator_period_s']:
        raise ValueError('Invalid operator calendar')
    return config


def keyed_rng(config, rate, pattern, seed, stream):
    key = [config['demand']['rng_namespace'], rate, pattern, seed, stream]
    digest = hashlib.sha256(json.dumps(key, separators=(',', ':')).encode()).digest()
    return random.Random(int.from_bytes(digest, 'big'))


def weighted_choice(rng, values, weights):
    draw, cumulative = rng.random(), 0.
    for value, weight in zip(values, weights):
        cumulative += weight
        if draw < cumulative:
            return value
    return values[-1]


def generate_requests(config, rate, pattern, seed):
    """Arrival and mark streams are independent of policy and execution order."""
    validate_config(config)
    demand = config['demand']
    if rate not in demand['rates_per_hour'] or pattern not in demand['patterns'] or not 0 <= seed < demand['seeds']:
        raise ValueError('Demand key outside frozen campaign')
    rng = {name: keyed_rng(config, rate, pattern, seed, name) for name in
           ('arrival', 'direction', 'mass', 'deadline', 'notice', 'load', 'unload')}
    rows, requested = [], 0.
    triangle = demand['handling_triangle_s']
    while True:
        requested += rng['arrival'].expovariate(rate / 3600.)
        if requested >= demand['horizon_s']:
            break
        requested_s = round(requested, 6)
        if requested_s >= demand['horizon_s']:
            break
        up_probability = .5 if pattern == 'balanced' else demand['alternating_up_probabilities'][int(requested_s // demand['alternating_block_s']) % 2]
        mass = weighted_choice(rng['mass'], demand['mass_kg'], demand['mass_probabilities'])
        slack = weighted_choice(rng['deadline'], demand['deadline_slack_s'], demand['deadline_probabilities'])
        known = max(0, requested_s - demand['advance_notice_s']) if rng['notice'].random() < demand['advance_notice_fraction'] else requested_s
        service = lambda name: round(rng[name].triangular(triangle['minimum'], triangle['maximum'], triangle['mode']) + demand['handling_s_per_kg'] * mass, 6)
        rows.append({'id': len(rows) + 1, 'known_s': known, 'requested_s': requested_s,
                     'deadline_s': requested_s + slack, 'origin': 0 if rng['direction'].random() < up_probability else 1,
                     'mass_kg': mass, 'load_s': service('load'), 'unload_s': service('unload')})
    validate_requests(rows, config)
    return rows


def validate_requests(rows, config):
    demand = config['demand']
    last, identifiers = -1., set()
    for row in rows:
        if set(row) != set(DEMAND_FIELDS):
            raise ValueError('Demand columns differ from schema')
        for key in DEMAND_FIELDS:
            finite_number(row[key], key)
        if row['id'] in identifiers or row['id'] != int(row['id']) or row['id'] < 1:
            raise ValueError('Demand IDs must be unique positive integers')
        identifiers.add(row['id'])
        if row['origin'] not in (0, 1) or row['mass_kg'] not in demand['mass_kg']:
            raise ValueError('Invalid origin or mass')
        requested = row['requested_s']
        if not last <= requested < demand['horizon_s'] or not 0 <= row['known_s'] <= requested < row['deadline_s']:
            raise ValueError('Invalid request chronology')
        if row['load_s'] <= 0 or row['unload_s'] <= 0:
            raise ValueError('Handling times must be positive')
        last = requested


def dataset_key(rate, pattern, seed):
    return f'{pattern}_r{rate:g}_s{seed:03d}'


def generate_dataset(config_path, output, params=None, predictor=None):
    config_path, output = Path(config_path).resolve(), Path(output).resolve()
    config = validate_config(read_json(config_path))
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / 'config.json', config)
    (output / 'dispatch.params').write_text(''.join(f'{key} {value}\n' for key, value in config['dispatch'].items()), encoding='utf-8')
    frozen_files = {'dispatch.params': sha256(output / 'dispatch.params')}
    for source, name in ((params, 'loop.params'), (predictor, 'predictor.csv')):
        if source is not None:
            shutil.copyfile(source, output / name)
            frozen_files[name] = sha256(output / name)
    if predictor is not None and Path(str(predictor)+'.manifest').is_file():
        shutil.copyfile(str(predictor)+'.manifest', output/'predictor.csv.manifest')
        frozen_files['predictor.csv.manifest'] = sha256(output/'predictor.csv.manifest')
    records = []
    for rate in config['demand']['rates_per_hour']:
        for pattern in config['demand']['patterns']:
            for seed in range(config['demand']['seeds']):
                key = dataset_key(rate, pattern, seed)
                directory = output / 'inputs' / key
                directory.mkdir(parents=True)
                rows = generate_requests(config, rate, pattern, seed)
                path = directory / 'requests.csv'
                with path.open('w', newline='', encoding='utf-8') as stream:
                    writer = csv.DictWriter(stream, fieldnames=DEMAND_FIELDS, lineterminator='\n')
                    writer.writeheader()
                    writer.writerows(rows)
                record = {'id': key, 'rate_per_hour': rate, 'pattern': pattern, 'seed': seed,
                          'requests': len(rows), 'useful_mass_kg': sum(row['mass_kg'] for row in rows),
                          'path': path.relative_to(output).as_posix(), 'sha256': sha256(path)}
                write_json(directory / 'metadata.json', record)
                records.append(record)
    manifest = {'schema': 'agro-demand-dataset-v1', 'synthetic': True,
                'config_sha256': sha256(output / 'config.json'),
                'generator_sha256': sha256(__file__), 'datasets': records,
                'frozen_files': frozen_files,
                'dataset_count': len(records), 'planned_runs': len(records) * len(POLICIES),
                'policies': list(POLICIES), 'rng': 'Python random.Random with SHA-256 keyed independent streams'}
    write_json(output / 'dataset.json', manifest)
    return manifest


def load_dataset(directory):
    directory = Path(directory).resolve()
    manifest = read_json(directory / 'dataset.json')
    if manifest['schema'] != 'agro-demand-dataset-v1' or sha256(directory / 'config.json') != manifest['config_sha256']:
        raise ValueError('Frozen dataset configuration changed')
    config = validate_config(read_json(directory / 'config.json'))
    for name, digest in manifest['frozen_files'].items():
        if name not in ('loop.params', 'dispatch.params', 'predictor.csv', 'predictor.csv.manifest') or sha256(directory / name) != digest:
            raise ValueError(f'Frozen input changed: {name}')
    expected = {dataset_key(rate, pattern, seed) for rate in config['demand']['rates_per_hour']
                for pattern in config['demand']['patterns'] for seed in range(config['demand']['seeds'])}
    records = manifest['datasets']
    if len(records) != len(expected) or {row['id'] for row in records} != expected:
        raise ValueError('Frozen dataset matrix is incomplete or duplicated')
    for record in records:
        path = directory / record['path']
        if not path.resolve().is_relative_to(directory) or sha256(path) != record['sha256']:
            raise ValueError(f'Demand bytes changed: {record["id"]}')
        with path.open(newline='', encoding='utf-8') as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != list(DEMAND_FIELDS):
                raise ValueError('Demand CSV header changed')
            rows = [{k: float(v) for k, v in row.items()} for row in reader]
        validate_requests(rows, config)
        if len(rows) != record['requests'] or sum(row['mass_kg'] for row in rows) != record['useful_mass_kg']:
            raise ValueError('Demand statistics differ from manifest')
    return config, manifest


SUMMARY_FIELDS = {
    'schema', 'policy', 'status', 'comparable', 'completed', 'orders_total',
    'orders_delivered', 'on_time_orders', 'on_time_mass_kg', 'total_useful_kg',
    'delivered_useful_kg', 'lateness_p95_s', 'max_lateness_s', 'deliberate_wait_s',
    'mandatory_wait_s', 'trips', 'buffer_moves_kg', 'restoration_positive_J',
    'restoration_time_s', 'energy_delta_J', 'simulation_s', 'drive_positive_J',
    'drive_absorbed_J', 'loss_work_J', 'load_energy_J', 'residual_J',
    'predictor_absolute_error_J', 'governor_or_stop_count',
}


def validate_summary(summary, dataset, policy):
    missing = SUMMARY_FIELDS - set(summary)
    if missing:
        raise ValueError('Missing demand summary fields: ' + ', '.join(sorted(missing)))
    if summary['policy'] != policy or summary['status'] not in ('completed', 'completed_noncomparable', 'failed', 'interrupted'):
        raise ValueError('Demand summary policy or terminal status is invalid')
    if not isinstance(summary['completed'], bool) or not isinstance(summary['comparable'], bool):
        raise ValueError('Demand summary completion flags must be booleans')
    for key in SUMMARY_FIELDS - {'schema', 'policy', 'status', 'completed', 'comparable'}:
        finite_number(summary[key], key, -math.inf if key in ('energy_delta_J', 'load_energy_J', 'residual_J') else 0)
    for key in ('orders_total', 'orders_delivered', 'on_time_orders', 'trips', 'governor_or_stop_count'):
        if summary[key] != int(summary[key]):
            raise ValueError('Discrete count is not an integer: ' + key)
    if summary['completed'] != (summary['status'] in ('completed', 'completed_noncomparable')):
        raise ValueError('Completion flag disagrees with terminal status')
    if summary['comparable'] != (summary['status'] == 'completed'):
        raise ValueError('Comparability flag disagrees with terminal status')
    if summary['orders_total'] != dataset['requests'] or not math.isclose(summary['total_useful_kg'], dataset['useful_mass_kg'], abs_tol=1e-9):
        raise ValueError('Demand summary differs from the frozen workload')
    if summary['orders_delivered'] > summary['orders_total'] or summary['on_time_orders'] > summary['orders_delivered'] or summary['on_time_mass_kg'] > summary['delivered_useful_kg'] + 1e-9:
        raise ValueError('Impossible delivered/on-time counts')
    if summary['completed'] and (summary['orders_delivered'] != summary['orders_total'] or not math.isclose(summary['delivered_useful_kg'], summary['total_useful_kg'], abs_tol=1e-9)):
        raise ValueError('A completed run must deliver the entire frozen workload')
    if summary['comparable'] and (not summary['completed'] or summary['status'] != 'completed'):
        raise ValueError('Comparable runs must be fully completed')
    return summary


def completed_record(directory, expected):
    """Only a hash-validated completed terminal record can bypass execution."""
    directory = Path(directory)
    record = read_json(directory / 'run_record.json')
    for key in ('dataset_sha256', 'binary_sha256', 'frozen_files', 'policy'):
        if record.get(key) != expected[key]:
            raise ValueError(f'Completed result provenance mismatch: {key}')
    if record.get('state') != 'completed' or record.get('exit_code') not in (0, 2):
        return None
    if not record.get('output_sha256'):
        raise ValueError('Completed result has no output hashes')
    for name, digest in record['output_sha256'].items():
        path = directory / name
        if not path.resolve().is_relative_to(directory.resolve()) or sha256(path) != digest:
            raise ValueError(f'Completed output changed: {name}')
    summary = read_json(directory / 'output/demand_summary.json')
    validate_summary(summary, expected['dataset'], expected['policy'])
    if not summary['completed']:
        raise ValueError('Completed record contains an incomplete summary')
    if record.get('summary') != summary:
        raise ValueError('Recorded summary differs from hashed native output')
    return record


def stop_owned_process(process):
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGINT)
    except ProcessLookupError:
        process.wait(timeout=5)
        return
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)


def memory_document(path, now=None):
    for attempt in range(3):
        try:
            document = read_json(path)
            break
        except OSError as exc:
            if exc.errno not in (2, 61) or attempt == 2:
                raise
            time.sleep(.1)
    timestamp = finite_number(document['unix_s'], 'host timestamp')
    finite_number(document['free_gib'], 'host free memory')
    age = (time.time() if now is None else now) - timestamp
    if document.get('error') or not -5 <= age <= 15:
        raise RuntimeError('Host memory evidence is stale or invalid')
    return document


def admission_from_history(document, now=None):
    """Use actual previous CIM samples, never fabricated admission timestamps."""
    now = time.time() if now is None else now
    history = document.get('history')
    if not isinstance(history, list) or len(history) < 2:
        return None
    try:
        samples = [{'unix_s': finite_number(item['unix_s'], 'history timestamp'),
                    'free_gib': finite_number(item['free_gib'], 'history free memory')}
                   for item in history]
    except (ValueError, TypeError, KeyError):
        return None
    last = samples[-1]
    if last['unix_s'] != document['unix_s'] or last['free_gib'] != document['free_gib'] or not -2 <= now-last['unix_s'] <= 2:
        return None
    if any(a['unix_s'] >= b['unix_s'] for a, b in zip(samples, samples[1:])):
        return None
    eligible = [index for index, item in enumerate(samples)
                if last['unix_s']-item['unix_s'] >= 5 and -2 <= now-item['unix_s'] <= 15]
    if not eligible:
        return None
    window = samples[max(eligible):]
    if any(item['free_gib'] < 9 for item in window):
        return None
    return {'method': 'recorded_CIM_history', 'samples': [window[0], window[-1]],
            'history': window, 'separation_s': window[-1]['unix_s']-window[0]['unix_s']}


def memory_admission(path, read_memory):
    if read_memory(path) < 6:
        raise RuntimeError('Admission requires two fresh samples >=6 GiB')
    document = memory_document(path)
    fast = admission_from_history(document)
    if fast is not None:
        return fast
    first = {'unix_s': document['unix_s'], 'free_gib': document['free_gib']}
    if first['free_gib'] < 6:
        raise RuntimeError('Admission requires two fresh samples >=6 GiB')
    started = time.monotonic()
    time.sleep(5)
    while True:
        if read_memory(path) < 6:
            raise RuntimeError('Admission requires two fresh samples >=6 GiB')
        document = memory_document(path)
        second = {'unix_s': document['unix_s'], 'free_gib': document['free_gib']}
        if second['free_gib'] < 6:
            raise RuntimeError('Admission requires two fresh samples >=6 GiB')
        if second['unix_s']-first['unix_s'] >= 5:
            return {'method': 'two_live_reads', 'samples': [first, second],
                    'history': [], 'separation_s': second['unix_s']-first['unix_s']}
        if time.monotonic()-started >= 15:
            raise RuntimeError('Host memory feed did not provide two samples >=5 seconds apart')
        time.sleep(1)


def run_attempt(directory, command, memory, expected, settings, read_memory, rss_reader):
    directory.mkdir(parents=True, exist_ok=False)
    record = {k: expected[k] for k in ('dataset_sha256', 'binary_sha256', 'frozen_files', 'policy')}
    record.update(schema='agro-demand-run-v1', command=command, state='failed',
                  exit_code=None, admission=[], errors=[], output_sha256={},
                  timeout_s=settings['timeout_s'])
    process, started, minimum, peak = None, time.monotonic(), None, 0.
    fatal_guard = False
    try:
        try:
            admission = memory_admission(memory, read_memory)
            record['admission'] = admission['samples']
            record['admission_evidence'] = admission
            if read_memory(memory) < 6:
                raise RuntimeError('Fresh prelaunch memory fell below 6 GiB')
            launch_sample = memory_document(memory)
            record['prelaunch_memory'] = {key: launch_sample[key] for key in ('unix_s', 'free_gib')}
            if launch_sample['free_gib'] < 6:
                raise RuntimeError('Fresh prelaunch memory fell below 6 GiB')
        except Exception:
            fatal_guard = True
            raise
        minimum = min(sample['free_gib'] for sample in record['admission'])
        with (directory / 'process.log').open('w', encoding='utf-8') as log, (directory / 'resources.jsonl').open('w', encoding='utf-8') as samples:
            started = time.monotonic()
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            record['pid'] = process.pid
            while process.poll() is None:
                try:
                    free = read_memory(memory)
                except Exception:
                    fatal_guard = True
                    raise
                rss, pids = rss_reader(process.pid)
                minimum, peak = min(minimum, free), max(peak, rss)
                elapsed = time.monotonic() - started
                samples.write(json.dumps({'wall_s': elapsed, 'host_free_gib': free, 'tree_rss_gib': rss, 'pids': pids}) + '\n')
                samples.flush()
                if free < 5:
                    fatal_guard = True
                    raise RuntimeError('Host free memory below 5 GiB; protecting 4 GiB reserve')
                if (Path(memory).parent / 'STOP_REQUESTED').exists() or any((parent / 'STOP_REQUESTED').exists() for parent in directory.parents[:4]):
                    fatal_guard = True
                    raise RuntimeError('Explicit STOP_REQUESTED')
                if elapsed > settings['timeout_s']:
                    fatal_guard = True
                    raise TimeoutError(f'Run exceeded {settings["timeout_s"]:g} wall seconds')
                time.sleep(settings['poll_s'])
        record['exit_code'] = process.returncode
        summary_path = directory / 'output/demand_summary.json'
        if summary_path.exists():
            summary = validate_summary(read_json(summary_path), expected['dataset'], expected['policy'])
            record['summary'] = summary
            expected_exit = 0 if summary['comparable'] else 2
            if process.returncode == expected_exit and summary['completed']:
                record['state'] = 'completed'
            else:
                record['errors'].append(f'Native terminal state: {summary["status"]}; exit {process.returncode}')
        else:
            record['errors'].append('Native demand_summary.json is missing')
    except BaseException as exc:
        record['errors'].append(f'{type(exc).__name__}: {exc}')
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            fatal_guard = True
    finally:
        if process is not None:
            try:
                stop_owned_process(process)
            except Exception as exc:
                record['errors'].append(f'Cleanup {type(exc).__name__}: {exc}')
                fatal_guard = True
                record['state'] = 'failed'
            record['exit_code'] = process.returncode
        record.update(wall_s=time.monotonic()-started, min_host_free_gib=minimum,
                      peak_tree_rss_gib=peak, fatal_guard=fatal_guard)
        if (directory / 'output').exists():
            record['output_sha256'] = {path.relative_to(directory).as_posix(): sha256(path)
                                       for path in sorted((directory / 'output').rglob('*')) if path.is_file()}
        write_json(directory / 'run_record.json', record)
    return record


def run_campaign(campaign, binary, memory, resume=False, limit=None, timeout=None):
    from run_loop_guarded import read_host_memory, tree_rss
    campaign, binary, memory = Path(campaign).resolve(), Path(binary).resolve(), Path(memory).resolve()
    config, manifest = load_dataset(campaign)
    if set(manifest['frozen_files']) != {'loop.params', 'dispatch.params', 'predictor.csv', 'predictor.csv.manifest'}:
        raise ValueError('Execution requires frozen loop.params, dispatch.params, predictor.csv and predictor.csv.manifest')
    binary_hash = sha256(binary)
    binding = {'schema': 'agro-demand-execution-v1', 'binary': str(binary), 'binary_sha256': binary_hash,
               'dataset_manifest_sha256': sha256(campaign / 'dataset.json'),
               'frozen_files': manifest['frozen_files'],
               'runner_sha256': sha256(__file__), 'host_memory': str(memory),
               'git_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
               'source_sha256': {path.relative_to(ROOT).as_posix(): sha256(path) for path in
                                 sorted((ROOT / 'include/agro').glob('*.hpp')) + [ROOT / 'src/loop_cli.cpp']}}
    execution_path = campaign / 'execution.json'
    if execution_path.exists():
        if not resume:
            raise ValueError('Campaign execution already exists; use --resume to verify terminal records')
        previous = read_json(execution_path)
        for key in ('binary_sha256', 'dataset_manifest_sha256', 'frozen_files', 'source_sha256', 'runner_sha256'):
            if previous[key] != binding[key]:
                raise ValueError('Cannot mix revisions in a resumed campaign: ' + key)
    else:
        write_json(execution_path, binding)
    if limit is not None and (isinstance(limit, bool) or limit <= 0):
        raise ValueError('--limit must be positive')
    settings = dict(config['runner'])
    if timeout is not None:
        settings['timeout_s'] = finite_number(timeout, 'timeout', 1)
    rows = [{'dataset': dataset['id'], 'policy': policy, 'state': 'pending'}
            for dataset in manifest['datasets'] for policy in POLICIES]
    report = {'schema': 'agro-demand-campaign-v1', 'dataset_manifest_sha256': sha256(campaign / 'dataset.json'),
              'planned_runs': len(rows), 'limit_requested': limit, 'timeout_s': settings['timeout_s'],
              'runs': rows, 'finished': False, 'stop_reason': None}
    launched = 0
    for index, row in enumerate(rows):
        dataset = manifest['datasets'][index // len(POLICIES)]
        folder = campaign / 'runs' / dataset['id'] / row['policy']
        expected = {'dataset_sha256': dataset['sha256'], 'binary_sha256': binary_hash,
                    'frozen_files': manifest['frozen_files'], 'policy': row['policy'], 'dataset': dataset}
        attempts = sorted(folder.glob('attempt_*')) if folder.exists() else []
        completed = None
        if attempts:
            if not resume:
                raise ValueError('Run output exists without --resume')
            for attempt in reversed(attempts):
                if (attempt / 'run_record.json').exists():
                    completed = completed_record(attempt, expected)
                    if completed:
                        row.update(state='completed', attempt=attempt.relative_to(campaign).as_posix(),
                                   comparable=completed['summary']['comparable'], resumed=True)
                        break
        if completed:
            print(json.dumps({'dataset': dataset['id'], 'policy': row['policy'], 'event': 'verified_completed_resume'}), flush=True)
            continue
        if attempts:
            latest = attempts[-1]
            if (latest / 'run_record.json').exists():
                previous = read_json(latest / 'run_record.json')
                row.update(state=previous['state'], attempt=latest.relative_to(campaign).as_posix(),
                           comparable=False, errors=previous.get('errors', []))
            else:
                row.update(attempt=latest.relative_to(campaign).as_posix(),
                           errors=['Attempt directory has no terminal record; preserved for inspection'])
        if limit is not None and launched >= limit:
            report['stop_reason'] = 'explicit_run_limit'
            continue
        if report['stop_reason'] and report['stop_reason'] != 'explicit_run_limit':
            continue
        attempt = folder / f'attempt_{len(attempts)+1:03d}'
        command = [str(binary), '--config', str(campaign / 'loop.params'), '--output', str(attempt / 'output'),
                   '--demand', str(campaign / dataset['path']), '--dispatch-config', str(campaign / 'dispatch.params'),
                   '--policy', row['policy'], '--predictor', str(campaign / 'predictor.csv'),
                   '--compact', '--mode', 'central_only', '--no-wind']
        record = run_attempt(attempt, command, memory, expected, settings, read_host_memory, tree_rss)
        launched += 1
        row.update(state=record['state'], attempt=attempt.relative_to(campaign).as_posix(),
                   comparable=record.get('summary', {}).get('comparable', False), errors=record['errors'])
        print(json.dumps({'dataset': dataset['id'], 'policy': row['policy'], 'state': row['state'],
                          'comparable': row['comparable'], 'exit_code': record['exit_code']}), flush=True)
        if record['fatal_guard']:
            report['stop_reason'] = 'resource_timeout_or_explicit_stop_guard'
        report['counts'] = {state: sum(item['state'] == state for item in rows) for state in ('completed', 'failed', 'pending')}
        write_json(campaign / 'campaign.json', report)
    report['counts'] = {state: sum(item['state'] == state for item in rows) for state in ('completed', 'failed', 'pending')}
    report['finished'] = report['counts']['pending'] == 0
    write_json(campaign / 'campaign.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    generate = sub.add_parser('generate', help='Freeze paired demand and simulator inputs; no simulation')
    generate.add_argument('--config', type=Path, default=ROOT / 'config/demand_pilot.json')
    generate.add_argument('--output', type=Path, required=True)
    generate.add_argument('--params', type=Path, required=True)
    generate.add_argument('--predictor', type=Path, required=True)
    run = sub.add_parser('run', help='Sequential guarded execution; existing results require --resume')
    run.add_argument('--campaign', type=Path, required=True)
    run.add_argument('--binary', type=Path, required=True)
    run.add_argument('--host-memory', type=Path, required=True)
    run.add_argument('--resume', action='store_true')
    run.add_argument('--limit', type=int)
    run.add_argument('--timeout', type=float)
    args = parser.parse_args()
    if args.command == 'generate':
        result = generate_dataset(args.config, args.output, args.params, args.predictor)
        print(json.dumps({'datasets': result['dataset_count'], 'planned_runs': result['planned_runs']}))
    else:
        result = run_campaign(args.campaign, args.binary, args.host_memory, args.resume, args.limit, args.timeout)
        print(json.dumps({'finished': result['finished'], 'counts': result['counts'], 'stop_reason': result['stop_reason']}))
        raise SystemExit(0 if result['finished'] and result['counts']['failed'] == 0 else 1)


if __name__ == '__main__':
    main()
