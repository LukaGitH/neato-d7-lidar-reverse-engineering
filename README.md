# Neato D7 LiDAR Reverse Engineering

This repository documents a working tap point and decoder for the LiDAR in a Neato Botvac D7 robot vacuum.

Neato app and cloud support is gone, which makes normal software rescue of these robots unlikely. The useful path is to reuse the hardware for an open robot vacuum platform. The D7 LiDAR is one of the most valuable parts, and this repo shows that it can be read as a standard serial scan stream.

![Neato D7 LiDAR live viewer](assets/neato_d7_lidar_live_viewer.png)

## Current Finding

The D7 LiDAR scan data is available at the output of an LM393 comparator on the stationary side of the LiDAR electronics. In this setup the signal was probed at TP20 and read with a USB-UART adapter.

Confirmed serial settings:

```text
115200 baud
8 data bits
no parity
1 stop bit
non-inverted
LSB first
```

The packet format matches the classic Neato LDS packet structure:

```text
FA II SS SS D0 D0 Q0 Q0 D1 D1 Q1 Q1 D2 D2 Q2 Q2 D3 D3 Q3 Q3 CC CC
```

Each packet contains four 1-degree samples. Packet indexes `0xA0` through `0xF9` provide a complete 360-sample rotation.

## Wiring

Use the USB-UART adapter as a receiver only:

```text
LM393 / TP20 data output -> USB-UART RX
Robot / LiDAR GND       -> USB-UART GND
USB-UART TX             -> not connected
USB-UART VCC            -> not connected
```

Do not power the LiDAR from the USB-UART adapter. Check the signal voltage before connecting it to a UART input.

## Live Viewer

The repository includes a simple Python/Tkinter viewer:

```bash
python tools/neato_d7_live_viewer.py --port COM15
```

On Linux:

```bash
python tools/neato_d7_live_viewer.py --port /dev/ttyUSB0
```

Install the only Python dependency:

```bash
pip install -r requirements.txt
```

The viewer:

- reads the 115200 baud serial byte stream,
- validates classic Neato packet checksums,
- decodes distance, quality, invalid, and strength-warning flags,
- displays a live 2D point cloud,
- reports RPM and packet health.

## Why This Matters

This makes the D7 LiDAR practical to reuse in an open-source robot vacuum build. A future control stack can replace the original cloud-dependent electronics while keeping the valuable mechanical and sensing hardware:

- D7 chassis and dust path,
- drive wheels and motors,
- brush and vacuum motors,
- bumper and cliff sensors,
- dock contacts,
- LiDAR scan data.

The next software step is a ROS2 `sensor_msgs/msg/LaserScan` publisher that collects full rotations and publishes the D7 LiDAR as a standard 2D laser scanner.

## Documentation

Detailed notes are in:

- [docs/NEATO_D7_LIDAR_REVERSE_ENGINEERING.md](docs/NEATO_D7_LIDAR_REVERSE_ENGINEERING.md)

## Status

Working:

- TP20 / LM393 serial tap
- 115200 8N1 decode
- classic LDS checksum validation
- live point-cloud viewer
- approximately 300 RPM scan rate

Not solved yet:

- standalone replacement for the LiDAR motor / inductive power electronics,
- ROS2 driver,
- integration into a full replacement robot control stack.
