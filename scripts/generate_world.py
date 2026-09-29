#!/usr/bin/env python3
"""Genera SDF autocontenido a partir de parámetros SI; no descarga modelos."""
import argparse
import math
from pathlib import Path
from xml.sax.saxutils import escape
import yaml


def validate(c):
    for key, value in c.items():
        if isinstance(value, (float, int)) and not math.isfinite(value):
            raise ValueError(f'{key} debe ser finito')
    positive = ['span', 'support_height', 'vehicle_mass', 'max_speed', 'dt',
                'duration', 'cable_mass_per_m', 'cable_EA', 'friction',
                'pendulum_length', 'spider_stiffness', 'winch_speed', 'track_separation']
    if any(not isinstance(c[k], (int, float)) or not math.isfinite(c[k]) or c[k] <= 0 for k in positive):
        raise ValueError('Los parámetros físicos positivos deben ser finitos y mayores que cero')
    if c['payload'] < 0 or not math.isfinite(c['payload']):
        raise ValueError('payload debe ser finito y no negativo')
    if c.get('clamp_normal_force', 150) < 0:
        raise ValueError('La fuerza normal de apriete no puede ser negativa')
    if not 0 < c['pretension_slack'] < .2 or not 0 <= c['slope_deg'] < 35:
        raise ValueError('Holgura o pendiente fuera del dominio del piloto')
    if not 0 <= c['spider_min_tension'] < c['spider_max_tension'] or c['spider_damping'] < 0:
        raise ValueError('Límites de tensión/amortiguación inválidos')
    if c['span'] != 20:
        raise ValueError('La demostración v1 usa span=20; otras luces requieren adaptar trayectorias y anclajes')


def model(name, pose, geometry, color, static=True, mass=1, collision=False):
    inertial = f'<inertial><mass>{mass}</mass><inertia><ixx>{mass*.12}</ixx><iyy>{mass*.12}</iyy><izz>{mass*.18}</izz></inertia></inertial>'
    return f'''<model name="{name}"><static>{str(static).lower()}</static><pose>{pose}</pose>
    <link name="body">{inertial}<visual name="visual"><geometry>{geometry}</geometry>
    <material><ambient>{color}</ambient><diffuse>{color}</diffuse></material></visual>
    {f'<collision name="collision"><geometry>{geometry}</geometry></collision>' if collision else ''}
    </link></model>'''


