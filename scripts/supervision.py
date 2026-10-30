"""Shared fresh host-memory validation and process-tree measurements; no ROS imports."""
import json
import math
from pathlib import Path
import subprocess
import time

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
