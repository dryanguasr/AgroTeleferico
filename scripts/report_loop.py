#!/usr/bin/env python3
"""Summarize existing loop-suite evidence; never substitutes for running tests."""
import argparse
import json
import math
from pathlib import Path


def report(summary_path, destination):
    data = json.loads(Path(summary_path).read_text(encoding='utf-8'))
    if not isinstance(data.get('cases'), dict):
        raise ValueError('Expected a run_loop_suite.py summary containing cases')
    lines = ['# Informe del circuito conceptual', '',
             f"Backend: `{data.get('backend', 'unknown')}`. Resultado de comprobaciones: **{data.get('passed', 'incomplete')}**.", '',
             'Esta evidencia corresponde al modelo reducido. No acredita contacto rueda–cable, validación física, seguridad constructiva ni almacenamiento eléctrico.', '',
             '| Caso | Estado | Tiempo simulado (s) | Balanceo máximo (grados) | Tensión máxima (N) | Residuo energético (J) |',
             '|---|---|---:|---:|---:|---:|']
    for name, c in data['cases'].items():
        if 'error' in c:
            lines.append(f"| {name} | FALLÓ: {str(c['error']).replace('|', '/')} | — | — | — | — |")
        else:
            lines.append(f"| {name} | {c.get('status', 'unknown')} | {c['simulated_s']:.3f} | {math.degrees(c['max_swing_rad']):.3f} | {c['peak_tension_N']:.2f} | {c['energy_residual_J']:.2f} |")
    lines += ['', '## Interpretación', '']
    a, b = data['cases'].get('hybrid_gust', {}), data['cases'].get('central_gust', {})
    if 'rms_swing_x_rad' in a and 'rms_swing_x_rad' in b:
        delta = 100*(a['rms_swing_x_rad']-b['rms_swing_x_rad'])/max(b['rms_swing_x_rad'], 1e-12)
        lines += [f"El RMS longitudinal híbrido cambia **{delta:+.2f}%** frente al central. Un cambio positivo significa MÁS balanceo; no se presupone superioridad híbrida.", '']
    if 'drive_positive_J' in a:
        lines += [f"Trabajo principal motriz: {a['drive_positive_J']:.2f} J; absorbido: {a['drive_absorbed_J']:.2f} J. Son integrales de potencia mecánica, no energía eléctrica almacenada.", '',
                  f"Intervenciones discretas acumuladas del gobernador/límites: {a['governor_or_stop_count']:.0f}. El contador depende del paso; no representa episodios independientes.", '']
    lines += ['## Comprobaciones comparativas', '', '```json', json.dumps(data.get('comparisons', {}), indent=2), '```', '',
              '## Pendientes', '',
              'Revisar el informe de entrega a Codex para compilación nativa, validación SDF, contacto visual, regresión del piloto y capturas. La diferencia energética del modelo incluye acoplamientos incompletos; no usarla para dimensionar una instalación real.', '']
    if data.get('execution_note'):
        lines += ['Nota de ejecución: '+data['execution_note'], '']
    out = Path(destination)
    if out.exists():
        raise FileExistsError(f'Refusing to overwrite {out}')
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text('\n'.join(lines), encoding='utf-8')
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--summary', required=True)
    p.add_argument('--output', required=True)
    a = p.parse_args()
    print(report(a.summary, a.output))


if __name__ == '__main__':
    main()
