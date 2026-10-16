#!/usr/bin/env python3
"""Objetivos ROS 2 y telemetría tipada; la física y el control interno usan simTime."""
import math
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import PoseStamped, TwistStamped
from std_msgs.msg import Float64, Float64MultiArray, Bool


class Interface(Node):
    def __init__(self):
        super().__init__('agro_interface')
        self.pose = self.create_publisher(PoseStamped, '/agro/pose', 10)
        self.velocity = self.create_publisher(TwistStamped, '/agro/velocity', 10)
        self.tensions = self.create_publisher(Float64MultiArray, '/agro/tensions', 10)
        self.lengths = self.create_publisher(Float64MultiArray, '/agro/lengths', 10)
        self.feasible = self.create_publisher(Bool, '/agro/feasible', 10)
        self.goal = self.create_publisher(PoseStamped, '/agro/goal_pose_bridge', 10)
        self.create_subscription(Float64MultiArray, '/agro/telemetry', self.state, 10)
        self.create_subscription(PoseStamped, '/agro/target_pose', self.target, 10)

    def target(self, msg):
        if msg.header.frame_id not in ('', 'world'):
            self.get_logger().error('target_pose requiere frame_id=world')
            return
        values = [msg.pose.position.x, msg.pose.position.y, msg.pose.position.z,
                  msg.pose.orientation.x, msg.pose.orientation.y, msg.pose.orientation.z, msg.pose.orientation.w]
        if not all(math.isfinite(x) for x in values):
            self.get_logger().error('Objetivo no finito rechazado')
            return
        self.goal.publish(msg)

    def state(self, msg):
        d = msg.data
        if len(d) != 50:
            return
        p = PoseStamped()
        p.header.frame_id = 'world'
        p.header.stamp.sec = int(d[0])
        p.header.stamp.nanosec = int((d[0]-int(d[0]))*1e9)
        p.pose.position.x, p.pose.position.y, p.pose.position.z = d[1:4]
        r, b, y = (v/2 for v in d[4:7])
        cr, sr, cp, sp, cy, sy = math.cos(r), math.sin(r), math.cos(b), math.sin(b), math.cos(y), math.sin(y)
        q = p.pose.orientation
        q.w, q.x = cr*cp*cy+sr*sp*sy, sr*cp*cy-cr*sp*sy
        q.y, q.z = cr*sp*cy+sr*cp*sy, cr*cp*sy-sr*sp*cy
        self.pose.publish(p)
        v = TwistStamped(header=p.header)
        v.twist.linear.x, v.twist.linear.y, v.twist.linear.z = d[7:10]
        v.twist.angular.x, v.twist.angular.y, v.twist.angular.z = d[10:13]
        self.velocity.publish(v)
        self.tensions.publish(Float64MultiArray(data=list(d[26::3])))
        self.lengths.publish(Float64MultiArray(data=list(d[27::3])))
        self.feasible.publish(Bool(data=bool(d[23])))


def main():
    rclpy.init()
    node = Interface()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
