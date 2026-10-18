#!/usr/bin/env python3
"""Run exactly one headless service with fresh host-memory admission and monitoring."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import time
import traceback
import uuid
import yaml
from generate_loop import generate, read_config
from run_loop_suite import assess


def read_host_memory(path, now=None):
    # Atomic Windows replacement can briefly report ENODATA/ENOENT through DrvFS.
    # Retry only these I/O errors; each successful read still needs fresh evidence.
    for attempt in range(3):
        try:
            raw = Path(path).read_text(encoding='utf-8-sig')
            break
        except OSError as exc:
            if exc.errno not in (2, 61) or attempt == 2:
                raise
            time.sleep(.1)
    sample = json.loads(raw)
    timestamp, free = sample['unix_s'], sample['free_gib']
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
           for v in (timestamp, free)):
        raise RuntimeError('Host memory measurement must contain finite numbers')
    age = (time.time() if now is None else now)-timestamp
    if not -5 <= age <= 15 or free < 0 or sample.get('error'):
        raise RuntimeError('Host memory measurement stale, invalid, or failed')
    return float(free)


def tree_rss(pid):
    rows = subprocess.check_output(['ps', '-eo', 'pid=,ppid=,rss='], text=True)
    records = [tuple(map(int, row.split())) for row in rows.splitlines()]
    selected = {pid}
    while True:
        expanded = selected | {p for p, parent, rss in records if parent in selected}
        if expanded == selected:
            break
        selected = expanded
    return sum(rss for p, parent, rss in records if p in selected)/1024**2, sorted(selected)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', required=True)
    p.add_argument('--host-memory', required=True)
    p.add_argument('--timeout', type=float, default=1200)
    p.add_argument('--case', choices=['hybrid_gust','central_gust','hybrid_calm','hybrid_half_dt','hybrid_half_shape'], default='hybrid_gust')
    p.add_argument('--scenario',choices=['buitrago_patio','buitrago_entre_pisos','ladera_agricola'])
    p.add_argument('--variant',choices=['baseline','compact_candidate','revised_supports'],default='revised_supports')
    args = p.parse_args()
    out = Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=False)
    memory = Path(args.host_memory)
    os.environ['GZ_PARTITION'] = 'agro_guarded_'+uuid.uuid4().hex
    from ament_index_python.packages import get_package_prefix
    os.environ['GZ_SIM_SYSTEM_PLUGIN_PATH'] = str(Path(get_package_prefix('agro_teleferico'))/'lib')
    from gz.transport13 import Node
    from gz.msgs10.server_control_pb2 import ServerControl
    from gz.msgs10.boolean_pb2 import Boolean
    node = Node()

    def host_free():
        return read_host_memory(memory)

    if host_free() < 9:
        raise RuntimeError('Admission requires 9 GiB host free memory (4 GiB workload, 4 GiB reserve, 1 GiB stop margin)')
    values = read_config(Path('config/loop.yaml').resolve())
    if args.scenario:
        from generate_ballasted import config as pilot_config
        values,_,_=pilot_config(args.scenario,variant=args.variant)
    if args.case == 'hybrid_half_dt':
        values['dt'] *= .5
    if args.case == 'hybrid_half_shape':
        values['shape_period'] *= .5
    config = out/'input.yaml'
    config.write_text(yaml.safe_dump(values,sort_keys=False))
    if args.scenario:
        from generate_ballasted import generate as generate_ballasted
        world=generate_ballasted(args.scenario,out/'pilot',stop_at_end=True,variant=args.variant)
    else:
        world = generate(config, out/'generated', mode='central_only' if args.case=='central_gust' else 'central_local', gust=args.case!='hybrid_calm', stop_at_end=True)
    plugin = Path(get_package_prefix('agro_teleferico'))/'lib/libAgroLoopSystem.so'
    sources = [Path('src/loop_system.cpp'), Path('src/loop_cli.cpp'),
               *sorted(Path('include/agro').glob('loop*.hpp')),
               Path('scripts/generate_loop.py'), Path(__file__)]
    if args.scenario:
        sources += [Path('scripts/generate_ballasted.py'),Path('scripts/check_ballasted.py'),
                    Path({'baseline':'config/ballasted_common.json','compact_candidate':'config/ballasted_compact_candidate.json','revised_supports':'config/ballasted_revised_supports.json'}[args.variant]),Path('config')/(args.scenario+'.json')]
    manifest = {
        'captured_before_launch': True,
        'case': args.case,
        'plugin_path': str(plugin),
        'plugin_sha256': hashlib.sha256(plugin.read_bytes()).hexdigest(),
        'world_sha256': hashlib.sha256(world.read_bytes()).hexdigest(),
        'source_sha256': {str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in sources},
        'git_head': subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        'git_status': subprocess.check_output(['git','status','--short'],text=True),
    }
    (out/'provenance.json').write_text(json.dumps(manifest,indent=2))
    reason = None
    peak, minimum = 0., host_free()
    started = time.monotonic()
    with (out/'process.log').open('w') as log, (out/'resources.jsonl').open('w') as samples:
        proc = subprocess.Popen(['gz', 'sim', '-s', '-r', str(world)], stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        (out/'process.json').write_text(json.dumps({'pid': proc.pid, 'partition': os.environ['GZ_PARTITION'], 'command': proc.args}))
        try:
            while proc.poll() is None:
                free = host_free()
                rss, pids = tree_rss(os.getpid())
                peak, minimum = max(peak,rss), min(minimum,free)
                samples.write(json.dumps({'wall_s': time.monotonic()-started, 'host_free_gib': free, 'tree_rss_gib': rss, 'pids': pids})+'\n')
                samples.flush()
                if (out.parent/'STOP_REQUESTED').exists():
                    reason = 'explicit_stop_request'
                elif free < 5:
                    reason = 'host_below_5_gib_stop_margin_for_4_gib_reserve'
                elif time.monotonic()-started > args.timeout:
                    reason = 'timeout'
                if reason:
                    break
                time.sleep(1)
        except BaseException as exc:
            reason = repr(exc)
            (out/'guard_error.txt').write_text(traceback.format_exc())
        finally:
            if proc.poll() is None:
                try:
                    node.request('/server_control', ServerControl(stop=True), ServerControl, Boolean, 5000)
                    proc.wait(timeout=15)
                except Exception:
                    os.killpg(proc.pid, signal.SIGINT)
                    try:
                        proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(proc.pid, signal.SIGKILL)
                        proc.wait(timeout=5)
    result = {'stop_reason': reason, 'exit_code': proc.returncode, 'peak_tree_rss_gib': peak, 'min_host_free_gib': minimum, 'wall_s': time.monotonic()-started, 'passed': False}
    if reason is None and proc.returncode == 0:
        try:
            if args.scenario:
                from check_ballasted import assess as assess_ballasted
                result['assessment']=assess_ballasted(out/'pilot')
                result['passed']=result['assessment']['core_passed']
                result['accepted_installation']=False
            else:
                result['assessment'], _ = assess(out/'generated/gazebo', read_config(config))
                result['passed'] = result['assessment']['passed']
        except Exception as exc:
            result['assessment_error'] = repr(exc)
    (out/'guard_summary.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2), flush=True)
    raise SystemExit(0 if result['passed'] else 1)


if __name__ == '__main__':
    main()
