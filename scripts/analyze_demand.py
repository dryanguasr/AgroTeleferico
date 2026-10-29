#!/usr/bin/env python3
"""Paired operational comparisons; electrical numbers are hypothetical proxies."""
import argparse
from collections import Counter
import csv
import hashlib
import itertools
import json
import math
from pathlib import Path
import random
import statistics

from demand_campaign import (POLICIES, completed_record, load_dataset, read_json,
                             sha256, validate_summary, write_json)

METRICS = ('drive_positive_J', 'drive_absorbed_J', 'simulation_s',
           'on_time_fraction', 'on_time_mass_fraction', 'lateness_p95_s',
           'max_lateness_s', 'deliberate_wait_s', 'mandatory_wait_s',
           'restoration_positive_J', 'buffer_moves_kg')
CONTRASTS = {'B-A': {'B': 1, 'A': -1}, 'C-A': {'C': 1, 'A': -1},
             'D-A': {'D': 1, 'A': -1}, 'C-B': {'C': 1, 'B': -1},
             'D-B': {'D': 1, 'B': -1}, 'D-C': {'D': 1, 'C': -1},
             '(D-C)-(B-A)': {'D': 1, 'C': -1, 'B': -1, 'A': 1}}


def quantile(values, probability):
    if not values:
        return None
    ordered = sorted(values)
    location = (len(ordered) - 1) * probability
    lo, hi = math.floor(location), math.ceil(location)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (location - lo)


def keyed_rng(key):
    digest = hashlib.sha256(json.dumps(key, sort_keys=True, separators=(',', ':')).encode()).digest()
    return random.Random(int.from_bytes(digest, 'big'))


def bootstrap_columns(columns, key, replicates=10000):
    """Resample paired seed rows together, preserving correlation across metrics."""
    sizes = {len(values) for values in columns.values()}
    if len(sizes) != 1:
        raise ValueError('Bootstrap columns must have identical paired row counts')
    count = sizes.pop() if sizes else 0
    if count == 0:
        return {name: [] for name in columns}
    if replicates < 1:
        raise ValueError('Bootstrap replicate count must be positive')
    if any(not math.isfinite(value) for values in columns.values() for value in values):
        raise ValueError('Bootstrap values must be finite')
    rng = keyed_rng(key)
    draws = {name: [] for name in columns}
    for _ in range(replicates):
        indices = rng.choices(range(count), k=count)
        for name, values in columns.items():
            draws[name].append(sum(values[index] for index in indices) / count)
    return draws


def describe(values, samples, confidence=.95):
    if not values:
        return {'n': 0, 'mean': None, 'median': None, 'ci95_low': None,
                'ci95_high': None, 'minimum': None, 'maximum': None}
    tail = (1 - confidence) / 2
    return {'n': len(values), 'mean': statistics.fmean(values),
            'median': statistics.median(values), 'ci95_low': quantile(samples, tail),
            'ci95_high': quantile(samples, 1-tail), 'minimum': min(values), 'maximum': max(values)}


def electric_components(summary, eta, p0, regen):
    if not 0 < eta <= 1 or p0 < 0 or not 0 <= regen <= 1:
        raise ValueError('Invalid hypothetical electrical scenario')
    draw = summary['drive_positive_J'] / eta + p0 * summary['simulation_s']
    recover = regen * summary['drive_absorbed_J']
    return {'E_draw_J': draw, 'E_recover_J': recover, 'E_net_J': draw - recover}


def summary_metrics(summary):
    result = {name: summary[name] for name in METRICS if name in summary}
    result['on_time_fraction'] = summary['on_time_orders'] / summary['orders_total'] if summary['orders_total'] else 1.
    result['on_time_mass_fraction'] = summary['on_time_mass_kg'] / summary['total_useful_kg'] if summary['total_useful_kg'] else 1.
    return result


