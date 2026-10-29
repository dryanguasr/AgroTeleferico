"""Local ROS adapter contract tests with doubles; these do not validate DDS/Gazebo."""
import importlib.util
import math
from pathlib import Path
import signal
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch


class Stamp:
    def __init__(self):
        self.sec = 0
        self.nanosec = 0

    def __setattr__(self, name, value):
        if name == 'sec':
            assert isinstance(value, int) and -(2**31) <= value < 2**31
        elif name == 'nanosec':
            assert isinstance(value, int) and 0 <= value < 10**9
        super().__setattr__(name, value)


def vector():
    return SimpleNamespace(x=0., y=0., z=0.)


class PoseStamped:
    def __init__(self):
        self.header = SimpleNamespace(frame_id='', stamp=Stamp())
        self.pose = SimpleNamespace(position=vector(), orientation=SimpleNamespace(x=0., y=0., z=0., w=0.))


class TwistStamped:
    def __init__(self, header):
        self.header = header
        self.twist = SimpleNamespace(linear=vector(), angular=vector())


class DataMessage:
    def __init__(self, data=None):
        self.data = data


class Publisher:
    def __init__(self):
        self.messages = []

    def publish(self, message):
        self.messages.append(message)


class Node:
    def __init__(self, name):
        self.publishers = {}
        self.subscriptions = {}
        self.logger = SimpleNamespace(error=Mock())

    def create_publisher(self, message_type, topic, depth):
        self.publishers[topic] = Publisher()
        return self.publishers[topic]

    def create_subscription(self, message_type, topic, callback, depth):
        self.subscriptions[topic] = callback

    def get_logger(self):
        return self.logger


class ExternalShutdownException(Exception):
    pass


def load_interface():
    """Import the production module, replacing only its external ROS imports."""
    modules = {name: ModuleType(name) for name in (
        'rclpy', 'rclpy.node', 'rclpy.executors', 'rclpy.signals', 'geometry_msgs',
        'geometry_msgs.msg', 'std_msgs', 'std_msgs.msg')}
    modules['rclpy.node'].Node = Node
    modules['rclpy.executors'].ExternalShutdownException = ExternalShutdownException
    modules['rclpy.signals'].SignalHandlerOptions = SimpleNamespace(NO=object())
    modules['geometry_msgs.msg'].PoseStamped = PoseStamped
    modules['geometry_msgs.msg'].TwistStamped = TwistStamped
    for name in ('Float64', 'Float64MultiArray', 'Bool'):
        setattr(modules['std_msgs.msg'], name, DataMessage)
    for name in ('init', 'spin_once', 'ok', 'try_shutdown'):
        setattr(modules['rclpy'], name, Mock())
    path = Path(__file__).resolve().parents[1]/'scripts/ros_interface.py'
    spec = importlib.util.spec_from_file_location('agro_ros_interface_under_test', path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules):
        spec.loader.exec_module(module)
    return module


interface = load_interface()


def row():
    data = [float(i) for i in range(50)]
    data[0] = 12.25
    data[4:7] = [math.pi/2, 0., math.pi/2]
    data[23] = 1.
    return data


