"""Independent output audit against operational CSV schema; no simulator launch."""
import copy
import csv
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import audit_demand_outputs as audit


def write_json(path, value):
    Path(path).write_text(json.dumps(value), encoding='utf-8')


def write_csv(path, fields, rows):
    with Path(path).open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def fixture(root, policy='A', aux_mass=0, simultaneous=False):
    root = Path(root)
    output = root/'output'
    output.mkdir(parents=True)
    requests = [dict(zip(audit.INPUT_FIELDS, ('1', 10, 10, 250, 0, 5, 20, 20)))]
    if simultaneous:
        requests.append(dict(zip(audit.INPUT_FIELDS, ('2', 10, 10, 100, 1, 5, 20, 20))))
    pairs = []
    def operation(begin, end, carrier, station, kind, identifier, mass, declared):
        data = {'carrier': carrier, 'station': station, 'operation': kind,
                'order_or_aux': identifier, 'mass_kg': mass, 'duration_s': declared}
        pairs.append((dict(data, time_s=begin, event='begin'), dict(data, time_s=end, event='end')))
    for carrier, request in enumerate(requests):
        operation(20, 40, carrier, request['origin'], 'load', request['id'], 5, 20)
        operation(100, 120, carrier, 1-request['origin'], 'unload', request['id'], 5, 20)
    if aux_mass:
        duration = 8+2*aux_mass
        operation(42, 42+duration, 0, 0, 'load', 'aux', aux_mass, duration)
        operation(122, 122+duration, 0, 1, 'unload', 'aux', aux_mass, duration)
        operation(124+duration, 124+2*duration, 0, 1, 'load', 'aux', aux_mass, duration)
        operation(220, 220+duration, 0, 0, 'unload', 'aux', aux_mass, duration)
    operations = sorted([row for pair in pairs for row in pair], key=lambda row: (row['time_s'], row['carrier']))
    inventory = []
    state = [dict(module_id=identifier, home=0 if identifier < 10 else 1,
                  station=0 if identifier < 10 else 1, carrier=-1, aboard_fraction=0, reserved=0)
             for identifier in range(20)]
    def snapshot(timestamp):
        inventory.extend(dict(row, time_s=timestamp) for row in state)
    snapshot(0)
    for row in operations:
        if row['event'] != 'end':
            continue
        if row['order_or_aux'] == 'aux':
            for module in state[:aux_mass]:
                module.update(station=-1 if row['operation'] == 'load' else row['station'],
                              carrier=row['carrier'] if row['operation'] == 'load' else -1,
                              aboard_fraction=1 if row['operation'] == 'load' else 0)
        snapshot(row['time_s'])
    orders = [dict(request, load_start_s=20, loaded_s=40, delivered_s=120,
                   lateness_s=max(0, 120-request['deadline_s']), state=4) for request in requests]
    lateness = sorted(row['lateness_s'] for row in orders)
    on_time = sum(row['lateness_s'] == 0 for row in orders)
    summary = {'policy': policy, 'status': 'completed', 'completed': True, 'comparable': True,
               'orders_total': len(orders), 'orders_delivered': len(orders), 'on_time_orders': on_time,
               'total_useful_kg': 5*len(orders), 'delivered_useful_kg': 5*len(orders), 'on_time_mass_kg': 5*on_time,
               'max_lateness_s': max(lateness), 'lateness_p95_s': lateness[math.ceil(.95*len(lateness))-1],
               'buffer_moves_kg': 2*aux_mass, 'governor_or_stop_count': 0,
               'load_energy_J': -9.81*3.2*sum(row['mass_kg']*(1 if row['origin'] == 0 else -1) for row in requests)}
    data = {'requests': requests, 'orders': orders, 'operations': operations,
            'inventory': inventory, 'summary': summary, 'output': output, 'root': root}
    save(data)
    return data


def save(data):
    write_csv(data['root']/'requests.csv', audit.INPUT_FIELDS, data['requests'])
    for key, fields in (('orders', audit.ORDER_FIELDS), ('operations', audit.OP_FIELDS), ('inventory', audit.INVENTORY_FIELDS)):
        write_csv(data['output']/(key+'.csv'), fields, data[key])
    write_json(data['output']/'demand_summary.json', data['summary'])


def run(data):
    save(data)
    return audit.audit_run(data['root']/'requests.csv', data['output'], data['summary']['policy'])