def collect_runs(campaign):
    campaign = Path(campaign).resolve()
    config, dataset = load_dataset(campaign)
    execution = read_json(campaign / 'execution.json')
    report = read_json(campaign / 'campaign.json')
    if report['dataset_manifest_sha256'] != sha256(campaign / 'dataset.json') or execution['dataset_manifest_sha256'] != report['dataset_manifest_sha256']:
        raise ValueError('Campaign and frozen input manifest disagree')
    expected_keys = {(item['id'], policy) for item in dataset['datasets'] for policy in POLICIES}
    rows = report['runs']
    if len(rows) != len(expected_keys) or {(row['dataset'], row['policy']) for row in rows} != expected_keys:
        raise ValueError('Campaign rows must retain every planned run, including failures and pending')
    inputs = {item['id']: item for item in dataset['datasets']}
    output = []
    for row in rows:
        data = inputs[row['dataset']]
        record = {**data, 'dataset': data['id'], 'policy': row['policy'], 'state': row['state'],
                  'comparable': False, 'reason': None, 'summary': None}
        if row['state'] == 'completed':
            directory = campaign / row['attempt']
            if not directory.resolve().is_relative_to(campaign):
                raise ValueError('Run path escapes campaign')
            expected = {'dataset': data, 'dataset_sha256': data['sha256'],
                        'binary_sha256': execution['binary_sha256'],
                        'frozen_files': dataset['frozen_files'], 'policy': row['policy']}
            terminal = completed_record(directory, expected)
            if terminal is None:
                raise ValueError('Campaign labels a nonterminal run completed')
            summary = validate_summary(read_json(directory / 'output/demand_summary.json'), data, row['policy'])
            record.update(summary=summary, comparable=summary['comparable'],
                          reason=None if summary['comparable'] else summary['status'],
                          attempt=row['attempt'], metrics=summary_metrics(summary))
        elif row['state'] in ('failed', 'pending'):
            record['reason'] = '; '.join(row.get('errors', [])) or row['state']
            record['attempt'] = row.get('attempt')
        else:
            raise ValueError('Unknown campaign run state: ' + str(row['state']))
        output.append(record)
    return config, dataset, report, output


def paired_group(rows, coefficients):
    by_seed = {}
    for row in rows:
        by_seed.setdefault(row['seed'], {})[row['policy']] = row
    usable, excluded = [], []
    for seed, policies in sorted(by_seed.items()):
        required = [policies.get(policy) for policy in coefficients]
        if any(row is None or not row['comparable'] for row in required):
            excluded.append({'seed': seed, 'reason': 'missing_or_noncomparable',
                             'policies': {policy: policies.get(policy, {}).get('reason', 'missing') for policy in coefficients if not policies.get(policy, {}).get('comparable')}})
            continue
        totals = {(row['summary']['orders_total'], row['summary']['orders_delivered'],
                   row['summary']['total_useful_kg'], row['summary']['delivered_useful_kg']) for row in required}
        if len(totals) != 1:
            excluded.append({'seed': seed, 'reason': 'different_fulfilled_workload'})
            continue
        usable.append((seed, policies))
    columns = {metric: [sum(coefficient * policies[policy]['metrics'][metric]
                           for policy, coefficient in coefficients.items())
                        for _, policies in usable] for metric in METRICS}
    return usable, excluded, columns