class TelemetryContract(unittest.TestCase):
    def setUp(self):
        self.node = interface.Interface()

    def published(self):
        return {topic: len(pub.messages) for topic, pub in self.node.publishers.items()}

    def test_valid_row_maps_pose_velocity_and_all_eight_cables(self):
        data = row()
        self.node.state(DataMessage(data))
        p = self.node.pose.messages[0]
        self.assertEqual(p.header.frame_id, 'world')
        self.assertEqual((p.header.stamp.sec, p.header.stamp.nanosec), (12, 250000000))
        self.assertEqual(vars(p.pose.position), dict(zip(('x', 'y', 'z'), data[1:4])))
        # Rz(pi/2) Ry(0) Rx(pi/2) gives q=(w,x,y,z)=(.5,.5,.5,.5).
        for value in vars(p.pose.orientation).values():
            self.assertAlmostEqual(value, .5)
        v = self.node.velocity.messages[0]
        self.assertIs(v.header, p.header)
        self.assertEqual(vars(v.twist.linear), dict(zip(('x', 'y', 'z'), data[7:10])))
        self.assertEqual(vars(v.twist.angular), dict(zip(('x', 'y', 'z'), data[10:13])))
        self.assertEqual(self.node.tensions.messages[0].data, [26., 29., 32., 35., 38., 41., 44., 47.])
        self.assertEqual(self.node.lengths.messages[0].data, [27., 30., 33., 36., 39., 42., 45., 48.])
        self.assertIs(self.node.feasible.messages[0].data, True)
        self.assertEqual(self.published(), {
            '/agro/pose': 1, '/agro/velocity': 1, '/agro/tensions': 1,
            '/agro/lengths': 1, '/agro/feasible': 1, '/agro/goal_pose_bridge': 0})

    def test_zero_angles_and_infeasible_state(self):
        data = row()
        data[4:7] = [0., 0., 0.]
        data[23] = 0.
        self.node.state(DataMessage(data))
        self.assertEqual(vars(self.node.pose.messages[0].pose.orientation), {'x': 0., 'y': 0., 'z': 0., 'w': 1.})
        self.assertIs(self.node.feasible.messages[0].data, False)

    def test_bad_lengths_publish_nothing(self):
        for length in (49, 51):
            with self.subTest(length=length):
                self.node.state(DataMessage([0.]*length))
                self.assertTrue(all(count == 0 for count in self.published().values()))

    def test_nonfinite_values_anywhere_publish_nothing(self):
        for index in range(50):
            for bad in (math.nan, math.inf, -math.inf):
                with self.subTest(index=index, bad=bad):
                    data = row()
                    data[index] = bad
                    self.node.state(DataMessage(data))
                    self.assertTrue(all(count == 0 for count in self.published().values()))

    def test_time_boundaries(self):
        for time_s in (0., -0., math.nextafter(0., 1.), 2**31-1., math.nextafter(float(2**31), 0.)):
            with self.subTest(time_s=time_s):
                data = row()
                data[0] = time_s
                previous_count = len(self.node.pose.messages)
                self.node.state(DataMessage(data))
                self.assertEqual(len(self.node.pose.messages), previous_count + 1)
                stamp = self.node.pose.messages[-1].header.stamp
                self.assertEqual(stamp.sec, int(time_s))
                self.assertTrue(0 <= stamp.nanosec < 10**9)
        before = self.published()
        for time_s in (-1., math.nextafter(0., -1.), float(2**31), 1e100):
            with self.subTest(time_s=time_s):
                data = row()
                data[0] = time_s
                self.node.state(DataMessage(data))
                self.assertEqual(self.published(), before)


