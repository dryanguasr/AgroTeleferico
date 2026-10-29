#!/usr/bin/env python3
"""Independently reconstruct completed demand results from frozen input and CSVs.

This checks recorded operational invariants, not Gazebo contacts or structural
capacity. The native summary is the quantity under test, not the source of truth.
"""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path

INPUT_FIELDS = ('id', 'known_s', 'requested_s', 'deadline_s', 'origin', 'mass_kg', 'load_s', 'unload_s')
ORDER_FIELDS = INPUT_FIELDS + ('load_start_s', 'loaded_s', 'delivered_s', 'lateness_s', 'state')
OP_FIELDS = ('time_s', 'event', 'carrier', 'station', 'operation', 'order_or_aux', 'mass_kg', 'duration_s')
INVENTORY_FIELDS = ('time_s', 'module_id', 'home', 'station', 'carrier', 'aboard_fraction', 'reserved')
TIME_EPS = 1e-7
DURATION_TOL = .0041
SUMMARY_EPS = 1e-6


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def number(value):
    if isinstance(value, bool):
        raise ValueError('Boolean where a number was required')
    result = float(value)
    if not math.isfinite(result):
        raise ValueError('Nonfinite numeric artifact')
    return result


def integer(value):
    result = number(value)
    if result != int(result):
        raise ValueError('Noninteger identifier/count')
    return int(result)


def read_rows(path, fields, strings=()):
    with Path(path).open(newline='', encoding='utf-8-sig') as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != list(fields):
            raise ValueError(f'{Path(path).name}: unexpected CSV columns')
        rows = []
        for row in reader:
            if set(row) != set(fields) or any(value is None for value in row.values()):
                raise ValueError(f'{Path(path).name}: malformed row')
            rows.append({key: value if key in strings else number(value) for key, value in row.items()})
        return rows


def close(a, b, tolerance=SUMMARY_EPS):
    return abs(number(a)-number(b)) <= tolerance


