#!/usr/bin/env python3
"""
Neato D7 / LDS live LiDAR viewer

Reads classic Neato LDS packets:
FA II SS SS D0 D0 Q0 Q0 ... D3 D3 Q3 Q3 CC CC

Confirmed with Neato D7 optical LM393 output:
115200 baud, 8N1, non-inverted.

Requirements:
    pip install pyserial

Run:
    python neato_d7_live_viewer.py --port COM15
or:
    python neato_d7_live_viewer.py --port /dev/ttyUSB0

Wiring:
    LiDAR LM393 data output -> USB-UART RX
    Robot/LiDAR GND         -> USB-UART GND
    Do NOT connect USB-UART TX unless you know you need it.
"""

import argparse
import math
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    serial = None


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
    """Return (rpm, list_of_points) or None if invalid.

    Point dict:
        angle_deg, distance_mm, quality, invalid, strength_warning
    """
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
    pts = []

    for n in range(4):
        off = 4 + n * 4

        dist_low = packet[off]
        dist_high = packet[off + 1]
        quality = packet[off + 2] | (packet[off + 3] << 8)

        invalid = bool(dist_high & 0x80)
        strength_warning = bool(dist_high & 0x40)

        # Lower 14 bits are distance in mm.
        distance_mm = dist_low | ((dist_high & 0x3F) << 8)
        angle_deg = (base_angle + n) % 360

        pts.append({
            "angle_deg": angle_deg,
            "distance_mm": distance_mm,
            "quality": quality,
            "invalid": invalid,
            "strength_warning": strength_warning,
            "rpm": rpm,
        })

    return rpm, pts


class SerialReader(threading.Thread):
    def __init__(self, port, baud, out_queue, stop_event):
        super().__init__(daemon=True)
        self.port = port
        self.baud = baud
        self.out_queue = out_queue
        self.stop_event = stop_event

    def run(self):
        if serial is None:
            self.out_queue.put(("error", "pyserial is not installed. Run: pip install pyserial"))
            return

        try:
            ser = serial.Serial(
                self.port,
                self.baud,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.05,
            )
        except Exception as e:
            self.out_queue.put(("error", f"Could not open serial port {self.port}: {e}"))
            return

        self.out_queue.put(("status", f"Opened {self.port} at {self.baud} baud"))

        buf = bytearray()
        packets_ok = 0
        packets_bad = 0
        last_stat = time.time()

        try:
            while not self.stop_event.is_set():
                data = ser.read(4096)
                if data:
                    buf.extend(data)

                # Keep buffer bounded if no valid packets are found.
                if len(buf) > 20000:
                    del buf[:-2000]

                while len(buf) >= PACKET_LEN:
                    # Find start byte.
                    if buf[0] != START_BYTE:
                        try:
                            pos = buf.index(START_BYTE)
                            del buf[:pos]
                        except ValueError:
                            buf.clear()
                            break

                    if len(buf) < PACKET_LEN:
                        break

                    packet = bytes(buf[:PACKET_LEN])
                    decoded = decode_packet(packet)

                    if decoded is None:
                        packets_bad += 1
                        # Move one byte and search again.
                        del buf[0]
                    else:
                        packets_ok += 1
                        del buf[:PACKET_LEN]
                        rpm, pts = decoded
                        self.out_queue.put(("points", rpm, pts))

                now = time.time()
                if now - last_stat > 1.0:
                    self.out_queue.put(("stats", packets_ok, packets_bad))
                    packets_ok = 0
                    packets_bad = 0
                    last_stat = now

        finally:
            try:
                ser.close()
            except Exception:
                pass
            self.out_queue.put(("status", "Serial closed"))


