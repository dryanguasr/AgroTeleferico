#!/usr/bin/env python3
"""Static primitive review of a SAVED world and sampled poses; no simulation or certification."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np


def rotation(r,p,y):
    cr,sr=math.cos(r),math.sin(r);cp,sp=math.cos(p),math.sin(p);cy,sy=math.cos(y),math.sin(y)
    rx=np.array([[1,0,0],[0,cr,-sr],[0,sr,cr]])
    ry=np.array([[cp,0,sp],[0,1,0],[-sp,0,cp]])
    rz=np.array([[cy,-sy,0],[sy,cy,0],[0,0,1]])
    return rz@ry@rx


def pose(node):
    value=list(map(float,node.findtext('pose','0 0 0 0 0 0').split()))
    return np.array(value[:3]),rotation(*value[3:])


def intersects(a,ra,ha,b,rb,hb):
    """Separating-axis test for two oriented boxes; touching is not penetration."""
    if np.any(np.abs(a-b)>np.abs(ra)@ha+np.abs(rb)@hb+1e-10):return False
    axes=[*ra.T,*rb.T,*[np.cross(x,y) for x in ra.T for y in rb.T]]
    for axis in axes:
        norm=np.linalg.norm(axis)
        if norm<1e-10:continue
        axis=axis/norm
        radius=np.abs(ra.T@axis)@ha+np.abs(rb.T@axis)@hb
        if abs((a-b)@axis)>=radius-1e-9:return False
    return True


def boxes(model):
    for link in model.findall('link'):
        lc,lr=pose(link)
        for v in link.findall('visual'):
            size=v.findtext('geometry/box/size')
            if size:
                vc,vr=pose(v)
                yield v.attrib['name'],lc+lr@vc,lr@vr,np.array(list(map(float,size.split())))/2


def review(world,telemetry,output,full_path=False):
    root=ET.parse(world).getroot().find('world')
    models={m.attrib['name']:m for m in root.findall('model')}
    obstacles=[]
    for name,m in models.items():
        if name.startswith(('rail_','corridor_')):
            mc,mr=pose(m)
            for vn,vc,vr,h in boxes(m):obstacles.append((name,mc+mr@vc,mr@vr,h))
    static=[]
    for name,m in models.items():
        if not name.startswith('ballasted_station_'):continue
        mc,mr=pose(m)
        for vn,vc,vr,h in boxes(m):
            center=mc+mr@vc;rot=mr@vr
            for on,oc,ori,oh in obstacles:
                if intersects(center,rot,h,oc,ori,oh):
                    hi=np.minimum(center+np.abs(rot)@h,oc+np.abs(ori)@oh)
                    lo=np.maximum(center-np.abs(rot)@h,oc-np.abs(ori)@oh)
                    static.append({'station':name,'primitive':vn,'obstacle':on,'world_z_interval_m':[float(lo[2]),float(hi[2])],
                                   'aabb_overlap_xyz_m':list(map(float,hi-lo)),
                                   'intersection':'confirmed between saved visual boxes'})
    if full_path:
        for name,m in models.items():
            if name.startswith('ballasted_station_'):
                mc,mr=pose(m)
                for vn,vc,vr,h in boxes(m):obstacles.append((name+'/'+vn,mc+mr@vc,mr@vr,h))
    metadata=json.loads((Path(world).parent/'metadata.json').read_text())
    X=metadata['core']['terrain'][-1][0]
    rows=np.genfromtxt(telemetry,delimiter=',',names=True)
    hits={};tested=0
    for row in rows:
        # Restrict orientation reconstruction to straight lanes at the rail crossing.
        # The palette quaternion in LoopSystem is Ry(-tx)*Rx(ty)*Rz(yaw).
        if not full_path and (row['lane'] not in (0,1) or abs(row['pallet_x_m']-8)>.8):continue
        ident=int(row['id']);yaw=0 if row['lane']==0 else math.pi
        if row['lane']<0:
            cx=X if row['lane']==-1 else 0
            yaw=math.atan2(row['pivot_x_m']-cx,-row['pivot_y_m'])
        rot=rotation(0,-row['swing_x_rad'],0)@rotation(row['swing_y_rad'],0,0)@rotation(0,0,yaw)
        center=np.array([row[f'pallet_{ax}_m'] for ax in 'xyz'])
        nearby=[o for o in obstacles if np.all(np.abs(center-o[1])<=np.abs(o[2])@o[3]+1.0)]
        for vn,vc,vr,h in boxes(models[f'pallet_{ident}']):
            for on,oc,ori,oh in nearby:
                tested+=1
                if intersects(center+rot@vc,rot@vr,h,oc,ori,oh):
                    key=(ident,vn,on)
                    hit=hits.setdefault(key,{'carrier':ident,'primitive':vn,'obstacle':on,'first_time_s':float(row['time_s']),
                                              'last_time_s':float(row['time_s']),'samples':0})
                    hit['last_time_s']=float(row['time_s']);hit['samples']+=1
        # Active boxes are located by the exact rendering offsets in LoopSystem.
        for j in range(2):
            if row['payload_kg']<=5*(j+.15)/2:continue
            offset=np.array([.13 if j else -.13,0,.15])
            for vn,vc,vr,h in boxes(models[f'load_{ident}_{j}']):
                for on,oc,ori,oh in nearby:
                    tested+=1
                    if intersects(center+rot@(offset+vc),rot@vr,h,oc,ori,oh):
                        key=(ident,f'load_{j}',on)
                        hit=hits.setdefault(key,{'carrier':ident,'primitive':f'load_{j}','obstacle':on,'first_time_s':float(row['time_s']),
                                                  'last_time_s':float(row['time_s']),'samples':0})
                        hit['last_time_s']=float(row['time_s']);hit['samples']+=1
    result={'method':'15-axis oriented box SAT on saved visual primitives; static station boxes plus sampled basket/load boxes',
            'moving_scope':'full route including returns against rail/slabs/station boxes' if full_path else 'straight-lane rail crossings',
            'world':str(world),'world_sha256':hashlib.sha256(Path(world).read_bytes()).hexdigest(),
            'telemetry':str(telemetry),'telemetry_sha256':hashlib.sha256(Path(telemetry).read_bytes()).hexdigest(),
            'static_intersections':static,'sampled_crossing_intersections':list(hits.values()),'box_pairs_tested':tested,
            'physical_validation':False,'continuous_collision_certification':False,
            'excluded':'bogie wheels, hanger, tractor/cables, braces and all other site obstacles; no structural capacity calculation'}
    target=Path(output)
    if target.exists():raise FileExistsError(target)
    target.write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--world',required=True);p.add_argument('--telemetry',required=True);p.add_argument('--output',required=True)
    p.add_argument('--full-path',action='store_true')
    a=p.parse_args();review(a.world,a.telemetry,a.output,a.full_path)