def select_representative(rows, analysis):
    matching = [row for row in rows if row['rate_per_hour'] == analysis['representative_rate_per_hour']
                and row['pattern'] == analysis['representative_pattern']]
    by_seed = {}
    for row in matching:
        by_seed.setdefault(row['seed'], {})[row['policy']] = row
    eligible = {seed: policies for seed, policies in by_seed.items()
                if all(policies.get(policy, {}).get('comparable', False) for policy in POLICIES)}
    if not eligible:
        return {'selected': False, 'reason': 'No nominal seed has four comparable completed policies'}
    baseline = analysis['representative_baseline_policy']
    median = statistics.median(policies[baseline]['summary']['drive_positive_J'] for policies in eligible.values())
    seed = min(eligible, key=lambda value: (abs(eligible[value][baseline]['summary']['drive_positive_J'] - median), value))
    policies = eligible[seed]
    return {'selected': True, 'seed': seed, 'dataset': policies[baseline]['dataset'],
            'rate_per_hour': analysis['representative_rate_per_hour'], 'pattern': analysis['representative_pattern'],
            'selection': 'closest baseline A drive_positive_J to eligible-seed median; ties use lower seed',
            'eligible_seeds': len(eligible), 'baseline_median_positive_J': median,
            'baseline_selected_positive_J': policies[baseline]['summary']['drive_positive_J'],
            'runs': {policy: policies[policy]['attempt'] for policy in POLICIES},
            'input_path': policies[baseline]['path'], 'input_sha256': policies[baseline]['sha256']}


