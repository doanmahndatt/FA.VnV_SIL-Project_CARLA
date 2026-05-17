import rclpy
from rclpy.node import Node
from nav_msgs.msg import Odometry
from autoware_auto_control_msgs.msg import AckermannControlCommand
from threading import Lock
import time

class Ros2Collector(Node):
    """
    Collects observable signals from ROS2 (Autoware or OEM ADAS SW).
    Black-box safe.
    """

    def __init__(self):
        super().__init__("ros2_kpi_collector")

        self.lock = Lock()
        self.last_odom = None
        self.last_control = None

        self.create_subscription(
            Odometry,
            "/localization/kinematic_state",
            self._odom_cb,
            10
        )

        self.create_subscription(
            AckermannControlCommand,
            "/control/command/control_cmd",
            self._control_cb,
            10
        )

    # ------------------------------------------------
    # Callbacks
    # ------------------------------------------------
    def _odom_cb(self, msg):
        with self.lock:
            self.last_odom = msg

    def _control_cb(self, msg):
        with self.lock:
            self.last_control = msg

    # ------------------------------------------------
    # Signal extraction
    # ------------------------------------------------
    def get_timestamp(self):
        return time.time()

    def get_ego_speed(self):
        if not self.last_odom:
            return None
        v = self.last_odom.twist.twist.linear
        return (v.x**2 + v.y**2 + v.z**2) ** 0.5

    def get_longitudinal_accel_cmd(self):
        if not self.last_control:
            return None
        return self.last_control.longitudinal.acceleration

    # ------------------------------------------------
    # Unified sample API
    # ------------------------------------------------
    def collect_sample(self):
        with self.lock:
            return {
                "timestamp": self.get_timestamp(),
                "signals": {
                    "ego_speed": self.get_ego_speed(),
                    "acc_cmd": self.get_longitudinal_accel_cmd()
                }
            }