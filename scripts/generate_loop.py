#!/usr/bin/env python3
"""Generate the multicarrier SDF and a strict SI parameter file, without network assets."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
from xml.sax.saxutils import escape
import yaml


def read_config(path):
    c = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(c, dict) or "terrain" not in c:
        raise ValueError("Expected a mapping containing terrain")
    for k, v in c.items():
        if k == "terrain":
            if len(v) != 5 or any(len(p) != 2 for p in v):
                raise ValueError("Five (x,z) landmarks required")
            numbers = [x for p in v for x in p]
        else:
            numbers = [v]
        if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in numbers):
            raise ValueError(f"Nonfinite/non-numeric value: {k}")
    if [p[0] for p in c["terrain"]] != sorted(set(p[0] for p in c["terrain"])):
        raise ValueError("Terrain x must be strictly increasing")
    if c["supports_per_segment"] not in range(3, 9) or c["carriers_per_lane"] not in range(1, 13):
        raise ValueError("Invalid support/carrier counts")
    return c


def ground(c, x):
    pts = c["terrain"]
    if x <= pts[0][0]:
        return pts[0][1]
    if x >= pts[-1][0]:
        return pts[-1][1]
    for a, b in zip(pts, pts[1:]):
        if x <= b[0]:
            u = (x - a[0]) / (b[0] - a[0])
            return a[1] + (b[1] - a[1]) * (.5 - .5 * math.cos(math.pi*u))
    raise ValueError("No terrain interval")


def supports(c):
    n = int(c["supports_per_segment"]) - 1
    return [a[0] + (b[0]-a[0])*i/n for a, b in zip(c["terrain"], c["terrain"][1:]) for i in range(n)] + [c["terrain"][-1][0]]


def write_params(c, path):
    rows = ["# Generated from loop.yaml; SI. Do not edit independently."]
    for k, v in c.items():
        if k == "terrain":
            rows.append("terrain 5 " + " ".join(str(x) for p in v for x in p))
        else:
            rows.append(f"{k} {v}")
    Path(path).write_text("\n".join(rows)+"\n", encoding="utf-8")


def box(x, y, z):
    return f"<box><size>{x} {y} {z}</size></box>"


def cylinder(radius, length):
    return f"<cylinder><radius>{radius}</radius><length>{length}</length></cylinder>"


def visual(name, geometry, color, pose="0 0 0 0 0 0"):
    return f'<visual name="{name}"><pose>{pose}</pose><geometry>{geometry}</geometry><material><ambient>{color}</ambient><diffuse>{color}</diffuse></material><cast_shadows>false</cast_shadows></visual>'


def model(name, pose, visuals):
    # Geometry is a renderer of reduced states, not duplicate native physics.
    return f'<model name="{name}"><static>true</static><pose>{pose}</pose><link name="body"><gravity>false</gravity>{visuals}</link></model>'


def segment(name, a, b, radius, color):
    d = [b[i]-a[i] for i in range(3)]
    length = math.sqrt(sum(v*v for v in d))
    pitch = math.acos(max(-1, min(1, d[2]/length)))
    yaw = math.atan2(d[1], d[0])
    mid = [(a[i]+b[i])/2 for i in range(3)]
    return model(name, f'{mid[0]} {mid[1]} {mid[2]} 0 {pitch} {yaw}', visual("line", cylinder(radius, length), color))


def terrain_mesh(c, path):
    # Monotonic cosine interpolation: exactly three valleys and two unequal peaks.
    X = c["terrain"][-1][0]
    n = int(math.ceil((X+8)/.25))
    vertices = []
    for i in range(n+1):
        x = -4+(X+8)*i/n
        for y in (-8, 8):
            vertices.extend((x, y, ground(c, x)))
    triangles = []
    for i in range(n):
        a = 2*i
        triangles.extend((a, a+2, a+1, a+1, a+2, a+3))
    text = f'''<?xml version="1.0" encoding="utf-8"?>
<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema" version="1.4.1"><asset><unit meter="1"/><up_axis>Z_UP</up_axis></asset>
<library_geometries><geometry id="terrain"><mesh><source id="points"><float_array id="xyz" count="{len(vertices)}">{' '.join(map(str,vertices))}</float_array><technique_common><accessor source="#xyz" count="{len(vertices)//3}" stride="3"><param name="X" type="float"/><param name="Y" type="float"/><param name="Z" type="float"/></accessor></technique_common></source><vertices id="v"><input semantic="POSITION" source="#points"/></vertices><triangles count="{len(triangles)//3}"><input semantic="VERTEX" source="#v" offset="0"/><p>{' '.join(map(str,triangles))}</p></triangles></mesh></geometry></library_geometries><library_visual_scenes><visual_scene id="scene"><node id="terrain-node"><instance_geometry url="#terrain"/></node></visual_scene></library_visual_scenes><scene><instance_visual_scene url="#scene"/></scene></COLLADA>'''
    path.write_text(text, encoding="utf-8")


def generate(config, directory, mode="central_local", gust=True, stop_at_end=False):
    if mode not in ("central_only", "central_local"):
        raise ValueError("Unknown mode")
    c = read_config(config)
    out = Path(directory).resolve()
    out.mkdir(parents=True, exist_ok=True)
    if (out/"world.sdf").exists():
        raise FileExistsError(f"Refusing to overwrite {out}; use a new output directory")
    write_params(c, out/"loop.params")
    (out/"loop.yaml").write_text(yaml.safe_dump(c, sort_keys=False), encoding="utf-8")
    terrain_mesh(c, out/"terrain.dae")
    xs, h, r, gauge = supports(c), c["support_height"], c["lane_half_width"], c["gauge"]
    dark, steel, orange, green = ".12 .16 .20 1", ".5 .55 .6 1", "1 .35 .05 1", ".16 .43 .2 1"
    items = [model("terrain_three_valleys_two_peaks", "0 0 0 0 0 0", visual("surface", f'<mesh><uri>{escape((out/"terrain.dae").as_uri())}</uri></mesh>', green))]
    for i, x in enumerate(xs):
        z = ground(c, x)
        shapes = [visual("crossbeam", box(.22, 9, .18), steel, f"0 0 {h+1.25} 0 0 0")]
        for side in (-1, 1):
            shapes.append(visual(f"column_{side}", box(.2, .2, h+1.25), steel, f"0 {side*4.4} {(h+1.25)/2} 0 0 0"))
        # All supports explicitly have a retention/guide assembly in this conceptual topology.
        for lane, y in enumerate((-r, r)):
            for rail, dy in enumerate((-gauge/2,gauge/2)):
                shapes.append(visual(f"retention_{lane}_{rail}", box(.15,.15,.12), dark, f"0 {y+dy} {h-.14} 0 0 0"))
        items.append(model(f"portal_{i:02d}", f"{x} 0 {z} 0 0 0", ''.join(shapes)))
    # Fixed local guides bridge retained support points; they are separate from flexible spans.
    for i, x in enumerate(xs):
        a, b = max(0, x-c['guide_half_length']), min(xs[-1], x+c['guide_half_length'])
        for lane,y in enumerate((-r,r)):
            for rail,dy in enumerate((-gauge/2,gauge/2)):
                for j in range(6):
                    xa,xb=a+(b-a)*j/6,a+(b-a)*(j+1)/6
                    items.append(segment(f"guide_{i}_{lane}_{rail}_{j}", (xa,y+dy,ground(c,xa)+h+c['guide_lift']), (xb,y+dy,ground(c,xb)+h+c['guide_lift']), .045, steel))
    # Return rails and separate orange tractor circuit; no cable is secretly made to move.
    line_points = []
    for i in range(97):
        x=xs[-1]*i/96
        line_points.append((x,-r,ground(c,x)+h+.8))
    for i in range(1,25):
        a=-math.pi/2+math.pi*i/24
        line_points.append((xs[-1]+r*math.cos(a),r*math.sin(a),ground(c,xs[-1])+h+.8))
    for i in range(1,97):
        x=xs[-1]*(1-i/96)
        line_points.append((x,r,ground(c,x)+h+.8))
    for i in range(1,25):
        a=math.pi/2+math.pi*i/24
        line_points.append((r*math.cos(a),r*math.sin(a),ground(c,0)+h+.8))
    for i,(a,b) in enumerate(zip(line_points,line_points[1:]+line_points[:1])):
        if math.dist(a,b)>1e-8:
            items.append(segment(f"tractor_{i:03d}",a,b,.018,orange))
    for end,x in enumerate((0,xs[-1])):
        for rail,rr in enumerate((r-gauge/2,r+gauge/2)):
            for i in range(24):
                angle=math.pi/2 if end==0 else -math.pi/2
                a,b=angle+math.pi*i/24,angle+math.pi*(i+1)/24
                za=ground(c,x)+h+c['guide_lift']
                items.append(segment(f"return_{end}_{rail}_{i}",(x+rr*math.cos(a),rr*math.sin(a),za),(x+rr*math.cos(b),rr*math.sin(b),za),.045,steel))
        deck = visual("deck",box(3,7,.15),".65 .60 .42 1",f"0 0 {h-c['suspension']-.4} 0 0 0")
        items.append(model("station_lower_LOAD" if end==0 else "station_upper_UNLOAD",f"{x} 0 {ground(c,x)} 0 0 0",deck))
    # Rendered segment lengths have 5% overlap; their centrelines use equal-arc model samples.
    for lane in range(2):
        for k in range(len(xs)-1):
            L=math.hypot(xs[k+1]-xs[k],ground(c,xs[k+1])-ground(c,xs[k]))*(1+c['slack'])
            for rail in range(2):
                for j in range(int(c['cable_segments'])):
                    name=f"flex_{lane}_{k}_{rail}_{j}"
                    items.append(model(name,"0 0 -50 0 0 0",visual("cable",cylinder(.025,1.05*L/c['cable_segments']),dark)))
    for i in range(2*int(c['carriers_per_lane'])):
        shapes=[visual("chassis",box(.8,gauge+.14,.16),orange),visual("local_motor",box(.22,.2,.2),".1 .4 .7 1","0 0 .20 0 0 0"),visual("traction_mast",box(.08,.08,.65),steel,"0 0 .37 0 0 0")]
        for x in (-.25,.25):
            for y in (-gauge/2,gauge/2):
                shapes.append(visual(f"wheel_{x}_{y}",cylinder(.11,.10),dark,f"{x} {y} -.015 {math.pi/2} 0 0"))
        items.append(model(f"bogie_{i}","0 0 -50 0 0 0",''.join(shapes)))
        pallet=visual("base",box(1.2,1,.12),".58 .38 .16 1")
        for y in (-.35,.35):
            pallet+=visual(f"runner_{y}",box(1.2,.12,.10),".45 .27 .10 1",f"0 {y} -.09 0 0 0")
        items.append(model(f"pallet_{i}","0 0 -50 0 0 0",pallet))
        items.append(model(f"hanger_{i}","0 0 -50 0 0 0",visual("rod",cylinder(.025,c['suspension']),steel)))
        items.append(model(f"coupler_{i}","0 0 -50 0 0 0",visual("slider",box(.38,.10,.08),".1 .4 .7 1")))
        for j in range(2):
            items.append(model(f"load_{i}_{j}","0 0 -50 0 0 0",visual("crate",box(.46,.75,.45),".24 .62 .30 1")))
    items.append(model("main_motor_lower",f"-1 0 {ground(c,0)+h+.9} 0 0 0",visual("motor",box(1.1,.7,.6),".12 .3 .6 1")))
    items.append(model("main_rotor",f"0 0 {ground(c,0)+h+.8} 0 0 0",visual("sheave",cylinder(r,.08),orange)+visual("spoke",box(2*r,.08,.12),steel)))
    items.append(model("wind_indicator", "0 0 -50 0 0 0", visual("shaft",box(2,.10,.10),".05 .65 1 1")+visual("tip",box(.35,.45,.15),".05 .65 1 1",".95 0 0 0 0 0")))
    parameters=f'<params>{escape(str(out/"loop.params"))}</params><output>{escape(str(out/"gazebo"))}</output><mode>{mode}</mode><gust>{str(gust).lower()}</gust><stop_at_end>{str(stop_at_end).lower()}</stop_at_end>'
    text=f'''<?xml version="1.0"?>
<sdf version="1.9"><world name="agro_loop"><gravity>0 0 -9.81</gravity><physics name="physics" type="ignored"><max_step_size>{c['dt']}</max_step_size><real_time_factor>1</real_time_factor></physics>
<plugin filename="gz-sim-physics-system" name="gz::sim::systems::Physics"/><plugin filename="gz-sim-user-commands-system" name="gz::sim::systems::UserCommands"/><plugin filename="gz-sim-scene-broadcaster-system" name="gz::sim::systems::SceneBroadcaster"/>
<plugin filename="AgroLoopSystem" name="agro::LoopSystem">{parameters}</plugin>
<scene><ambient>.65 .65 .65 1</ambient><background>.65 .8 .95 1</background><shadows>false</shadows></scene><light name="sun" type="directional"><pose>0 0 40 0 0 0</pose><diffuse>.9 .9 .9 1</diffuse><direction>-.5 .2 -1</direction></light>
<gui fullscreen="false"><plugin filename="MinimalScene" name="3D View"><gz-gui><title>AgroTeleferico — MODELO REDUCIDO — {mode}</title><property type="bool" key="showTitleBar">true</property><property type="string" key="state">docked</property></gz-gui><engine>ogre2</engine><scene>scene</scene><camera_pose>65 -65 40 0 .40 2.1</camera_pose></plugin><plugin filename="GzSceneManager" name="Scene Manager"/><plugin filename="InteractiveViewControl" name="Interactive view control"/><plugin filename="CameraTracking" name="Camera Tracking"/><plugin filename="WorldControl" name="World control"/><plugin filename="WorldStats" name="World stats"/></gui>
{''.join(items)}
</world></sdf>'''
    (out/"world.sdf").write_text(text,encoding="utf-8")
    try:
        commit=subprocess.check_output(["git","rev-parse","HEAD"],cwd=Path(config).resolve().parent,text=True,stderr=subprocess.DEVNULL).strip()
    except (subprocess.CalledProcessError,FileNotFoundError):
        commit="unavailable"
    meta={"schema":"agro-loop-config-v1","commit":commit,"configuration_sha256":hashlib.sha256((out/"loop.yaml").read_bytes()).hexdigest(),"mode":mode,"gust":gust,"seed":0,"randomness":"none; deterministic prescribed scenario","units":"SI","parameter_origin":{"topology_and_six_carriers":"user_requirement","terrain_landmark_order":"user_requirement","numeric_values":"conceptual_assumptions; not identified or certified"},"support_cables_per_lane":2,"lanes":2,"unique_portals":len(xs),"static_visual_models":len(items),"native_contact_physics":False}
    (out/"metadata.json").write_text(json.dumps(meta,indent=2),encoding="utf-8")
    return out/"world.sdf"


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config",required=True)
    p.add_argument("--output",required=True)
    p.add_argument("--mode",choices=["central_only","central_local"],default="central_local")
    p.add_argument("--no-wind",action="store_true")
    p.add_argument("--stop-at-end",action="store_true")
    a=p.parse_args()
    print(generate(a.config,a.output,a.mode,not a.no_wind,a.stop_at_end))


if __name__=="__main__":
    main()
