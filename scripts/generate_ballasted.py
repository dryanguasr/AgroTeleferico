#!/usr/bin/env python3
"""One-span variant, sharing the live reduced core and Gazebo rendering pipeline."""
import argparse
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET
import yaml
from generate_loop import generate as generate_loop, model, visual, box, cylinder, segment

ROOT = Path(__file__).resolve().parents[1]
if not (ROOT/'config/ballasted_common.json').exists():
    from ament_index_python.packages import get_package_share_directory
    ROOT=Path(get_package_share_directory('agro_teleferico'))
SCENARIOS = ('buitrago_patio', 'buitrago_entre_pisos', 'ladera_agricola')
STEEL = '.35 .42 .46 1'


def config(scenario, fill=None, dt=None, calm=False, variant='revised_supports'):
    spec = json.loads((ROOT/'config'/f'{scenario}.json').read_text())
    if variant not in ('baseline','compact_candidate','revised_supports'):raise ValueError('Unknown equipment variant')
    if scenario=='buitrago_patio' and variant!='revised_supports':
        spec=json.loads((ROOT/'config/legacy/buitrago_patio.json').read_text())
    filename={'baseline':'ballasted_common.json','compact_candidate':'ballasted_compact_candidate.json','revised_supports':'ballasted_revised_supports.json'}[variant]
    common = json.loads((ROOT/'config'/filename).read_text(encoding='utf-8-sig'))
    spec.update(common.get('scenario_overrides',{}).get(scenario,{}))
    spec['equipment_variant']=variant
    core = yaml.safe_load((ROOT/'config/loop.yaml').read_text())
    core.update(common['core'])
    core['terrain'] = [[0, 0], [spec['span_horizontal_m'], spec['floor_rise_m']]]
    if dt is not None:
        core['dt'] = dt
    if fill is not None:
        if not math.isfinite(fill) or not 0 <= fill <= 1:
            raise ValueError('Fill fraction outside [0,1]')
        common['station']['fill_fraction'] = fill
    if calm:
        spec['gust'] = False
    b=common['station']
    core.update(ballast_litres=b['capacity_litres'],ballast_fill=b['fill_fraction'],station_dry_mass=b['dry_mass_kg'],
                base_x=b['footprint_x_m'],base_y=b['footprint_y_m'],soil_mu=b['friction_coefficient'],
                tractor_pretension=b['tractor_pretension_N'],tank_bottom=b['tank_bottom_m'],tank_height=b['tank_height_m'],dry_cg_z=b['dry_cg_z_m'])
    return core, common['station'], spec


def solid(name, pos, size, color):
    return model(name, ' '.join(map(str, (*pos, 0, 0, 0))), visual('surface', box(*size), color))


def atrium(decorations=True):
    """Identical assumed atrium for BOTH Buitrago cases. Photo stays private."""
    a = [solid('atrium_floor', (4, 0, -.12), (23, 15, .24), '.75 .73 .67 1')]
    # Corridor edge at x=8, width 5 m: room for upper base and return.
    for level in (1, 2):
        z = 3.2*level
        a.append(solid(f'corridor_{level}', (10.5, 0, z-.12), (5, 15, .24), '.68 .66 .61 1'))
        a.append(solid(f'orange_band_{level}', (8, 0, z-.32), (.16, 15, .4), '.65 .22 .09 1'))
        a.append(solid(f'rail_top_{level}', (8, 0, z+1.05), (.06, 15, .06), STEEL))
        for y in range(-7, 8):
            a.append(solid(f'rail_post_{level}_{y}', (8, y, z+.52), (.05, .05, 1.04), STEEL))
        for zoff in (.28, .55, .8):
            a.append(solid(f'rail_mid_{level}_{zoff}', (8, 0, z+zoff), (.025, 15, .025), STEEL))
    for x in (-6, 8, 13):
        for y in (-6.8, 6.8):
            a.append(solid(f'column_{x}_{y}', (x, y, 4.6), (.22, .22, 9.2), STEEL))
    # Roof has spaced translucent strips so overhead cameras retain visibility.
    for x in range(-6, 14, 2):
        a.append(solid(f'roof_beam_{x}', (x, 0, 9.2), (.09, 15, .16), STEEL))
    a.append(solid('translucent_roof', (3.5, 0, 9.3), (19, 15, .04), '.75 .86 .87 .12'))
    for i, x in enumerate((1.2, 6.8) if decorations else ()):
        y = -3.1
        a.append(model(f'planter_{i}', f'{x} {y} .35 0 0 0', visual('pot', cylinder(.38, .7), '.48 .46 .4 1')))
        a.append(model(f'palm_{i}', f'{x} {y} 1.2 0 0 0', visual('trunk', cylinder(.07, 1.2), '.34 .25 .13 1')))
        for k in range(8):
            ang=k*math.pi/4
            a.append(segment(f'leaf_{i}_{k}', (x,y,1.85), (x+.85*math.cos(ang),y+.85*math.sin(ang),1.55), .05, '.12 .32 .1 1'))
    for k in range(20 if decorations else 0):
        ang=k*math.pi/16
        a.append(solid(f'curved_stair_{k}', (-3+1.2*math.cos(ang),4+1.2*math.sin(ang),.08+k*.15), (.6,.5,.15), '.55 .52 .46 1'))
    return a


