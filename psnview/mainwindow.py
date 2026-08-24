# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 The OpenFollow Project
"""PSNView main window: connection toolbar, live tracker table, status bar,
and the Send PSN test dialog."""

from __future__ import annotations

import time

from PySide6.QtCore import QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QComboBox,
    QHeaderView,
    QLabel,
    QMainWindow,
    QSpinBox,
    QTableView,
    QToolBar,
)

from . import __version__
from .model import TrackerStore, TrackerTableModel
from .netutils import PSN_DEFAULT_MCAST_IP, PSN_DEFAULT_PORT, list_interface_ips
from .receiver import PsnReceiver
from .senddialog import SendDialog

GUI_REFRESH_MS = 66  # ~15 Hz table refresh
RATE_WINDOW_S = 1.0  # packets/sec averaging window
NO_DATA_AFTER_S = 2.0  # "no data" indicator threshold


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"PSNView {__version__} - PosiStageNet Viewer")
        self.resize(1200, 500)

        self.store = TrackerStore()
        self.receiver = PsnReceiver(self)
        self.receiver.info_received.connect(self._on_info)
        self.receiver.data_received.connect(self._on_data)
        self.receiver.error.connect(self._on_error)
        self.send_dialog: SendDialog | None = None

        self._rate_marker_time = time.monotonic()
        self._rate_marker_count = 0
        self._pps = 0.0
        self._last_error = ""

        self._build_toolbar()
        self._build_table()
        self._build_statusbar()

        self._timer = QTimer(self)
        self._timer.setInterval(GUI_REFRESH_MS)
        self._timer.timeout.connect(self._on_refresh)
        self._timer.start()

    # -- UI construction ---------------------------------------------------
    def _build_toolbar(self) -> None:
        tb = QToolBar("Connection")
        tb.setMovable(False)
        self.addToolBar(tb)

        tb.addWidget(QLabel(" Interface: "))
        self.iface_combo = QComboBox()
        self.iface_combo.addItems(list_interface_ips())
        self.iface_combo.setMinimumWidth(140)
        tb.addWidget(self.iface_combo)

        tb.addWidget(QLabel("  Multicast: "))
        self.mcast_label = QLabel(PSN_DEFAULT_MCAST_IP)
        tb.addWidget(self.mcast_label)

        tb.addWidget(QLabel("  Port: "))
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(PSN_DEFAULT_PORT)
        tb.addWidget(self.port_spin)

        tb.addSeparator()
        self.start_action = QAction("Start", self)
        self.start_action.triggered.connect(self._on_start_stop)
        tb.addAction(self.start_action)

        self.clear_action = QAction("Clear", self)
        self.clear_action.triggered.connect(self._on_clear)
        tb.addAction(self.clear_action)

        tb.addSeparator()
        self.send_action = QAction("Send", self)
        self.send_action.triggered.connect(self._on_send)
        tb.addAction(self.send_action)

    def _build_table(self) -> None:
        self.table_model = TrackerTableModel(self.store, self)
        self.table = QTableView()
        self.table.setModel(self.table_model)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setDefaultSectionSize(78)
        header.setStretchLastSection(True)
        self.table.setColumnWidth(1, 140)  # Name
        self.setCentralWidget(self.table)

    def _build_statusbar(self) -> None:
        self.status_conn = QLabel("Stopped")
        self.status_server = QLabel("Server: -")
        self.status_rate = QLabel("0.0 pkt/s")
        self.status_frame = QLabel("Frame: -")
        sb = self.statusBar()
        for w in (self.status_conn, self.status_server, self.status_rate, self.status_frame):
            w.setContentsMargins(6, 0, 6, 0)
            sb.addWidget(w)

    # -- receiver callbacks (GUI thread via queued signals) ----------------
    def _on_info(self, packet) -> None:
        self.store.apply_info(packet)

    def _on_data(self, packet) -> None:
        self.store.apply_data(packet)

    def _on_error(self, message: str) -> None:
        self._last_error = message

    # -- actions -----------------------------------------------------------
    def _on_start_stop(self) -> None:
        if self.receiver.running:
            self.receiver.stop()
            self.start_action.setText("Start")
            self.iface_combo.setEnabled(True)
            self.port_spin.setEnabled(True)
            self.status_conn.setText("Stopped")
        else:
            self._last_error = ""
            iface = self.iface_combo.currentText()
            port = self.port_spin.value()
            self.receiver.start(iface, port)
            self.start_action.setText("Stop")
            self.iface_combo.setEnabled(False)
            self.port_spin.setEnabled(False)

    def _on_clear(self) -> None:
        self.store.clear()
        self.table_model.refresh()

    def _on_send(self) -> None:
        """Open (or raise) the Send PSN test dialog."""
        if self.send_dialog is None:
            self.send_dialog = SendDialog(self)
        self.send_dialog.show()
        self.send_dialog.raise_()
        self.send_dialog.activateWindow()

    # -- periodic refresh --------------------------------------------------
    def _on_refresh(self) -> None:
        self.table_model.refresh()

        now = time.monotonic()
        total = self.store.data_packet_count + self.store.info_packet_count
        dt = now - self._rate_marker_time
        if dt >= RATE_WINDOW_S:
            self._pps = (total - self._rate_marker_count) / dt
            self._rate_marker_time = now
            self._rate_marker_count = total

        if self.receiver.running:
            if self._last_error and total == 0:
                self.status_conn.setText(f"Error: {self._last_error}")
            elif self.store.last_packet_time and now - self.store.last_packet_time < NO_DATA_AFTER_S:
                self.status_conn.setText("Receiving")
            else:
                self.status_conn.setText("Listening (no data)")
        server = self.store.server_name or "-"
        version = f" (PSN v{self.store.psn_version})" if self.store.psn_version else ""
        self.status_server.setText(f"Server: {server}{version}")
        self.status_rate.setText(f"{self._pps:.1f} pkt/s")
        frame = self.store.last_frame_id
        self.status_frame.setText(f"Frame: {'-' if frame is None else frame}")

    # -- shutdown ----------------------------------------------------------
    def closeEvent(self, event) -> None:
        self._timer.stop()
        self.receiver.stop()
        if self.send_dialog is not None:
            self.send_dialog.close()
        super().closeEvent(event)
