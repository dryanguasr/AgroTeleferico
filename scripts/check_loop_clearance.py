#!/usr/bin/env python3
"""Conservative sampled clearance screen; complements, never replaces, visual review."""
import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--case', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    guard = json.loads((args.case/'guard_summary.json').read_text())
    if not guard['passed']:
        raise ValueError('Complete guarded evidence required')
    world = ET.parse(args.case/'generated/world.sdf')
    obstacles = []
    for model in world.findall('.//world/model'):
        name = model.get('name')
        if not (name.startswith('portal_') or name.startswith('station_') or name == 'main_motor_lower'):
            continue
        pose = np.fromstring(model.findtext('pose', '0 0 0 0 0 0'), sep=' ')
        if np.any(pose[3:] != 0):
            raise ValueError('Rotated obstacle not supported')
        for visual in model.findall('link/visual'):
            # Retentions are part of intended wheel/guide support interaction.
            if visual.get('name').startswith('retention_'):
                continue
            size = np.fromstring(visual.findtext('geometry/box/size', ''), sep=' ')
            local = np.fromstring(visual.findtext('pose', '0 0 0 0 0 0'), sep=' ')
            if len(size) != 3 or np.any(local[3:] != 0):
                raise ValueError('Expected axis-aligned structural box')
            obstacles.append((name+'/'+visual.get('name'), pose[:3]+local[:3], size/2))
    rows = np.genfromtxt(args.case/'generated/gazebo/carriers.csv', names=True, delimiter=',')
    pivot = np.column_stack([rows['pivot_'+axis+'_m'] for axis in 'xyz'])
    pallet = np.column_stack([rows['pallet_'+axis+'_m'] for axis in 'xyz'])
    # Current generator: full pallet/crate corner radius <=0.817 m; bogie <=0.70 m.
    # Use 0.85 m spheres independent of yaw/pitch/roll and payload visibility.
    bodies = [('bogie', pivot+np.array([0, 0, .11]), .85), ('pallet_and_load', pallet, .85)]
    findings = {}
    for body, centers, radius in bodies:
        closest = None
        for name, center, half in obstacles:
            distance = np.linalg.norm(np.maximum(np.abs(centers-center)-half, 0), axis=1)-radius
            i = int(np.argmin(distance))
            record = {'lower_bound_m': float(distance[i]), 'obstacle': name,
                      'time_s': float(rows['time_s'][i]), 'carrier_id': int(rows['id'][i])}
            if closest is None or record['lower_bound_m'] < closest['lower_bound_m']:
                closest = record
        findings[body] = closest
    result = {'scope': 'Sampled CSV poses against portal columns/crossbeams, station decks and motor boxes only. Sphere overlap is inconclusive, not proof of contact. Excludes couplers, hanger, rails, retentions, tractor, rotor, terrain and intersample motion.',
              'sphere_radius_m': .85, 'samples': len(rows), 'obstacles': len(obstacles),
              'findings': findings,
              'all_screened_spheres_clear': all(v['lower_bound_m'] > 0 for v in findings.values())}
    args.output.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
