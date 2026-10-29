#!/usr/bin/env python3
"""Sequential low-memory reduced-model checks; not a substitute for Gazebo evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from generate_ballasted import generate,SCENARIOS
from check_ballasted import assess

def provenance(binary):
    source = Path(__file__).resolve().parents[1]
    if (source/'include/agro/loop.hpp').exists():
        revision = subprocess.check_output(['git', 'describe', '--always', '--dirty'], cwd=source, text=True).strip()
        headers = source/'include/agro'
    else:
        from ament_index_python.packages import get_package_share_directory
        share = Path(get_package_share_directory('agro_teleferico'))
        revision = (share/'revision.txt').read_text().strip()
        headers = share/'include/agro'
    files = [*headers.glob('loop*.hpp'), Path(__file__).with_name('generate_ballasted.py'), Path(__file__)]
    return {'revision': revision, 'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
            'source_sha256': {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in files}}

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--binary',default='build-ballasted/agro_loop_cli')
    p.add_argument('--edge-cases-only',action='store_true')
    p.add_argument('--variant',choices=('baseline','compact_candidate','revised_supports'),default='revised_supports')
    a=p.parse_args();out=Path(a.output).resolve();out.mkdir(parents=True,exist_ok=False)
    binary=Path(a.binary).resolve();rows=[]
    identity=provenance(binary)
    cases=[(s,{}) for s in SCENARIOS]+[('ladera_agricola',{'calm':True}),('ladera_agricola',{'dt':.001}),('buitrago_patio',{'fill':.2})]
    if a.edge_cases_only:cases=[('buitrago_patio',{'descending_payload':5}),('buitrago_patio',{'fill':0})]
    for i,(scenario,options) in enumerate(cases):
        folder=out/f'{i:02d}_{scenario}'
        world=generate(scenario,folder,variant=a.variant,**options)
        metadata=json.loads((world.parent/'metadata.json').read_text())
        cmd=[str(binary),'--config',str(world.parent/'loop.params'),'--output',str(folder/'core'),'--mode','central_only']
        if not metadata['scenario']['gust']:cmd.append('--no-wind')
        result=subprocess.run(cmd,capture_output=True,text=True)
        (folder/'process.log').write_text(result.stdout+result.stderr)
        row={'scenario':scenario,'options':options,'exit_code':result.returncode,'command':cmd}
        if (folder/'core/bases.csv').exists():
            try:row['assessment']=assess(folder)
            except Exception as exc:row['assessment_error']=repr(exc)
        rows.append(row);print(json.dumps({'case':i,'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr}),flush=True)
    (out/'suite.json').write_text(json.dumps({'cases':rows,'provenance':identity},indent=2))
    raise SystemExit(0 if all(r['exit_code']==0 and r.get('assessment',{}).get('core_passed',False) for r in rows) else 1)

if __name__=='__main__':main()
