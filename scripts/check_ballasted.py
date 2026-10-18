#!/usr/bin/env python3
"""Assess sampled reduced telemetry; failures stay visible and never certify structure."""
import argparse
import csv
import json
from pathlib import Path
import numpy as np


def read(path):
    return np.genfromtxt(path, delimiter=',', names=True)


def assess(directory):
    out=Path(directory)
    m=json.loads((out/'generated/metadata.json').read_text())
    data=out/'gazebo' if (out/'gazebo/summary.json').exists() else out/'core'
    if not data.exists():
        data=out/'generated/gazebo'
    s=json.loads((data/'summary.json').read_text())
    carts=read(data/'carriers.csv');bases=read(data/'bases.csv');g=read(data/'global.csv')
    c=m['core'];spec=m['scenario'];failures=[]
    checks={'completed':s['status']=='completed','two_persistent_ids':set(carts['id'])=={0,1},
            'two_stations':s['unique_supports']==2,'full_loop':abs(s['final_q_m']-s['reference_loop_m'])<c['station_tolerance'],
            'no_local_motor_force':np.max(np.abs(carts['local_force_N']))==0,
            'nominal_indoor_calm':spec['gust'] or np.max(g['wind_m_s'])==0}
    checks={k:bool(v) for k,v in checks.items()}
    operations=[e for e in s['events'] if e['name'] in ('load_end','unload_end')]
    checks['both_carriers_serviced']=len(operations)==4 and {e['carrier'] for e in operations}=={0,1}
    checks['loading_line_stopped']=True
    for ident in (0,1):
        rows=carts[carts['id']==ident]
        changing=np.flatnonzero(abs(np.diff(rows['payload_kg']))>1e-8)+1
        for i in changing:
            j=np.argmin(abs(g['time_s']-rows['time_s'][i]))
            if abs(g['speed_m_s'][j])>=c['stop_speed']:
                checks['loading_line_stopped']=False
    stability=[]
    for ident in (0,1):
        rows=bases[bases['station']==ident]
        stability.append({'station':ident,'water_kg':float(rows['water_kg'][0]),'mass_kg':float(rows['total_mass_kg'][0]),
                          'minimum_sliding_margin':float(min(rows['sliding_margin'])),
                          'minimum_overturn_margin':float(min(rows['overturn_margin'])),
                          'normal_range_N':[float(min(rows['normal_N'])),float(max(rows['normal_N']))],
                          'maximum_mean_pressure_Pa':float(max(rows['mean_pressure_Pa'])),
                          'out_of_domain_samples':int(sum(rows['in_domain']==0))})
    # Conservative sampled basket envelopes: rotation-independent bounding sphere.
    # The steel rail at x=8 is NEVER removed to make the route fit.
    conflicts=[]
    if spec['scenario'].startswith('buitrago'):
        for ident in (0,1):
            rows=carts[carts['id']==ident]
            for level in (1,2):
                z=3.2*level
                mask=(abs(rows['pallet_x_m']-8)<.5)&(rows['pallet_z_m']-.5<z+1.08)&(rows['pallet_z_m']+.5>z)&(abs(rows['pallet_y_m'])<7.5)
                if np.any(mask):
                    conflicts.append({'object':f'corridor_rail_{level}','carrier':ident,'first_time_s':float(rows['time_s'][mask][0]),'samples':int(sum(mask)),
                                      'method':'conservative basket bounding sphere; candidate conflict, requires finer envelope review'})
        for station,(x,z) in enumerate(c['terrain']):
            bx=x+c.get('base_offset',0)*(1 if station else -1)
            height=c['support_height']+(.51 if c.get('base_offset',0) else .8)
            if bx+c['base_x']/2>=8 and z+height>=2.96 and z<2.96:
                conflicts.append({'object':'first_corridor_slab','station':station,'method':'station height/footprint envelope'})
            if bx>=8 and z+height>=6.16:
                conflicts.append({'object':'second_corridor_slab','station':station,'method':'station mast/tractor envelope'})
    if any(v['out_of_domain_samples'] for v in stability):failures.append('Fixed bases fail preliminary static force envelope during part of service')
    if conflicts:failures.append('Geometric conflicts require resolution; scene is not an accepted installation')
    result={'scenario':spec['scenario'],'core_checks':checks,'core_passed':all(checks.values()),'static_stability':stability,
            'geometric_conflicts':conflicts,'warnings':failures,'energy_residual_J':s['energy_residual_J'],
            'drive_positive_J':s['drive_positive_J'],'drive_absorbed_J':s['drive_absorbed_J'],
            'structural_floor_capacity':'unknown','native_base_dynamics':False,'continuous_collision_certification':False,
            'geometry_review':'partial: basket/rail and station/slab candidates only; cables, braces, bogie and site obstacles remain pending',
            'accepted':False}
    (out/'assessment.json').write_text(json.dumps(result,indent=2))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('directory');a=p.parse_args()
    print(json.dumps(assess(a.directory),indent=2))
