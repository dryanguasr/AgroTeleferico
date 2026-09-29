#!/usr/bin/env python3
"""Ejecuta Gazebo real, registra métricas y falla si no se cumplen los criterios."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time
import numpy as np
import yaml
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from generate_world import generate


def metrics(csv):
    data = np.genfromtxt(csv, delimiter=',', names=True)
    if data.size < 2 or not all(np.isfinite(data[name]).all() for name in data.dtype.names):
        raise RuntimeError(f'Telemetría vacía o no finita: {csv}')
    steady = data[data['time'] >= 2]
    return data, {
        'duration_s': float(data['time'][-1]),
        'position_rms_m': float(np.sqrt(np.mean(steady['position_error']**2))),
        'orientation_rms_deg': float(np.rad2deg(np.sqrt(np.mean(steady['orientation_error']**2)))),
        'peak_tension_N': max(float(data[f'tension_{i}'].max()) for i in range(8)),
        'min_tension_N': min(float(data[f'tension_{i}'].min()) for i in range(8)),
        'roll_peak_deg': float(np.rad2deg(np.abs(data['roll']).max())),
        'infeasible_fraction': float(np.mean(data['feasible'] == 0)),
        'saturated_fraction': float(np.mean(data['saturated'] > 0)),
        'final_position_error_m': float(data['position_error'][-1]),
    }


def plots(data, destination, title):
    fig, axes = plt.subplots(3, 1, figsize=(10, 9), sharex=True)
    axes[0].plot(data['time'], data['position_error'], label='Error de posición [m]')
    axes[1].plot(data['time'], np.rad2deg(data['orientation_error']), label='Error angular [°]')
    for i in range(8):
        if data[f'tension_{i}'].max() > 0:
            axes[2].plot(data['time'], data[f'tension_{i}'], label=f'Cable {i}')
    for ax in axes:
        ax.grid(alpha=.3)
        ax.legend(loc='upper right', ncol=2)
    axes[2].set_ylabel('Tensión [N]')
    axes[2].set_xlabel('Tiempo simulado [s]')
    fig.suptitle(title)
    fig.tight_layout()
    fig.savefig(destination, dpi=140)
    plt.close(fig)


def run(config, scenario, directory):
    config = dict(config, render_cables=False, real_time_factor=0)  # Visual geometry has no physical role.
    directory.mkdir(parents=True, exist_ok=True)
    world = generate(config, scenario, directory/'world.sdf', directory/'telemetry.csv')
    iterations = round(config['duration']/config['dt'])+1
    env = dict(os.environ, GZ_PARTITION=f'agro_{os.getpid()}_{directory.name}')
    from ament_index_python.packages import get_package_prefix
    plugin_dir = Path(get_package_prefix('agro_teleferico'))/'lib'
    env['GZ_SIM_SYSTEM_PLUGIN_PATH'] = str(plugin_dir)+':'+env.get('GZ_SIM_SYSTEM_PLUGIN_PATH', '')
    start = time.monotonic()
    with (directory/'gazebo.log').open('w') as log:
        subprocess.run(['gz', 'sim', '-s', '-r', '--iterations', str(iterations), str(world)],
                       env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=600)
    wall = time.monotonic()-start
    data, result = metrics(directory/'telemetry.csv')
    result['wall_seconds'] = wall
    result['real_time_factor'] = result['duration_s']/wall
    result['config'] = config
    result['passed'] = (result['duration_s'] >= config['duration']-.05
                        and result['position_rms_m'] <= .1
                        and result['orientation_rms_deg'] <= 5
                        and result['min_tension_N'] >= 0
                        and result['final_position_error_m'] <= .1
                        and result['infeasible_fraction'] == 0)
    (directory/'metrics.json').write_text(json.dumps(result, indent=2))
    plots(data, directory/'metrics.png', f'{scenario} · carga {config["payload"]} kg · dt {config["dt"]} s')
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', default='config/pilot.yaml')
    p.add_argument('--output', default='results/suite')
    p.add_argument('--quick', action='store_true', help='Sólo carga nominal y paso nominal')
    p.add_argument('--scenario', choices=['single', 'double', 'spider'])
    p.add_argument('--duration', type=float)
    args = p.parse_args()
    config = yaml.safe_load(Path(args.config).read_text())
    if args.duration is not None:
        config['duration'] = args.duration
    root = Path(args.output).resolve()
    root.mkdir(parents=True, exist_ok=True)
    results, comparisons = {}, {}
    for scenario in ([args.scenario] if args.scenario else ['single', 'double', 'spider']):
        for payload in ([5] if args.quick else [0, 5, 10]):
            for scale in ([1] if args.quick else [1, .5]):
                c = dict(config, payload=payload, dt=config['dt']*scale)
                name = f'{scenario}_p{payload}_dt{c["dt"]}'
                print(f'Running {name}', flush=True)
                results[name] = run(c, scenario, root/name)
                print(json.dumps({k:v for k,v in results[name].items() if k != 'config'}), flush=True)
            if not args.quick:
                a = results[f'{scenario}_p{payload}_dt{config["dt"]}']
                b = results[f'{scenario}_p{payload}_dt{config["dt"]*.5}']
                # Floors explicitly avoid meaningless relative errors near zero.
                changes = {key: abs(a[key]-b[key])/max(abs(b[key]), floor)
                           for key, floor in [('position_rms_m', .001), ('orientation_rms_deg', .1), ('peak_tension_N', 1)]}
                comparisons[f'{scenario}_p{payload}'] = dict(changes, passed=all(v < .05 for v in changes.values()))
        if not args.quick:
            name = f'{scenario}_perturbation'
            results[name] = run(dict(config, payload=5, perturbation=True), scenario, root/name)
    report = {'runs': results, 'step_convergence': comparisons,
              'gazebo_version': subprocess.check_output(['gz', 'sim', '--versions'], text=True).strip(),
              'passed': all(r['passed'] for r in results.values()) and all(c['passed'] for c in comparisons.values())}
    (root/'summary.json').write_text(json.dumps(report, indent=2))
    if not report['passed']:
        raise SystemExit('Algún criterio no se cumple; revisar summary.json (los resultados no se ocultan).')


if __name__ == '__main__':
    main()
