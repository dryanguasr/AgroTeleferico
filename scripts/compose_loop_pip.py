#!/usr/bin/env python3
"""Compose synchronized live general/follow camera recordings into a PiP video."""
import argparse
import csv
import json
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--allow-partial', action='store_true', help='Explicitly compose a cleanly stopped partial capture; mark it incomplete')
    args = parser.parse_args()
    directory = args.capture
    destination = directory/'gazebo_pip.mp4'
    if destination.exists():
        raise FileExistsError(destination)
    def stamps(view):
        with (directory/f'frame_times_{view}.csv').open() as stream:
            return [float(row['simulation_s']) for row in csv.DictReader(stream)]
    general, follow = stamps('overview'), stamps('follow')
    if not general or general != follow:
        raise ValueError('Camera timestamps differ: do not silently combine unsynchronized frames')
    capture = json.loads((directory/'capture.json').read_text())
    carrier_id = capture['follow_carrier']
    if not isinstance(carrier_id, int) or carrier_id < 0:
        raise ValueError('Capture does not identify its followed carrier')
    partial = bool(capture['errors'])
    expected_stop = all('Preventive render stop: host reserve or explicit request' in error for error in capture['errors'])
    if capture['gazebo_exit_code'] != 0 or (partial and not (args.allow_partial and expected_stop)):
        raise ValueError('Live capture did not close successfully')
    graph = ('[1:v]scale=384:240,drawbox=x=0:y=0:w=iw:h=ih:color=white:t=3[inset];'
             '[0:v][inset]overlay=x=W-w-18:y=18,'
             'drawbox=x=878:y=258:w=384:h=24:color=black@0.75:t=fill,'
             f"drawtext=text='Carro {carrier_id} - seguimiento':x=888:y=262:fontsize=16:fontcolor=white[out]")
    subprocess.run(['ffmpeg','-n','-v','error','-threads','2','-i',str(directory/'gazebo.mp4'),'-threads','2','-i',str(directory/'follow.mp4'),
                    '-filter_complex_threads','1','-filter_complex',graph,'-map','[out]','-c:v','libx264','-threads','2','-preset','fast','-crf','20',
                    '-pix_fmt','yuv420p',str(destination)], check=True)
    probe = subprocess.run(['ffprobe','-v','error','-select_streams','v:0','-count_frames','-show_entries',
                            'stream=width,height,nb_read_frames,duration','-of','json',str(destination)],
                           check=True, text=True, capture_output=True)
    video = json.loads(probe.stdout)['streams'][0]
    subprocess.run(['ffmpeg','-v','error','-xerror','-i',str(destination),'-f','null','-'],check=True)
    passed = int(video['nb_read_frames']) == len(general) and (video['width'],video['height']) == (1280,800)
    report={'passed':passed,'partial_capture':partial,'capture_errors':capture['errors'],'live_cameras':True,'same_simulation_timestamps':True,'frames':len(general),
            'simulation_start_s':general[0],'simulation_end_s':general[-1],'video':video,
            'inset':{'carrier_id':carrier_id,'width':384,'height':240,'camera':'world-fixed offset following simulated pallet'},
            'note':'Both views rendered live by the same Gazebo world; postprocessing only scales and overlays the synchronized videos.'}
    (directory/'pip_verification.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
    if not passed:
        raise RuntimeError('Composed video failed verification')


if __name__ == '__main__':
    main()