def stations(c, b):
    a=[]
    for end,(x,z) in enumerate(c['terrain']):
        h=c['support_height']
        offset=c.get('base_offset',0)*(1 if end else -1)
        bx=x+offset
        shapes=[visual('frame',box(b['footprint_x_m'],b['footprint_y_m'],.12),STEEL,'0 0 .18 0 0 0')]
        for sx in (-1,1):
            for sy in (-1,1):
                px=sx*(b['footprint_x_m']/2-.12);py=sy*(b['footprint_y_m']/2-.12)
                shapes += [visual(f'foot_{sx}_{sy}',box(.3,.3,.12),STEEL,f'{px} {py} .06 0 0 0'),
                           visual(f'retracted_wheel_{sx}_{sy}',cylinder(.10,.06),'.12 .12 .12 1',f'{px} {py} .36 1.5708 0 0')]
        # Central tank and mast leave both loaded carrier lanes outside the tank.
        depth=b['capacity_litres']/1000/(1.2*b['tank_height_m'])
        tankz=b['tank_bottom_m']+b['tank_height_m']/2
        shapes.append(visual('tank_shell',box(1.2,depth,b['tank_height_m']),'.65 .8 .85 .25',f'0 0 {tankz} 0 0 0'))
        if b.get('support_layout')=='external_posts':
            sign=1 if end else -1
            for tx in (-.4,.4):
                shapes.append(visual(f'tank_cradle_{tx}',box(.12,depth,.02),STEEL,f'{tx} 0 .25 0 0 0'))
            # Posts and bracing stay outside both straight lanes and the return.
            # Tank, vertical members and carriers have separate occupied volumes.
            for px in (-offset,sign*1.65-offset):
                for sy in (-1,1):
                    shapes.append(visual(f'post_{px}_{sy}',box(.12,.12,h+.51-.24),STEEL,f'{px} {sy*1.5} {(.24+h+.51)/2} 0 0 0'))
                hx=sign*.45-offset if px==-offset else px
                shapes.append(visual(f'header_{px}',box(.12,3.12,.10),STEEL,f'{hx} 0 {h+.45} 0 0 0'))
            for sy in (-1,1):
                shapes.append(visual(f'side_beam_{sy}',box(1.65,.12,.10),STEEL,f'{sign*.825-offset} {sy*1.5} {h+.45} 0 0 0'))
                # Outer-rail brackets stop before the hanger sweep. Their tops
                # meet the rail underside, below the wheel flanges.
                shapes.append(visual(f'rail_seat_{sy}',box(.06,.34,.04),STEEL,f'{sign*.55-offset} {sy*1.36} {h-.045} 0 0 0'))
                shapes.append(visual(f'rail_seat_drop_{sy}',box(.06,.06,.515),STEEL,f'{sign*.55-offset} {sy*1.5} {h+.1925} 0 0 0'))
            rear=sign*1.65-offset
            shapes.append(visual('rear_post',box(.10,.10,h+.4-.24),STEEL,f'{rear} 0 {(.24+h+.4)/2} 0 0 0'))
            shapes.append(visual('return_seat',box(.37,.08,.04),STEEL,f'{sign*1.465-offset} 0 {h-.045} 0 0 0'))
            for sx in (-1,1):
                for sy in (-1,1):
                    px=sx*(b['footprint_x_m']/2-.12);py=sy*(b['footprint_y_m']/2-.12)
                    shapes.append(visual(f'wheel_mount_{sx}_{sy}',box(.08,.08,.14),STEEL,f'{px} {py} .29 0 0 0'))
        elif offset:
            # Explicit projected head and side posts; dimensions remain assumptions.
            shapes.append(visual('head',box(.2,3.2,.12),STEEL,f'{-offset} 0 {h+.45} 0 0 0'))
            for sy in (-1,1):
                shapes += [visual(f'side_post_{sy}',box(.12,.12,h+.51),STEEL,f'0 {sy*1.5} {(h+.51)/2} 0 0 0'),
                           visual(f'projected_arm_{sy}',box(abs(offset),.16,.12),STEEL,f'{-offset/2} {sy*1.5} {h+.4} 0 0 0')]
        else:
            shapes += [visual('mast',box(.12,.12,h+.8),STEEL,f'0 0 {(h+.8)/2} 0 0 0'),
                       visual('head',box(.2,2.8,.12),STEEL,f'0 0 {h+.45} 0 0 0')]
        fill=b['fill_fraction']
        if fill>0:
            shapes.append(visual('water_level',box(1.18,depth*.96,fill*b['tank_height_m']),'.08 .43 .74 .85',f'0 0 {b["tank_bottom_m"]+fill*b["tank_height_m"]/2} 0 0 0'))
        a.append(model(f'ballasted_station_{end}_{b["capacity_litres"]*fill:g}L',f'{bx} 0 {z} 0 0 0',''.join(shapes)))
        for sy in (-1,1):
            if b.get('support_layout')=='external_posts':
                sign=1 if end else -1
                a.append(segment(f'brace_{end}_{sy}',(x,sy*1.5,z+.24),(x+sign*1.65,sy*1.5,z+h+.4),.035,STEEL))
            else:
                a.append(segment(f'brace_{end}_{sy}',(bx,sy*1.45,z+.2),(x,sy*1.5 if offset else 0,z+h+.35),.035,STEEL))
    return a


