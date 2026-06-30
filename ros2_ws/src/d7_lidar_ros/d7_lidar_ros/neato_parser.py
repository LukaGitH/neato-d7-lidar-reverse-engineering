PACKET_LEN = 22
START_BYTE = 0xFA
INDEX_MIN = 0xA0
INDEX_MAX = 0xF9


def neato_checksum(packet: bytes) -> int:
    """Classic Neato XV/LDS checksum over a 22-byte packet."""
    chk32 = 0
    for i in range(10):
        word = packet[2 * i] | (packet[2 * i + 1] << 8)
        chk32 = (chk32 << 1) + word

    chk32 = (chk32 & 0x7FFF) + (chk32 >> 15)
    chk32 = chk32 & 0x7FFF
    return chk32


def decode_packet(packet: bytes):
    """Return (index, rpm, points) for a valid 22-byte packet, else None."""
    if len(packet) != PACKET_LEN or packet[0] != START_BYTE:
        return None

    index = packet[1]
    if not (INDEX_MIN <= index <= INDEX_MAX):
        return None

    expected = packet[20] | (packet[21] << 8)
    if neato_checksum(packet) != expected:
        return None

    rpm_raw = packet[2] | (packet[3] << 8)
    rpm = rpm_raw / 64.0
    base_angle = (index - INDEX_MIN) * 4
    points = []

    for sample in range(4):
        offset = 4 + sample * 4
        dist_low = packet[offset]
        dist_high = packet[offset + 1]
        quality = packet[offset + 2] | (packet[offset + 3] << 8)

        invalid = bool(dist_high & 0x80)
        strength_warning = bool(dist_high & 0x40)
        distance_mm = dist_low | ((dist_high & 0x3F) << 8)
        angle_deg = (base_angle + sample) % 360

        points.append(
            {
                "angle_deg": angle_deg,
                "distance_mm": distance_mm,
                "quality": quality,
                "invalid": invalid,
                "strength_warning": strength_warning,
            }
        )

    return index, rpm, points


class PacketStream:
    """Incremental parser for classic Neato LDS packets."""

    def __init__(self):
        self.buffer = bytearray()

    def feed(self, data: bytes):
        self.buffer.extend(data)
        packets = []

        if len(self.buffer) > 20000:
            del self.buffer[:-2000]

        while len(self.buffer) >= PACKET_LEN:
            if self.buffer[0] != START_BYTE:
                try:
                    pos = self.buffer.index(START_BYTE)
                    del self.buffer[:pos]
                except ValueError:
                    self.buffer.clear()
                    break

            if len(self.buffer) < PACKET_LEN:
                break

            packet = bytes(self.buffer[:PACKET_LEN])
            decoded = decode_packet(packet)
            if decoded is None:
                del self.buffer[0]
                continue

            del self.buffer[:PACKET_LEN]
            packets.append(decoded)

        return packets
