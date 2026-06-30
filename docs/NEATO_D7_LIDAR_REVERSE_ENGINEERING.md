# Neato D7 LiDAR Reverse Engineering Notes

These are working notes for decoding and using the LiDAR module from a Neato Botvac D7.

## Current status

The Neato D7 LiDAR optical data output has been successfully decoded and the LiDAR has been run standalone from a laptop/USB-UART setup.

The useful data line is the output of an **LM393 comparator** on the stationary/main-side board. This line carries a normal serial byte stream:

```text
115200 baud
8 data bits
no parity
1 stop bit
non-inverted
LSB first
```

The decoded packet format matches the classic Neato LDS packet structure.

## Hardware observations

Observed connections from the LiDAR assembly:

```text
2 wires: motor drive
2 wires: inductive power / coil drive, around 57 kHz
optical link: data/status between spinning head and stationary board
```

Important: the ~57 kHz seen on some lines is not the final LiDAR scan packet stream. The scan data is available after the optical receiver/comparator as a 115200 baud serial stream.

## Standalone connector pinout

Confirmed useful pins on the 20-pin connector:

```text
Pin 20 = LDS_M+
Pin 18 = TP21
Pin 17 = TP20 / DATA
Pin 11 = GND
Pin 9  = LDS_M-
Pin 3  = GND
Pin 2  = 5V
```

Standalone operation requires TP21 to be held high:

```text
Pin 18 / TP21 -> 5V
```

TP21 also worked when connected to 5V through a 4.7k resistor, so it appears to be a logic/control input rather than a heavy power rail.

Power observations:

```text
LiDAR board logic: 5V
LDS motor: around 5V to 6V, depending on target RPM
Target speed: about 300 RPM
```

The LiDAR can produce packets at lower motor speeds, but about 300 RPM is the normal target speed.

## Standalone wiring

```text
5V power        -> pin 2
GND             -> pin 3 and/or pin 11
TP21 enable     -> pin 18 pulled to 5V, direct or through 4.7k
Motor positive  -> pin 20 / LDS_M+
Motor negative  -> pin 9 / LDS_M-
DATA            -> pin 17 / TP20 / DATA -> USB-UART RX
USB-UART GND    -> pin 3 or pin 11
USB-UART TX     -> not connected
USB-UART VCC    -> not connected
```

## Useful probe point

Probe the LM393 output that goes to the large digital IC on the main board.

Recommended logic analyzer / serial settings:

```text
Analyzer: Async Serial
Bit rate: 115200
Bits per frame: 8
Stop bits: 1
Parity: none
Significant bit: least significant bit first
Signal inversion: non-inverted
```

## Wiring for USB-UART live reading

For a live viewer, use a USB-UART adapter connected only as a receiver.

```text
Pin 17 / TP20 / DATA -> USB-UART RX
LiDAR GND            -> USB-UART GND
USB-UART TX          -> not connected
USB-UART VCC         -> not connected
```

Do not power the LiDAR from the USB-UART.

Check signal voltage before connecting:

```text
If LM393 output high is ~3.3 V: use 3.3 V UART input
If LM393 output high is ~5 V: use 5 V-tolerant UART input or a resistor divider
```

## Packet format

Each packet is 22 bytes:

```text
FA II SS SS D0 D0 Q0 Q0 D1 D1 Q1 Q1 D2 D2 Q2 Q2 D3 D3 Q3 Q3 CC CC
```

Meaning:

```text
FA      packet start byte
II      packet index, normally 0xA0 to 0xF9
SS SS   motor speed, little-endian, divided by 64 = RPM
D0/Q0   distance and quality for point 0
D1/Q1   distance and quality for point 1
D2/Q2   distance and quality for point 2
D3/Q3   distance and quality for point 3
CC CC   checksum, little-endian
```

Each packet contains 4 angle samples.

There are 90 packet indexes:

```text
0xA0 ... 0xF9
```

So:

```text
90 packets * 4 samples = 360 samples per rotation
```

## Angle calculation

```python
angle_deg = (packet_index - 0xA0) * 4 + sample_number
```

Where:

```text
packet_index  = II byte
sample_number = 0, 1, 2, or 3
```

Example:

```text
packet index = 0xBA

0xBA - 0xA0 = 26
26 * 4 = 104

sample 0 = 104°
sample 1 = 105°
sample 2 = 106°
sample 3 = 107°
```

## Speed calculation

```python
rpm = speed_raw / 64.0
```

Example from capture:

```text
31 4A = 0x4A31 = 18993
18993 / 64 = 296.765625 RPM
```

## Distance and quality decoding

Each sample uses 4 bytes:

```text
distance_low distance_high quality_low quality_high
```

Distance:

```python
invalid = bool(distance_high & 0x80)
strength_warning = bool(distance_high & 0x40)
distance_mm = distance_low | ((distance_high & 0x3F) << 8)
quality = quality_low | (quality_high << 8)
```