def audit_run(requests, output, policy, height_m=3.2):
    requests, output = Path(requests), Path(output)
    result = {'policy': policy, 'passed': False, 'mismatches': [], 'sha256': {}, 'recomputed': {}}
    errors = result['mismatches']
    def check(condition, message):
        if not condition:
            errors.append(message)
    try:
        paths = {'requests.csv': requests, **{name: output/name for name in
                 ('orders.csv', 'operations.csv', 'inventory.csv', 'demand_summary.json')}}
        result['sha256'] = {name: digest(path) for name, path in paths.items()}
        inputs = read_rows(requests, INPUT_FIELDS, ('id',))
        orders = read_rows(output/'orders.csv', ORDER_FIELDS, ('id',))
        operations = read_rows(output/'operations.csv', OP_FIELDS, ('event', 'operation', 'order_or_aux'))
        inventory = read_rows(output/'inventory.csv', INVENTORY_FIELDS)
        summary = read_json(output/'demand_summary.json')
        check(policy in ('A', 'B', 'C', 'D'), 'Unknown policy')
        check(summary.get('policy') == policy, 'Summary policy differs from run')
        check(summary.get('completed') is True and summary.get('comparable') is True and summary.get('status') == 'completed',
              'Run selected for audit is not completed and comparable')
        source_ids, output_ids = [row['id'] for row in inputs], [row['id'] for row in orders]
        check(len(set(source_ids)) == len(source_ids), 'Frozen input IDs are not unique')
        check(len(set(output_ids)) == len(output_ids), 'Output order IDs are not unique')
        check(Counter(source_ids) == Counter(output_ids), 'Output orders differ from the entire frozen input ID set')
        source = {row['id']: row for row in inputs}
        useful_events = defaultdict(lambda: defaultdict(list))
        active, pairs = {}, []
        last_end = {0: -math.inf, 1: -math.inf}
        payload, peaks = {0: 0., 1: 0.}, {0: 0., 1: 0.}
        aux_moves = 0.
        for line, row in enumerate(operations, 2):
            carrier, station = integer(row['carrier']), integer(row['station'])
            check(carrier in (0, 1) and station in (0, 1), f'operations row {line}: invalid carrier/station')
            if carrier not in (0, 1) or station not in (0, 1):
                continue
            check(row['operation'] in ('load', 'unload'), f'operations row {line}: invalid operation')
            check(row['event'] in ('begin', 'end'), f'operations row {line}: invalid event')
            check(row['time_s'] >= 0 and 0 < row['mass_kg'] <= 10 and row['duration_s'] > 0,
                  f'operations row {line}: invalid time, mass or duration')
            label = row['order_or_aux']
            if label != 'aux':
                check(label in source, f'operations row {line}: unknown useful order {label}')
                if label in source:
                    request = source[label]
                    check(close(row['mass_kg'], request['mass_kg']), f'order {label}: operation mass differs from frozen demand')
                    origin = integer(request['origin'])
                    expected_station = origin if row['operation'] == 'load' else 1-origin
                    check(station == expected_station, f'order {label}: wrong origin/destination station')
                    declared = request['load_s'] if row['operation'] == 'load' else request['unload_s']
                    check(close(row['duration_s'], declared, TIME_EPS), f'order {label}: handling duration differs from frozen demand')
            else:
                check(row['mass_kg'] == int(row['mass_kg']), f'operations row {line}: auxiliary mass is not whole 1 kg modules')
                check(close(row['duration_s'], 8+2*row['mass_kg'], TIME_EPS), f'operations row {line}: auxiliary handling time mismatch')
                check(policy in ('C', 'D'), f'policy {policy}: auxiliary handling is forbidden')
            if row['event'] == 'begin':
                check(carrier not in active, f'carrier {carrier}: overlapping operations')
                check(row['time_s'] >= last_end[carrier]-TIME_EPS, f'carrier {carrier}: next operation begins before previous end')
                active[carrier] = row
            elif row['event'] == 'end':
                start = active.pop(carrier, None)
                check(start is not None, f'carrier {carrier}: operation end without begin')
                if start is None:
                    continue
                for key in ('station', 'operation', 'order_or_aux', 'mass_kg', 'duration_s'):
                    check(start[key] == row[key], f'carrier {carrier}: begin/end {key} mismatch')
                elapsed = row['time_s']-start['time_s']
                check(row['duration_s']-TIME_EPS <= elapsed <= row['duration_s']+DURATION_TOL,
                      f'carrier {carrier}, {label}: actual handling duration outside declared+[0,0.0041] s')
                period_start = math.floor((start['time_s']+TIME_EPS)/600)*600
                check(start['time_s'] >= period_start-TIME_EPS and start['time_s']+row['duration_s'] <= period_start+480+TIME_EPS
                      and row['time_s'] <= period_start+480+DURATION_TOL,
                      f'carrier {carrier}, {label}: handling crosses closed operator window')
                pair = {'begin': start, 'end': row}
                pairs.append(pair)
                if label != 'aux':
                    useful_events[label][row['operation']].append(pair)
                elif row['operation'] == 'load':
                    aux_moves += row['mass_kg']
                payload[carrier] += row['mass_kg'] if row['operation'] == 'load' else -row['mass_kg']
                peaks[carrier] = max(peaks[carrier], payload[carrier])
                check(-TIME_EPS <= payload[carrier] <= 10+TIME_EPS, f'carrier {carrier}: reconstructed payload outside [0,10] kg')
                last_end[carrier] = row['time_s']
        check(not active, 'Unclosed operation begin records')
        for carrier in (0, 1):
            check(abs(payload[carrier]) <= TIME_EPS, f'carrier {carrier}: terminal payload is not zero')
        for station in (0, 1):
            station_pairs = sorted((pair for pair in pairs if pair['begin']['station'] == station), key=lambda pair: pair['begin']['time_s'])
            for previous, following in zip(station_pairs, station_pairs[1:]):
                check(following['begin']['time_s'] >= previous['end']['time_s']-TIME_EPS,
                      f'station {station}: overlapping use of its operator')
        lateness, delivered_mass, on_time_mass, on_time = [], 0., 0., 0
        for order in orders:
            identifier = order['id']
            if identifier not in source:
                continue
            request = source[identifier]
            for field in INPUT_FIELDS[1:]:
                check(close(order[field], request[field], TIME_EPS), f'order {identifier}: output changed input {field}')
            check(integer(order['state']) == 4, f'order {identifier}: terminal state is not delivered')
            check(order['load_start_s'] >= request['known_s']-TIME_EPS, f'order {identifier}: loaded before announcement')
            if policy in ('A', 'B'):
                check(order['load_start_s'] >= request['requested_s']-TIME_EPS, f'order {identifier}: nonbuffer policy loaded before request')
            check(order['loaded_s'] >= order['load_start_s'] and order['delivered_s'] >= order['loaded_s'],
                  f'order {identifier}: invalid service chronology')
            events = useful_events[identifier]
            check(len(events['load']) == 1 and len(events['unload']) == 1, f'order {identifier}: useful load/unload must each occur exactly once')
            if len(events['load']) == len(events['unload']) == 1:
                loading, unloading = events['load'][0], events['unload'][0]
                check(loading['begin']['carrier'] == unloading['begin']['carrier'], f'order {identifier}: changed carrier in transit')
                check(close(order['load_start_s'], loading['begin']['time_s'], TIME_EPS)
                      and close(order['loaded_s'], loading['end']['time_s'], TIME_EPS)
                      and close(order['delivered_s'], unloading['end']['time_s'], TIME_EPS),
                      f'order {identifier}: order timestamps differ from operation events')
            late = max(0., order['delivered_s']-request['deadline_s'])
            check(close(order['lateness_s'], late), f'order {identifier}: recorded lateness differs from timestamps')
            lateness.append(late)
            delivered_mass += request['mass_kg']
            if late <= 1e-8:
                on_time += 1
                on_time_mass += request['mass_kg']
        expected_metrics = {'orders_total': len(inputs), 'orders_delivered': len(orders), 'on_time_orders': on_time,
                            'total_useful_kg': sum(row['mass_kg'] for row in inputs), 'delivered_useful_kg': delivered_mass,
                            'on_time_mass_kg': on_time_mass, 'max_lateness_s': max(lateness, default=0),
                            'lateness_p95_s': sorted(lateness)[math.ceil(.95*len(lateness))-1] if lateness else 0,
                            'buffer_moves_kg': aux_moves}
        for key, expected in expected_metrics.items():
            check(key in summary and close(summary[key], expected), f'summary {key}: differs from reconstructed artifacts')
        check(summary.get('governor_or_stop_count') == 0, 'Comparable result activated an ideal stop/governor')
        check(len(inventory) > 0 and len(inventory) % 20 == 0, 'Inventory is not a sequence of complete 20-row snapshots')
        snapshots = [inventory[index:index+20] for index in range(0, len(inventory), 20)]
        check(len(snapshots) == len(pairs)+1, 'Inventory snapshot count differs from initial state plus completed actions')
        previous_time = -math.inf
        previous_modules, inventory_aux_moves = None, 0
        for index, snapshot in enumerate(snapshots):
            if not snapshot:
                continue
            timestamp = snapshot[0]['time_s']
            expected_time = 0 if index == 0 else pairs[index-1]['end']['time_s'] if index <= len(pairs) else None
            check(expected_time is not None and close(timestamp, expected_time, TIME_EPS),
                  f'inventory snapshot {index}: timestamp differs from its completed action')
            check(timestamp >= previous_time-TIME_EPS, f'inventory snapshot {index}: time moved backward')
            previous_time = timestamp
            check({integer(row['module_id']) for row in snapshot} == set(range(20)) and len(snapshot) == 20,
                  f'inventory snapshot {index}: missing or duplicated module IDs')
            current_modules = {integer(row['module_id']): row for row in snapshot}
            if previous_modules is not None and index <= len(pairs):
                action = pairs[index-1]['end']
                changed = [(previous_modules[identifier], row) for identifier, row in current_modules.items()
                           if identifier in previous_modules and
                           (previous_modules[identifier]['station'], previous_modules[identifier]['carrier']) != (row['station'], row['carrier'])]
                expected_changes = integer(action['mass_kg']) if action['order_or_aux'] == 'aux' else 0
                check(len(changed) == expected_changes, f'inventory snapshot {index}: module transfer count differs from auxiliary operation mass')
                for before, after in changed:
                    if action['operation'] == 'load':
                        check(before['station'] == action['station'] and before['carrier'] == -1
                              and after['station'] == -1 and after['carrier'] == action['carrier'],
                              f'inventory snapshot {index}: auxiliary load has incorrect custody')
                        inventory_aux_moves += 1
                    else:
                        check(before['station'] == -1 and before['carrier'] == action['carrier']
                              and after['station'] == action['station'] and after['carrier'] == -1,
                              f'inventory snapshot {index}: auxiliary unload has incorrect custody')
            previous_modules = current_modules
            stock = {0: 0., 1: 0.}
            for row in snapshot:
                identifier, home, station, carrier, reserved = [integer(row[key]) for key in ('module_id', 'home', 'station', 'carrier', 'reserved')]
                fraction = row['aboard_fraction']
                check(close(timestamp, row['time_s'], TIME_EPS), f'inventory snapshot {index}: mixed snapshot timestamps')
                check(home == (0 if identifier < 10 else 1), f'module {identifier}: home changed')
                check(station in (-1, 0, 1) and carrier in (-1, 0, 1) and reserved in (0, 1), f'module {identifier}: invalid inventory state')
                check(-TIME_EPS <= fraction <= 1+TIME_EPS, f'module {identifier}: negative stock or fraction outside [0,1]')
                check((station >= 0 and carrier == -1) or (station == -1 and carrier >= 0), f'module {identifier}: missing or double physical location')
                if carrier == -1 and not reserved:
                    check(abs(fraction) <= TIME_EPS, f'module {identifier}: station module has unexplained aboard fraction')
                if station in stock:
                    stock[station] += 1-fraction
                if index in (0, len(snapshots)-1):
                    check(station == home and carrier == -1 and abs(fraction) <= TIME_EPS and reserved == 0,
                          f'module {identifier}: {"initial" if index == 0 else "terminal"} inventory is not restored')
            check(all(value >= -TIME_EPS for value in stock.values()), f'inventory snapshot {index}: negative station stock')
        initial_pe = final_pe = None
        if snapshots and len(snapshots[0]) == len(snapshots[-1]) == 20:
            def potential(snapshot):
                if any(row['station'] not in (0, 1) or row['carrier'] != -1 or abs(row['aboard_fraction']) > TIME_EPS for row in snapshot):
                    return None
                return sum(row['station']*9.81*height_m for row in snapshot)
            initial_pe, final_pe = potential(snapshots[0]), potential(snapshots[-1])
        delta_pe = None if initial_pe is None or final_pe is None else final_pe-initial_pe
        check(delta_pe is not None and abs(delta_pe) <= SUMMARY_EPS, 'Buffer inventory gravitational potential is not closed')
        check(close(inventory_aux_moves, aux_moves), 'Auxiliary moves reconstructed from module custody differ from operations')
        up_mass = sum(row['mass_kg'] for row in inputs if row['origin'] == 0)
        down_mass = sum(row['mass_kg'] for row in inputs if row['origin'] == 1)
        useful_exchange = -9.81*height_m*(up_mass-down_mass)
        exchange_expected = None if delta_pe is None else useful_exchange-delta_pe
        observed_exchange = number(summary['load_energy_J'])
        result['recomputed'] = {**expected_metrics, 'maximum_payload_kg': peaks, 'terminal_payload_kg': payload,
                                'completed_operations': len(pairs), 'inventory_snapshots': len(snapshots),
                                'buffer_initial_PE_J': initial_pe, 'buffer_final_PE_J': final_pe,
                                'buffer_delta_PE_J': delta_pe, 'station_height_difference_m': height_m,
                                'buffer_moves_from_inventory_kg': inventory_aux_moves,
                                'useful_up_kg': up_mass, 'useful_down_kg': down_mass,
                                'useful_exchange_potential_expected_J': useful_exchange,
                                'buffer_exchange_potential_expected_J': None if delta_pe is None else -delta_pe,
                                'load_energy_expected_J': exchange_expected,
                                'load_energy_recorded_J': observed_exchange,
                                'load_energy_difference_J': None if exchange_expected is None else observed_exchange-exchange_expected,
                                'energy_crosscheck_note': 'Reported analytical ledger comparison; no hard acceptance threshold because reduced transient terms remain. Not structural certification.'}
    except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
        errors.append(f'Artifact error: {type(exc).__name__}: {exc}')
    result['passed'] = not errors
    return result