def generate(config, scenario, destination, output):
    c = dict(config)
    validate(c)
    slope = math.tan(math.radians(c['slope_deg']))
    span, h = c['span'], c['support_height']
    items = []
    items.append(model('terrain', f'10 0 {10*slope-.3} 0 {-math.atan(slope)} 0',
                       '<box><size>36 24 0.5</size></box>', '.24 .40 .15 1', collision=True))
    # Agricultural rows are local geometric primitives, no network assets.
    for i in range(-4, 5):
        items.append(model(f'row_{i+4}', f'10 {i*2} {10*slope} 0 {-math.atan(slope)} 0',
                           '<box><size>24 .16 .12</size></box>', '.45 .30 .12 1'))
    if scenario == 'spider':
        for i in range(8):
            angle = math.pi/4 + (i % 4)*math.pi/2
            ax, ay = 10+7*math.cos(angle), 7*math.sin(angle)
            az = 10*slope + (10 if i < 4 else 2)
            items.append(model(f'anchor_{i}', f'{ax} {ay} {az/2} 0 0 0',
                               f'<cylinder><radius>.10</radius><length>{az}</length></cylinder>', '.5 .5 .55 1'))
        pose = f'10 0 {10*slope+5} 0 0 0'
        count, seglen = 8, .27
    else:
        for i, ax in enumerate([0, span]):
            z = h+ax*slope
            items.append(model(f'tower_{i}', f'{ax} 0 {z/2} 0 0 0',
                               f'<box><size>.3 2 {z}</size></box>', '.5 .5 .55 1'))
        pose = f'1 0 {h} 0 0 0'
        count, seglen = (2 if scenario == 'double' else 1), math.hypot(span, span*slope)*(1+c['pretension_slack'])/32
    vehicle = model('vehicle', pose, '<box><size>1.0 .8 .5</size></box>',
                    '.95 .42 .08 1', static=scenario != 'spider',
                    mass=c['vehicle_mass']+c['payload'], collision=True)
    if scenario != 'spider':
        vehicle = vehicle.replace('<visual name="visual">', '<visual name="visual"><pose>0 0 -.5 0 0 0</pose>')
        visuals = []
        for track in ([-c['track_separation']/2,c['track_separation']/2] if scenario == 'double' else [0]):
            for wx in [-.3,.3]:
                visuals.append(f'<visual name="wheel_{len(visuals)}"><pose>{wx} {track} .12 1.5708 0 0</pose><geometry><cylinder><radius>.14</radius><length>.12</length></cylinder></geometry><material><diffuse>.12 .12 .12 1</diffuse></material></visual>')
        visuals.append('<visual name="hanger"><pose>0 0 -.2 0 0 0</pose><geometry><box><size>.08 .08 .5</size></box></geometry><material><diffuse>.3 .3 .35 1</diffuse></material></visual>')
        vehicle = vehicle.replace('</link>', ''.join(visuals)+'</link>')
    items.append(vehicle)
    for i in range(count*32 if c.get('render_cables', True) else 0):
        items.append(model(f'cable_{i}', '0 0 -50 0 0 0',
                           f'<cylinder><radius>.025</radius><length>{seglen}</length></cylinder>', '.12 .15 .2 1'))
    parameters = ''.join(f'<{key}>{str(value).lower() if isinstance(value,bool) else value}</{key}>' for key, value in c.items())
    text = f'''<?xml version="1.0"?>
<sdf version="1.9"><world name="agro">
<gravity>0 0 -9.81</gravity>
<physics name="physics" type="ignored"><max_step_size>{c['dt']}</max_step_size><real_time_factor>{c.get('real_time_factor',1)}</real_time_factor></physics>
<plugin filename="gz-sim-physics-system" name="gz::sim::systems::Physics"/>
<plugin filename="gz-sim-user-commands-system" name="gz::sim::systems::UserCommands"/>
<plugin filename="gz-sim-scene-broadcaster-system" name="gz::sim::systems::SceneBroadcaster"/>
<plugin filename="AgroCableSystem" name="agro::CableSystem"><scenario>{scenario}</scenario><output>{escape(str(Path(output).resolve()))}</output>{parameters}</plugin>
<scene><ambient>.65 .65 .65 1</ambient><background>.65 .8 .95 1</background><shadows>true</shadows></scene>
<light name="sun" type="directional"><pose>0 0 30 0 0 0</pose><diffuse>.9 .9 .9 1</diffuse><direction>-.5 .2 -1</direction></light>
<gui fullscreen="false"><plugin filename="MinimalScene" name="3D View"><gz-gui><title>AgroTeleferico — {scenario}</title><property type="bool" key="showTitleBar">false</property><property type="string" key="state">docked</property></gz-gui><engine>ogre2</engine><scene>scene</scene><camera_pose>30 -30 22 0 .35 2.2</camera_pose></plugin><plugin filename="GzSceneManager" name="Scene Manager"/><plugin filename="InteractiveViewControl" name="Interactive view control"/><plugin filename="CameraTracking" name="Camera Tracking"/></gui>
{''.join(items)}
</world></sdf>'''
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding='utf-8')
    return destination


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', required=True)
    p.add_argument('--scenario', choices=['single', 'double', 'spider'], required=True)
    p.add_argument('--world', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--payload', type=float)
    p.add_argument('--dt', type=float)
    args = p.parse_args()
    config = yaml.safe_load(Path(args.config).read_text())
    for field in ('payload', 'dt'):
        if getattr(args, field) is not None:
            config[field] = getattr(args, field)
    generate(config, args.scenario, args.world, args.output)


if __name__ == '__main__':
    main()
