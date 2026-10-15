#!/usr/bin/env python3
"""Run and assess identical loop services. Gazebo checks are explicit, never inferred."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import numpy as np
import yaml
from generate_loop import generate, read_config


def assess(folder, config):
    summary = json.loads((folder/'summary.json').read_text())
    glob = np.genfromtxt(folder/'global.csv', delimiter=',', names=True)
    carts = np.genfromtxt(folder/'carriers.csv', delimiter=',', names=True)
    cables = np.genfromtxt(folder/'cables.csv', delimiter=',', names=True)
    checks = {}
    checks['completed'] = summary['status'] == 'completed' and abs(summary['simulated_s']-summary['duration_target_s']) < 1e-6
    checks['all_csv_finite'] = all(all(np.isfinite(a[k]).all() for k in a.dtype.names) for a in (glob, carts, cables))
    checks['ids_persist'] = set(carts['id']) == set(range(2*int(config['carriers_per_lane'])))
    checks['full_loop'] = abs(summary['final_q_m']-summary['reference_loop_m']) < config['station_tolerance']
    checks['initial_distribution'] = [int(sum(carts['lane'][:summary['carriers']] == i)) for i in (0,1)] == [config['carriers_per_lane']]*2
    checks['payload_service'] = summary['loaded_kg'] == summary['unloaded_kg'] == config['nominal_payload']
    checks['stroke_limit'] = summary['max_local_offset_m'] <= config['local_stroke']+1e-9
    checks['speed_limit'] = summary['max_local_speed_m_s'] <= config['local_speed']+1e-9
    checks['force_limit'] = summary['peak_local_force_N'] <= config['local_force_limit']+1e-9
    checks['main_force_limit'] = summary['peak_main_force_N'] <= config['main_force_limit']+1e-9
    checks['tension_domain'] = (cables['H_N'] > 0).all() and summary['peak_tension_N'] < config['max_tension']
    checks['clearance'] = summary['min_pallet_ground_clearance_m'] > config['min_clearance']
    checks['carrier_envelopes'] = summary['min_carrier_center_distance_m'] > 1.5
    checks['no_large_pose_jump'] = summary['max_step_pallet_displacement_m'] < .025
    checks['closed_loop_error'] = summary['max_reference_error_m'] < .01
    for field in ('swing_x_rad','swing_y_rad'):
        summary['rms_'+field] = float(np.sqrt(np.mean(carts[field]**2)))
    summary['peak_power_W'] = float(max(abs(glob['power_W'])))
    summary['governor_or_stop_carrier_seconds'] = summary['governor_or_stop_count']*config['dt']
    summary['checks'] = checks
    summary['passed'] = all(checks.values())
    # This reports a residual; it is NOT a certificate of energetic/model validity.
    summary['residual_over_positive_work'] = summary['energy_residual_J']/max(1,summary['drive_positive_J']+summary['local_positive_J'])
    return summary, carts


def compare_cases(results, traces):
    """Apply the same comparison gates to CLI, native, or collected services."""
    comparison = {}
    required = {'hybrid_gust', 'central_gust', 'hybrid_calm', 'hybrid_half_dt', 'hybrid_half_shape'}
    if set(results) != required or not all(r['passed'] for r in results.values()):
        return {'complete_suite': {'passed': False}}
    base = results['hybrid_gust']
    for name in ('hybrid_half_dt', 'hybrid_half_shape'):
        differences = {}
        for k, floor in [('rms_swing_x_rad', .001), ('rms_swing_y_rad', .001), ('peak_tension_N', 1)]:
            differences[k] = abs(results[name][k]-base[k])/max(abs(base[k]), floor)
        comparison[name] = {'relative_changes': differences, 'passed': max(differences.values()) < .05}
    a, b = traces['hybrid_gust'], traces['hybrid_calm']
    aligned = len(a) == len(b) and np.allclose(a['time_s'], b['time_s']) and np.array_equal(a['id'], b['id'])
    response = float(np.max(abs(a['swing_y_rad']-b['swing_y_rad']))) if aligned else 0
    comparison['wind_response'] = {'max_transverse_difference_rad': response, 'passed': aligned and response > .003}
    comparison['same_service'] = {'passed': all(r['loaded_kg'] == base['loaded_kg'] and r['unloaded_kg'] == base['unloaded_kg'] and abs(r['final_q_m']-base['final_q_m']) < .01 for r in results.values())}
    return comparison


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',default='config/loop.yaml')
    p.add_argument('--binary',help='Path to compiled agro_loop_cli')
    p.add_argument('--backend',choices=['standalone','gazebo'],default='standalone')
    p.add_argument('--plugin-dir',help='Gazebo plugin directory when using backend=gazebo')
    p.add_argument('--output',required=True)
    p.add_argument('--quick',action='store_true',help='Only the main central_local+gust run')
    p.add_argument('--timeout',type=float,default=900)
    args=p.parse_args()
    root=Path(args.output).resolve()
    if root.exists():
        raise FileExistsError(f'{root} already exists; preserve earlier evidence and use a new directory')
    root.mkdir(parents=True)
    config=read_config(args.config)
    if args.backend=='standalone' and (not args.binary or not Path(args.binary).is_file()):
        raise ValueError('A compiled --binary is required')
    if args.backend=='gazebo' and not shutil.which('gz'):
        raise RuntimeError('gz is not installed; Gazebo validation NOT executed')
    cases=[('hybrid_gust','central_local',True,1,1)]
    if not args.quick:
        cases += [('central_gust','central_only',True,1,1),('hybrid_calm','central_local',False,1,1),
                  ('hybrid_half_dt','central_local',True,.5,1),('hybrid_half_shape','central_local',True,1,.5)]
    results={};traces={}
    for name,mode,gust,dt_factor,shape_factor in cases:
        case=root/name;case.mkdir()
        c=dict(config);c['dt']*=dt_factor;c['shape_period']*=shape_factor
        cfg=case/'input.yaml';cfg.write_text(yaml.safe_dump(c,sort_keys=False))
        generated=case/'generated';world=generate(cfg,generated,mode,gust,True)
        if args.backend=='standalone':
            result=case/'core'
            cmd=[str(Path(args.binary).resolve()),'--config',str(generated/'loop.params'),'--output',str(result),'--mode',mode]
            if not gust:cmd.append('--no-wind')
        else:
            result=generated/'gazebo';cmd=['gz','sim','-s','-r',str(world)]
        env=os.environ.copy()
        if args.plugin_dir:
            env['GZ_SIM_SYSTEM_PLUGIN_PATH']=str(Path(args.plugin_dir).resolve())+os.pathsep+env.get('GZ_SIM_SYSTEM_PLUGIN_PATH','')
        if args.backend=='gazebo':env['GZ_PARTITION']='agro_loop_'+name+'_'+str(os.getpid())
        started=time.monotonic()
        try:
            with (case/'process.log').open('w') as log:
                run=subprocess.run(cmd,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=args.timeout,check=False)
            if run.returncode:
                raise RuntimeError(f'process returned {run.returncode}; see {case}/process.log')
            summary,trace=assess(result,c)
            summary['end_to_end_wall_s']=time.monotonic()-started
            results[name]=summary;traces[name]=trace
        except Exception as exc:
            results[name]={'passed':False,'error':str(exc)}
        (root/'summary.json').write_text(json.dumps({'backend':args.backend,'cases':results},indent=2))
        print(name, 'PASS' if results[name]['passed'] else 'FAIL',flush=True)
    comparison = {} if args.quick else compare_cases(results, traces)
    passed=all(r['passed'] for r in results.values()) and all(r['passed'] for r in comparison.values())
    output={'schema':'agro-loop-suite-v1','backend':args.backend,'passed':passed,'cases':results,'comparisons':comparison,
            'interpretation':'Numeric conceptual checks only. No inference of physical validation, stored electrical energy, or superiority of hybrid control.'}
    (root/'summary.json').write_text(json.dumps(output,indent=2))
    raise SystemExit(0 if passed else 1)


if __name__=='__main__':main()
