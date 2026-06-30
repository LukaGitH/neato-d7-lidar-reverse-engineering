# ROS2 Quickstart

This is the first ROS2 milestone for the Neato D7 LiDAR:

```text
D7 LiDAR -> USB-UART -> ROS2 node -> /scan -> RViz
```

The package in `ros2_ws/src/d7_lidar_ros` publishes `sensor_msgs/msg/LaserScan` from the same 115200 baud Neato LDS packets used by the live viewer.

## Environment

Use Debian WSL if that is already your working Linux environment. If ROS2 packages become painful on Debian, add Ubuntu 24.04 WSL later and keep the same workspace.

You need:

```text
ROS2
python3-serial / pyserial
colcon
USB-UART visible inside WSL as /dev/ttyUSB0 or similar
```

## Build

From the repository root inside WSL:

```bash
cd ros2_ws
colcon build --symlink-install
source install/setup.bash
```

## Run

Replace `/dev/ttyUSB0` with the USB-UART device used by your laptop:

```bash
ros2 run d7_lidar_ros d7_lidar_scan --ros-args -p port:=/dev/ttyUSB0
```

Useful parameters:

```bash
ros2 run d7_lidar_ros d7_lidar_scan --ros-args \
  -p port:=/dev/ttyUSB0 \
  -p frame_id:=laser \
  -p range_max:=6.0 \
  -p angle_offset_deg:=0.0
```

## Inspect

In another terminal:

```bash
source ros2_ws/install/setup.bash
ros2 topic list
ros2 topic hz /scan
ros2 topic echo /scan --once
```

## RViz

```bash
rviz2
```

Set the fixed frame to:

```text
laser
```

Add a `LaserScan` display and select:

```text
/scan
```

## Next

After `/scan` looks correct in RViz, the next milestone is:

```text
/scan -> slam_toolbox -> /map
```

For useful room mapping, the robot will eventually also need wheel odometry published as `/odom`.
