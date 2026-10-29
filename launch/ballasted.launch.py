"""Select one of the three single-span worlds. Use the Windows guard on shared hosts."""
import os
import subprocess
import sys
from pathlib import Path
from ament_index_python.packages import get_package_prefix
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument,OpaqueFunction,ExecuteProcess,SetEnvironmentVariable
from launch.substitutions import LaunchConfiguration

def start(context):
    def value(k):return LaunchConfiguration(k).perform(context)
    prefix=Path(get_package_prefix('agro_teleferico'))
    out=Path(value('output')).expanduser().resolve();gui=value('gui')=='true'
    command=[sys.executable,str(prefix/'lib/agro_teleferico/generate_ballasted.py'),
             '--scenario',value('scenario'),'--output',str(out),'--fill',value('fill')]
    if gui:command.append('--gui')
    subprocess.run(command,check=True)
    run=['gz','sim','-r',str(out/'generated/world.sdf')]
    if not gui:run.insert(2,'-s')
    return [SetEnvironmentVariable('GZ_SIM_SYSTEM_PLUGIN_PATH',str(prefix/'lib')+os.pathsep+os.environ.get('GZ_SIM_SYSTEM_PLUGIN_PATH','')),
            ExecuteProcess(cmd=run,output='screen')]

def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('scenario',default_value='buitrago_patio',choices=['buitrago_patio','buitrago_entre_pisos','ladera_agricola']),
        DeclareLaunchArgument('output',default_value='results/ballasted_new'),
        DeclareLaunchArgument('fill',default_value='0.8'),
        DeclareLaunchArgument('gui',default_value='false',choices=['true','false']),
        OpaqueFunction(function=start)])