def generate(scenario, directory, fill=None, dt=None, calm=False, stop_at_end=True, descending_payload=None, variant='revised_supports'):
    c,b,spec=config(scenario,fill,dt,calm,variant)
    if descending_payload is not None:
        if not math.isfinite(descending_payload) or descending_payload<0:
            raise ValueError('Descending payload must be finite and nonnegative')
        c['descending_payload']=descending_payload
    out=Path(directory).resolve()
    out.mkdir(parents=True,exist_ok=False)
    inp=out/'input.yaml';inp.write_text(yaml.safe_dump(c,sort_keys=False))
    world=generate_loop(inp,out/'generated',mode='central_only',gust=spec['gust'],stop_at_end=stop_at_end,server_step=.02)
    tree=ET.parse(world);w=tree.getroot().find('world')
    # Headless completion uses simulation time without wall-clock throttling.
    # Sensor captures remain at real-time pacing to limit rendering pressure.
    w.find('physics/real_time_factor').text='0' if stop_at_end else '1'
    for m in list(w.findall('model')):
        n=m.attrib['name']
        if n.startswith(('terrain_', 'portal_', 'station_', 'tractor_')):
            w.remove(m)
        elif n.startswith('bogie_'):
            link=m.find('link')
            link.remove(link.find("visual[@name='local_motor']"))
            if c.get('base_offset',0):
                mast=link.find("visual[@name='traction_mast']")
                if mast is None:raise ValueError('Expected traction mast missing')
                link.remove(mast)
        elif n.startswith('pallet_') or n.startswith('load_'):
            # A miniature removable basket; masses are in the common core config.
            for size in m.findall('.//box/size'):
                size.text=' '.join(str(float(v)*.5) for v in size.text.split())
            for pose in m.findall('.//visual/pose'):
                vals=list(map(float,pose.text.split()));pose.text=' '.join(map(str,[v*.5 for v in vals[:3]]+vals[3:]))
    new=stations(c,b)
    if c.get('base_offset',0):
        for j in range(2):
            new.append(model(f'traction_link_{j}','0 0 -50 0 0 0',visual('link',cylinder(.025,c['tractor_lift']-.14),STEEL)))
        motor=w.find("model[@name='main_motor_lower']")
        if motor is not None:
            motor.find('pose').text=f"0 0 {c['support_height']+c['tractor_lift']+.25} 0 0 0"
            for size in motor.findall('.//box/size'):size.text='.5 .5 .3'
        rotor=w.find("model[@name='main_rotor']/pose")
        if rotor is not None:rotor.text=f"0 0 {c['support_height']+c['tractor_lift']} 0 0 0"
        if variant=='revised_supports':
            new.append(solid('drive_mount',(-.35,0,c['support_height']+.5),(.20,.20,.10),STEEL))
            new.append(model('drive_mount_shaft',f"0 0 {c['support_height']+.37} 0 0 0",visual('shaft',cylinder(.04,.06),STEEL)))
    if scenario.startswith('buitrago'):
        new+=atrium(decorations=variant!='revised_supports')
    else:
        # Single inclined ground plus explicit level end pads.
        X=spec['span_horizontal_m'];Z=spec['floor_rise_m'];angle=-math.atan2(Z,X)
        new.append(model('single_slope',f'{X/2} 0 {Z/2-.15} 0 {angle} 0',visual('soil',box(math.hypot(X,Z),10,.3),'.3 .39 .17 1')))
        for end,(x,z) in enumerate(c['terrain']):
            bx=x+c.get('base_offset',0)*(1 if end else -1)
            new.append(solid(f'level_pad_{end}',(bx,0,z-.16),(3.3,3.8,.32),'.45 .4 .25 1'))
        for x in range(2,11,2):
            for y in (-3,-2,2,3):
                new.append(solid(f'low_crop_{x}_{y}',(x,y,Z*x/X+.12),(.5,.5,.24),'.18 .36 .07 1'))
    L=2*math.hypot(spec['span_horizontal_m'],spec['floor_rise_m'])+2*math.pi*c['lane_half_width']
    for j in range(96):
        new.append(model(f'pilot_tractor_{j}','0 0 -50 0 0 0',visual('tractor',cylinder(.014,1.08*L/96),'.85 .35 .05 1')))
    for j in range(8):
        new.append(model(f'tractor_marker_{j}','0 0 -50 0 0 0',visual('motion_mark',box(.09,.06,.06),'.95 .85 .1 1')))
    for item in new:
        w.append(ET.fromstring(item))
    w.find('.//camera_pose').text='15 -18 8 0 .28 2.15'
    tree.write(world,encoding='unicode')
    metadata=json.loads((world.parent/'metadata.json').read_text())
    metadata.update(scenario=spec,station=b,core=c,unique_portals=0,stations=2,support_style='ballasted_fixed_analytic_screening',
                    carrier_style='small_passive_bogie_removable_basket',parameter_origin='all dimensions assumed, photo is not metrology',
                    atrium_shared_asset='generate_ballasted.atrium',native_contact_physics=False)
    metadata['static_visual_models']=len(w.findall('model'))
    metadata['requested_real_time_factor']=0 if stop_at_end else 1
    (world.parent/'metadata.json').write_text(json.dumps(metadata,indent=2,ensure_ascii=False))
    return world


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--scenario',choices=SCENARIOS,required=True);p.add_argument('--output',required=True)
    p.add_argument('--fill',type=float);p.add_argument('--dt',type=float);p.add_argument('--calm',action='store_true')
    p.add_argument('--descending-payload',type=float)
    p.add_argument('--variant',choices=('baseline','compact_candidate','revised_supports'),default='revised_supports')
    p.add_argument('--gui',action='store_true',help='Keep world open at completion; launch with gz sim -r')
    a=p.parse_args();print(generate(a.scenario,a.output,a.fill,a.dt,a.calm,not a.gui,a.descending_payload,a.variant))
