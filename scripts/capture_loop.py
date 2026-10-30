#!/usr/bin/env python3
"""Capture live Gazebo rendering of the reduced loop, never a telemetry replay."""
import argparse
import hashlib
import ctypes as C
from functools import partial
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import threading
import time
import uuid
import xml.etree.ElementTree as ET

from PIL import Image,ImageDraw
from ament_index_python.packages import get_package_prefix
from generate_loop import generate
from supervision import read_host_memory, tree_rss
from validate_demand_native import demand_inputs, configure_demand_world, in_video_window, validate_window


def finish_encoder(process, label, errors):
    """Always reap this encoder; preserve a failure as evidence, not an orphan."""
    if process is None:
        return
    try:
        if process.stdin is not None and not process.stdin.closed:
            process.stdin.close()
        process.wait(timeout=30)
    except Exception as exc:
        errors.append(label + ' encoder cleanup: ' + repr(exc))
        for stop in (process.terminate, process.kill):
            if process.poll() is not None:
                break
            try:
                stop()
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                continue
            except Exception as cleanup_exc:
                errors.append(label + ' encoder reap: ' + repr(cleanup_exc))
    if process.returncode:
        errors.append(label + ' encoder exited ' + str(process.returncode))


def close_x11_windows(pid):
    """Request a normal Qt window close, scoped to this GUI's _NET_WM_PID."""
    x = C.CDLL('libX11.so.6')
    display, window, atom = C.c_void_p, C.c_ulong, C.c_ulong
    x.XOpenDisplay.argtypes = [C.c_char_p]
    x.XOpenDisplay.restype = display
    x.XDefaultRootWindow.argtypes = [display]
    x.XDefaultRootWindow.restype = window
    x.XInternAtom.argtypes = [display, C.c_char_p, C.c_int]
    x.XInternAtom.restype = atom
    x.XQueryTree.argtypes = [display, window, C.POINTER(window), C.POINTER(window), C.POINTER(C.POINTER(window)), C.POINTER(C.c_uint)]
    x.XGetWindowProperty.argtypes = [display, window, atom, C.c_long, C.c_long, C.c_int, atom, C.POINTER(atom), C.POINTER(C.c_int), C.POINTER(C.c_ulong), C.POINTER(C.c_ulong), C.POINTER(C.c_void_p)]
    x.XFree.argtypes = [C.c_void_p]
    x.XCloseDisplay.argtypes = [display]
    x.XFlush.argtypes = [display]

    class Data(C.Union):
        _fields_ = [('l', C.c_long*5), ('b', C.c_char*20)]

    class Message(C.Structure):
        _fields_ = [('type', C.c_int), ('serial', C.c_ulong), ('send_event', C.c_int), ('display', display), ('window', window), ('message_type', atom), ('format', C.c_int), ('data', Data)]

    class Event(C.Union):
        _fields_ = [('client', Message), ('pad', C.c_long*24)]

    x.XSendEvent.argtypes = [display, window, C.c_int, C.c_long, C.POINTER(Event)]
    d = x.XOpenDisplay(None)
    if not d:
        raise RuntimeError('Cannot open X11 display for controlled GUI close')
    count = 0
    try:
        pid_atom = x.XInternAtom(d, b'_NET_WM_PID', 0)
        pending = [x.XDefaultRootWindow(d)]
        while pending:
            w = pending.pop()
            actual, fmt, n, remaining, data = atom(), C.c_int(), C.c_ulong(), C.c_ulong(), C.c_void_p()
            x.XGetWindowProperty(d, w, pid_atom, 0, 1, 0, 0, C.byref(actual), C.byref(fmt), C.byref(n), C.byref(remaining), C.byref(data))
            owned = bool(data.value and fmt.value == 32 and n.value == 1 and C.cast(data, C.POINTER(C.c_ulong))[0] == pid)
            if data.value:
                x.XFree(data)
            if owned:
                event = Event()
                event.client = Message(33, 0, 1, d, w, x.XInternAtom(d, b'WM_PROTOCOLS', 0), 32, Data())
                event.client.data.l[0] = x.XInternAtom(d, b'WM_DELETE_WINDOW', 0)
                x.XSendEvent(d, w, 0, 0, C.byref(event))
                count += 1
            root, parent, children, size = window(), window(), C.POINTER(window)(), C.c_uint()
            if x.XQueryTree(d, w, C.byref(root), C.byref(parent), C.byref(children), C.byref(size)):
                pending.extend(children[i] for i in range(size.value))
                if children:
                    x.XFree(children)
        x.XFlush(d)
    finally:
        x.XCloseDisplay(d)
    return count


