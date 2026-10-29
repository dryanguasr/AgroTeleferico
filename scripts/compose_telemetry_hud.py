#!/usr/bin/env python3
"""Compose a truthful offline HUD over synchronized live Gazebo camera videos.

No simulation is run. Every instrument uses a recorded sample at or before the
camera timestamp, never a future/interpolated value. Missing/stale data fail.
"""
import argparse
from bisect import bisect_right
import csv
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import subprocess

from PIL import Image, ImageDraw, ImageFont


TABLE_KEYS = {'global': (), 'carriers': ('id',), 'cables': ('lane', 'span'),
              'bases': ('station',), 'geometry': ('id',)}
WIDTH, HEIGHT = 1920, 1080
BG, PANEL, EDGE = '#09121e', '#111f30', '#24394d'
WHITE, MUTED, CYAN, AMBER = '#edf4fa', '#9db0c4', '#57d4e8', '#ffc580'
STAGES = {0: ('CARGA EN ESTACIONES', 'Preparar las dos cargas'),
          1: ('TRAYECTO CON CARGA', 'Alcanzar la estación opuesta'),
          2: ('DESCARGA EN PARADA', 'Retirar las cargas en las estaciones'),
          3: ('RETORNO', 'Completar la vuelta de los carros'),
          4: ('PARADA FINAL', 'Terminar el servicio programado')}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def camera_times(path):
    with Path(path).open() as stream:
        times = [float(row['simulation_s']) for row in csv.DictReader(stream)]
    if not times or any(not math.isfinite(t) for t in times):
        raise ValueError(f'Empty/nonfinite camera timestamps: {path}')
    if any(b <= a for a, b in zip(times, times[1:])):
        raise ValueError(f'Camera timestamps must increase strictly: {path}')
    return times


def require_synchronized_cameras(overview, follow):
    if overview != follow:
        raise ValueError('Camera timestamps differ; refusing unsynchronized PiP')
    if max((b-a for a, b in zip(overview, overview[1:])), default=0) > .201:
        raise ValueError('Camera frame gap exceeds nominal 0.2 simulation seconds')


class Timeline:
    def __init__(self, rows, keys=()):
        self.groups = {}
        previous = -math.inf
        for row in rows:
            row = {key: float(value) for key, value in row.items()}
            if not row or any(not math.isfinite(v) for v in row.values()):
                raise ValueError('Telemetry contains missing/nonfinite values')
            t = row['time_s']
            if t < previous:
                raise ValueError('Telemetry timestamps decrease')
            previous = t
            identity = tuple(row[key] for key in keys)
            group = self.groups.setdefault(t, {})
            # The logger can flush its final identical sample twice.
            if identity in group and group[identity] != row:
                raise ValueError('Conflicting telemetry rows at the same time')
            group[identity] = row
        self.times = sorted(self.groups)
        if not self.times:
            raise ValueError('Empty telemetry')

    def previous(self, stamp, max_lag=.051):
        index = bisect_right(self.times, stamp) - 1
        if index < 0:
            raise ValueError(f'No telemetry at or before camera time {stamp}')
        t = self.times[index]
        lag = stamp - t
        if lag > max_lag + 1e-9:
            raise ValueError(f'Stale telemetry: camera={stamp}, sample={t}, lag={lag}')
        return list(self.groups[t].values()), lag


def load_timeline(path, keys):
    with Path(path).open() as stream:
        return Timeline(list(csv.DictReader(stream)), keys)


def snapshot(timelines, stamp, max_lag=.051):
    values, lags = {}, {}
    for name, timeline in timelines.items():
        values[name], lags[name] = timeline.previous(stamp, max_lag)
    if len(values['global']) != 1:
        raise ValueError('Expected one global row')
    for name, key in [('carriers', 'id'), ('geometry', 'id'), ('bases', 'station')]:
        if {r[key] for r in values[name]} != {0., 1.}:
            raise ValueError(f'Expected two persistent identities in {name}')
    if {(r['lane'], r['span']) for r in values['cables']} != {(0., 0.), (1., 0.)}:
        raise ValueError('HUD requires the two-lane single-span cable model')
    return values, lags


def font(size, bold=False):
    filenames = (['/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
                  'C:/Windows/Fonts/arialbd.ttf'] if bold else
                 ['/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
                  'C:/Windows/Fonts/arial.ttf'])
    for filename in filenames:
        if Path(filename).exists():
            return ImageFont.truetype(filename, size)
    raise FileNotFoundError('Install DejaVu Sans or provide Windows Arial fonts')


