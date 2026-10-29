#!/usr/bin/env python3
"""Compose demand-policy HUDs from actual Gazebo cameras and causal telemetry."""
import argparse
from fractions import Fraction
import json
import math
from pathlib import Path
import subprocess

from PIL import Image, ImageDraw
from compose_telemetry_hud import (TABLE_KEYS, WIDTH, HEIGHT, BG, PANEL, EDGE, WHITE,
                                  MUTED, CYAN, AMBER, font, sha256, camera_times,
                                  require_synchronized_cameras, load_timeline, snapshot,
                                  probe, decode_strict, decoder_command, read_exact,
                                  stop_processes)

POLICIES = {
    0: ('A', 'INMEDIATO', 'Sin buffers', 'A_inmediato.mp4'),
    1: ('B', 'COORDINADO', 'Espera ≤60 s · sin buffers', 'B_coordinado.mp4'),
    2: ('C', 'INMEDIATO + BUFFERS', 'Mercancía adelantable + contrapesos', 'C_inmediato_buffers.mp4'),
    3: ('D', 'COORDINADO + BUFFERS', 'Espera ≤60 s · ambos buffers', 'D_coordinado_buffers.mp4'),
}
PHASES = {0: 'SIN PEDIDOS LISTOS', 1: 'ESPERA COORDINADA', 2: 'CARGANDO',
          3: 'EN TRÁNSITO', 4: 'DESCARGANDO', 5: 'RESTITUYENDO INVENTARIOS',
          6: 'SERVICIO TERMINADO'}
DEMAND_FIELDS = {
    'time_s', 'policy', 'phase', 'queue_up', 'queue_down', 'slack_up_s', 'slack_down_s',
    'next_dispatch_s', 'operator_lower', 'operator_upper', 'useful_0_kg', 'useful_1_kg',
    'aux_0_kg', 'aux_1_kg', 'inventory_lower_kg', 'inventory_upper_kg',
    'early_lower_kg', 'early_upper_kg', 'delivered_orders', 'late_orders',
}


def validate_capture_times(times, start=600., end=1200.):
    expected = round((end - start) * 5)
    if len(times) != expected:
        raise ValueError(f'Expected {expected} camera frames in [{start},{end}); found {len(times)}')
    for index, stamp in enumerate(times):
        if abs(stamp - (start + index / 5)) > 1e-6:
            raise ValueError(f'Unexpected camera tick at {index}: {stamp}')


def demand_snapshot(timeline, stamp, policy):
    rows, lag = timeline.previous(stamp, .051)
    if len(rows) != 1:
        raise ValueError('Expected one demand state at each sample')
    row = rows[0]
    if not DEMAND_FIELDS.issubset(row):
        raise ValueError('Incomplete demand telemetry schema')
    if row['policy'] != policy or row['phase'] not in PHASES:
        raise ValueError('Demand policy/phase does not match the video')
    for key in ('queue_up', 'queue_down', 'delivered_orders', 'late_orders'):
        if row[key] < 0 or row[key] != int(row[key]):
            raise ValueError('Invalid demand event counter: ' + key)
    for key in ('operator_lower', 'operator_upper'):
        if row[key] not in (0, 1):
            raise ValueError('Invalid operator availability')
    for suffix in ('0', '1'):
        useful, aux = row['useful_' + suffix + '_kg'], row['aux_' + suffix + '_kg']
        if useful < -1e-8 or aux < -1e-8 or useful + aux > 10 + 1e-7:
            raise ValueError('Demand payload exceeds the experimental domain')
    return row, lag


def electrical_estimate_wh(positive_j, stamp):
    # A displayed reference scenario, not measured electricity or a battery model.
    return (positive_j / .85 + 5 * stamp) / 3600


def clock_label(seconds):
    minutes = int(seconds) // 60
    return f'{minutes:02d}:{seconds - 60 * minutes:05.2f}'


