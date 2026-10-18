#!/usr/bin/env python3
"""Check saved live capture coverage, decode, telemetry parity and memory evidence."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import subprocess

p=argparse.ArgumentParser();p.add_argument('capture');p.add_argument('--reference',required=True)
a=p.parse_args();root=Path(a.capture);reference=Path(a.reference)
meta=json.loads((root/'capture.json').read_text())
native=root/'pilot/generated/gazebo'
summary=json.loads((native/'summary.json').read_text())
checks={'gazebo_clean_exit':meta['gazebo_exit_code']==0,'no_capture_errors':not meta['errors'],
        'complete_core_cycle':summary['status']=='completed','live_sensor':meta['live_gazebo_sensor'] and not meta['replay']}
coverage={}
for f in sorted(root.glob('frame_times_*.csv')):
    rows=list(csv.DictReader(f.open()));times=[float(r['simulation_s']) for r in rows]
    gaps=[b-a for a,b in zip(times,times[1:])]
    name=f.stem.removeprefix('frame_times_')
    coverage[name]={'frames':len(times),'first_s':min(times) if times else None,'last_s':max(times) if times else None,
                    'max_gap_s':max(gaps,default=0)}
    checks['coverage_'+name]=bool(times) and times[0]<=.3 and times[-1]>=summary['duration_target_s'] and max(gaps,default=0)<=.41
videos={}
for filename in ('gazebo.mp4','follow.mp4'):
    path=root/filename
    if not path.exists():continue
    probe=subprocess.run(['ffprobe','-v','error','-count_frames','-select_streams','v:0','-show_entries',
                          'stream=width,height,nb_read_frames,r_frame_rate,duration','-of','json',str(path)],capture_output=True,text=True)
    decode=subprocess.run(['ffmpeg','-v','error','-i',str(path),'-f','null','-'],capture_output=True,text=True)
    stream=json.loads(probe.stdout)['streams'][0] if probe.returncode==0 else {}
    view=meta['view'] if filename=='gazebo.mp4' else 'follow'
    checks['decode_'+filename]=probe.returncode==0 and decode.returncode==0 and not decode.stderr
    checks['frames_'+filename]=int(stream.get('nb_read_frames',-1))==coverage.get(view,{}).get('frames')
    videos[filename]={'stream':stream,'decode_exit_code':decode.returncode,'decode_error':decode.stderr}
parity={}
for name in ('global.csv','carriers.csv','cables.csv','bases.csv','geometry.csv'):
    if name=='geometry.csv' and not (reference/name).exists():continue
    left=hashlib.sha256((native/name).read_bytes()).hexdigest();right=hashlib.sha256((reference/name).read_bytes()).hexdigest()
    parity[name]={'native_sha256':left,'reference_sha256':right,'identical':left==right}
    checks['parity_'+name]=left==right
resources=[json.loads(row) for row in (root/'resources.jsonl').read_text().splitlines() if row]
free=min(r['host_free_gib'] for r in resources);peak=max(r['tree_rss_gib'] for r in resources)
checks['reserve_preserved']=free>=4
result={'passed':all(checks.values()),'checks':checks,'coverage':coverage,'videos':videos,'parity':parity,
        'min_host_free_gib':free,'peak_tree_rss_gib':peak,'physical_validation':False,
        'visual_review_required':True,'known_geometry_conflicts_not_cleared':True}
target=root/'verification.json'
if target.exists():raise FileExistsError(target)
target.write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
raise SystemExit(0 if result['passed'] else 1)
