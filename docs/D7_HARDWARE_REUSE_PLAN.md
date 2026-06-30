# Neato D7 Hardware Reuse Plan

The D7 is best treated as a hardware donor for a new open robot vacuum control stack, not as a robot whose original cloud-dependent control software should be preserved.

## Recommended Architecture

Use a split-control architecture:

- Raspberry Pi 5 or similar Linux SBC for ROS2, mapping, navigation, UI, and Home Assistant integration.
- ESP32, STM32, or RP2040 class microcontroller for motor PWM, encoder counting, bump and cliff sensors, battery telemetry, and emergency stop behavior.
- Dedicated power board for fuses, buck regulators, motor switching, current sensing, and charging supervision.

## Reuse Buckets

| Part | Reuse | Notes |
| --- | --- | --- |
| Chassis, shell, dustbin path | Yes | Valuable D-shape vacuum body and airflow path. |
| Drive wheels and gearmotors | Yes | Reuse with new motor drivers after measuring stall current and encoder signals. |
| Wheel encoders | Likely | Probe output levels and tick rate before final MCU choice. |
| Main brush motor | Yes | Use current sensing for jam detection. |
| Side brush motor | Yes | Simple PWM motor output. |
| Vacuum blower | Yes | High-current load; use a properly rated MOSFET or driver and fuse. |
| LiDAR | Yes | Runs standalone. Pin 17 / TP20 / LM393 output produces classic Neato LDS packets at 115200 baud; pin 18 / TP21 must be held at 5V. |
| Bumper switches | Yes | Usually easy direct MCU inputs. |
| Cliff sensors | Maybe | Reuse if outputs are easy to read; otherwise replace with simple IR or ToF sensors. |
| Battery pack | Maybe | Reuse only if the pack and BMS are healthy and understood. |
| Dock contacts | Yes | Useful mechanically; redesign charge supervision unless original electronics are understood. |
| Original mainboard | Reference only | Useful for probing, not a good long-term dependency. |

## Near-Term Milestones

1. Publish the LiDAR as a ROS2 `LaserScan`.
2. Bench-test wheel motors and encoders.
3. Build a microcontroller motor/sensor board.
4. Create a teleoperated driveable base.
5. Add SLAM and Nav2.
6. Add brush, blower, and cleaning modes.
7. Implement docking and charging last.