def write_csv(path, rows, fields):
    with Path(path).open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n', extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def analyze(campaign, output):
    campaign, output = Path(campaign).resolve(), Path(output).resolve()
    config, dataset, campaign_report, rows = collect_runs(campaign)
    output.mkdir(parents=True, exist_ok=False)
    analysis = config['analysis']
    comparisons, electrical, exclusions = [], [], []
    for rate, pattern in itertools.product(config['demand']['rates_per_hour'], config['demand']['patterns']):
        group = [row for row in rows if row['rate_per_hour'] == rate and row['pattern'] == pattern]
        for contrast, coefficients in CONTRASTS.items():
            usable, excluded, columns = paired_group(group, coefficients)
            draws = bootstrap_columns(columns, ['agro-demand-bootstrap-v1', rate, pattern, contrast],
                                      analysis['bootstrap_replicates'])
            context = {'rate_per_hour': rate, 'pattern': pattern, 'contrast': contrast,
                       'planned_pairs': config['demand']['seeds'], 'excluded_pairs': len(excluded)}
            exclusions.append({**context, 'usable_seeds': [seed for seed, _ in usable], 'excluded': excluded})
            for metric in METRICS:
                comparisons.append({**context, 'metric': metric,
                                    **describe(columns[metric], draws[metric], analysis['confidence_level'])})
            for eta, p0, regen in itertools.product(analysis['motor_efficiencies'], analysis['idle_powers_W'], analysis['regeneration_efficiencies']):
                point = {'E_draw_J': [positive / eta + p0 * duration for positive, duration in zip(columns['drive_positive_J'], columns['simulation_s'])],
                         'E_recover_J': [regen * absorbed for absorbed in columns['drive_absorbed_J']]}
                point['E_net_J'] = [draw - recover for draw, recover in zip(point['E_draw_J'], point['E_recover_J'])]
                boot = {'E_draw_J': [positive / eta + p0 * duration for positive, duration in zip(draws['drive_positive_J'], draws['simulation_s'])],
                        'E_recover_J': [regen * absorbed for absorbed in draws['drive_absorbed_J']]}
                boot['E_net_J'] = [draw - recover for draw, recover in zip(boot['E_draw_J'], boot['E_recover_J'])]
                for metric in point:
                    electrical.append({**context, 'eta_motor': eta, 'P0_W': p0, 'eta_regen': regen,
                                       'metric': metric, **describe(point[metric], boot[metric], analysis['confidence_level'])})
    representative = select_representative(rows, analysis)
    write_json(output / 'representative.json', representative)
    flat_rows, electrical_runs = [], []
    for row in rows:
        flat = {key: row[key] for key in ('dataset', 'policy', 'rate_per_hour', 'pattern', 'seed', 'state', 'comparable', 'reason')}
        if row['summary']:
            flat.update(row['summary'])
            flat.update(row['metrics'])
            flat['positive_J_per_useful_kg'] = row['summary']['drive_positive_J'] / row['summary']['delivered_useful_kg'] if row['summary']['delivered_useful_kg'] else None
            for eta, p0, regen in itertools.product(analysis['motor_efficiencies'], analysis['idle_powers_W'], analysis['regeneration_efficiencies']):
                electrical_runs.append({key: flat[key] for key in ('dataset', 'policy', 'rate_per_hour', 'pattern', 'seed', 'comparable')} | {'eta_motor': eta, 'P0_W': p0, 'eta_regen': regen} | electric_components(row['summary'], eta, p0, regen))
        flat_rows.append(flat)
    run_fields = ['dataset', 'policy', 'rate_per_hour', 'pattern', 'seed', 'state', 'comparable', 'reason'] + sorted({key for row in flat_rows for key in row} - {'dataset', 'policy', 'rate_per_hour', 'pattern', 'seed', 'state', 'comparable', 'reason'})
    write_csv(output / 'run_metrics.csv', flat_rows, run_fields)
    stats_fields = ['rate_per_hour', 'pattern', 'contrast', 'metric', 'planned_pairs', 'excluded_pairs', 'n', 'mean', 'median', 'ci95_low', 'ci95_high', 'minimum', 'maximum']
    write_csv(output / 'comparisons.csv', comparisons, stats_fields)
    write_csv(output / 'electrical_comparisons.csv', electrical, stats_fields[:4] + ['eta_motor', 'P0_W', 'eta_regen'] + stats_fields[4:])
    write_csv(output / 'electrical_runs.csv', electrical_runs, ['dataset', 'policy', 'rate_per_hour', 'pattern', 'seed', 'comparable', 'eta_motor', 'P0_W', 'eta_regen', 'E_draw_J', 'E_recover_J', 'E_net_J'])
    counts = Counter(row['state'] for row in rows)
    result = {'schema': 'agro-demand-analysis-v1', 'planned_runs': len(rows),
              'counts': {key: counts[key] for key in ('completed', 'failed', 'pending')},
              'comparable_runs': sum(row['comparable'] for row in rows),
              'noncomparable_completed_runs': sum(row['state'] == 'completed' and not row['comparable'] for row in rows),
              'all_runs_completed_comparable': all(row['comparable'] for row in rows),
              'failure_reasons': dict(Counter(row['reason'] for row in rows if row['reason'])),
              'bootstrap': {'replicates': analysis['bootstrap_replicates'], 'confidence_level': analysis['confidence_level'],
                            'method': 'paired seed resampling, percentile interval for the mean difference',
                            'key': 'SHA-256 of namespace, rate, pattern, contrast; deterministic'},
              'contrast_direction': 'first policy minus second; energy <0 favors first, punctuality >0 favors first',
              'factorial_interaction': '(D-C)-(B-A), only four-policy comparable seeds',
              'electrical_interpretation': {'classification': 'hypothetical estimate, not verified electricity or storage',
                  'scenarios': 18, 'E_draw_J': 'W_positive/eta_motor + P0*simulation_s',
                  'E_recover_J': 'eta_regen*W_absorbed', 'E_net_J': 'E_draw_J-E_recover_J, signed',
                  'P0': 'constant auxiliary power throughout the entire run, including drain/restoration',
                  'capacity_and_recovery_rate_constraints': 'not modeled'},
              'pair_exclusions': exclusions, 'representative': representative,
              'provenance': {'dataset_sha256': sha256(campaign / 'dataset.json'),
                             'campaign_sha256': sha256(campaign / 'campaign.json'),
                             'execution_sha256': sha256(campaign / 'execution.json'),
                             'analyzer_sha256': sha256(__file__)},
              'scope': 'synthetic paired operational simulation, no structural or safety certification'}
    write_json(output / 'analysis.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--campaign', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.campaign, args.output)
    print(json.dumps({key: result[key] for key in ('planned_runs', 'counts', 'comparable_runs', 'all_runs_completed_comparable')}))
    raise SystemExit(0 if result['all_runs_completed_comparable'] else 2)


if __name__ == '__main__':
    main()
