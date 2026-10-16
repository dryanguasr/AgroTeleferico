import os
import tempfile
from pathlib import Path
import subprocess
from ament_index_python.packages import get_package_share_directory, get_package_prefix
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction, ExecuteProcess, SetEnvironmentVariable
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def start(context):
    scenario = LaunchConfiguration('scenario').perform(context)
    config = LaunchConfiguration('config').perform(context)
    gui = LaunchConfiguration('gui').perform(context).lower() == 'true'
    output = Path(LaunchConfiguration('output').perform(context)).resolve()
    prefix = get_package_prefix('agro_teleferico')
    world = Path(tempfile.mkdtemp(prefix='agro_'))/'world.sdf'
    subprocess.run([os.path.join(prefix, 'lib/agro_teleferico/generate_world.py'),
                    '--config', config, '--scenario', scenario, '--world', str(world), '--output', str(output)], check=True)
    command = ['gz', 'sim', '-r', str(world)]
    if not gui:
        command.insert(2, '-s')
    return [SetEnvironmentVariable('GZ_SIM_SYSTEM_PLUGIN_PATH', os.path.join(prefix, 'lib')+':'+os.environ.get('GZ_SIM_SYSTEM_PLUGIN_PATH', '')),
            ExecuteProcess(cmd=command, output='screen'),
            Node(package='ros_gz_bridge', executable='parameter_bridge', arguments=[
                '/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock',
                '/agro/goal_x@std_msgs/msg/Float64]gz.msgs.Double',
                '/agro/goal_pose@geometry_msgs/msg/PoseStamped]gz.msgs.Pose'],
                remappings=[('/agro/goal_pose', '/agro/goal_pose_bridge')], parameters=[{'use_sim_time': True}]),
            Node(package='agro_teleferico', executable='agro_telemetry_bridge', parameters=[{'use_sim_time': True}]),
            Node(package='agro_teleferico', executable='ros_interface.py', parameters=[{'use_sim_time': True}])]


def generate_launch_description():
    share = get_package_share_directory('agro_teleferico')
    return LaunchDescription([
        DeclareLaunchArgument('scenario', default_value='single', choices=['single', 'double', 'spider']),
        DeclareLaunchArgument('config', default_value=os.path.join(share, 'config/pilot.yaml')),
        DeclareLaunchArgument('gui', default_value='true'),
        DeclareLaunchArgument('output', default_value='results/interactive.csv'),
        OpaqueFunction(function=start)])
