# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 The OpenFollow Project
"""PSN sender for testing: builds INFO/DATA packets from hand-edited
trackers and sends them once or streams them at a fixed rate.

Runs on the GUI thread with a QTimer. The only mutable inputs (tracker
rows, animation settings) are edited by the GUI, so no locking is needed,
and encoding plus UDP sendto for a handful of trackers takes microseconds.
Encoding is done by pypsn; one multicast socket is kept open while
streaming instead of pypsn.send_psn_packet's socket-per-call. On macOS a
live window drag can block the event loop and pause the stream briefly.
"""

from __future__ import annotations

import contextlib
import math
import socket
import time
from dataclasses import dataclass

import multicast_expert
import pypsn
from PySide6.QtCore import QObject, Qt, QTimer, Signal

from .netutils import PSN_DEFAULT_MCAST_IP, PSN_DEFAULT_PORT

V3_FIELDS = ("pos", "speed", "ori", "accel", "trgtpos")
PSN_VERSION_HIGH = 2
PSN_VERSION_LOW = 3
DEFAULT_RATE_HZ = 30
MAX_RATE_HZ = 60
INFO_INTERVAL_S = 1.0
# pypsn emits 104 bytes per tracker after a 20-byte header and does not
# fragment: 13 trackers = 1372 bytes, 14 would exceed a 1500-byte MTU.
MAX_TRACKERS_PER_PACKET = 13
EFFECTS = ("Sine", "Ramp")

Vec3 = tuple[float, float, float]
ZERO: Vec3 = (0.0, 0.0, 0.0)


@dataclass
class SendTracker:
    tracker_id: int
    name: str = ""
    pos: Vec3 = ZERO
    speed: Vec3 = ZERO
    ori: Vec3 = ZERO
    accel: Vec3 = ZERO
    trgtpos: Vec3 = ZERO
    status: float = 1.0
    timestamp: int | None = None  # None = automatic (ms since sender start)

    def to_psn_info(self) -> pypsn.PsnTrackerInfo:
        return pypsn.PsnTrackerInfo(tracker_id=self.tracker_id, tracker_name=self.name)

    def to_psn_data(self, now_ms: int, pos: Vec3 | None = None) -> pypsn.PsnTracker:
        """Build the pypsn tracker; the encoder needs every vector set, so zeros are wrapped here."""
        return pypsn.PsnTracker(
            tracker_id=self.tracker_id,
            pos=pypsn.PsnVector3(*(self.pos if pos is None else pos)),
            speed=pypsn.PsnVector3(*self.speed),
            ori=pypsn.PsnVector3(*self.ori),
            accel=pypsn.PsnVector3(*self.accel),
            trgtpos=pypsn.PsnVector3(*self.trgtpos),
            status=self.status,
            timestamp=self.timestamp if self.timestamp is not None else now_ms,
        )


@dataclass
class Animation:
    enabled: bool = False
    effect: str = "Sine"
    amplitude: float = 1.0  # metres
    period_s: float = 4.0


def animate_position(pos: Vec3, anim: Animation, t_s: float, phase_offset: float = 0.0) -> Vec3:
    """Offset ``pos`` by the animation effect at time ``t_s``.

    Sine orbits in the XY plane around the edited position, Ramp is a
    sawtooth on X. ``phase_offset`` (0..1) spreads several trackers apart.
    """
    if not anim.enabled or anim.period_s <= 0:
        return pos
    x, y, z = pos
    phase = (t_s / anim.period_s + phase_offset) % 1.0
    a = anim.amplitude
    if anim.effect == "Ramp":
        return (x + a * phase, y, z)
    phi = 2 * math.pi * phase
    return (x + a * math.cos(phi), y + a * math.sin(phi), z)


