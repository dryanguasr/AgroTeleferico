#!/usr/bin/env python3
"""Prueba real de launch + bridge + ROS: telemetría, objetivos y rechazo."""
import os
from pathlib import Path
import signal
import subprocess
import time
import uuid


def main():
    # Partition/domain isolate this test from existing user simulations.
    os.environ['GZ_PARTITION'] = 'agro_test_'+uuid.uuid4().hex
    os.environ['ROS_DOMAIN_ID'] = '73'
    import rclpy
    from geometry_msgs.msg import PoseStamped
    from std_msgs.msg import Float64MultiArray, Float64
    rclpy.init()
    node = rclpy.create_node('agro_integration_test')
    state = []
    node.create_subscription(Float64MultiArray, '/agro/telemetry', lambda m: state.append(list(m.data)), 10)
    pose_pub = node.create_publisher(PoseStamped, '/agro/target_pose', 10)
    cart_pub = node.create_publisher(Float64, '/agro/goal_x', 10)
    directory = Path('results/ros_integration').resolve()
    directory.mkdir(parents=True, exist_ok=True)

    def wait(predicate, timeout=20, publish=None):
        deadline = time.monotonic()+timeout
        next_publish = 0
        while time.monotonic()<deadline:
            if publish is not None and time.monotonic() >= next_publish:
                publish()
                next_publish = time.monotonic()+.2
            rclpy.spin_once(node, timeout_sec=.05)
            if state and predicate(state[-1]):
                return state[-1]
        raise AssertionError('Timeout esperando estado ROS: '+str(state[-1] if state else 'sin telemetría'))

    for scenario in ['single', 'spider']:
        state.clear()
        with (directory/f'{scenario}.log').open('w') as log:
            process = subprocess.Popen(['ros2', 'launch', 'agro_teleferico', 'pilot.launch.py',
                                        f'scenario:={scenario}', 'gui:=false', f'output:={directory/scenario}.csv'],
                                       stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                wait(lambda d: len(d)==50 and d[0]>1)
                if scenario == 'single':
                    # DDS and Gazebo discovery are independent: receiving telemetry
                    # does not imply that the command bridge is already connected.
                    wait(lambda d: abs(d[13]-12)<1e-6,
                         publish=lambda: cart_pub.publish(Float64(data=12.0)))
                    previous=state[-1][24]
                    wait(lambda d: d[24]>previous and abs(d[13]-12)<1e-6,
                         publish=lambda: cart_pub.publish(Float64(data=100.0)))
                else:
                    goal=PoseStamped();goal.header.frame_id='world'
                    goal.pose.position.x=10.2;goal.pose.position.z=7.68;goal.pose.orientation.w=1.
                    wait(lambda d: abs(d[13]-10.2)<1e-6,
                         publish=lambda: pose_pub.publish(goal))
                    previous=state[-1][24]
                    goal.pose.position.x=100.
                    wait(lambda d: d[24]>previous and abs(d[13]-10.2)<1e-6,
                         publish=lambda: pose_pub.publish(goal))
                print(scenario+': ROS telemetry, accepted goal and rejected goal passed', flush=True)
            except Exception:
                print((directory/f'{scenario}.log').read_text()[-8000:], flush=True)
                raise
            finally:
                os.killpg(process.pid, signal.SIGINT)
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGTERM)
                    process.wait(timeout=5)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
