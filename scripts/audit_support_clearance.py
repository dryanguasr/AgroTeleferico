#!/usr/bin/env python3
"""Conservative sampled primitive audit; this is not a contact or structural solver."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np
from review_ballasted_geometry import pose,rotation,intersects


def primitives(model):
    for link in model.findall('link'):
        lc,lr=pose(link)
        for v in link.findall('visual'):
            vc,vr=pose(v)
            size=v.findtext('geometry/box/size')
            cylinder=v.find('geometry/cylinder')
            if size:h=np.array(list(map(float,size.split())))/2
            elif cylinder is not None:
                r=float(cylinder.findtext('radius'));h=np.array([r,r,float(cylinder.findtext('length'))/2])
            else:continue
            yield v.attrib['name'],lc+lr@vc,lr@vr,h


def audit(folder):
    folder=Path(folder);world=folder/'generated/world.sdf'
    models={m.attrib['name']:m for m in ET.parse(world).getroot().find('world').findall('model')}
    meta=json.loads((world.parent/'metadata.json').read_text());c=meta['core']
    building=[];equipment=[];tank_hits=[]
    for name,m in models.items():
        target=building if name.startswith(('rail_','corridor_','orange_band_','column_','roof_','translucent_')) else equipment if name.startswith(('ballasted_station_','brace_','main_motor_lower','drive_mount')) else None
        if target is None:continue
        mc,mr=pose(m)
        for vn,vc,vr,h in primitives(m):target.append((name+'/'+vn,mc+mr@vc,mr@vr,h))
    for a in equipment:
        if not a[0].endswith('/tank_shell'):continue
        prefix=a[0].split('/')[0]+'/'
        for b in equipment:
            if b[0]==a[0] or b[0].endswith('/water_level'):continue
            if intersects(*a[1:],*b[1:]):tank_hits.append([a[0],b[0]])
    static_hits=[];motor_hits=[]
    for a in equipment:
        if not a[0].startswith('main_motor_lower/'):continue
        for b in equipment:
            if b[0].startswith('ballasted_station_') and intersects(*a[1:],*b[1:]):motor_hits.append([a[0],b[0]])
    for a in equipment:
        for b in building:
            if intersects(*a[1:],*b[1:]):static_hits.append([a[0],b[0]])
    rows=np.genfromtxt(folder/'core/carriers.csv',delimiter=',',names=True)
    poses=np.genfromtxt(folder/'core/geometry.csv',delimiter=',',names=True)
    if len(rows)!=len(poses) or not np.all(rows['time_s']==poses['time_s']) or not np.all(rows['id']==poses['id']):raise ValueError('Pose/telemetry mismatch')
    obstacles=building+equipment;hits={};pairs=0
    cache={name:list(primitives(m)) for name,m in models.items() if name.startswith(('bogie_','pallet_','load_','coupler_'))}
    for row,p in zip(rows,poses):
        ident=int(row['id']);yaw=p['yaw_rad'];pitch=p['pitch_rad']
        pivot=np.array([row[f'pivot_{axis}_m'] for axis in 'xyz'])
        pallet=np.array([row[f'pallet_{axis}_m'] for axis in 'xyz'])
        coupling=np.array([p[f'coupling_{axis}_m'] for axis in 'xyz'])
        body=rotation(0,pitch,yaw)
        swing=rotation(0,-row['swing_x_rad'],0)@rotation(row['swing_y_rad'],0,0)@rotation(0,0,yaw)
        moving=[]
        for name,center,rot in [(f'bogie_{ident}',pivot+[0,0,.11],body),(f'pallet_{ident}',pallet,swing),(f'coupler_{ident}',coupling,body)]:
            moving.extend((name+'/'+vn,center+rot@vc,rot@vr,h) for vn,vc,vr,h in cache[name])
        for j in range(2):
            if row['payload_kg']<=c['nominal_payload']*(j+.15)/2:continue
            offset=np.array([.13 if j else -.13,0,.15]);name=f'load_{ident}_{j}'
            moving.extend((name+'/'+vn,pallet+swing@(offset+vc),swing@vr,h) for vn,vc,vr,h in cache[name])
        for name,a,b,r in [('hanger',pivot,pallet,.025),('traction_link',pivot+[0,0,.14],coupling,.025)]:
            d=b-a;length=np.linalg.norm(d)
            rot=rotation(0,math.acos(np.clip(d[2]/length,-1,1)),math.atan2(d[1],d[0]))
            moving.append((name,(a+b)/2,rot,np.array([r,r,length/2])))
        nearby=[o for o in obstacles if np.all(np.abs(pivot-o[1])<=np.abs(o[2])@o[3]+1.3)]
        for name,center,rot,h in moving:
            for on,oc,ori,oh in nearby:
                pairs+=1
                if intersects(center,rot,h,oc,ori,oh):
                    hit=hits.setdefault((ident,name,on),{'carrier':ident,'part':name,'obstacle':on,'first_s':float(row['time_s']),'last_s':float(row['time_s']),'samples':0})
                    hit['last_s']=float(row['time_s']);hit['samples']+=1
    result={'passed':not(static_hits or tank_hits or motor_hits or hits),'method':'15-axis SAT; cylinders conservatively enclosed by oriented boxes; exact logged body orientations',
            'motor_member_intersections':motor_hits,
            'static_building_intersections':static_hits,'tank_member_intersections':tank_hits,'moving_intersections':list(hits.values()),
            'pairs':pairs,'samples':len(rows),'sample_period_s':c['log_period'],
            'scope':'station boxes/braces/motor versus building; tank versus support members; bogies including wheels/flanges, couplers, baskets, payload, hangers and traction links versus building and equipment',
            'excluded':'wheel/guide contact, flexible cables and moving tractor/sheeve contacts, terrain/pad contact; connected structural joints deliberately overlap; not continuous collision or structural validation',
            'physical_validation':False,'world_sha256':hashlib.sha256(world.read_bytes()).hexdigest(),
            'telemetry_sha256':{n:hashlib.sha256((folder/'core'/n).read_bytes()).hexdigest() for n in ('carriers.csv','geometry.csv')}}
    target=folder/'support_clearance.json'
    if target.exists():raise FileExistsError(target)
    target.write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
    return result['passed']


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('folder');args=p.parse_args()
    raise SystemExit(0 if audit(args.folder) else 1)
