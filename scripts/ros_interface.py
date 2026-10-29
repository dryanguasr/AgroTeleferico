#!/usr/bin/env python3
"""Objetivos ROS 2 y telemetría tipada; la física y el control interno usan simTime."""
import math
import signal
import rclpy
from rclpy.node import Node
from rclpy.executors import ExternalShutdownException
from rclpy.signals import SignalHandlerOptions
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
        # Validate the complete row before publishing any derived message.
        # builtin_interfaces/Time uses signed int32 seconds and nanoseconds
        # in [0, 1e9); this interface accepts only nonnegative simulation time.
        if len(d) != 50 or not all(math.isfinite(value) for value in d):
            return
        if not 0 <= d[0] < 2**31:
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
    node = None
    original_error = None
    stop_requested = False
    previous_handlers = {}

    def request_stop(signum, frame):
        nonlocal stop_requested
        stop_requested = True

    try:
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous_handlers[signum] = signal.signal(signum, request_stop)
        # Keep the context alive while a subscription callback is being taken.
        # Our handlers request a stop; cleanup follows the last spin_once.
        rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
        node = Interface()
        while not stop_requested and rclpy.ok():
            rclpy.spin_once(node, timeout_sec=.1)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    except BaseException as error:
        original_error = error
        raise
    finally:
        cleanup_errors = []
        # External code may already have closed the context. Always attempt
        # destruction, idempotent shutdown, and restoration of our handlers.
        cleanup = ([node.destroy_node] if node is not None else []) + [rclpy.try_shutdown]
        cleanup += [lambda signum=signum, handler=handler: signal.signal(signum, handler)
                    for signum, handler in previous_handlers.items()]
        for close in cleanup:
            try:
                close()
            except BaseException as error:
                cleanup_errors.append(error)
        if cleanup_errors:
            primary = original_error if original_error is not None else cleanup_errors.pop(0)
            for error in cleanup_errors:
                primary.add_note(f'ROS cleanup failed: {error!r}')
            if original_error is None:
                raise primary


if __name__ == '__main__':
    main()
