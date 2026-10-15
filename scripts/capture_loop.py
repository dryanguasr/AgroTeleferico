#!/usr/bin/env python3
"""Capture live Gazebo rendering of the reduced loop, never a telemetry replay."""
import argparse
import ctypes as C
from functools import partial
import json
import os
from pathlib import Path
import signal
import subprocess
import threading
import time
import uuid
import xml.etree.ElementTree as ET

from PIL import Image
from ament_index_python.packages import get_package_prefix
from generate_loop import generate
from run_loop_guarded import read_host_memory, tree_rss


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
    parser.add_argument('--view', choices=['overview', 'lower', 'upper'], default='overview')
    parser.add_argument('--until', type=float, default=341)
    parser.add_argument('--timeout', type=float, default=900)
    parser.add_argument('--gui', action='store_true')
    parser.add_argument('--video', action='store_true')
    parser.add_argument('--all-views', action='store_true', help='Capture all three cameras in one live world; video uses --view')
    parser.add_argument('--host-memory', type=Path, help='Fresh Windows samples; admission 14 GiB with GUI or 10 GiB without; stops below 5 GiB')
    args = parser.parse_args()
    directory = Path(args.output).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    admission_gib = 14 if args.gui else 10
    if args.host_memory and read_host_memory(args.host_memory) < admission_gib:
        raise RuntimeError(f'Render admission requires {admission_gib} GiB host free memory')
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

    world = generate(args.config, directory/'generated', stop_at_end=False)
    tree = ET.parse(world)
    root = tree.getroot().find('world')
    poses = {'overview': '34 -43 30 0 .48 1.80',
             'lower': '-9 -12 11 0 .30 .92',
             'upper': '56 -12 14 0 .30 2.16'}
    root.append(ET.fromstring('<plugin filename="gz-sim-sensors-system" name="gz::sim::systems::Sensors"><render_engine>ogre2</render_engine></plugin>'))
    views = list(poses) if args.all_views else [args.view]
    for view in views:
        root.append(ET.fromstring(f'''<model name="inspection_camera_{view}"><static>true</static><pose>{poses[view]}</pose><link name="link"><sensor name="camera" type="camera"><always_on>true</always_on><update_rate>5</update_rate><topic>/agro_loop/inspection/{view}</topic><camera><horizontal_fov>1.15</horizontal_fov><image><width>1280</width><height>800</height><format>R8G8B8</format></image><clip><near>.1</near><far>150</far></clip></camera></sensor></link></model>'''))
    tree.write(world, encoding='unicode')
    done = threading.Event()
    node = Node()
    frames_by_view = {view: [] for view in views}
    frames, errors = frames_by_view[args.view], []
    encoder = None
    if args.video:
        encoder = subprocess.Popen(['ffmpeg', '-n', '-loglevel', 'error', '-f', 'rawvideo', '-pixel_format', 'rgb24', '-video_size', '1280x800', '-framerate', '20', '-i', '-', '-c:v', 'libx264', '-preset', 'fast', '-crf', '23', '-pix_fmt', 'yuv420p', str(directory/'gazebo.mp4')], stdin=subprocess.PIPE)
    checkpoints = [1, 4, 10, 60, 145, 150, 151, 153, 170, 180, 200, 212, 215, 218, 220, 228, 250, 300, 340]
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
            view_frames = frames_by_view[view]
            if not view_frames:
                print(f'First {view} frame after {time.monotonic()-started:.3f} wall seconds', flush=True)
            view_frames.append((stamp, time.monotonic()-started))
            if encoder and view == args.view:
                encoder.stdin.write(msg.data)
            for checkpoint in checkpoints:
                if stamp >= checkpoint and checkpoint not in saved_by_view[view]:
                    Image.frombytes('RGB', (msg.width, msg.height), msg.data).save(directory/f'{view}_{checkpoint:03d}s.png')
                    saved_by_view[view].add(checkpoint)
            if all(f and f[-1][0] >= args.until for f in frames_by_view.values()):
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
    returncode = None
    with (directory/'gazebo.log').open('w') as log, (directory/'gui.log').open('w') as gui_log, (directory/'resources.jsonl').open('w') as resources:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
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
                    ok, response = node.request('/server_control', ServerControl(stop=True), ServerControl, Boolean, 5000)
                    stop_acknowledged = bool(ok and response.data)
                    if not stop_acknowledged:
                        errors.append('Server stop was not acknowledged')
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
            if encoder:
                encoder.stdin.close()
                encoder.wait(timeout=30)
            (directory/'frame_times.csv').write_text('simulation_s,wall_s\n' + '\n'.join(f'{s},{w}' for s, w in frames) + '\n')
            coverage = {}
            for view, recorded in frames_by_view.items():
                (directory/f'frame_times_{view}.csv').write_text('simulation_s,wall_s\n'+'\n'.join(f'{s},{w}' for s,w in recorded)+'\n')
                coverage[view] = {'frames': len(recorded), 'last_simulation_s': recorded[-1][0] if recorded else None, 'checkpoints': sorted(saved_by_view[view])}
            (directory/'camera_coverage.json').write_text(json.dumps(coverage, indent=2))
            (directory/'capture.json').write_text(json.dumps({'command': command, 'view': args.view, 'live_gazebo_sensor': True, 'replay': False, 'video_speedup_nominal': 4, 'frames': len(frames), 'first_frame_wall_s': frames[0][1] if frames else None, 'last_simulation_s': frames[-1][0] if frames else None, 'gazebo_exit_code': returncode, 'gui_exit_code': gui.returncode if gui else None, 'stop_acknowledged': stop_acknowledged, 'errors': errors}, indent=2))
    if errors or any(not f or f[-1][0] < args.until for f in frames_by_view.values()) or returncode != 0 or (gui and gui.returncode != 0) or (encoder and encoder.returncode):
        raise RuntimeError('Capture incomplete; inspect capture.json and gazebo.log')
    print(f'Live capture saved to {directory}', flush=True)


if __name__ == '__main__':
    main()