class LidarViewer(tk.Tk):
    def __init__(self, port="", baud=115200):
        super().__init__()
        self.title("Neato D7 LiDAR Live Viewer")
        self.geometry("980x760")

        self.port_var = tk.StringVar(value=port)
        self.baud_var = tk.IntVar(value=baud)
        self.status_var = tk.StringVar(value="Disconnected")
        self.rpm_var = tk.StringVar(value="RPM: --")
        self.packet_var = tk.StringVar(value="Packets/s: --")
        self.range_var = tk.IntVar(value=5000)
        self.min_quality_var = tk.IntVar(value=0)
        self.show_warn_var = tk.BooleanVar(value=True)
        self.angle_offset_var = tk.IntVar(value=0)

        self.q = queue.Queue()
        self.stop_event = threading.Event()
        self.reader = None

        # latest scan: angle -> point
        self.scan = {}
        self.last_draw = 0
        self.total_ok_rate = 0
        self.total_bad_rate = 0

        self._build_ui()
        self.after(30, self._poll_queue)
        self.after(80, self._draw)

    def _build_ui(self):
        top = ttk.Frame(self)
        top.pack(side=tk.TOP, fill=tk.X, padx=8, pady=6)

        ttk.Label(top, text="Port:").pack(side=tk.LEFT)
        ports = self._list_ports()
        self.port_combo = ttk.Combobox(top, textvariable=self.port_var, values=ports, width=18)
        self.port_combo.pack(side=tk.LEFT, padx=(4, 10))

        ttk.Button(top, text="Refresh", command=self._refresh_ports).pack(side=tk.LEFT, padx=(0, 10))

        ttk.Label(top, text="Baud:").pack(side=tk.LEFT)
        ttk.Entry(top, textvariable=self.baud_var, width=8).pack(side=tk.LEFT, padx=(4, 10))

        self.connect_btn = ttk.Button(top, text="Connect", command=self._toggle_connect)
        self.connect_btn.pack(side=tk.LEFT, padx=(0, 10))

        ttk.Label(top, textvariable=self.status_var).pack(side=tk.LEFT, padx=(10, 0))

        opts = ttk.Frame(self)
        opts.pack(side=tk.TOP, fill=tk.X, padx=8, pady=2)

        ttk.Label(opts, textvariable=self.rpm_var).pack(side=tk.LEFT, padx=(0, 16))
        ttk.Label(opts, textvariable=self.packet_var).pack(side=tk.LEFT, padx=(0, 16))

        ttk.Label(opts, text="Max range mm:").pack(side=tk.LEFT)
        ttk.Entry(opts, textvariable=self.range_var, width=7).pack(side=tk.LEFT, padx=(4, 16))

        ttk.Label(opts, text="Min quality:").pack(side=tk.LEFT)
        ttk.Entry(opts, textvariable=self.min_quality_var, width=5).pack(side=tk.LEFT, padx=(4, 16))

        ttk.Label(opts, text="Angle offset °:").pack(side=tk.LEFT)
        ttk.Entry(opts, textvariable=self.angle_offset_var, width=5).pack(side=tk.LEFT, padx=(4, 16))

        ttk.Checkbutton(opts, text="Show strength-warning points", variable=self.show_warn_var).pack(side=tk.LEFT)

        self.canvas = tk.Canvas(self, bg="black", highlightthickness=0)
        self.canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8, pady=8)

        bottom = ttk.Frame(self)
        bottom.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=(0, 8))
        ttk.Label(
            bottom,
            text="Wiring: LM393 data output -> USB-UART RX, GND -> GND. Settings: 115200, 8N1, non-inverted."
        ).pack(side=tk.LEFT)

    def _list_ports(self):
        if serial is None:
            return []
        return [p.device for p in serial.tools.list_ports.comports()]

    def _refresh_ports(self):
        self.port_combo["values"] = self._list_ports()

    def _toggle_connect(self):
        if self.reader and self.reader.is_alive():
            self.stop_event.set()
            self.reader = None
            self.connect_btn.configure(text="Connect")
            self.status_var.set("Disconnecting...")
            return

        port = self.port_var.get().strip()
        if not port:
            messagebox.showerror("No port", "Select or type a serial port, for example COM5 or /dev/ttyUSB0.")
            return

        self.scan.clear()
        self.stop_event = threading.Event()
        self.reader = SerialReader(port, int(self.baud_var.get()), self.q, self.stop_event)
        self.reader.start()
        self.connect_btn.configure(text="Disconnect")

    def _poll_queue(self):
        try:
            while True:
                msg = self.q.get_nowait()
                kind = msg[0]

                if kind == "error":
                    self.status_var.set(msg[1])
                    messagebox.showerror("Serial error", msg[1])
                    self.connect_btn.configure(text="Connect")

                elif kind == "status":
                    self.status_var.set(msg[1])

                elif kind == "stats":
                    ok, bad = msg[1], msg[2]
                    self.total_ok_rate = ok
                    self.total_bad_rate = bad
                    self.packet_var.set(f"Packets/s: OK {ok}, bad {bad}")

                elif kind == "points":
                    rpm, pts = msg[1], msg[2]
                    self.rpm_var.set(f"RPM: {rpm:.2f}")
                    for p in pts:
                        self.scan[p["angle_deg"]] = p

        except queue.Empty:
            pass

        self.after(30, self._poll_queue)

    def _draw(self):
        w = max(100, self.canvas.winfo_width())
        h = max(100, self.canvas.winfo_height())
        cx = w / 2
        cy = h / 2

        try:
            max_range = max(500, int(self.range_var.get()))
        except Exception:
            max_range = 5000

        try:
            min_quality = max(0, int(self.min_quality_var.get()))
        except Exception:
            min_quality = 0

        try:
            angle_offset = int(self.angle_offset_var.get())
        except Exception:
            angle_offset = 0

        scale = min(w, h) * 0.46 / max_range

        self.canvas.delete("all")

        # Range rings
        for r in range(1000, max_range + 1, 1000):
            rr = r * scale
            self.canvas.create_oval(cx - rr, cy - rr, cx + rr, cy + rr, outline="#222222")
            self.canvas.create_text(cx + 4, cy - rr, text=f"{r//1000}m", fill="#555555", anchor="nw")

        self.canvas.create_line(cx, 0, cx, h, fill="#222222")
        self.canvas.create_line(0, cy, w, cy, fill="#222222")

        valid_count = 0
        for angle, p in list(self.scan.items()):
            if p["invalid"]:
                continue
            if p["distance_mm"] <= 0 or p["distance_mm"] > max_range:
                continue
            if p["quality"] < min_quality:
                continue
            if p["strength_warning"] and not self.show_warn_var.get():
                continue

            a = math.radians((p["angle_deg"] + angle_offset) % 360)
            x = p["distance_mm"] * math.cos(a)
            y = p["distance_mm"] * math.sin(a)

            sx = cx + x * scale
            sy = cy - y * scale

            # Keep colors simple and readable.
            color = "#ff9900" if p["strength_warning"] else "#00ff66"
            self.canvas.create_oval(sx - 2, sy - 2, sx + 2, sy + 2, fill=color, outline="")
            valid_count += 1

        # Robot center and forward direction
        self.canvas.create_oval(cx - 5, cy - 5, cx + 5, cy + 5, fill="#66aaff", outline="")
        self.canvas.create_line(cx, cy, cx + 45, cy, fill="#66aaff", arrow=tk.LAST)

        self.canvas.create_text(
            10, 10,
            text=f"Valid points: {valid_count} / {len(self.scan)}    Max range: {max_range} mm",
            fill="white",
            anchor="nw",
        )

        self.after(80, self._draw)

    def destroy(self):
        self.stop_event.set()
        super().destroy()


def main():
    parser = argparse.ArgumentParser(description="Live viewer for Neato D7 / classic LDS packets.")
    parser.add_argument("--port", default="", help="Serial port, e.g. COM5 or /dev/ttyUSB0")
    parser.add_argument("--baud", default=115200, type=int, help="Baud rate, default 115200")
    args = parser.parse_args()

    app = LidarViewer(port=args.port, baud=args.baud)
    app.mainloop()


if __name__ == "__main__":
    main()