class DemandHud:
    def __init__(self, policy):
        self.policy = policy
        self.fonts = {(size, bold): font(size, bold)
                      for size in (16, 18, 20, 22, 24, 28, 34, 46, 52)
                      for bold in (False, True)}

    def draw(self, overview, follow, stamp, values, state, lags):
        image = Image.new('RGB', (WIDTH, HEIGHT), BG)
        draw = ImageDraw.Draw(image)

        def text(x, y, content, size=20, color=WHITE, bold=False):
            draw.text((x, y), str(content), font=self.fonts[size, bold], fill=color)

        def panel(box):
            draw.rounded_rectangle(box, radius=14, fill=PANEL, outline=EDGE, width=2)

        def line(y):
            draw.line((1352, y, 1872, y), fill=EDGE, width=2)

        letter, title, subtitle, _ = POLICIES[self.policy]
        global_row = values['global'][0]
        carts = sorted(values['carriers'], key=lambda row: row['id'])
        tension = max(row['max_tension_N'] for row in values['cables'])
        text(24, 18, f'{letter}  /  {title}', 34, CYAN, True)
        text(24, 65, subtitle, 20, MUTED)
        text(1328, 26, 'GAZEBO · HUD POSTERIOR · 4×', 20, AMBER, True)
        text(1328, 64, 'T SIM  ' + clock_label(stamp), 28, WHITE, True)

        # Preserve the native camera pixels below their original caption strip.
        image.paste(overview.crop((0, 68, 1280, 800)), (24, 177))
        draw.rectangle((24, 108, 1304, 176), fill=PANEL)
        draw.rectangle((24, 108, 1304, 908), outline=EDGE, width=2)
        text(44, 118, PHASES[int(state['phase'])], 22, CYAN, True)
        next_dispatch = state['next_dispatch_s']
        departure = ('Sin salida programada' if next_dispatch < 0
                     else f'Tope de espera {clock_label(next_dispatch)} · en {max(0., next_dispatch-stamp):.1f} s')
        text(44, 148, departure, 18, MUTED)
        text(880, 122, 'PATIO ENTRE PISOS', 22, MUTED, True)
        follow_image = follow.crop((0, 68, 1280, 800)).resize((400, 229), Image.Resampling.LANCZOS)
        image.paste(follow_image, (880, 654))
        draw.rectangle((880, 631, 1280, 654), fill=PANEL)
        draw.rectangle((880, 631, 1280, 883), outline=CYAN, width=2)
        text(890, 632, 'SEGUIMIENTO · CARRO 0', 16, CYAN, True)

        panel((1328, 108, 1896, 1016))
        text(1352, 126, 'PEDIDOS SOLICITADOS EN COLA', 18, MUTED, True)
        for station, label, key, slack_key, color in (
                (0, 'SUBIDA ↑', 'queue_up', 'slack_up_s', CYAN),
                (1, 'BAJADA ↓', 'queue_down', 'slack_down_s', AMBER)):
            x = 1352 + 268 * station
            text(x, 159, label, 18, color, True)
            text(x, 186, int(state[key]), 46, WHITE, True)
            slack = state[slack_key]
            slack_text = 'Sin pedidos' if state[key] == 0 else f'Plazo próximo {slack:+.0f} s'
            text(x, 241, slack_text, 16, AMBER if state[key] and slack < 0 else MUTED)
        text(1352, 277, f'ENTREGADOS  {int(state["delivered_orders"])}', 20, WHITE, True)
        text(1640, 277, f'TARDE  {int(state["late_orders"])}', 20, AMBER, True)
        line(315)
        text(1352, 329, 'ATENCIÓN DE OPERARIOS', 18, MUTED, True)
        for station, name, field in ((0, 'ABAJO', 'operator_lower'), (1, 'ARRIBA', 'operator_upper')):
            available = bool(state[field])
            x = 1352 + station * 268
            text(x, 360, name, 16, MUTED)
            text(x, 384, 'HABILITADA' if available else 'NO DISPONIBLE', 18,
                 CYAN if available else AMBER, True)
        line(422)
        for j, color in ((0, CYAN), (1, AMBER)):
            x = 1352 + j * 268
            text(x, 438, f'CARRO {j} · MÁX. 10 kg*', 16, color, True)
            text(x, 468, f'Útil   {state[f"useful_{j}_kg"]:.1f} kg', 24, WHITE, True)
            text(x, 503, f'Aux.  {state[f"aux_{j}_kg"]:.1f} kg', 24, color, True)
            swing = math.degrees(math.hypot(carts[j]['swing_x_rad'], carts[j]['swing_y_rad']))
            text(x, 539, f'Balanceo combinado {swing:.2f}°', 16, MUTED)
        line(575)
        text(1352, 591, 'INVENTARIOS EN ESTACIÓN', 18, MUTED, True)
        for station, name, suffix in ((0, 'ABAJO', 'lower'), (1, 'ARRIBA', 'upper')):
            x = 1352 + station * 268
            text(x, 624, name, 16, CYAN if station == 0 else AMBER, True)
            if self.policy in (0, 1):
                text(x, 650, 'Buffers deshabilitados', 18, MUTED)
                text(x, 682, 'No se usan en A/B', 16, MUTED)
            else:
                text(x, 650, f'Contrapesos {state[f"inventory_{suffix}_kg"]:.0f} kg', 20)
                text(x, 682, f'Adelantable {state[f"early_{suffix}_kg"]:.1f} kg', 20)
        inventory_note = ('Inventarios habilitados solo en C/D.' if self.policy in (0, 1)
                          else 'Los contrapesos deben volver a su origen.')
        text(1352, 718, inventory_note, 16, MUTED)
        line(749)
        text(1352, 766, 'VELOCIDAD DE LÍNEA', 16, MUTED, True)
        text(1352, 791, f'{global_row["speed_m_s"]:.3f}', 46, WHITE, True)
        text(1542, 817, 'm/s', 20, CYAN)
        text(1640, 766, 'TENSIÓN / PORTANTE', 16, MUTED, True)
        text(1640, 800, f'{tension:.0f} N', 34, WHITE, True)
        line(858)
        text(1352, 875, f'Potencia mecánica  {global_row["power_W"]:+.2f} W', 22, WHITE, True)
        text(1352, 916, '*Límite experimental, no capacidad certificada.', 16, AMBER)
        text(1352, 947, 'Imagen: sensores vivos. Datos: modelo reducido.', 16, MUTED)
        text(1352, 978, f'Muestra previa ≤{1000 * max(lags.values()):.0f} ms', 18, CYAN)

        panel((24, 924, 1304, 1016))
        energy = [('MOTOR POSITIVO', f'{global_row["drive_positive_J"]:.1f} J', WHITE),
                  ('ABSORBIDO MECÁNICO', f'{global_row["drive_absorbed_J"]:.1f} J', WHITE),
                  ('RESIDUO DEL BALANCE', f'{global_row["residual_J"]:+.2f} J', AMBER),
                  ('ELÉCTRICA HIPOTÉTICA', f'{electrical_estimate_wh(global_row["drive_positive_J"], stamp):.3f} Wh', AMBER)]
        for j, (label, value, color) in enumerate(energy):
            x = 44 + 320 * j
            text(x, 937, label, 16, MUTED, True)
            text(x, 965, value, 28, color, True)
        text(24, 1034, 'ACUMULADOS DESDE t=0 · Eléctrica: η=85 %, auxiliares=5 W, recuperación=0 % · Sin batería', 18, MUTED)
        text(1328, 1034, 'No certifica contacto, estructura ni seguridad.', 18, AMBER)
        return image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--preview-frame', type=int)
    args = parser.parse_args()
    capture, out = args.capture.resolve(), args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    audit = {'schema': 'agro-demand-hud-v1', 'passed': False, 'capture': str(capture),
             'synchronization': 'exact sensor ticks; causal previous telemetry; no interpolation',
             'physical_validation': False, 'simulation_started': False,
             'electrical_reference': {'hypothetical': True, 'efficiency': .85,
                                      'auxiliary_W': 5, 'recovery_fraction': 0, 'battery': False}}
    try:
        metadata = json.loads((capture/'capture.json').read_text())
        if metadata['errors'] or metadata['gazebo_exit_code'] != 0 or metadata['view'] != 'overview':
            raise ValueError('Require a cleanly stopped overview capture')
        if not metadata['live_gazebo_sensor'] or metadata['replay'] or metadata['follow_carrier'] != 0:
            raise ValueError('Require live cameras and follow carrier 0')
        if metadata['recording_window_s'] != [600., 1200.] or metadata['policy'] not in 'ABCD':
            raise ValueError('Require an approved demand policy in window [600,1200)')
        policy = 'ABCD'.index(metadata['policy'])
        native = capture/'pilot/generated/gazebo'
        times = camera_times(capture/'frame_times_overview.csv')
        require_synchronized_cameras(times, camera_times(capture/'frame_times_follow.csv'))
        validate_capture_times(times)
        videos = {name: probe(capture/name) for name in ('gazebo.mp4', 'follow.mp4')}
        for name, video in videos.items():
            if (video['width'], video['height']) != (1280, 800) or int(video['nb_read_frames']) != len(times):
                raise ValueError('Input camera dimensions/frame count mismatch: ' + name)
            if Fraction(video['r_frame_rate']) != 20:
                raise ValueError('Require 20 fps camera video')
        timelines = {name: load_timeline(native/(name+'.csv'), keys) for name, keys in TABLE_KEYS.items()}
        demand = load_timeline(native/'demand_status.csv', ())
        source_paths = [capture/name for name in ('capture.json', 'gazebo.mp4', 'follow.mp4',
                                                 'frame_times_overview.csv', 'frame_times_follow.csv')]
        source_paths += [native/(name+'.csv') for name in TABLE_KEYS]
        source_paths += [native/'demand_status.csv', native/'summary.json', native/'demand_summary.json',
                         native.parent/'metadata.json']
        audit['source_sha256'] = {str(path): sha256(path) for path in source_paths}
        audit['composer_sha256'] = sha256(__file__)
        audit['helper_sha256'] = sha256(Path(__file__).with_name('compose_telemetry_hud.py'))
        indices = [args.preview_frame] if args.preview_frame is not None else range(len(times))
        if any(index < 0 or index >= len(times) for index in indices):
            raise ValueError('Preview index outside camera recording')
        max_lags = {name: 0. for name in list(TABLE_KEYS)+['demand']}
        for index in indices:
            _, lags = snapshot(timelines, times[index])
            _, lags['demand'] = demand_snapshot(demand, times[index], policy)
            for name, lag in lags.items():
                max_lags[name] = max(max_lags[name], lag)
        hud = DemandHud(policy)
        audit.update(policy=metadata['policy'], input_frames=len(times), input_videos=videos,
                     simulation_range_s=[times[0], times[-1]], recording_window_s=[600, 1200],
                     max_telemetry_lag_s=max_lags, speedup=4, fps=20,
                     source_is_live_sensor=True, matched_camera_timestamps=True,
                     scene_changes=False, output_size=[WIDTH, HEIGHT])
        screenshots = []

        def render(pair_bytes, index):
            pair = Image.frombytes('RGB', (2560, 800), pair_bytes)
            values, lags = snapshot(timelines, times[index])
            state, lags['demand'] = demand_snapshot(demand, times[index], policy)
            return hud.draw(pair.crop((0, 0, 1280, 800)), pair.crop((1280, 0, 2560, 800)),
                            times[index], values, state, lags)

        byte_count = 2560 * 800 * 3
        if args.preview_frame is not None:
            decoded = subprocess.run(decoder_command(capture, args.preview_frame), check=True, capture_output=True)
            if decoded.stderr or len(decoded.stdout) != byte_count:
                raise RuntimeError('Preview decoding failed')
            render(decoded.stdout, args.preview_frame).save(out/'preview.png')
            screenshots.append('preview.png')
        else:
            for name in videos:
                decode_strict(capture/name)
            destination = out/POLICIES[policy][3]
            command = ['ffmpeg', '-n', '-v', 'error', '-f', 'rawvideo', '-pixel_format', 'rgb24',
                       '-video_size', f'{WIDTH}x{HEIGHT}', '-framerate', '20', '-i', '-', '-an',
                       '-c:v', 'libx264', '-threads', '2', '-preset', 'fast', '-crf', '18',
                       '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(destination)]
            with (out/'decode.log').open('wb') as decode_log, (out/'encode.log').open('wb') as encode_log:
                reader, encoder = None, None
                try:
                    reader = subprocess.Popen(decoder_command(capture), stdout=subprocess.PIPE, stderr=decode_log)
                    encoder = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=encode_log)
                    for index in range(len(times)):
                        frame = render(read_exact(reader.stdout, byte_count), index)
                        if index in (0, len(times)//2, len(times)-1):
                            name = f'qa_{index:05d}.png'
                            frame.save(out/name)
                            screenshots.append(name)
                        encoder.stdin.write(frame.tobytes())
                    if reader.stdout.read(1):
                        raise RuntimeError('Extra decoded frames')
                    encoder.stdin.close()
                    if reader.wait(timeout=30) or encoder.wait(timeout=60):
                        raise RuntimeError('Encoding/decoding failed')
                finally:
                    errors = stop_processes((reader, encoder))
                    if errors:
                        audit['cleanup_errors'] = errors
            if (out/'decode.log').stat().st_size or (out/'encode.log').stat().st_size:
                raise RuntimeError('FFmpeg emitted errors')
            result = probe(destination)
            decode_strict(destination)
            if int(result['nb_read_frames']) != 3000 or abs(float(result['duration'])-150) > .001:
                raise ValueError('Output must contain 3000 frames over 150 seconds')
            if (result['width'], result['height']) != (1920, 1080) or Fraction(result['r_frame_rate']) != 20:
                raise ValueError('Output is not 1080p/20fps')
            audit.update(output_video=result, output_file=destination.name,
                         output_sha256=sha256(destination), strict_decode=True)
        audit.update(passed=True, screenshots=screenshots)
    except BaseException as exc:
        audit['error'] = repr(exc)
        raise
    finally:
        (out/'audit.json').write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({'passed': audit['passed'], 'policy': audit['policy'], 'frames': audit['input_frames']}))


if __name__ == '__main__':
    main()
