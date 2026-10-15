#!/usr/bin/env python3
"""Require complete services and compare every logged CLI/Gazebo state exactly."""
import argparse
import json
from pathlib import Path
import numpy as np
import yaml


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cli', type=Path, required=True)
    p.add_argument('--gazebo', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--case', action='append', choices=['hybrid_gust', 'central_gust', 'hybrid_calm', 'hybrid_half_dt', 'hybrid_half_shape'], help='Only assess explicitly selected services; omitted means all five')
    args = p.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    reports = {}
    for name in (args.case or ['hybrid_gust', 'central_gust', 'hybrid_calm', 'hybrid_half_dt', 'hybrid_half_shape']):
        left, right = args.cli/name, args.gazebo/name
        report = {}
        try:
            left_input = left/'input.yaml' if (left/'input.yaml').exists() else left/'generated/loop.yaml'
            right_input = right/'input.yaml' if (right/'input.yaml').exists() else right/'generated/loop.yaml'
            report['same_input'] = yaml.safe_load(left_input.read_text()) == yaml.safe_load(right_input.read_text())
            a = json.loads((left/'core/summary.json').read_text())
            b = json.loads((right/'generated/gazebo/summary.json').read_text())
            report['complete_services'] = all(s['status'] == 'completed' and abs(s['simulated_s']-s['duration_target_s']) < 1e-6 for s in (a,b))
            report['same_events'] = a['events'] == b['events']
            report['same_mode_and_wind'] = (a['mode'],a['gust_enabled']) == (b['mode'],b['gust_enabled'])
            report['files'] = {}
            for filename in ('global.csv', 'carriers.csv', 'cables.csv'):
                x = np.genfromtxt(left/'core'/filename, delimiter=',', names=True)
                y = np.genfromtxt(right/'generated/gazebo'/filename, delimiter=',', names=True)
                same_schema = x.dtype.names == y.dtype.names and x.shape == y.shape
                differences = {k: float(np.max(np.abs(x[k]-y[k]))) for k in x.dtype.names} if same_schema else {}
                report['files'][filename] = {'same_schema_and_rows': same_schema, 'rows_cli': x.size, 'rows_gazebo': y.size, 'max_absolute_difference': differences,
                    'exactly_equal': same_schema and bool(x.size > 1) and all(np.isfinite(x[k]).all() and np.isfinite(y[k]).all() and np.array_equal(x[k],y[k]) for k in x.dtype.names)}
            report['passed'] = all(report[k] for k in ('same_input','complete_services','same_events','same_mode_and_wind')) and all(f['exactly_equal'] for f in report['files'].values())
        except Exception as exc:
            report.update(passed=False, error=repr(exc))
        reports[name] = report
    result = {'passed': all(r['passed'] for r in reports.values()), 'cases': reports,
              'scope': 'All logged states and events, at CSV precision; not proof of physical validity or correctness of rendered geometry.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2))
    print(json.dumps({k:v['passed'] for k,v in reports.items()}, indent=2))
    raise SystemExit(0 if result['passed'] else 1)


if __name__ == '__main__':
    main()