class ArtifactAudit(unittest.TestCase):
    def test_valid_useful_operations_and_nearest_rank_p95(self):
        with tempfile.TemporaryDirectory() as temp:
            result = run(fixture(temp, simultaneous=True))
            self.assertTrue(result['passed'], result['mismatches'])
            self.assertEqual(result['recomputed']['lateness_p95_s'], 20)
            self.assertEqual(result['recomputed']['on_time_orders'], 1)
            self.assertEqual(result['recomputed']['inventory_snapshots'], 5)
            # Two separate 20-row snapshots at each duplicate completion time.
            self.assertEqual(result['recomputed']['buffer_delta_PE_J'], 0)

    def test_auxiliary_inventory_round_trip_and_mass_moves(self):
        with tempfile.TemporaryDirectory() as temp:
            result = run(fixture(temp, policy='C', aux_mass=2))
            self.assertTrue(result['passed'], result['mismatches'])
            self.assertEqual(result['recomputed']['maximum_payload_kg'][0], 7)
            self.assertEqual(result['recomputed']['buffer_moves_kg'], 4)
            self.assertAlmostEqual(result['recomputed']['buffer_initial_PE_J'], 10*9.81*3.2)
            self.assertEqual(result['recomputed']['buffer_delta_PE_J'], 0)

    def test_duplicate_missing_or_changed_orders_are_rejected(self):
        for change in ('duplicate', 'missing', 'changed_mass'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temp:
                data = fixture(temp)
                if change == 'duplicate': data['orders'].append(copy.deepcopy(data['orders'][0]))
                if change == 'missing': data['orders'].clear()
                if change == 'changed_mass': data['orders'][0]['mass_kg'] = 6
                self.assertFalse(run(data)['passed'])

    def test_information_and_requested_time_constraints(self):
        with tempfile.TemporaryDirectory() as temp:
            data = fixture(temp)
            data['requests'][0]['requested_s'] = data['orders'][0]['requested_s'] = 50
            self.assertTrue(any('before request' in text for text in run(data)['mismatches']))
            data['summary']['policy'] = 'C'
            self.assertTrue(run(data)['passed'])
            data['requests'][0]['known_s'] = data['orders'][0]['known_s'] = 25
            self.assertTrue(any('before announcement' in text for text in run(data)['mismatches']))

    def test_wrong_destination_missing_end_and_overlapping_actions(self):
        for change, expected in (('destination', 'wrong origin/destination'), ('missing_end', 'Unclosed'), ('overlap', 'overlapping')):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temp:
                data = fixture(temp)
                if change == 'destination':
                    for row in data['operations']:
                        if row['operation'] == 'unload': row['station'] = 0
                if change == 'missing_end': data['operations'].pop()
                if change == 'overlap': data['operations'].insert(1, copy.deepcopy(data['operations'][0]))
                result = run(data)
                self.assertFalse(result['passed'])
                self.assertTrue(any(expected in text for text in result['mismatches']), result['mismatches'])

    def test_declared_duration_and_operator_windows(self):
        for change, expected in (('short', 'actual handling duration'), ('long', 'actual handling duration'), ('window', 'closed operator window')):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temp:
                data = fixture(temp)
                if change == 'short': data['operations'][1]['time_s'] = 39.99
                if change == 'long': data['operations'][1]['time_s'] = 40.01
                if change == 'window':
                    data['operations'][0]['time_s'] = 470
                    data['operations'][1]['time_s'] = 490
                result = run(data)
                self.assertTrue(any(expected in text for text in result['mismatches']), result['mismatches'])

    def test_substep_end_rounding_within_recorded_tolerance(self):
        with tempfile.TemporaryDirectory() as temp:
            data = fixture(temp)
            data['operations'][1]['time_s'] = data['orders'][0]['loaded_s'] = 40.003
            for row in data['inventory'][20:40]: row['time_s'] = 40.003
            self.assertTrue(run(data)['passed'])

    def test_capacity_includes_auxiliary_mass(self):
        with tempfile.TemporaryDirectory() as temp:
            result = run(fixture(temp, policy='C', aux_mass=6))
            self.assertTrue(any('payload outside' in text for text in result['mismatches']))

    def test_auxiliary_custody_independently_checks_operation_mass(self):
        with tempfile.TemporaryDirectory() as temp:
            data = fixture(temp, policy='C', aux_mass=3)
            endings = iter(row['time_s'] for row in data['operations'] if row['order_or_aux'] == 'aux' and row['event'] == 'end')
            current_end = None
            for row in data['operations']:
                if row['order_or_aux'] != 'aux': continue
                row['mass_kg'], row['duration_s'] = 2, 12
                if row['event'] == 'begin':
                    current_end = next(endings)
                    row['time_s'] = current_end-12
            data['summary']['buffer_moves_kg'] = 4
            result = run(data)
            self.assertFalse(result['passed'])
            self.assertTrue(any('transfer count differs' in text for text in result['mismatches']), result['mismatches'])

    def test_inventory_identity_fraction_and_terminal_potential(self):
        for change, expected in (('duplicate', 'duplicated module'), ('negative', 'negative stock'), ('foreign', 'not restored'), ('missing', '20-row')):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temp:
                data = fixture(temp)
                if change == 'duplicate': data['inventory'][1]['module_id'] = 0
                if change == 'negative': data['inventory'][21]['aboard_fraction'] = 1.1
                if change == 'foreign': data['inventory'][-20]['station'] = 1
                if change == 'missing': data['inventory'].pop()
                result = run(data)
                self.assertFalse(result['passed'])
                self.assertTrue(any(expected in text for text in result['mismatches']), result['mismatches'])
                if change == 'foreign': self.assertAlmostEqual(result['recomputed']['buffer_delta_PE_J'], 9.81*3.2)

    def test_summary_is_recomputed_not_trusted(self):
        for field in ('orders_delivered', 'on_time_orders', 'delivered_useful_kg', 'lateness_p95_s', 'buffer_moves_kg'):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temp:
                data = fixture(temp)
                data['summary'][field] += 1
                result = run(data)
                self.assertTrue(any(f'summary {field}' in text for text in result['mismatches']))

    def test_nonfinite_artifacts_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            data = fixture(temp)
            data['operations'][0]['mass_kg'] = float('nan')
            result = run(data)
            self.assertFalse(result['passed'])
            self.assertTrue(any('Nonfinite' in text for text in result['mismatches']))


class MatrixAccounting(unittest.TestCase):
    def test_all_planned_rows_remain_counted_with_pending_and_noncomparable(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data = fixture(root)
            for name, text in (('loop.params', 'terrain 2 0 0 8.6 3.2\n'), ('dispatch.params', 'capacity_kg 10\n'), ('predictor.csv', 'unit fixture\n')):
                (root/name).write_text(text)
            config = {'dispatch': {'capacity_kg': 10, 'operator_period_s': 600, 'operator_open_s': 480,
                                   'buffer_unit_kg': 1, 'buffer_units_per_station': 10}}
            write_json(root/'config.json', config)
            inputs, rows = [], []
            for rate in (12, 24, 36):
                for pattern in ('balanced', 'alternating'):
                    for seed in range(30):
                        identifier = f'{pattern}_r{rate}_s{seed:03d}'
                        inputs.append({'id': identifier, 'path': 'requests.csv', 'sha256': audit.digest(root/'requests.csv')})
                        rows.extend({'dataset': identifier, 'policy': policy, 'state': 'pending'} for policy in ('A', 'B', 'C', 'D'))
            frozen = {name: audit.digest(root/name) for name in ('loop.params', 'dispatch.params', 'predictor.csv')}
            dataset = {'datasets': inputs, 'planned_runs': 720, 'config_sha256': audit.digest(root/'config.json'), 'frozen_files': frozen}
            write_json(root/'dataset.json', dataset)
            dataset_hash = audit.digest(root/'dataset.json')
            write_json(root/'execution.json', {'dataset_manifest_sha256': dataset_hash, 'binary_sha256': 'test-double'})
            # Auditable successful native-format output without invoking a simulator.
            rows[0].update(state='completed', attempt='.')
            write_json(root/'run_record.json', {'dataset_sha256': inputs[0]['sha256'], 'binary_sha256': 'test-double',
                                                'frozen_files': frozen, 'output_sha256': {f'output/{name}': audit.digest(root/'output'/name)
                                                for name in ('orders.csv', 'operations.csv', 'inventory.csv', 'demand_summary.json')}})
            (root/'noncomparable/output').mkdir(parents=True)
            write_json(root/'noncomparable/output/demand_summary.json', {'policy': 'B', 'status': 'completed_noncomparable', 'completed': True, 'comparable': False})
            rows[1].update(state='completed', attempt='noncomparable')
            rows[2].update(state='failed', errors=['controlled fixture failure'])
            report = {'dataset_manifest_sha256': dataset_hash, 'planned_runs': 720, 'runs': rows}
            write_json(root/'campaign.json', report)
            result = audit.audit_campaign(root, root/'audit.json')
            self.assertEqual(result['counts'], {'completed': 2, 'failed': 1, 'pending': 717})
            self.assertEqual(result['passed_audits'], 1)
            self.assertEqual(result['not_audited_completed'], 1)
            self.assertFalse(result['passed'])
            self.assertFalse(result['matrix_mismatches'], result['matrix_mismatches'])
            with self.assertRaises(FileExistsError): audit.audit_campaign(root, root/'audit.json')
            rows.pop()
            write_json(root/'campaign.json', report)
            reduced = audit.audit_campaign(root, root/'audit_missing.json')
            self.assertTrue(any('missing' in text for text in reduced['matrix_mismatches']))


if __name__ == '__main__':
    unittest.main()
