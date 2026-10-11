"""Live reduced-model integration in Gazebo; this is not a recording/replay."""
import os
import subprocess
import sys
from pathlib import Path
from ament_index_python.packages import get_package_share_directory, get_package_prefix
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction, ExecuteProcess, SetEnvironmentVariable
from launch.substitutions import LaunchConfiguration


def start(context):
    def value(k):
        return LaunchConfiguration(k).perform(context)
    prefix = get_package_prefix('agro_teleferico')
    output = Path(value('output')).expanduser().resolve()
    gui = value('gui') == 'true'
    cmd = [sys.executable, os.path.join(prefix, 'lib/agro_teleferico/generate_loop.py'),
           '--config', value('config'), '--output', str(output), '--mode', value('mode')]
    if value('gust') == 'false':
        cmd.append('--no-wind')
    if not gui:
        cmd.append('--stop-at-end')
    subprocess.run(cmd, check=True)
    run = ['gz', 'sim', '-r', str(output/'world.sdf')]
    if not gui:
        run.insert(2, '-s')
    return [SetEnvironmentVariable('GZ_SIM_SYSTEM_PLUGIN_PATH', os.path.join(prefix, 'lib')+os.pathsep+os.environ.get('GZ_SIM_SYSTEM_PLUGIN_PATH', '')),
            ExecuteProcess(cmd=run, output='screen')]


def generate_launch_description():
    share = get_package_share_directory('agro_teleferico')
    return LaunchDescription([
        DeclareLaunchArgument('config', default_value=os.path.join(share, 'config/loop.yaml')),
        DeclareLaunchArgument('output', default_value='results/loop_demo'),
        DeclareLaunchArgument('mode', default_value='central_local', choices=['central_only', 'central_local']),
        DeclareLaunchArgument('gui', default_value='true', choices=['true', 'false']),
        DeclareLaunchArgument('gust', default_value='true', choices=['true', 'false']),
        OpaqueFunction(function=start)])
