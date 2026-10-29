#!/usr/bin/env python3
"""Exercise installed Python dependencies outside the source checkout."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from ament_index_python.packages import get_package_prefix


def main():
    commands = Path(get_package_prefix('agro_teleferico'))/'lib/agro_teleferico'
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    with tempfile.TemporaryDirectory(prefix='agro_install_') as directory:
        for path in sorted(commands.glob('*.py')):
            code = ("import runpy,sys;sys.path.insert(0,sys.argv[1]);"
                    "runpy.run_path(sys.argv[2],run_name='installed_import_check')")
            subprocess.run([sys.executable, '-c', code, str(commands), str(path)],
                           cwd=directory, env=env, check=True, timeout=30)
        for name in ('capture_loop', 'generate_ballasted', 'validate_demand_native',
                     'compose_telemetry_hud', 'run_ballasted_core'):
            subprocess.run([sys.executable, str(commands/(name+'.py')), '--help'],
                           cwd=directory, env=env, check=True, timeout=30,
                           stdout=subprocess.DEVNULL)
        subprocess.run([sys.executable, str(commands/'generate_ballasted.py'),
                        '--scenario', 'buitrago_patio', '--output', str(Path(directory)/'pilot')],
                       cwd=directory, env=env, check=True, timeout=30)
        code = ("import sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);"
                "from run_ballasted_core import provenance;"
                "p=provenance(Path(sys.argv[1])/'agro_loop_cli');"
                "assert p['revision'] and len(p['source_sha256'])>=3")
        subprocess.run([sys.executable, '-c', code, str(commands)],
                       cwd=directory, env=env, check=True, timeout=30)
    print('Installed imports, help, scene generation and provenance passed')


if __name__ == '__main__':
    main()