class ShutdownContract(unittest.TestCase):
    def run_main(self, spin_error=None, destroy_error=None, shutdown_error=None,
                 already_closed=False, stop_signals=(signal.SIGINT,), signal_during_destroy=False):
        calls = []
        context = {'active': False}
        initial_handlers = {signal.SIGINT: object(), signal.SIGTERM: object()}
        handlers = initial_handlers.copy()

        def set_handler(signum, handler):
            previous = handlers[signum]
            handlers[signum] = handler
            return previous

        def init(*, signal_handler_options):
            self.assertIs(signal_handler_options, interface.SignalHandlerOptions.NO)
            calls.append('init')
            context['active'] = True

        def spin_once(node, *, timeout_sec):
            self.assertEqual(timeout_sec, .1)
            calls.append('spin_once')
            for signum in stop_signals:
                handlers[signum](signum, None)
                self.assertTrue(context['active'], 'signal must not destroy a context during spin_once')
            if already_closed:
                context['active'] = False
            if spin_error is not None:
                raise spin_error
            if not stop_signals:
                context['active'] = False

        def destroy():
            calls.append('destroy')
            if signal_during_destroy:
                handlers[signal.SIGTERM](signal.SIGTERM, None)
            if destroy_error is not None:
                raise destroy_error

        def try_shutdown():
            calls.append('try_shutdown')
            context['active'] = False
            if shutdown_error is not None:
                raise shutdown_error

        fake_node = SimpleNamespace(destroy_node=destroy)
        with patch.object(interface, 'Interface', return_value=fake_node), \
                patch.object(interface.signal, 'signal', side_effect=set_handler), \
                patch.object(interface.rclpy, 'init', side_effect=init), \
                patch.object(interface.rclpy, 'ok', side_effect=lambda: context['active']), \
                patch.object(interface.rclpy, 'spin_once', side_effect=spin_once), \
                patch.object(interface.rclpy, 'try_shutdown', side_effect=try_shutdown):
            try:
                interface.main()
            finally:
                self.assertEqual(calls, ['init', 'spin_once', 'destroy', 'try_shutdown'])
                self.assertFalse(context['active'])
                self.assertEqual(handlers, initial_handlers)

    def test_normal_exit(self):
        self.run_main(stop_signals=())

    def test_sigint_stops_before_context_destruction(self):
        self.run_main()

    def test_sigterm_stops_before_context_destruction(self):
        self.run_main(stop_signals=(signal.SIGTERM,))

    def test_repeated_signals_and_signal_during_cleanup_are_requests_only(self):
        self.run_main(stop_signals=(signal.SIGINT, signal.SIGTERM, signal.SIGINT), signal_during_destroy=True)

    def test_keyboard_interrupt_with_active_context(self):
        self.run_main(spin_error=KeyboardInterrupt())

    def test_keyboard_interrupt_after_external_context_shutdown(self):
        self.run_main(spin_error=KeyboardInterrupt(), already_closed=True)

    def test_external_shutdown(self):
        self.run_main(spin_error=ExternalShutdownException(), already_closed=True, stop_signals=())

    def test_unexpected_spin_exception_is_preserved(self):
        original = RuntimeError('spin failed')
        with self.assertRaises(RuntimeError) as caught:
            self.run_main(spin_error=original, stop_signals=())
        self.assertIs(caught.exception, original)

    def test_unexpected_runtime_error_after_stop_request_is_not_swallowed(self):
        original = RuntimeError('take_message failed')
        with self.assertRaises(RuntimeError) as caught:
            self.run_main(spin_error=original, stop_signals=(signal.SIGINT,))
        self.assertIs(caught.exception, original)

    def test_node_destruction_failure_still_closes_context(self):
        original = RuntimeError('destroy failed')
        with self.assertRaises(RuntimeError) as caught:
            self.run_main(destroy_error=original)
        self.assertIs(caught.exception, original)

    def test_interrupt_during_destruction_still_closes_context(self):
        with self.assertRaises(KeyboardInterrupt):
            self.run_main(destroy_error=KeyboardInterrupt())

    def test_original_error_survives_cleanup_failures(self):
        original = RuntimeError('spin failed')
        with self.assertRaises(RuntimeError) as caught:
            self.run_main(spin_error=original, destroy_error=ValueError('destroy failed'),
                          shutdown_error=ValueError('shutdown failed'))
        self.assertIs(caught.exception, original)
        self.assertEqual(len(original.__notes__), 2)
        self.assertIn('destroy failed', original.__notes__[0])
        self.assertIn('shutdown failed', original.__notes__[1])

    def test_first_cleanup_error_survives_second_cleanup_error(self):
        original = ValueError('destroy failed')
        with self.assertRaises(ValueError) as caught:
            self.run_main(destroy_error=original, shutdown_error=RuntimeError('shutdown failed'))
        self.assertIs(caught.exception, original)
        self.assertIn('shutdown failed', original.__notes__[0])

    def test_caller_handled_exception_does_not_hide_cleanup_failure(self):
        original = RuntimeError('destroy failed')
        try:
            raise ValueError('already handled by caller')
        except ValueError:
            with self.assertRaises(RuntimeError) as caught:
                self.run_main(destroy_error=original)
        self.assertIs(caught.exception, original)

    def test_constructor_failure_still_closes_context(self):
        original = ValueError('node creation failed')
        with patch.object(interface, 'Interface', side_effect=original), \
                patch.object(interface.signal, 'signal') as handlers, \
                patch.object(interface.rclpy, 'init'), \
                patch.object(interface.rclpy, 'try_shutdown') as shutdown, \
                self.assertRaises(ValueError) as caught:
            interface.main()
        shutdown.assert_called_once_with()
        self.assertEqual(handlers.call_count, 4)
        self.assertIs(caught.exception, original)

    def test_initialization_failure_restores_handlers_and_propagates(self):
        original = ValueError('init failed')
        with patch.object(interface, 'Interface') as create, \
                patch.object(interface.signal, 'signal') as handlers, \
                patch.object(interface.rclpy, 'init', side_effect=original), \
                patch.object(interface.rclpy, 'try_shutdown') as shutdown, \
                self.assertRaises(ValueError) as caught:
            interface.main()
        create.assert_not_called()
        shutdown.assert_called_once_with()
        self.assertEqual(handlers.call_count, 4)
        self.assertIs(caught.exception, original)


if __name__ == '__main__':
    unittest.main()
