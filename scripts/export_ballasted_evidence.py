#!/usr/bin/env python3
"""Export verified critical evidence, excluding private references and build trees."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile


def main():
    p=argparse.ArgumentParser();p.add_argument('--suite',required=True);p.add_argument('--patio',required=True);p.add_argument('--ladera',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();suite=Path(a.suite);out=Path(a.output)
    cases=sorted(suite.glob('0*'))
    for case in cases[:3]:
        if not json.loads((case/'support_clearance.json').read_text())['passed']:raise ValueError('Geometry audit failed: '+str(case))
    captures={'patio':Path(a.patio),'ladera':Path(a.ladera)}
    for name,path in captures.items():
        if not json.loads((path/'verification.json').read_text())['passed']:raise ValueError('Capture unverified: '+name)
    out.mkdir(parents=True,exist_ok=False)
    metrics=[]
    for case in cases:
        dest=out/case.name;dest.mkdir()
        for name in ('assessment.json','support_clearance.json'):
            if (case/name).exists():shutil.copy2(case/name,dest/name)
        shutil.copy2(case/'core/summary.json',dest/'summary.json')
        shutil.copy2(case/'generated/metadata.json',dest/'metadata.json')
        if case in cases[:3]:
            with zipfile.ZipFile(dest/'reproduction.zip','w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
                for f in sorted((case/'core').glob('*.csv')):z.write(f,'core/'+f.name)
                for name in ('world.sdf','loop.params','loop.yaml','metadata.json'):z.write(case/'generated'/name,'generated/'+name)
        metrics.append({'case':case.name,'summary':json.loads((case/'core/summary.json').read_text()),'assessment':json.loads((case/'assessment.json').read_text())})
    for name,path in captures.items():
        dest=out/('capture_'+name);dest.mkdir()
        filenames=['gazebo.mp4','follow.mp4','verification.json','provenance.json','camera_coverage.json',
                   'overview_004s.png','upper_004s.png','follow_050s.png','follow_070s.png']
        for filename in filenames:
            if (path/filename).exists():shutil.copy2(path/filename,dest/filename)
        shutil.copy2(path.parent/'admission.json',dest/'admission.json')
        # Preserve the exact rendered world and telemetry independently of the
        # standalone world: Gazebo adds cameras and live plugin output paths.
        with zipfile.ZipFile(dest/'native_reproduction.zip','w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
            for f in sorted((path/'pilot/generated/gazebo').glob('*.csv')):z.write(f,'gazebo/'+f.name)
            for f in sorted((path/'pilot/generated').glob('*.sdf')):z.write(f,'generated/'+f.name)
            for f in path.glob('frame_times_*.csv'):z.write(f,f.name)
    sensitivity=json.loads((suite/'reassessment.json').read_text())['sensitivity']
    (out/'metrics.json').write_text(json.dumps({'cases':metrics,'sensitivity':sensitivity},indent=2))
    sources=[*Path('include/agro').glob('loop*.hpp'),Path('src/loop_system.cpp'),
             *Path('config').glob('ballasted*.json'),*Path('config').glob('buitrago*.json'),Path('config/ladera_agricola.json'),Path('config/legacy/buitrago_patio.json'),
             Path('CMakeLists.txt'),Path('scripts/windows/run_guarded_loop.ps1'),
             *Path('tests').glob('test_ballasted*'),
             *[Path('scripts')/n for n in ('generate_ballasted.py','generate_loop.py','audit_support_clearance.py','capture_loop.py','verify_ballasted_capture.py','export_ballasted_evidence.py','run_ballasted_core.py','check_ballasted.py','summarize_ballasted.py','run_loop_guarded.py')]]
    manifest={'schema':'single-span-critical-evidence-v1','scope':'reduced model and sampled geometry; no structural certification',
              'private_reference_included':False,'source_sha256':{f.as_posix():hashlib.sha256(f.read_bytes()).hexdigest() for f in sources},
              'files':{f.relative_to(out).as_posix():{'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()} for f in sorted(out.rglob('*')) if f.is_file()}}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2))
    print(json.dumps({'output':str(out),'files':len(manifest['files']),'bytes':sum(v['bytes'] for v in manifest['files'].values())}))


if __name__=='__main__':main()
