#!/usr/bin/env python3
"""Plot complete native CSV evidence without rerunning the simulation."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', type=Path, required=True, help='Guarded case directory')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--reference', type=Path, help='Complete central_gust case for RMS comparison')
    parser.add_argument('--calm', type=Path, help='Complete hybrid_calm case for wind comparison')
    args = parser.parse_args()
    guard = json.loads((args.case/'guard_summary.json').read_text())
    if not guard['passed'] or guard['exit_code'] != 0 or guard['stop_reason'] is not None:
        raise ValueError('A complete successful guarded service is required')
    source = args.case/'generated/gazebo'
    g = np.genfromtxt(source/'global.csv', names=True, delimiter=',')
    c = np.genfromtxt(source/'carriers.csv', names=True, delimiter=',')
    if not all(np.isfinite(a[k]).all() for a in (g, c) for k in a.dtype.names):
        raise ValueError('Nonfinite source data')
    args.output.mkdir(parents=True, exist_ok=False)
    fig, axes = plt.subplots(3, 2, figsize=(12, 10), sharex=True, constrained_layout=True)
    axes[0, 0].plot(g['time_s'], 1000*(g['q_m']-g['reference_m']))
    axes[0, 0].set_ylabel('Error longitudinal (mm)')
    for ident in sorted(set(c['id'])):
        rows = c[c['id'] == ident]
        axes[0, 1].plot(rows['time_s'], np.degrees(rows['swing_x_rad']), lw=.7, label=f'Carro {int(ident)}')
        axes[1, 0].plot(rows['time_s'], np.degrees(rows['swing_y_rad']), lw=.7)
    axes[0, 1].set_ylabel('Balanceo longitudinal (°)')
    axes[0, 1].legend(ncol=3, fontsize=7)
    axes[1, 0].set_ylabel('Balanceo transversal (°)')
    axes[1, 1].plot(g['time_s'], g['max_tension_N'])
    axes[1, 1].set_ylabel('Tensión máxima portantes (N)')
    axes[2, 0].plot(g['time_s'], g['force_N'])
    axes[2, 0].set_ylabel('Fuerza principal (N)')
    axes[2, 1].plot(g['time_s'], g['power_W'])
    axes[2, 1].set_ylabel('Potencia mecánica principal (W)')
    for ax in axes.flat:
        ax.grid(alpha=.25)
        ax.set_xlabel('Tiempo simulado (s)')
    fig.suptitle(args.case.name+' — Gazebo, modelo reducido; sin contacto rueda–cable')
    fig.savefig(args.output/'dynamics.png', dpi=150)
    fig.savefig(args.output/'dynamics.pdf')
    plt.close(fig)
    if args.reference or args.calm:
        if not (args.reference and args.calm):
            raise ValueError('Provide both --reference and --calm')
        datasets = {'Híbrido, ráfaga': c}
        for label, path in [('Central, ráfaga', args.reference), ('Híbrido, calma', args.calm)]:
            other = json.loads((path/'guard_summary.json').read_text())
            if not other['passed'] or other['exit_code'] != 0 or other['stop_reason'] is not None:
                raise ValueError('Comparisons require complete successful services')
            data = np.genfromtxt(path/'generated/gazebo/carriers.csv', names=True, delimiter=',')
            if not all(np.isfinite(data[k]).all() for k in data.dtype.names):
                raise ValueError('Nonfinite comparison data')
            if not np.array_equal(c['time_s'], data['time_s']) or not np.array_equal(c['id'], data['id']):
                raise ValueError('Comparison time/id rows must align exactly')
            datasets[label] = data
        fig, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)
        metrics = {}
        for ax, field, title in zip(axes[0], ('swing_x_rad', 'swing_y_rad'), ('RMS longitudinal', 'RMS transversal')):
            values = [float(np.degrees(np.sqrt(np.mean(d[field]**2)))) for d in datasets.values()]
            ax.bar(list(datasets), values, color=['#b55d26', '#31688e', '#4b8763'])
            ax.set_ylabel(title+' (°)')
            for i, value in enumerate(values):
                ax.annotate(f'{value:.4f}°', (i, value), ha='center', va='bottom')
            ax.margins(y=.15)
            metrics[field] = dict(zip(datasets, values))
        palette = ['#b55d26', '#31688e', '#4b8763']
        for (label, data), color in zip(datasets.items(), palette):
            times, inverse = np.unique(data['time_s'], return_inverse=True)
            envelope = np.zeros(len(times))
            np.maximum.at(envelope, inverse, np.abs(np.degrees(data['swing_y_rad'])))
            axes[1, 0].plot(times, envelope, label=label, color=color, lw=1)
        axes[1, 0].set_ylabel('Máximo |balanceo transversal|, 6 carros (°)')
        axes[1, 0].legend(fontsize=8)
        for (label, data), color in zip(datasets.items(), palette):
            selected = data[data['id'] == 0]
            axes[1, 1].plot(selected['time_s'], selected['payload_kg'], label=label, color=color)
        axes[1, 1].set_ylabel('Carga del carro 0 (kg)')
        for ax in axes[1]:
            ax.set_xlabel('Tiempo simulado (s)')
            ax.grid(alpha=.25)
        fig.suptitle('Comparación nativa — modelo reducido, sin ajuste de ganancias')
        fig.savefig(args.output/'comparison.png', dpi=150)
        fig.savefig(args.output/'comparison.pdf')
        plt.close(fig)
        metrics['sources'] = [str(p.resolve()) for p in (args.case, args.reference, args.calm)]
        (args.output/'comparison.json').write_text(json.dumps(metrics, indent=2))
    (args.output/'source.json').write_text(json.dumps({
        'case_directory': str(args.case.resolve()),
        'global_rows': len(g), 'carrier_rows': len(c),
        'scope': 'Complete recorded reduced-model dynamics; not physical validation or stored electrical energy.'
    }, indent=2))
    print(args.output/'dynamics.png')


if __name__ == '__main__':
    main()