class PsnSender(QObject):
    """Builds and sends PSN packets. Use from the GUI thread only."""

    error = Signal(str)
    sent = Signal(int)  # frame id of the packet(s) just sent

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.system_name = "PSNView"
        self.trackers: list[SendTracker] = []
        self.animation = Animation()
        self.iface_ip = "127.0.0.1"
        self.mcast_ip = PSN_DEFAULT_MCAST_IP
        self.port = PSN_DEFAULT_PORT
        self.frame_id = 0
        self.data_packet_count = 0
        self.info_packet_count = 0

        self._stack: contextlib.ExitStack | None = None
        self._sock: multicast_expert.McastTxSocket | None = None
        self._t0 = time.monotonic()
        self._last_info_t = -math.inf

        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self._on_tick)

    @property
    def running(self) -> bool:
        return self._timer.isActive()

    # -- public API --------------------------------------------------------
    def start(self, rate_hz: int) -> bool:
        """Start streaming DATA at ``rate_hz`` (INFO every INFO_INTERVAL_S)."""
        if self.running:
            return True
        if not self._open_socket():
            return False
        self._t0 = time.monotonic()
        self._last_info_t = -math.inf
        self._timer.start(max(1, round(1000 / rate_hz)))
        return True

    def stop(self) -> None:
        self._timer.stop()
        self._close_socket()

    def send_once(self) -> bool:
        """Send one INFO and one DATA packet (temporary socket unless streaming)."""
        if not self.trackers:
            return False
        temporary = self._sock is None
        if temporary and not self._open_socket():
            return False
        try:
            frame = self._next_frame()
            t = time.monotonic() - self._t0
            ok = self._send(self._build_info_bytes(frame), info=True) and self._send(self._build_data_bytes(frame, t))
        finally:
            if temporary:
                self._close_socket()
        if ok:
            self.sent.emit(frame)
        return ok

    # -- socket ------------------------------------------------------------
    def _open_socket(self) -> bool:
        if self._sock is not None:
            return True
        stack = contextlib.ExitStack()
        try:
            # enable_external_loopback: multicast_expert otherwise disables
            # IP_MULTICAST_LOOP on non-loopback interfaces, so PSNView's own
            # receiver on the same machine would never see these packets.
            sock = multicast_expert.McastTxSocket(
                socket.AF_INET,
                mcast_ips=[self.mcast_ip],
                iface=self.iface_ip,
                enable_external_loopback=True,
            )
            self._sock = stack.enter_context(sock)
        except (OSError, multicast_expert.MulticastExpertError) as exc:
            stack.close()
            self.error.emit(f"Could not open send socket on {self.iface_ip}: {exc}")
            return False
        self._stack = stack
        return True

    def _close_socket(self) -> None:
        stack, self._stack, self._sock = self._stack, None, None
        if stack is not None:
            try:
                stack.close()
            except OSError:
                pass

    def _send(self, data: bytes, info: bool = False) -> bool:
        if self._sock is None:
            return False
        try:
            self._sock.sendto(data, (self.mcast_ip, self.port))
        except OSError as exc:
            self.stop()
            self.error.emit(f"Send failed: {exc}")
            return False
        if info:
            self.info_packet_count += 1
        else:
            self.data_packet_count += 1
        return True

    # -- packet building ---------------------------------------------------
    def _now_ms(self) -> int:
        return int((time.monotonic() - self._t0) * 1000)

    def _next_frame(self) -> int:
        frame = self.frame_id
        self.frame_id = (frame + 1) % 256  # uint8 on the wire
        return frame

    def _make_info(self, frame_id: int) -> pypsn.PsnInfo:
        return pypsn.PsnInfo(
            timestamp=self._now_ms(),
            version_high=PSN_VERSION_HIGH,
            version_low=PSN_VERSION_LOW,
            frame_id=frame_id,
            packet_count=1,
        )

    def _build_info_bytes(self, frame_id: int) -> bytes:
        packet = pypsn.PsnInfoPacket(
            info=self._make_info(frame_id),
            name=self.system_name,
            trackers=[t.to_psn_info() for t in self.trackers[:MAX_TRACKERS_PER_PACKET]],
        )
        return pypsn.prepare_psn_info_packet_bytes(packet)

    def _build_data_bytes(self, frame_id: int, t_s: float) -> bytes:
        rows = self.trackers[:MAX_TRACKERS_PER_PACKET]
        now_ms = self._now_ms()
        trackers = [
            t.to_psn_data(now_ms, animate_position(t.pos, self.animation, t_s, i / len(rows)))
            for i, t in enumerate(rows)
        ]
        packet = pypsn.PsnDataPacket(info=self._make_info(frame_id), trackers=trackers)
        return pypsn.prepare_psn_data_packet_bytes(packet)

    # -- streaming ---------------------------------------------------------
    def _on_tick(self) -> None:
        if not self.trackers:
            return
        frame = self._next_frame()
        t = time.monotonic() - self._t0
        if t - self._last_info_t >= INFO_INTERVAL_S:
            self._last_info_t = t
            if not self._send(self._build_info_bytes(frame), info=True):
                return
        if self._send(self._build_data_bytes(frame, t)):
            self.sent.emit(frame)
