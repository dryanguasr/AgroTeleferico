#!/usr/bin/env python3
"""Verify a deliberately partial live capture and parity at its actual stop time."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

import yaml


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(root, binary, until):
    root = root.resolve()
    destination = root/'excerpt_verification.json'
    if destination.exists():
        raise FileExistsError(destination)
    capture = json.loads((root/'capture.json').read_text())
    world = root/'pilot/generated/world.sdf'
    native = root/'pilot/generated/gazebo'
    summary = json.loads((native/'summary.json').read_text())
    values = yaml.safe_load((root/'pilot/input.yaml').read_text())
    plugin = ET.parse(world).getroot().find("world/plugin[@name='agro::LoopSystem']")
    checks = {
        'clean_exit': capture['gazebo_exit_code'] == 0,
        'capture_without_errors': not capture['errors'],
        'stop_requested_and_acknowledged': capture['stop_requested'] and capture['stop_acknowledged'],
        'live_sensor': capture['live_gazebo_sensor'] and not capture['replay'],
        'intentional_partial_segment': summary['status'] == 'interrupted',
        'requested_coverage': summary['simulated_s'] >= until,
    }
    coverage, stamps_by_view = {}, {}
    for view in (capture['view'], 'follow'):
        with (root/f'frame_times_{view}.csv').open() as stream:
            times = [float(row['simulation_s']) for row in csv.DictReader(stream)]
        gaps = [b-a for a,b in zip(times,times[1:])]
        valid = bool(times) and all(math.isfinite(t) for t in times)
        checks['coverage_'+view] = valid and times[0] <= .3 and times[-1] >= until and all(0 < gap <= .41 for gap in gaps)
        stamps_by_view[view] = times
        coverage[view] = {'frames':len(times),'first_s':times[0] if times else None,
                          'last_s':times[-1] if times else None,'max_gap_s':max(gaps,default=0)}
    checks['cameras_synchronized'] = stamps_by_view[capture['view']] == stamps_by_view['follow']
    videos = {}
    for name,view in (('gazebo.mp4',capture['view']),('follow.mp4','follow')):
        path = root/name
        probe = subprocess.run(['ffprobe','-v','error','-select_streams','v:0','-count_frames',
                                '-show_entries','stream=width,height,nb_read_frames,r_frame_rate,duration',
                                '-of','json',str(path)],check=True,capture_output=True,text=True)
        stream = json.loads(probe.stdout)['streams'][0]
        decode = subprocess.run(['ffmpeg','-v','error','-xerror','-threads','2','-i',str(path),'-f','null','-'],
                                capture_output=True,text=True)
        checks['decode_'+name] = decode.returncode == 0 and not decode.stderr
        checks['frames_'+name] = int(stream['nb_read_frames']) == len(stamps_by_view[view])
        videos[name] = {'stream':stream,'sha256':digest(path),'decode_exit_code':decode.returncode,
                        'decode_stderr':decode.stderr}
    resources = [json.loads(line) for line in (root/'resources.jsonl').read_text().splitlines() if line]
    free = min(row['host_free_gib'] for row in resources)
    checks['reserve_preserved'] = free >= 4
    reference = root/'reference_core'
    command = [str(binary.resolve()),'--config',plugin.findtext('params'),'--output',str(reference),
               '--mode',plugin.findtext('mode'),'--until',str(summary['simulated_s']-values['dt']/2)]
    if plugin.findtext('gust') == 'false':
        command.append('--no-wind')
    result = subprocess.run(command,capture_output=True,text=True)
    (root/'reference_core.log').write_text(result.stdout+result.stderr)
    checks['reference_exit'] = result.returncode == 0
    parity = {}
    for name in ('global.csv','carriers.csv','cables.csv','bases.csv','geometry.csv'):
        same = (reference/name).exists() and (native/name).read_bytes() == (reference/name).read_bytes()
        checks['parity_'+name] = same
        parity[name] = {'identical':same,'native_sha256':digest(native/name),
                        'reference_sha256':digest(reference/name) if (reference/name).exists() else None}
    if result.returncode == 0:
        ref_summary = json.loads((reference/'summary.json').read_text())
        checks['same_stop_time'] = abs(ref_summary['simulated_s']-summary['simulated_s']) < 1e-9
        checks['same_events'] = ref_summary['events'] == summary['events']
    report = {'passed':all(checks.values()),'checks':checks,'requested_until_s':until,
              'actual_core_stop_s':summary['simulated_s'],'coverage':coverage,'videos':videos,'parity':parity,
              'reference_command':command,'min_host_free_gib':free,
              'peak_tree_rss_gib':max(row['tree_rss_gib'] for row in resources),
              'scope':'partial live rendering and same-core parity; not a complete service or physical validation'}
    destination.write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture',type=Path,required=True)
    parser.add_argument('--binary',type=Path,required=True)
    parser.add_argument('--until',type=float,required=True)
    args = parser.parse_args()
    raise SystemExit(0 if verify(args.capture,args.binary,args.until)['passed'] else 1)
