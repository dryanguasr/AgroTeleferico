#!/usr/bin/env python3
"""Verify completed live capture, temporal coverage and full video decoding."""
import argparse
import csv
import json
from pathlib import Path
import subprocess


def verify(directory, until, expected_views):
    capture = json.loads((directory/'capture.json').read_text())
    coverage = json.loads((directory/'camera_coverage.json').read_text())
    core = json.loads((directory/'generated/gazebo/summary.json').read_text())
    service_complete = core['status'] == 'completed' and abs(core['simulated_s']-core['duration_target_s']) < 1e-6
    checks = {
        'live_sensor': capture['live_gazebo_sensor'] and not capture['replay'],
        'clean_server': capture['gazebo_exit_code'] == 0,
        'clean_gui': capture.get('gui_exit_code') in (None, 0),
        'requested_stop_completed': capture.get('stop_requested', capture.get('stop_acknowledged', False)) and capture['gazebo_exit_code'] == 0,
        'no_capture_errors': not capture['errors'],
        'requested_views': set(coverage) == set(expected_views),
        'requested_service_completion': until < core['duration_target_s'] or service_complete,
    }
    timing = {}
    for view, summary in coverage.items():
        with (directory/f'frame_times_{view}.csv').open() as stream:
            rows = list(csv.DictReader(stream))
        stamps = [float(row['simulation_s']) for row in rows]
        wall = [float(row['wall_s']) for row in rows]
        gaps = [b-a for a, b in zip(stamps, stamps[1:])]
        checks[view+'_coverage'] = bool(stamps and stamps[0] <= .21 and stamps[-1] >= until)
        checks[view+'_continuous'] = bool(gaps and min(gaps) > 0 and max(gaps) <= .211)
        checks[view+'_metadata'] = bool(stamps and len(rows) == summary['frames'] and abs(stamps[-1]-summary['last_simulation_s']) < 1e-8)
        checks[view+'_checkpoints'] = all((directory/f'{view}_{checkpoint:03d}s.png').is_file() for checkpoint in summary['checkpoints'])
        timing[view] = {'frames': len(rows), 'first_simulation_s': stamps[0] if stamps else None,
                        'last_simulation_s': stamps[-1] if stamps else None,
                        'max_gap_s': max(gaps) if gaps else None,
                        'render_simulation_to_wall_ratio': (stamps[-1]-stamps[0])/(wall[-1]-wall[0]) if len(wall) > 1 else None}
    probe = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-count_frames',
                            '-show_entries', 'stream=codec_name,width,height,r_frame_rate,nb_read_frames,duration',
                            '-of', 'json', str(directory/'gazebo.mp4')], text=True, capture_output=True, check=True)
    video = json.loads(probe.stdout)['streams'][0]
    frames = timing[capture['view']]['frames']
    checks['video_format'] = (video['width'], video['height'], video['codec_name'], video['r_frame_rate']) == (1280, 800, 'h264', '20/1')
    checks['video_frames'] = int(video['nb_read_frames']) == frames
    checks['video_duration'] = abs(float(video['duration'])-frames/20) < .051
    decode = subprocess.run(['ffmpeg', '-v', 'error', '-xerror', '-i', str(directory/'gazebo.mp4'), '-f', 'null', '-'], text=True, capture_output=True)
    checks['video_decodes'] = decode.returncode == 0 and not decode.stderr.strip()
    resources = [json.loads(line) for line in (directory/'resources.jsonl').read_text().splitlines() if line.strip()]
    measured = {'peak_tree_rss_gib': max(row['tree_rss_gib'] for row in resources),
                'minimum_host_free_gib': min(row['host_free_gib'] for row in resources)} if resources else None
    checks['host_reserve'] = measured is not None and measured['minimum_host_free_gib'] >= 4
    return {'passed': all(checks.values()), 'full_service_verified': service_complete, 'checks': checks, 'timing': timing, 'video': video,
            'resources': measured, 'decode_stderr': decode.stderr,
            'scope': 'File integrity, full decode and timing only. Visual geometry and absence of residual processes require separate inspection.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--until', type=float, default=341)
    parser.add_argument('--expected-views', default='overview,lower,upper')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError('Preserve existing verification evidence')
    try:
        result = verify(args.capture, args.until, args.expected_views.split(','))
    except Exception as exc:
        result = {'passed': False, 'error': repr(exc)}
    args.output.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['passed'] else 1)


if __name__ == '__main__':
    main()
