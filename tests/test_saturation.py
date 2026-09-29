#!/usr/bin/env python3
"""Condiciones degradadas deben aparecer en telemetría, no fingir seguimiento."""
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import yaml
from run_suite import run

config=yaml.safe_load(Path('config/pilot.yaml').read_text())
out=Path('results/saturation').resolve()
results={}
for scenario, changes in [('single',dict(friction=.02,clamp_normal_force=0)),
                           ('spider',dict(winch_speed=.0001))]:
    result=run(dict(config,duration=20,**changes),scenario,out/scenario)
    assert result['saturated_fraction']>.01, 'La saturación debe ser observable'
    assert result['min_tension_N']>=0, 'Ningún cable puede empujar'
    assert result['duration_s']>=19.95, 'El ensayo degradado debe terminar'
    assert result['position_rms_m']>.01, 'Un actuador insuficiente no puede fingir seguimiento perfecto'
    results[scenario]=dict(result,expected_degraded=True)
(out/'summary.json').write_text(json.dumps(results,indent=2))
print('Degraded actuator scenarios detected correctly')
