import math
import time

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import LaserScan
import serial

from .neato_parser import INDEX_MIN, PacketStream


class D7LidarScanNode(Node):
    def __init__(self):
        super().__init__("d7_lidar_scan")

        self.declare_parameter("port", "/dev/ttyUSB0")
        self.declare_parameter("baud", 115200)
        self.declare_parameter("frame_id", "laser")
        self.declare_parameter("range_min", 0.05)
        self.declare_parameter("range_max", 6.0)
        self.declare_parameter("angle_offset_deg", 0.0)
        self.declare_parameter("min_quality", 0)
        self.declare_parameter("include_strength_warning", True)
        self.declare_parameter("min_points_per_scan", 180)

        self.port = self.get_parameter("port").value
        self.baud = int(self.get_parameter("baud").value)
        self.frame_id = self.get_parameter("frame_id").value
        self.range_min = float(self.get_parameter("range_min").value)
        self.range_max = float(self.get_parameter("range_max").value)
        self.angle_offset_deg = float(self.get_parameter("angle_offset_deg").value)
        self.min_quality = int(self.get_parameter("min_quality").value)
        self.include_strength_warning = bool(
            self.get_parameter("include_strength_warning").value
        )
        self.min_points_per_scan = int(self.get_parameter("min_points_per_scan").value)

        self.publisher = self.create_publisher(LaserScan, "scan", 10)
        self.parser = PacketStream()
        self.ranges = [math.inf] * 360
        self.intensities = [0.0] * 360
        self.seen = set()
        self.latest_rpm = 300.0
        self.scan_start_time = self.get_clock().now()
        self.packets_ok = 0
        self.last_stats_time = time.monotonic()

        self.serial = serial.Serial(self.port, self.baud, timeout=0.02)
        self.get_logger().info(f"Opened {self.port} at {self.baud} baud")

        self.timer = self.create_timer(0.01, self.read_serial)

    def read_serial(self):
        data = self.serial.read(4096)
        if not data:
            self.publish_stats_if_due()
            return

        for index, rpm, points in self.parser.feed(data):
            if index == INDEX_MIN and self.seen:
                self.publish_scan()
                self.reset_scan()

            self.latest_rpm = rpm
            self.packets_ok += 1
            for point in points:
                self.add_point(point)

        self.publish_stats_if_due()

    def add_point(self, point):
        angle = int((point["angle_deg"] + self.angle_offset_deg) % 360)
        distance_m = point["distance_mm"] / 1000.0
        valid = (
            not point["invalid"]
            and distance_m >= self.range_min
            and distance_m <= self.range_max
            and point["quality"] >= self.min_quality
            and (self.include_strength_warning or not point["strength_warning"])
        )

        self.ranges[angle] = distance_m if valid else math.inf
        self.intensities[angle] = float(point["quality"]) if valid else 0.0
        self.seen.add(angle)

    def publish_scan(self):
        if len(self.seen) < self.min_points_per_scan:
            self.get_logger().warn(
                f"Skipping partial scan with {len(self.seen)} points",
                throttle_duration_sec=2.0,
            )
            return

        scan = LaserScan()
        scan.header.stamp = self.scan_start_time.to_msg()
        scan.header.frame_id = self.frame_id
        scan.angle_min = 0.0
        scan.angle_increment = math.radians(1.0)
        scan.angle_max = scan.angle_min + scan.angle_increment * 359
        scan.range_min = self.range_min
        scan.range_max = self.range_max

        rpm = self.latest_rpm if self.latest_rpm > 0 else 300.0
        scan.scan_time = 60.0 / rpm
        scan.time_increment = scan.scan_time / 360.0
        scan.ranges = self.ranges
        scan.intensities = self.intensities
        self.publisher.publish(scan)

    def reset_scan(self):
        self.ranges = [math.inf] * 360
        self.intensities = [0.0] * 360
        self.seen = set()
        self.scan_start_time = self.get_clock().now()

    def publish_stats_if_due(self):
        now = time.monotonic()
        if now - self.last_stats_time >= 2.0:
            self.get_logger().info(
                f"rpm={self.latest_rpm:.1f}, packets={self.packets_ok}/2s, points={len(self.seen)}/360"
            )
            self.packets_ok = 0
            self.last_stats_time = now

    def destroy_node(self):
        try:
            self.serial.close()
        finally:
            super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = D7LidarScanNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