class Hud:
    def __init__(self, metadata, summary, follow_id, historical=False):
        self.metadata, self.summary, self.follow_id = metadata, summary, follow_id
        self.historical = historical
        self.fonts = {(s, bold): font(s, bold) for s in (16, 18, 20, 22, 24, 28, 34, 52)
                      for bold in (False, True)}

    def draw(self, overview, follow, stamp, values, lags):
        image = Image.new('RGB', (WIDTH, HEIGHT), BG)
        d = ImageDraw.Draw(image)
        def text(x, y, value, size=20, color=WHITE, bold=False):
            d.text((x, y), str(value), fill=color, font=self.fonts[size, bold])
        def panel(box):
            d.rounded_rectangle(box, radius=14, fill=PANEL, outline=EDGE, width=2)
        def line(x1, y1, x2, y2):
            d.line((x1, y1, x2, y2), fill=EDGE, width=2)
        g = values['global'][0]
        carts = sorted(values['carriers'], key=lambda r: r['id'])
        bases = sorted(values['bases'], key=lambda r: r['station'])
        total = self.summary['reference_loop_m']
        progress = min(1., max(0., g['q_m'] / total))
        stage, objective = STAGES[int(g['stage'])]
        scenario = self.metadata['scenario']['name'] if 'name' in self.metadata['scenario'] else self.metadata['scenario'].get('id', '')
        if not scenario:
            scenario = 'Ladera agrícola' if self.metadata['scenario'].get('gust') else 'Patio entre pisos'
        text(24, 18, 'AGROTELEFÉRICO', 34, CYAN, True)
        text(390, 31, str(scenario).replace('_', ' ').upper(), 20, MUTED)
        badge = 'PREVIA · FUENTE HISTÓRICA' if self.historical else 'SENSORES GAZEBO · HUD POSTERIOR'
        text(1328, 28, badge, 18, AMBER, True)
        text(24, 67, stage, 22, WHITE, True)
        text(495, 69, 'OBJETIVO  /  ' + objective, 20, MUTED)
        text(1328, 67, f'T SIM  {stamp:07.2f} s', 24, WHITE, True)

        image.paste(overview, (24, 108))
        # Existing camera captions occupy these 68 px; replace the caption strip,
        # not unannotated scene pixels, at native overview resolution.
        d.rectangle((24, 108, 1303, 175), fill=PANEL)
        text(44, 118, '01  /  VISTA GENERAL', 20, CYAN, True)
        text(44, 147, 'Dos carros persistentes · un vano · bases fijas', 18, MUTED)
        text(1000, 126, f'VIENTO  {g["wind_m_s"]:.2f} m/s', 20, WHITE, True)
        d.rectangle((24, 108, 1303, 907), outline=EDGE, width=2)
        inset = follow.resize((400, 250), Image.Resampling.LANCZOS)
        image.paste(inset, (880, 632))
        d.rectangle((880, 632, 1279, 653), fill=PANEL)
        text(890, 633, f'02 / SEGUIMIENTO · CARRO {self.follow_id}', 16, CYAN, True)
        d.rectangle((879, 631, 1280, 883), outline=CYAN, width=2)

        panel((1328, 108, 1896, 1016))
        text(1352, 127, 'ESTADO DEL MODELO', 18, MUTED, True)
        text(1352, 157, f'{g["speed_m_s"]:.3f}', 52, WHITE, True)
        text(1560, 186, 'm/s', 22, CYAN)
        text(1716, 169, f'{100 * progress:.1f} %', 28, CYAN, True)
        text(1716, 205, 'de la vuelta', 16, MUTED)
        d.rounded_rectangle((1352, 238, 1872, 247), radius=4, fill=EDGE)
        progress_pixels = min(520, max(0, round(520 * progress)))
        if progress_pixels:
            # Pillow's rounded corners can invert a subpixel/narrow rectangle.
            d.rectangle((1352, 238, 1352 + progress_pixels - 1, 247), fill=CYAN)
        text(1352, 263, f'Avance {g["q_m"]:.2f} / {total:.2f} m', 18, MUTED)
        text(1352, 299, 'RUTA ESQUEMÁTICA · SIN ESCALA', 16, MUTED)
        left, right, top, bottom = 1420, 1804, 337, 395
        d.rounded_rectangle((left, top, right, bottom), radius=29, outline=EDGE, width=5)
        text(1355, 348, 'A', 22, MUTED, True)
        text(1832, 348, 'B', 22, MUTED, True)
        # Position is the recorded normalized route coordinate, no future path.
        for cart, color in zip(carts, (CYAN, AMBER)):
            u = (cart['reference_s_m'] % total) / total
            x = left + (right-left) * (2*u if u <= .5 else 2-2*u)
            y = top if u <= .5 else bottom
            d.ellipse((x-8, y-8, x+8, y+8), fill=color)
            text(x-5, y-25 if u <= .5 else y+9, int(cart['id']), 16, color, True)
        line(1352, 433, 1872, 433)
        for j, cart in enumerate(carts):
            x = 1352 + j * 268
            text(x, 447, f'CARRO {j} / CARGA', 16, CYAN if j == 0 else AMBER, True)
            text(x, 475, f'{cart["payload_kg"]:.2f} kg', 28, WHITE, True)
            text(x, 514, f'Balanceo X/Y  {math.degrees(cart["swing_x_rad"]):+.2f}°', 16, MUTED)
            text(x, 537, f'                         {math.degrees(cart["swing_y_rad"]):+.2f}°', 16, MUTED)
        line(1352, 571, 1872, 571)
        tension = max(row['max_tension_N'] for row in values['cables'])
        text(1352, 585, 'TENSIÓN MÁXIMA POR PORTANTE', 16, MUTED, True)
        text(1352, 611, f'{tension:.1f} N', 34, WHITE, True)
        limit = self.metadata['core']['max_tension']
        text(1352, 657, f'Límite conceptual del modelo: {limit:g} N', 16, AMBER)
        text(1352, 681, 'No representa capacidad admisible.', 16, MUTED)
        line(1352, 715, 1872, 715)
        for j, (label, key, unit) in enumerate((('FUERZA', 'force_N', 'N'),
                                               ('PAR', 'torque_Nm', 'N·m'),
                                               ('POTENCIA', 'power_W', 'W'))):
            x = 1352 + j * 180
            text(x, 731, label, 16, MUTED, True)
            text(x, 758, f'{g[key]:+.1f}', 28, WHITE, True)
            text(x, 798, unit, 18, CYAN)
        line(1352, 833, 1872, 833)
        text(1352, 848, 'BASES / CRIBADO ANALÍTICO', 18, AMBER, True)
        for j, base in enumerate(bases):
            x = 1352 + j * 268
            text(x, 882, f'BASE {"AB"[j]} · {base["litres"]:.0f} L', 16, MUTED)
            text(x, 910, f'Desliz.  {base["sliding_margin"]:.3f}', 20, WHITE)
            text(x, 940, f'Vuelco  {base["overturn_margin"]:.3f}', 20, WHITE)
        text(1352, 980, 'Bases fijas; estructura y suelo sin verificar.', 16, AMBER)

        panel((24, 924, 1304, 1016))
        energy = [('TRABAJO POSITIVO', 'drive_positive_J'), ('ABSORBIDO MECÁNICO', 'drive_absorbed_J'),
                  ('CARGA / DESCARGA', 'load_energy_J'), ('RESIDUO DEL BALANCE', 'residual_J')]
        for j, (label, key) in enumerate(energy):
            x = 44 + j * 320
            text(x, 936, label, 16, MUTED, True)
            text(x, 962, f'{g[key]:+.2f} J', 28, AMBER if key == 'residual_J' else WHITE, True)
        text(24, 1034, 'MODELO REDUCIDO · No certifica seguridad ni contacto físico · Absorbido ≠ electricidad almacenada', 18, MUTED)
        text(1390, 1034, f'Muestra previa ≤{1000*max(lags.values()):.0f} ms · nominal 4×', 18, CYAN)
        return image


