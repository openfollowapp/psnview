# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 The OpenFollow Project
"""PSN receiver: background thread that joins the multicast group,
parses packets with pypsn and forwards them to the GUI via Qt signals.

We run our own receive loop (instead of pypsn.Receiver) for a clean,
silent shutdown and per-packet statistics, but reuse pypsn's socket
setup and packet parsing.
"""

from __future__ import annotations

from pypsn import PsnDataPacket, PsnInfoPacket, get_socket, parse_psn_packet
from PySide6.QtCore import QObject, QThread, Signal

RECV_TIMEOUT_S = 0.5
MAX_PSN_PACKET_SIZE = 1500


class PsnReceiverWorker(QObject):
    """Worker object living in a QThread. Receives and parses PSN packets."""

    info_received = Signal(object)  # PsnInfoPacket
    data_received = Signal(object)  # PsnDataPacket
    error = Signal(str)
    stopped = Signal()

    def __init__(self, iface_ip: str, mcast_port: int) -> None:
        super().__init__()
        self._iface_ip = iface_ip
        self._mcast_port = mcast_port
        self._running = False

    def stop(self) -> None:
        self._running = False

    def run(self) -> None:
        sock = get_socket(self._iface_ip, self._mcast_port)
        if sock is None:
            self.error.emit(
                f"Could not open socket on {self._iface_ip}:{self._mcast_port} "
                "(interface down or multicast join failed)"
            )
            self.stopped.emit()
            return

        sock.settimeout(RECV_TIMEOUT_S)
        self._running = True
        try:
            while self._running:
                try:
                    data, _addr = sock.recvfrom(MAX_PSN_PACKET_SIZE)
                except TimeoutError:
                    continue
                except OSError as exc:
                    if self._running:
                        self.error.emit(f"Network error: {exc}")
                    break

                try:
                    packet = parse_psn_packet(data)
                except Exception as exc:  # malformed/foreign packet: skip
                    self.error.emit(f"Parse error: {exc}")
                    continue

                if isinstance(packet, PsnDataPacket):
                    self.data_received.emit(packet)
                elif isinstance(packet, PsnInfoPacket):
                    self.info_received.emit(packet)
        finally:
            try:
                sock.close()
            except OSError:
                pass
            self.stopped.emit()


class PsnReceiver(QObject):
    """Owns the QThread + worker pair. Start/stop from the GUI thread."""

    info_received = Signal(object)
    data_received = Signal(object)
    error = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: PsnReceiverWorker | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.isRunning()

    def start(self, iface_ip: str, mcast_port: int) -> None:
        if self.running:
            return
        self._thread = QThread()
        self._worker = PsnReceiverWorker(iface_ip, mcast_port)
        self._worker.moveToThread(self._thread)

        self._worker.info_received.connect(self.info_received)
        self._worker.data_received.connect(self.data_received)
        self._worker.error.connect(self.error)
        self._worker.stopped.connect(self._thread.quit)
        self._thread.started.connect(self._worker.run)

        self._thread.start()

    def stop(self) -> None:
        if self._worker is not None:
            self._worker.stop()
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(2000)
        self._worker = None
        self._thread = None
