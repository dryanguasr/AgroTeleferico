#!/usr/bin/env python3
"""Reassess saved runs without rerunning simulation or erasing failed attempts."""
import argparse
import json
from pathlib import Path
from check_ballasted import assess,read
import numpy as np

p=argparse.ArgumentParser();p.add_argument('suite');a=p.parse_args();root=Path(a.suite)
reports={f.name:assess(f) for f in sorted(root.glob('0*')) if f.is_dir()}
names=list(reports)
normal=read(root/names[2]/'core/global.csv');fine=read(root/names[4]/'core/global.csv');calm=read(root/names[3]/'core/carriers.csv')
wind=read(root/names[2]/'core/carriers.csv')
qerr=float(np.max(abs(np.interp(normal['time_s'],fine['time_s'],fine['q_m'])-normal['q_m'])))
delta=float(np.max(abs(wind['swing_y_rad']-calm['swing_y_rad'])))
result={'reports':reports,'sensitivity':{'half_step_max_q_difference_m':qerr,'half_step_q_tolerance_m':.005,'passed':qerr<.005,
       'wind_changes_swing_max_rad':delta,'wind_response_detected':delta>1e-5},
       'note':'All inputs are preserved. Native Gazebo evidence and full collision review are separate.'}
(root/'reassessment.json').write_text(json.dumps(result,indent=2))
print(json.dumps({'core_checks':{k:v['core_passed'] for k,v in reports.items()},'sensitivity':result['sensitivity'],
                  'warnings':{k:v['warnings'] for k,v in reports.items()},'stability':{k:v['static_stability'] for k,v in reports.items()}},indent=2))