def audit_campaign(campaign, output):
    campaign, output = Path(campaign).resolve(), Path(output)
    if output.exists():
        raise FileExistsError('Preserve previous audit; --output must be new')
    result = {'schema': 'agro-demand-artifact-audit-v1', 'passed': False, 'matrix_mismatches': [],
              'planned_runs': 720, 'runs': [], 'sha256': {},
              'scope': 'independent recorded order, operation and inventory invariants; not physical or structural certification',
              'duration_tolerance_s': DURATION_TOL, 'summary_tolerance': SUMMARY_EPS}
    errors = result['matrix_mismatches']
    def check(condition, message):
        if not condition:
            errors.append(message)
    try:
        names = ('dataset.json', 'campaign.json', 'execution.json', 'config.json', 'loop.params', 'dispatch.params', 'predictor.csv', 'predictor.csv.manifest')
        names = tuple(name for name in names if name != 'predictor.csv.manifest' or (campaign/name).exists())
        documents = {name: read_json(campaign/name) for name in names if name.endswith('.json')}
        result['sha256'] = {name: digest(campaign/name) for name in names}
        result['sha256']['auditor'] = digest(__file__)
        dataset, report, execution, config = [documents[name] for name in ('dataset.json', 'campaign.json', 'execution.json', 'config.json')]
        expected = {(f'{pattern}_r{rate:g}_s{seed:03d}', policy) for rate in (12, 24, 36)
                    for pattern in ('balanced', 'alternating') for seed in range(30) for policy in ('A', 'B', 'C', 'D')}
        input_records = dataset['datasets']
        indexed = {row['id']: row for row in input_records}
        check(len(input_records) == len(indexed) == 180, 'Frozen demand must contain exactly 180 unique inputs')
        check(dataset.get('planned_runs') == report.get('planned_runs') == 720, 'Declared planned count is not 720')
        rows = report['runs']
        check(len(rows) == 720 and Counter((row['dataset'], row['policy']) for row in rows) == Counter(expected),
              'The 720-policy matrix has missing, duplicate or foreign rows')
        check(dataset['config_sha256'] == result['sha256']['config.json'], 'Frozen JSON configuration hash changed')
        check(report['dataset_manifest_sha256'] == execution['dataset_manifest_sha256'] == result['sha256']['dataset.json'],
              'Campaign provenance does not match frozen input manifest')
        for name, value in dataset['frozen_files'].items():
            check(name in ('loop.params', 'dispatch.params', 'predictor.csv', 'predictor.csv.manifest') and result['sha256'].get(name) == value, f'Frozen {name} hash changed')
        check(config['dispatch']['capacity_kg'] == 10 and config['dispatch']['operator_period_s'] == 600
              and config['dispatch']['operator_open_s'] == 480 and config['dispatch']['buffer_unit_kg'] == 1
              and config['dispatch']['buffer_units_per_station'] == 10,
              'Frozen experimental capacity, staffing or auxiliary module contract differs')
        terrain = next(line.split() for line in (campaign/'loop.params').read_text().splitlines() if line.startswith('terrain '))
        height = number(terrain[5])-number(terrain[3])
        check(integer(terrain[1]) == 2 and close(height, 3.2), 'Audited inventory potential assumes the frozen 3.2 m patio geometry')
        for row in rows:
            item = {'dataset': row['dataset'], 'policy': row['policy'], 'state': row['state'],
                    'audited': False, 'passed': False, 'mismatches': [], 'reason': None}
            result['runs'].append(item)
            try:
                source = indexed[row['dataset']]
                path = (campaign/source['path']).resolve()
                if not path.is_relative_to(campaign) or digest(path) != source['sha256']:
                    raise ValueError('Frozen demand CSV hash/path changed')
                item['request_sha256'] = source['sha256']
                if row['state'] != 'completed':
                    item['reason'] = '; '.join(row.get('errors', [])) or row['state']
                    check(row['state'] in ('failed', 'pending'), 'Unknown terminal campaign state')
                    continue
                attempt = (campaign/row['attempt']).resolve()
                if not attempt.is_relative_to(campaign):
                    raise ValueError('Attempt escapes campaign directory')
                native = read_json(attempt/'output/demand_summary.json')
                item['native_status'] = native.get('status')
                if native.get('comparable') is not True or native.get('completed') is not True:
                    item['reason'] = native.get('status', 'noncomparable')
                    item['native_summary_sha256'] = digest(attempt/'output/demand_summary.json')
                    continue
                record = read_json(attempt/'run_record.json')
                if record['dataset_sha256'] != source['sha256'] or record['binary_sha256'] != execution['binary_sha256'] or record['frozen_files'] != dataset['frozen_files']:
                    raise ValueError('Run provenance differs from frozen inputs/executable')
                for name, value in record['output_sha256'].items():
                    artifact = (attempt/name).resolve()
                    if not artifact.is_relative_to(attempt) or digest(artifact) != value:
                        raise ValueError(f'Output hash/path changed: {name}')
                audit = audit_run(path, attempt/'output', row['policy'], height)
                item.update(audit, audited=True, run_record_sha256=digest(attempt/'run_record.json'))
            except (OSError, ValueError, KeyError, TypeError) as exc:
                item['mismatches'].append(f'{type(exc).__name__}: {exc}')
    except (OSError, ValueError, KeyError, TypeError, StopIteration, IndexError) as exc:
        errors.append(f'Matrix artifact error: {type(exc).__name__}: {exc}')
    counts = Counter(row['state'] for row in result['runs'])
    result['counts'] = {key: counts[key] for key in ('completed', 'failed', 'pending')}
    result['audited_comparable_runs'] = sum(row['audited'] for row in result['runs'])
    result['passed_audits'] = sum(row['audited'] and row['passed'] for row in result['runs'])
    result['not_audited_completed'] = sum(row['state'] == 'completed' and not row['audited'] for row in result['runs'])
    result['failed_or_noncomparable_reasons'] = dict(Counter(row['reason'] for row in result['runs'] if row['reason']))
    result['passed'] = not errors and len(result['runs']) == 720 and result['passed_audits'] == 720
    with output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--campaign', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = audit_campaign(args.campaign, args.output)
    print(json.dumps({key: result[key] for key in ('passed', 'counts', 'audited_comparable_runs', 'passed_audits')}))
    raise SystemExit(0 if result['passed'] else 1)


if __name__ == '__main__':
    main()