The upper two bits of the distance high byte are flags:

```text
bit 7 = invalid measurement
bit 6 = strength warning
bits 0..5 = upper distance bits
```

## Example decoded packet

Raw packet:

```text
FA BA 31 4A 57 07 60 00 5E 07 36 00 6F 07 36 00 7F 07 37 00 AF 26
```

Decoded:

```text
FA          header
BA          index = 0xBA
31 4A       speed = 0x4A31 / 64 = 296.77 RPM

57 07 60 00   angle 104°, distance 1879 mm, quality 96
5E 07 36 00   angle 105°, distance 1886 mm, quality 54
6F 07 36 00   angle 106°, distance 1903 mm, quality 54
7F 07 37 00   angle 107°, distance 1919 mm, quality 55

AF 26       checksum
```

## Checksum

Classic Neato LDS checksum:

```python
def neato_checksum(packet):
    chk32 = 0

    for i in range(10):
        word = packet[2 * i] | (packet[2 * i + 1] << 8)
        chk32 = (chk32 << 1) + word

    chk32 = (chk32 & 0x7FFF) + (chk32 >> 15)
    chk32 = chk32 & 0x7FFF

    return chk32
```

Packet is valid when:

```python
expected = packet[20] | (packet[21] << 8)
calculated = neato_checksum(packet)
valid = calculated == expected
```

## Minimal parser

```python
import math

PACKET_LEN = 22
START_BYTE = 0xFA
INDEX_MIN = 0xA0
INDEX_MAX = 0xF9

def neato_checksum(packet):
    chk32 = 0
    for i in range(10):
        word = packet[2 * i] | (packet[2 * i + 1] << 8)
        chk32 = (chk32 << 1) + word

    chk32 = (chk32 & 0x7FFF) + (chk32 >> 15)
    chk32 = chk32 & 0x7FFF
    return chk32

def decode_packet(packet):
    if len(packet) != PACKET_LEN:
        return None

    if packet[0] != START_BYTE:
        return None

    index = packet[1]

    if not (INDEX_MIN <= index <= INDEX_MAX):
        return None

    expected = packet[20] | (packet[21] << 8)
    calculated = neato_checksum(packet)

    if calculated != expected:
        return None

    rpm_raw = packet[2] | (packet[3] << 8)
    rpm = rpm_raw / 64.0

    base_angle = (index - INDEX_MIN) * 4
    points = []

    for n in range(4):
        offset = 4 + n * 4

        distance_low = packet[offset]
        distance_high = packet[offset + 1]
        quality_low = packet[offset + 2]
        quality_high = packet[offset + 3]

        invalid = bool(distance_high & 0x80)
        strength_warning = bool(distance_high & 0x40)

        distance_mm = distance_low | ((distance_high & 0x3F) << 8)
        quality = quality_low | (quality_high << 8)
        angle_deg = base_angle + n

        if not invalid:
            angle_rad = math.radians(angle_deg)
            x_mm = distance_mm * math.cos(angle_rad)
            y_mm = distance_mm * math.sin(angle_rad)

            points.append({
                "angle_deg": angle_deg,
                "distance_mm": distance_mm,
                "quality": quality,
                "rpm": rpm,
                "x_mm": x_mm,
                "y_mm": y_mm,
                "strength_warning": strength_warning,
            })

    return rpm, points
```

## Live viewer app

A Python/Tkinter live viewer was created for this project:

```text
neato_d7_live_viewer.py
```

Requirements:

```bash
pip install pyserial
```

Run:

```bash
python neato_d7_live_viewer.py --port COM5
```

Replace `COM5` with the correct serial port, for example:

```bash
python neato_d7_live_viewer.py --port /dev/ttyUSB0
```

## Saleae use

Saleae Logic 2 is excellent for capture and verification.

Recommended use:

```text
Probe LM393 output
Add Async Serial analyzer
115200 baud, 8N1, non-inverted
Export decoded bytes or CSV
```

Saleae can be used to decode the data, but for a real live point-cloud viewer a USB-UART is simpler and better because it provides a continuous byte stream.

## Confirmed capture results

From a decoded capture:

```text
3960 decoded points
3960 / 360 = 11 full rotations
speed ≈ 296.77 RPM
packet indexes observed: 0xA0 to 0xF9
checksum OK on valid packets
```

Example decoded points:

```text
104°  1879 mm  quality 96
105°  1886 mm  quality 54
106°  1903 mm  quality 54
107°  1919 mm  quality 55
```

## Next project steps

1. Tap LM393 output with USB-UART RX.
2. Run the live viewer.
3. Confirm point cloud orientation.
4. Add angle offset if robot-forward is not 0°.
5. Decide whether to keep original robot board powered, or later reproduce:
   - motor drive,
   - inductive power drive,
   - optical receiver circuit.
