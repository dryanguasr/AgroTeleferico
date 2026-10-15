#!/usr/bin/env python3
"""Consolidate five separately guarded native services, preserving original files."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

from generate_loop import read_config
from run_loop_suite import assess, compare_cases

CASES = ('hybrid_gust', 'central_gust', 'hybrid_calm', 'hybrid_half_dt', 'hybrid_half_shape')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--case', action='append', required=True, help='name=guarded case directory; repeat for all five')
    p.add_argument('--cli', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    paths = {}
    for item in args.case:
        name, value = item.split('=', 1)
        if name not in CASES or name in paths:
            raise ValueError('Unknown or duplicate case: '+name)
        paths[name] = Path(value).resolve()
    if set(paths) != set(CASES):
        raise ValueError('All five native services are required; partial results cannot pass')
    args.output.mkdir(parents=True, exist_ok=False)
    results, traces, guards, sources, parity = {}, {}, {}, {}, {}
    for name in CASES:
        case = paths[name]
        try:
            guard = json.loads((case/'guard_summary.json').read_text())
            supervisor = json.loads((case.parent/'supervisor.json').read_text(encoding='utf-8-sig'))
            if not guard['passed'] or guard['exit_code'] != 0 or guard['stop_reason'] is not None:
                raise ValueError('Guard did not finish successfully')
            if supervisor['exit_code'] != 0 or supervisor['monitoring_error'] is not None:
                raise ValueError('Windows supervisor did not finish successfully')
            config = case/'input.yaml'
            if not config.exists():
                config = case/'generated/loop.yaml'
            results[name], traces[name] = assess(case/'generated/gazebo', read_config(config))
            guards[name] = {k: guard[k] for k in ('peak_tree_rss_gib', 'min_host_free_gib', 'wall_s')}
            sources[name] = str(case)
            destination = args.output/(name+'_parity.json')
            run = subprocess.run([sys.executable, str(Path(__file__).with_name('compare_loop_backends.py')),
                                  '--cli', str(args.cli.resolve()), '--gazebo', str(case.parent),
                                  '--case', name, '--output', str(destination)], check=False)
            parity[name] = run.returncode == 0 and json.loads(destination.read_text())['passed']
            results[name]['passed'] = results[name]['passed'] and parity[name]
        except Exception as exc:
            results[name] = {'passed': False, 'error': repr(exc)}
    comparisons = compare_cases(results, traces)
    passed = all(r['passed'] for r in results.values()) and all(r['passed'] for r in comparisons.values())
    report = {'schema': 'agro-loop-suite-v1', 'backend': 'gazebo', 'passed': passed,
              'cases': results, 'comparisons': comparisons, 'resource_measurements': guards,
              'sources': sources, 'cli_parity': parity,
              'execution_note': 'Five separately guarded runs; all CSV files re-assessed and compared to CLI. Original evidence is preserved. Reduced dynamics do not establish physical validation.'}
    (args.output/'summary.json').write_text(json.dumps(report, indent=2))
    raise SystemExit(0 if passed else 1)


if __name__ == '__main__':
    main()