def probe(path):
    result = subprocess.run(['ffprobe', '-v', 'error', '-threads', '2', '-count_frames',
                             '-select_streams', 'v:0', '-show_entries',
                             'stream=width,height,nb_read_frames,r_frame_rate,duration',
                             '-of', 'json', str(path)], check=True, capture_output=True, text=True)
    if result.stderr.strip():
        raise RuntimeError(result.stderr)
    return json.loads(result.stdout)['streams'][0]


def decode_strict(path):
    result = subprocess.run(['ffmpeg', '-v', 'error', '-xerror', '-err_detect', 'explode',
                             '-threads', '2', '-i', str(path), '-f', 'null', '-'],
                            capture_output=True, text=True)
    if result.returncode or result.stderr.strip():
        raise RuntimeError(f'Decode failed: {path}: {result.stderr}')


def decoder_command(capture, frame=None):
    graph = '[0:v][1:v]hstack=inputs=2'
    if frame is not None:
        graph += f',select=eq(n\\,{frame})'
    command = ['ffmpeg', '-v', 'error', '-xerror', '-err_detect', 'explode', '-threads', '2',
               '-i', str(capture/'gazebo.mp4'), '-threads', '2', '-i', str(capture/'follow.mp4'),
               '-filter_complex_threads', '1', '-filter_complex', graph]
    if frame is not None:
        command += ['-frames:v', '1']
    return command + ['-fps_mode', 'passthrough', '-threads', '2', '-pix_fmt', 'rgb24',
                      '-f', 'rawvideo', '-']


