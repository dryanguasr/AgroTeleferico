#!/usr/bin/env python3
"""Consolida evidencia medida; no sustituye resultados fallidos por valores esperados."""
import json
from pathlib import Path
import shutil


def main():
    root=Path(__file__).resolve().parents[1]
    summary=json.loads((root/'results/suite/summary.json').read_text())
    clean=json.loads((root/'results/clean/summary.json').read_text()) if (root/'results/clean/summary.json').exists() else None
    assets=root/'docs/assets';assets.mkdir(parents=True,exist_ok=True)
    evidence=root/'docs/evidence';evidence.mkdir(parents=True,exist_ok=True)
    shutil.copy2(root/'results/suite/summary.json',evidence/'summary.json')
    if clean: shutil.copy2(root/'results/clean/summary.json',evidence/'clean-build.json')
    if (root/'results/saturation/summary.json').exists():
        shutil.copy2(root/'results/saturation/summary.json',evidence/'saturation.json')
    lines=['# Resultados del piloto','',
           'Ejecución local verificada en Ubuntu 24.04 / WSL, ROS 2 Jazzy y Gazebo Harmonic '+summary['gazebo_version']+'.',
           '',f'**Matriz de validación: {len(summary["runs"])} ensayos, resultado {"APROBADO" if summary["passed"] else "NO APROBADO"}.**',
           'Cada ensayo cubre 120 segundos simulados. Los valores siguientes corresponden a carga útil de 5 kg y paso de 1 ms.',
           '', '| Escenario | RMS posición [mm] | RMS angular [°] | Tensión máxima [N] |',
           '|---|---:|---:|---:|']
    for name in ['single','double','spider']:
        result=summary['runs'][name+'_p5_dt0.001']
        lines.append(f'| {name} | {1000*result["position_rms_m"]:.3f} | {result["orientation_rms_deg"]:.3f} | {result["peak_tension_N"]:.2f} |')
        screenshot=root/f'results/recorded/{name}/gazebo.png'
        if not screenshot.exists(): screenshot=root/f'results/visual/{name}/gazebo.png'
        if screenshot.exists(): shutil.copy2(screenshot,assets/f'{name}.png')
        shutil.copy2(root/f'results/suite/{name}_p5_dt0.001/metrics.png',assets/f'{name}_metrics.png')
    maximum=max(v for row in summary['step_convergence'].values() for key,v in row.items() if key!='passed')
    lines += ['',f'Máxima diferencia de las métricas al reducir el paso a 0,5 ms: **{100*maximum:.3f} %** (criterio <5 %; suelos de normalización definidos en el protocolo).',
              '', 'Los carros usan error longitudinal y la plataforma error 3D; sus RMS no son medidas intercambiables de capacidad de trabajo.',
              '', '## Verificaciones adicionales', '',
              '- Equilibrio y flecha analítica de catenaria; tensión unilateral; rango y factibilidad de las ocho cuerdas a lo largo del barrido, con tres masas.',
              '- ROS 2: recepción de telemetría, aceptación de objetivos y rechazo de objetivos fuera de dominio para carro y plataforma.',
              '- Dos ensayos degradados: baja adherencia y cabrestantes demasiado lentos. Ambos detectan saturación y pérdida de seguimiento; no se cuentan como ensayos nominales aprobados.',
              '- GUI de Gazebo abierta en WSLg y escenas inspeccionadas mediante una cámara del motor Ogre2.',
              '- Compilación independiente desde cero y repetición de los tres ensayos nominales: '+('APROBADA.' if clean and clean['passed'] else 'ver estado en la evidencia.'),
              '', '## Balanceo ante perturbación lateral', '', '| Escenario | Máximo roll [°] | RMS posición [mm] |', '|---|---:|---:|']
    for name in ['single','double','spider']:
        r=summary['runs'][name+'_perturbation']
        lines.append(f'| {name} | {r["roll_peak_deg"]:.3f} | {1000*r["position_rms_m"]:.3f} |')
    lines += ['', 'Fuerza de 20 N durante un segundo. La reducción de balanceo del doble portante refleja la rigidez lateral equivalente asumida; requiere identificación física antes de extrapolarse.',
              '', '## Escenas y gráficos']
    for name in ['single','double','spider']:
        lines += ['',f'### {name}', '',f'![Escena de Gazebo: {name}](assets/{name}.png)', '',f'![Métricas: {name}](assets/{name}_metrics.png)']
    lines += ['', '## Reproducibilidad y límites', '',
              'Los CSV, SDF, logs y videos se entregan como archivos generados; el repositorio conserva los resúmenes medidos en [evidence](evidence/summary.json). La suite de CI vuelve a producir los datos completos.',
              '', 'Para grabar la cámara de Gazebo: `python3 scripts/capture_scene.py --headless --video --scenario spider --output results/recorded/spider`. Requiere los bindings Python `gz.transport13`/`gz.msgs10`, Pillow, ffmpeg y un renderizador disponible. Los tiempos de cada fotograma se guardan en `frame_times.csv`.',
              '', 'Para reproducir la trayectoria medida en un gráfico: `python3 scripts/render_replay.py results/suite/spider_p5_dt0.001/telemetry.csv --scenario spider --output results/videos/spider.mp4`. Estos videos se rotulan como reproducción de telemetría, no como captura de GUI.',
              '', 'La catenaria de los carros es cuasiestática; la plataforma usa cables rectos sin masa y la inercia asumida. No se han validado tensiones ni motores contra hardware. Ver [modelo](modelo.md), [protocolo](validacion.md) y [referencias](referencias.md).',
              '', 'La compilación en el volumen compartido Windows/WSL produjo avisos de reloj del sistema de archivos; terminó correctamente y se repitió en un directorio de compilación vacío. Las advertencias de antialiasing del renderizador no impidieron generar las imágenes.']
    (root/'docs/resultados.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


if __name__=='__main__':
    main()