def main():
    # A background WSL launcher can inherit SIGINT ignored. Restore a handler
    # so exec children receive the normal default disposition.
    signal.signal(signal.SIGINT, signal.default_int_handler)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--config', default='config/loop.yaml')
    parser.add_argument('--scenario',choices=['buitrago_patio','buitrago_entre_pisos','ladera_agricola'])
    parser.add_argument('--variant',choices=['baseline','compact_candidate','revised_supports'],default='revised_supports')
    parser.add_argument('--view', choices=['overview', 'lower', 'upper'], default='overview')
    parser.add_argument('--until', type=float, default=341)
    parser.add_argument('--timeout', type=float, default=900)
    parser.add_argument('--gui', action='store_true')
    parser.add_argument('--video', action='store_true')
    parser.add_argument('--all-views', action='store_true', help='Capture all three cameras in one live world; video uses --view')
    parser.add_argument('--follow-carrier', type=int, help='Additional live camera following this carrier; records follow.mp4')
    parser.add_argument('--host-memory', type=Path, help='Fresh Windows samples; admission 14 GiB with GUI, 7.5 GiB for headless demand, otherwise 10 GiB; stops below 5 GiB')
    parser.add_argument('--demand', type=Path, help='Demand CSV; requires dispatch configuration, policy and predictor')
    parser.add_argument('--dispatch-config', type=Path)
    parser.add_argument('--policy', choices=list('ABCD'))
    parser.add_argument('--predictor', type=Path)
    parser.add_argument('--video-start', type=float, default=0, help='First included simulated timestamp')
    parser.add_argument('--video-end', type=float, help='Exclusive final timestamp; simulation still starts at zero')
    parser.add_argument('--real-time-factor', type=float, default=1., help='Requested wall-clock pacing; zero runs unthrottled')
    args = parser.parse_args()
    inputs = demand_inputs(args.demand, args.dispatch_config, args.policy, args.predictor)
    validate_window(args.video_start, args.video_end, args.until)
    if not math.isfinite(args.real_time_factor) or args.real_time_factor < 0:
        raise ValueError('--real-time-factor must be finite and nonnegative')
    if inputs and (args.scenario not in ('buitrago_patio', 'buitrago_entre_pisos') or args.variant != 'revised_supports'):
        raise ValueError('Demand capture requires the revised patio scene')
    if inputs and not args.host_memory:
        raise ValueError('Demand capture requires a fresh host memory feed')
    directory = Path(args.output).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    admission_gib = 14 if args.gui else (7.5 if inputs else 10)
    if args.host_memory and read_host_memory(args.host_memory) < admission_gib:
        raise RuntimeError(f'Render admission requires {admission_gib} GiB host free memory')
    if inputs:
        time.sleep(5)
        if read_host_memory(args.host_memory) < admission_gib:
            raise RuntimeError(f'Second render admission requires {admission_gib} GiB host free memory')
    gui_config = directory/'gui.config'
    if args.gui:
        template = Path(get_package_prefix('gz_sim_vendor'))/'opt/gz_sim_vendor/share/gz/gz-sim8/gui/gui.config'
        gui_config.write_text(template.read_text().replace('<dialog_on_exit>true</dialog_on_exit>', '<dialog_on_exit>false</dialog_on_exit>').replace('show_again="true"', 'show_again="false"'))
    os.environ['GZ_PARTITION'] = 'agro_loop_capture_' + uuid.uuid4().hex
    os.environ['GZ_SIM_SYSTEM_PLUGIN_PATH'] = str(Path(get_package_prefix('agro_teleferico'))/'lib') + os.pathsep + os.environ.get('GZ_SIM_SYSTEM_PLUGIN_PATH', '')
    from gz.transport13 import Node
    from gz.msgs10.image_pb2 import Image as ImageMessage
    from gz.msgs10.server_control_pb2 import ServerControl
    from gz.msgs10.boolean_pb2 import Boolean

    if args.scenario:
        from generate_ballasted import generate as generate_ballasted
        world=generate_ballasted(args.scenario,directory/'pilot',stop_at_end=False,variant=args.variant,
                                 calm=True if inputs else False)
    else:
        world = generate(args.config, directory/'generated', stop_at_end=False)
    configure_demand_world(world, inputs)
    tree = ET.parse(world)
    root = tree.getroot().find('world')
    root.find('physics/real_time_factor').text = str(args.real_time_factor)
    metadata_file = world.parent/'metadata.json'
    metadata = json.loads(metadata_file.read_text())
    metadata['requested_real_time_factor'] = args.real_time_factor
    metadata['demand_inputs'] = inputs
    metadata_file.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))
    poses = {'overview': '34 -43 30 0 .48 1.80',
             'lower': '-9 -12 11 0 .30 .92',
             'upper': '56 -12 14 0 .30 2.16'}
    if args.scenario:
        poses={'overview':'-7 -13 7 0 .28 .91','lower':'-4 -6 4 0 .20 .65','upper':'12 -8 5.5 0 .08 1.95'}
        if args.scenario=='ladera_agricola':poses['overview']='-7 -17 9 0 .3 .9'
    root.append(ET.fromstring('<plugin filename="gz-sim-sensors-system" name="gz::sim::systems::Sensors"><render_engine>ogre2</render_engine></plugin>'))
    views = list(poses) if args.all_views else [args.view]
    if args.follow_carrier is not None:
        if not 0 <= args.follow_carrier < (2 if args.scenario else 6):
            raise ValueError('Follow carrier must be in [0,5] for this six-carrier demo')
        views.append('follow')
        poses['follow'] = '3 -6 7 0 .3 2.2'
        plugin = root.find("plugin[@name='agro::LoopSystem']")
        ET.SubElement(plugin, 'follow_carrier').text = str(args.follow_carrier)
    for view in views:
        root.append(ET.fromstring(f'''<model name="inspection_camera_{view}"><static>true</static><pose>{poses[view]}</pose><link name="link"><sensor name="camera" type="camera"><always_on>true</always_on><update_rate>5</update_rate><topic>/agro_loop/inspection/{view}</topic><camera><horizontal_fov>1.15</horizontal_fov><image><width>1280</width><height>800</height><format>R8G8B8</format></image><clip><near>.1</near><far>150</far></clip></camera></sensor></link></model>'''))
    tree.write(world, encoding='unicode')
    plugin_file=Path(get_package_prefix('agro_teleferico'))/'lib/libAgroLoopSystem.so'
    (directory/'provenance.json').write_text(json.dumps({
        'captured_before_launch':True,'world_sha256':hashlib.sha256(world.read_bytes()).hexdigest(),
        'plugin_sha256':hashlib.sha256(plugin_file.read_bytes()).hexdigest(),
        'git_head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        'git_status':subprocess.check_output(['git','status','--short'],text=True),
        'sensor_images_with_caption':bool(args.scenario),
        'demand_inputs': inputs,
        'demand_input_sha256': {key:hashlib.sha256(Path(inputs[key]).read_bytes()).hexdigest()
                                for key in ('demand','dispatch_config','predictor')} if inputs else None,
        'recording_window_s': [args.video_start,args.video_end],
        'requested_real_time_factor': args.real_time_factor},indent=2))
    done = threading.Event()
    node = Node()
    frames_by_view = {view: [] for view in views}
    last_seen_by_view = {view: -1. for view in views}
    frames, errors = frames_by_view[args.view], []
    encoder = None
    follow_encoder = None
    if args.video:
        encoder = subprocess.Popen(['ffmpeg', '-n', '-loglevel', 'error', '-f', 'rawvideo', '-pixel_format', 'rgb24', '-video_size', '1280x800', '-framerate', '20', '-i', '-', '-c:v', 'libx264', '-threads', '2', '-preset', 'fast', '-crf', '23', '-pix_fmt', 'yuv420p', str(directory/'gazebo.mp4')], stdin=subprocess.PIPE)
        if args.follow_carrier is not None:
            try:
                follow_encoder = subprocess.Popen(['ffmpeg', '-n', '-loglevel', 'error', '-f', 'rawvideo', '-pixel_format', 'rgb24', '-video_size', '1280x800', '-framerate', '20', '-i', '-', '-c:v', 'libx264', '-threads', '2', '-preset', 'fast', '-crf', '23', '-pix_fmt', 'yuv420p', str(directory/'follow.mp4')], stdin=subprocess.PIPE)
            except BaseException:
                finish_encoder(encoder, 'Overview', errors)
                raise
    checkpoints = [1, 4, 10, 60, 145, 150, 151, 153, 170, 180, 200, 212, 215, 218, 220, 228, 250, 300, 340]
    if args.scenario:
        checkpoints=[1,4,10,30,50,60,70,90,110,130,150,170,190]
    if args.video_end is not None:
        checkpoints=[int(args.video_start),int((args.video_start+args.video_end)/2),int(args.video_end-1)]
    saved_by_view = {view: set() for view in views}
    started = time.monotonic()
    capture_lock = threading.Lock()

    def capture(view, msg):
        with capture_lock:
            capture_frame(view, msg)

    def capture_frame(view, msg):
        if done.is_set():
            return
        try:
            stamp = msg.header.stamp.sec + msg.header.stamp.nsec*1e-9
            last_seen_by_view[view] = stamp
            if not in_video_window(stamp, args.video_start, args.video_end):
                if all(last >= args.until-1e-7 for last in last_seen_by_view.values()):
                    done.set()
                return
            view_frames = frames_by_view[view]
            if not view_frames:
                print(f'First {view} frame after {time.monotonic()-started:.3f} wall seconds', flush=True)
            view_frames.append((stamp, time.monotonic()-started))
            pixels=msg.data
            if args.scenario:
                frame=Image.frombytes('RGB',(msg.width,msg.height),pixels)
                draw=ImageDraw.Draw(frame);draw.rectangle((0,0,msg.width,48),fill=(20,27,32))
                draw.text((10,6),f'{args.scenario} | t={stamp:.1f} s | 2 carros | 480 L / 480 kg de agua por base',fill='white')
                draw.text((10,25),'Modelo reducido - bases fijas - estabilidad analitica preliminar - capacidad de losa/suelo no verificada',fill=(255,210,120))
                if args.scenario=='buitrago_entre_pisos' or args.variant=='revised_supports':
                    draw.rectangle((0,48,msg.width,68),fill=(110,35,25))
                    warning='SOPORTES REVISADOS: geometria muestreada; estructura y medidas reales pendientes' if args.variant=='revised_supports' else 'VARIANTE COMPACTA: revision geometrica parcial; ubicacion conceptual no aceptada' if args.variant=='compact_candidate' else 'CONFLICTOS GEOMETRICOS: baranda y losa superior; ubicacion conceptual no aceptada'
                    draw.text((10,51),warning,fill='white')
                pixels=frame.tobytes()
            if encoder and view == args.view:
                encoder.stdin.write(pixels)
            if follow_encoder and view == 'follow':
                follow_encoder.stdin.write(pixels)
            for checkpoint in checkpoints:
                if stamp >= checkpoint and checkpoint not in saved_by_view[view]:
                    Image.frombytes('RGB', (msg.width, msg.height), pixels).save(directory/f'{view}_{checkpoint:03d}s.png')
                    saved_by_view[view].add(checkpoint)
            if all(last >= args.until-1e-7 for last in last_seen_by_view.values()):
                done.set()
        except Exception as exc:
            errors.append(repr(exc))
            done.set()

    for view in views:
        node.subscribe(ImageMessage, '/agro_loop/inspection/'+view, partial(capture, view))
    # Separate owners prevent the combined launcher from orphaning its server.
    command = ['gz', 'sim', '-s', '-r', '-v', '3', str(world)]
    gui = None
    stop_acknowledged = False
    stop_requested = False
    returncode = None
    with (directory/'gazebo.log').open('w') as log, (directory/'gui.log').open('w') as gui_log, (directory/'resources.jsonl').open('w') as resources:
        try:
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        except BaseException:
            finish_encoder(encoder, 'Overview', errors)
            finish_encoder(follow_encoder, 'Follow', errors)
            raise
        if args.gui:
            gui = subprocess.Popen(['gz', 'sim', '-g', '--gui-config', str(gui_config), '-v', '3'], stdout=gui_log, stderr=subprocess.STDOUT, start_new_session=True, env={**os.environ, 'QT_QPA_PLATFORM': 'xcb'})
        (directory/'process.json').write_text(json.dumps({'pid': process.pid, 'gui_pid': gui.pid if gui else None, 'partition': os.environ['GZ_PARTITION'], 'command': command}))
        try:
            while not done.wait(.5):
                if args.host_memory:
                    try:
                        free = read_host_memory(args.host_memory)
                        rss, pids = tree_rss(os.getpid())
                        resources.write(json.dumps({'wall_s': time.monotonic()-started, 'host_free_gib': free, 'tree_rss_gib': rss, 'pids': pids})+'\n')
                        resources.flush()
                        if free < 5 or (directory.parent/'STOP_REQUESTED').exists():
                            raise RuntimeError('Preventive render stop: host reserve or explicit request')
                    except Exception as exc:
                        errors.append(repr(exc))
                        break
                if process.poll() is not None:
                    raise RuntimeError(f'Gazebo exited early: {process.returncode}')
                if time.monotonic()-started > args.timeout:
                    raise TimeoutError('No complete rendering; inspect gazebo.log')
        except Exception as exc:
            errors.append(repr(exc))
        finally:
            done.set()
            # Finish an in-flight write before closing the encoder pipe.
            with capture_lock:
                pass
            for view in views:
                node.unsubscribe('/agro_loop/inspection/'+view)
            if gui and gui.poll() is None:
                try:
                    if not close_x11_windows(gui.pid):
                        raise RuntimeError('No owned GUI window found')
                    gui.wait(timeout=30)
                except Exception as exc:
                    errors.append('GUI window close failed: '+repr(exc))
                    os.killpg(gui.pid, signal.SIGKILL)
                    gui.wait(timeout=5)
            if process.poll() is None:
                try:
                    stop_requested = True
                    ok, response = node.request('/server_control', ServerControl(stop=True), ServerControl, Boolean, 5000)
                    stop_acknowledged = bool(ok and response.data)
                except Exception as exc:
                    errors.append('Stop service failed: '+repr(exc))
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGINT)
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait(timeout=5)
            returncode = process.returncode
            finish_encoder(encoder, 'Overview', errors)
            finish_encoder(follow_encoder, 'Follow', errors)
            (directory/'frame_times.csv').write_text('simulation_s,wall_s\n' + '\n'.join(f'{s},{w}' for s, w in frames) + '\n')
            coverage = {}
            for view, recorded in frames_by_view.items():
                (directory/f'frame_times_{view}.csv').write_text('simulation_s,wall_s\n'+'\n'.join(f'{s},{w}' for s,w in recorded)+'\n')
                coverage[view] = {'frames': len(recorded), 'last_simulation_s': recorded[-1][0] if recorded else None, 'checkpoints': sorted(saved_by_view[view])}
            (directory/'camera_coverage.json').write_text(json.dumps(coverage, indent=2))
            (directory/'capture.json').write_text(json.dumps({'command': command, 'view': args.view, 'follow_carrier': args.follow_carrier, 'live_gazebo_sensor': True, 'replay': False, 'video_speedup_nominal': 4, 'frames': len(frames), 'first_frame_wall_s': frames[0][1] if frames else None, 'last_simulation_s': frames[-1][0] if frames else None, 'gazebo_exit_code': returncode, 'gui_exit_code': gui.returncode if gui else None, 'stop_requested': stop_requested, 'stop_acknowledged': stop_acknowledged, 'errors': errors, 'policy': args.policy, 'recording_window_s': [args.video_start,args.video_end], 'last_sensor_timestamp_s':last_seen_by_view, 'requested_real_time_factor':args.real_time_factor}, indent=2))
    if errors or any(not f for f in frames_by_view.values()) or any(last < args.until-1e-7 for last in last_seen_by_view.values()) or returncode != 0 or (gui and gui.returncode != 0) or (encoder and encoder.returncode):
        raise RuntimeError('Capture incomplete; inspect capture.json and gazebo.log')
    print(f'Live capture saved to {directory}', flush=True)


if __name__ == '__main__':
    main()
