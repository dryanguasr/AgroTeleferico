#!/usr/bin/env python3
"""Terminal mechanical ledger acceptance for the calm, central-only demand pilot."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

SCHEMA = 'agro-demand-energy-v1'
ABS_J, REL, TERMINAL_J = .5, .01, .1


def finite(value):
    if isinstance(value, bool):
        raise ValueError('Boolean energy value')
    value = float(value)
    if not math.isfinite(value):
        raise ValueError('Nonfinite energy value')
    return value


def near(a, b):
    return abs(a-b) <= 1e-5+1e-8*(abs(a)+abs(b))


def audit_energy(requests, output, params):
    output, requests, params = Path(output), Path(requests), Path(params)
    result = {'schema': SCHEMA, 'passed': False, 'errors': [],
              'scope': 'Terminal mechanical ledger; transient residual remains diagnostic',
              'criteria': {'absolute_J': ABS_J, 'relative': REL, 'terminal_delta_J': TERMINAL_J}}
    def check(value, message):
        if not value and message not in result['errors']:
            result['errors'].append(message)
    try:
        paths = [requests, params, output/'global.csv', output/'demand_summary.json']
        result['sha256'] = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
        summary = json.loads((output/'demand_summary.json').read_text())
        with (output/'global.csv').open(newline='') as stream:
            rows = [{k: finite(v) for k, v in row.items()} for row in csv.DictReader(stream)]
        check(len(rows) >= 2, 'Missing initial/final telemetry')
        first, last = rows[0], rows[-1]
        check(first['time_s'] == 0 and last['time_s'] > 0, 'Telemetry must cover the complete service')
        counters = ('drive_positive_J', 'drive_absorbed_J', 'local_positive_J',
                    'local_absorbed_J', 'loss_work_J', 'stop_loss_J')
        peak, previous = 0., first
        for row in rows:
            check(row['time_s'] >= previous['time_s'], 'Telemetry time decreased')
            for key in counters:
                check(row[key] >= -1e-8 and row[key]+1e-8 >= previous[key], 'Invalid cumulative work: '+key)
            # The wind ledger also contains aerodynamic drag from carrier motion
            # in still air. Calm means ambient wind is zero, not zero drag work.
            check(abs(row['wind_m_s']) <= 1e-8 and abs(row['local_positive_J']) <= 1e-8
                  and abs(row['local_absorbed_J']) <= 1e-8 and abs(row['stop_loss_J']) <= 1e-8,
                  'Energy audit requires calm central-only operation without ideal stops')
            work = (row['drive_positive_J']-row['drive_absorbed_J']+row['local_positive_J']
                    -row['local_absorbed_J']+row['wind_work_J']+row['load_energy_J']
                    -row['loss_work_J']-row['stop_loss_J'])
            residual = row['energy_J']-first['energy_J']-work
            check(near(residual, row['residual_J']), 'Recorded residual differs from reconstructed ledger')
            peak = max(peak, abs(residual))
            previous = row
        for key in counters+('wind_work_J', 'load_energy_J', 'residual_J'):
            check(abs(first[key]) <= 1e-8, 'Nonzero initial ledger: '+key)
        for key in ('drive_positive_J', 'drive_absorbed_J', 'loss_work_J', 'load_energy_J', 'residual_J'):
            check(near(last[key], finite(summary[key])), 'Summary/telemetry mismatch: '+key)
        delta = last['energy_J']-first['energy_J']
        check(near(delta, finite(summary['energy_delta_J'])), 'Terminal energy delta mismatch')
        check(near(last['time_s'], finite(summary['simulation_s'])), 'Incomplete terminal telemetry')
        budget = ABS_J+REL*(last['drive_positive_J']+last['drive_absorbed_J']+last['loss_work_J'])
        check(abs(last['residual_J']) <= budget, 'Terminal residual exceeds budget')
        check(abs(delta) <= TERMINAL_J, 'Terminal state energy not restored')
        check(summary.get('energy_acceptance_schema') == SCHEMA and summary.get('energy_accepted') is True,
              'Missing or rejected native energy acceptance')
        check(near(finite(summary['energy_residual_budget_J']), budget), 'Native budget mismatch')
        check(finite(summary['peak_abs_energy_residual_J'])+1e-4 >= peak, 'Native peak omits observed transient residual')
        check(summary.get('completed') is True and summary.get('comparable') is True
              and summary.get('status') == 'completed' and finite(summary['governor_or_stop_count']) == 0,
              'Service is incomplete or noncomparable')
        terrain = next(line.split() for line in params.read_text().splitlines() if line.startswith('terrain '))
        check(terrain[1] == '2' and len(terrain) == 6, 'Energy audit requires two-endpoint terrain')
        height = finite(terrain[5])-finite(terrain[3])
        with requests.open(newline='') as stream:
            orders = list(csv.DictReader(stream))
        total, directional = 0., 0.
        for order in orders:
            mass, origin = finite(order['mass_kg']), finite(order['origin'])
            check(mass > 0 and origin in (0, 1), 'Invalid useful load')
            total += mass
            directional += mass*(1 if origin == 0 else -1)
        check(finite(summary['orders_delivered']) == len(orders)
              and near(total, finite(summary['delivered_useful_kg'])), 'Useful service not completely delivered')
        # Auxiliary stocks must be restored by the separate inventory audit.
        expected = -9.81*height*directional
        exchange_budget = ABS_J+REL*9.81*abs(height)*total
        check(abs(last['load_energy_J']-expected) <= exchange_budget, 'Mass-transfer energy exceeds budget')
        result['recomputed'] = {'terminal_residual_J': last['residual_J'], 'residual_budget_J': budget,
                                'terminal_delta_J': delta, 'sampled_peak_abs_residual_J': peak,
                                'load_energy_expected_J': expected, 'load_energy_recorded_J': last['load_energy_J'],
                                'load_energy_budget_J': exchange_budget, 'telemetry_rows': len(rows)}
    except (OSError, ValueError, TypeError, KeyError, IndexError, StopIteration) as exc:
        result['errors'].append(str(exc))
    result['passed'] = not result['errors']
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--requests', type=Path, required=True)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--params', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = audit_energy(args.requests, args.run, args.params)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2)
    raise SystemExit(0 if result['passed'] else 1)


if __name__ == '__main__':
    main()