def read_exact(stream, count):
    chunks, remaining = [], count
    while remaining:
        data = stream.read(remaining)
        if not data:
            raise EOFError(f'Incomplete decoded frame ({remaining} bytes missing)')
        chunks.append(data)
        remaining -= len(data)
    return b''.join(chunks)


def stop_processes(processes):
    """Release pipe backpressure and reap every owned process without masking errors."""
    processes = [process for process in processes if process is not None]
    errors = []
    for process in processes:
        for name in ('stdout', 'stdin'):
            stream = getattr(process, name, None)
            if stream is not None:
                try:
                    stream.close()
                except Exception as exc:
                    errors.append(f'close {name}: {exc!r}')
    for process in processes:
        try:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        except Exception as exc:
            # Continue to the other process even if this one cannot be reaped.
            # The caller records these errors; the original rendering error wins.
            errors.append(f'cleanup pid={getattr(process, "pid", None)}: {exc!r}')
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='New output directory')
    parser.add_argument('--preview-frame', type=int, help='Only one design PNG; no video rendering')
    parser.add_argument('--historical-preview', action='store_true', help='Label historical design source explicitly')
    args = parser.parse_args()
    if args.historical_preview and args.preview_frame is None:
        parser.error('--historical-preview requires --preview-frame')
    capture, out = args.capture.resolve(), args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    audit = {'schema': 'agro-telemetry-hud-v1', 'passed': False, 'capture': str(capture),
             'historical_design_preview': args.historical_preview, 'simulation_started': False,
             'synchronization': 'exact camera timestamps; previous telemetry only; no interpolation',
             'max_allowed_telemetry_lag_s': .051, 'physical_validation': False}
    try:
        native = capture/'pilot/generated/gazebo'
        source_paths = [capture/name for name in ('gazebo.mp4', 'follow.mp4', 'capture.json',
                        'frame_times_overview.csv', 'frame_times_follow.csv')]
        source_paths += [native/(name+'.csv') for name in TABLE_KEYS]
        source_paths += [native/'summary.json', native.parent/'metadata.json']
        audit['source_sha256'] = {str(p): sha256(p) for p in source_paths}
        audit['composer_sha256'] = sha256(__file__)
        meta = json.loads((capture/'capture.json').read_text())
        if meta['view'] != 'overview' or meta['errors'] or meta['gazebo_exit_code'] != 0:
            raise ValueError('Require a cleanly stopped overview/follow capture')
        if not meta['live_gazebo_sensor'] or meta['replay'] or meta['video_speedup_nominal'] != 4:
            raise ValueError('Require live Gazebo sensor source at nominal 4x')
        times = camera_times(capture/'frame_times_overview.csv')
        require_synchronized_cameras(times, camera_times(capture/'frame_times_follow.csv'))
        videos = {name: probe(capture/name) for name in ('gazebo.mp4', 'follow.mp4')}
        for name, video in videos.items():
            if (video['width'], video['height']) != (1280, 800) or int(video['nb_read_frames']) != len(times):
                raise ValueError(f'Video dimensions/frame count mismatch: {name}')
        fps = videos['gazebo.mp4']['r_frame_rate']
        if Fraction(fps) != Fraction(videos['follow.mp4']['r_frame_rate']) or Fraction(fps) != 20:
            raise ValueError('Require synchronized 20 fps camera videos')
        timelines = {name: load_timeline(native/(name+'.csv'), keys) for name, keys in TABLE_KEYS.items()}
        metadata = json.loads((native.parent/'metadata.json').read_text())
        summary = json.loads((native/'summary.json').read_text())
        if metadata['core']['single_span'] != 1 or summary['carriers'] != 2:
            raise ValueError('HUD only supports the current single-span two-carrier model')
        if meta['follow_carrier'] not in (0, 1):
            raise ValueError('Missing/invalid followed carrier identity')
        hud = Hud(metadata, summary, meta['follow_carrier'], args.historical_preview)
        indices = [args.preview_frame] if args.preview_frame is not None else range(len(times))
        if any(i < 0 or i >= len(times) for i in indices):
            raise ValueError('Preview frame outside the recording')
        max_lags = {name: 0. for name in TABLE_KEYS}
        for i in indices:
            _, lags = snapshot(timelines, times[i])
            max_lags = {name: max(max_lags[name], lag) for name, lag in lags.items()}
        audit.update(input_videos=videos, input_frames=len(times), simulation_range_s=[times[0], times[-1]],
                     fps=fps, nominal_speedup=4, max_telemetry_lag_s=max_lags,
                     core_status=summary['status'], output_size=[WIDTH, HEIGHT],
                     matched_camera_timestamps=True, scene_changes=False,
                     caption_replacement='Existing 68 px overview caption strip; follow caption strip',
                     derived_signals={'progress': 'q_m/reference_loop_m',
                                      'swing_degrees': 'recorded swing_x/y_rad * 180/pi',
                                      'route_marker': 'recorded reference_s_m normalized; schematic only'})
        bytes_per_frame = 2560 * 800 * 3
        screenshots = []
        if args.preview_frame is not None:
            decoded = subprocess.run(decoder_command(capture, args.preview_frame), check=True, capture_output=True)
            if decoded.stderr or len(decoded.stdout) != bytes_per_frame:
                raise RuntimeError('Preview decoding failed or produced an incomplete frame')
            pair = Image.frombytes('RGB', (2560, 800), decoded.stdout)
            values, lags = snapshot(timelines, times[args.preview_frame])
            frame = hud.draw(pair.crop((0, 0, 1280, 800)), pair.crop((1280, 0, 2560, 800)),
                             times[args.preview_frame], values, lags)
            path = out/'design_preview.png'; frame.save(path); screenshots.append(path.name)
            audit['rendered_frame_indices'] = [args.preview_frame]
        else:
            for name in videos:
                decode_strict(capture/name)
            destination = out/'telemetry_hud.mp4'
            command = ['ffmpeg', '-n', '-v', 'error', '-f', 'rawvideo', '-pixel_format', 'rgb24',
                       '-video_size', f'{WIDTH}x{HEIGHT}', '-framerate', fps, '-i', '-',
                       '-an', '-c:v', 'libx264', '-threads', '2', '-preset', 'fast',
                       '-crf', '18', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(destination)]
            qa_indices = {0, len(times)//2, len(times)-1}
            with (out/'decode.log').open('wb') as decode_log, (out/'encode.log').open('wb') as encode_log:
                reader = subprocess.Popen(decoder_command(capture), stdout=subprocess.PIPE, stderr=decode_log)
                encoder = None
                try:
                    encoder = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=encode_log)
                    for i, stamp in enumerate(times):
                        pair = Image.frombytes('RGB', (2560, 800), read_exact(reader.stdout, bytes_per_frame))
                        values, lags = snapshot(timelines, stamp)
                        frame = hud.draw(pair.crop((0, 0, 1280, 800)), pair.crop((1280, 0, 2560, 800)), stamp, values, lags)
                        if i in qa_indices:
                            path = out/f'qa_{i:05d}.png'; frame.save(path); screenshots.append(path.name)
                        encoder.stdin.write(frame.tobytes())
                    if reader.stdout.read(1):
                        raise ValueError('More decoded frames than camera timestamps')
                    encoder.stdin.close()
                    if reader.wait(timeout=30) or encoder.wait(timeout=60):
                        raise RuntimeError('Decoder or encoder failed')
                finally:
                    cleanup_errors = stop_processes((reader, encoder))
                    if cleanup_errors:
                        audit['cleanup_errors'] = cleanup_errors
            if (out/'decode.log').stat().st_size or (out/'encode.log').stat().st_size:
                raise RuntimeError('FFmpeg reported decoding/encoding errors')
            output_video = probe(destination)
            decode_strict(destination)
            if int(output_video['nb_read_frames']) != len(times) or (output_video['width'], output_video['height']) != (WIDTH, HEIGHT):
                raise ValueError('Composed video failed frame/dimension verification')
            if abs(float(output_video['duration']) - len(times)/float(Fraction(fps))) > .001:
                raise ValueError('Composed video duration mismatch')
            audit.update(output_video=output_video, output_sha256=sha256(destination),
                         output_decode_strict=True, input_decode_strict=True)
        audit.update(passed=True, screenshots=screenshots)
    except Exception as exc:
        audit['error'] = repr(exc)
        raise
    finally:
        (out/'audit.json').write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(audit, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
