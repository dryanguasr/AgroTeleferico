#!/usr/bin/env python3
"""Abre Gazebo y captura una cámara de inspección (requiere WSLg o DISPLAY)."""
import argparse
import os
from pathlib import Path
import signal
import subprocess
import threading
import time
import uuid
import xml.etree.ElementTree as ET
import yaml
from PIL import Image
from ament_index_python.packages import get_package_prefix
from generate_world import generate


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario',choices=['single','double','spider'],required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--headless',action='store_true')
    parser.add_argument('--video',action='store_true',help='Graba 120 s simulados con cámara de Gazebo, acelerados a 20 fps')
    args=parser.parse_args()
    os.environ['GZ_PARTITION']='agro_capture_'+uuid.uuid4().hex
    os.environ['GZ_SIM_SYSTEM_PLUGIN_PATH']=str(Path(get_package_prefix('agro_teleferico'))/'lib')
    from gz.transport13 import Node
    from gz.msgs10.image_pb2 import Image as ImageMessage
    directory=Path(args.output).resolve();directory.mkdir(parents=True,exist_ok=True)
    config=yaml.safe_load(Path('config/pilot.yaml').read_text())
    world=generate(config,args.scenario,directory/'capture.sdf',directory/'telemetry.csv')
    tree=ET.parse(world);root=tree.getroot().find('world')
    root.find('physics/real_time_factor').text='0' if args.video else '1'
    root.append(ET.fromstring('''<plugin filename="gz-sim-sensors-system" name="gz::sim::systems::Sensors"><render_engine>ogre2</render_engine></plugin>'''))
    root.append(ET.fromstring('''<model name="inspection_camera"><static>true</static><pose>29 -27 19 0 .35 2.18</pose><link name="link"><sensor name="camera" type="camera"><always_on>true</always_on><update_rate>5</update_rate><topic>/agro/inspection</topic><camera><horizontal_fov>1.05</horizontal_fov><image><width>1280</width><height>800</height><format>R8G8B8</format></image><clip><near>.1</near><far>100</far></clip></camera></sensor></link></model>'''))
    tree.write(world,encoding='unicode')
    received=threading.Event();node=Node()
    encoder=None;frame_times=[]
    if args.video:
        encoder=subprocess.Popen(['ffmpeg','-y','-loglevel','error','-f','rawvideo','-pixel_format','rgb24','-video_size','1280x800','-framerate','20','-i','-','-c:v','libx264','-preset','fast','-crf','23','-pix_fmt','yuv420p',str(directory/'gazebo.mp4')],stdin=subprocess.PIPE)
    def capture(msg):
        if received.is_set():
            return
        stamp=msg.header.stamp.sec+msg.header.stamp.nsec*1e-9
        if args.video:
            encoder.stdin.write(msg.data)
            frame_times.append(stamp)
        if stamp>=3 and not (directory/'gazebo.png').exists():
            Image.frombytes('RGB',(msg.width,msg.height),msg.data).save(directory/'gazebo.png')
        if stamp>=(120 if args.video else 3):
            received.set()
    node.subscribe(ImageMessage,'/agro/inspection',capture)
    command=['gz','sim','-r','-v','3',str(world)]
    if args.headless: command.insert(2,'-s')
    with (directory/'gui.log').open('w') as log:
        process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        try:
            if not received.wait(timeout=300 if args.video else 50):
                raise RuntimeError('No se recibió imagen de Gazebo; revisar gui.log')
            print('Rendered scene: '+str(directory/'gazebo.png'),flush=True)
        finally:
            os.killpg(process.pid,signal.SIGINT)
            try: process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid,signal.SIGTERM)
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=5)
            if encoder:
                encoder.stdin.close();encoder.wait(timeout=30)
                (directory/'frame_times.csv').write_text('simulation_time\n'+'\n'.join(str(t) for t in frame_times))
                if encoder.returncode!=0 or len(frame_times)<500:
                    raise RuntimeError('Grabación incompleta; revisar frame_times.csv')


if __name__=='__main__':
    main()
