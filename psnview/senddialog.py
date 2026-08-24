# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 The OpenFollow Project
"""Send PSN dialog: an editable tracker table plus controls to send the
trackers once or stream them, for testing PSNView and other receivers."""

from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTableView,
    QVBoxLayout,
)

from .model import COLUMNS
from .netutils import PSN_DEFAULT_MCAST_IP, PSN_DEFAULT_PORT, list_interface_ips
from .sender import (
    DEFAULT_RATE_HZ,
    EFFECTS,
    MAX_RATE_HZ,
    MAX_TRACKERS_PER_PACKET,
    V3_FIELDS,
    PsnSender,
    SendTracker,
)

SEND_COLUMNS = COLUMNS[:-1]  # same layout as the viewer, minus "Age (s)"
COL_ID, COL_NAME, COL_STATUS, COL_TIMESTAMP = 0, 1, 17, 18


class SendTrackerTableModel(QAbstractTableModel):
    """Editable table over a list of SendTracker (the list is shared with PsnSender)."""

    def __init__(self, rows: list[SendTracker], parent=None) -> None:
        super().__init__(parent)
        self.rows = rows

    # -- row editing -------------------------------------------------------
    def add_tracker(self) -> bool:
        if len(self.rows) >= MAX_TRACKERS_PER_PACKET:
            return False
        tracker_id = max((t.tracker_id for t in self.rows), default=0) + 1
        row = len(self.rows)
        self.beginInsertRows(QModelIndex(), row, row)
        self.rows.append(SendTracker(tracker_id, f"tracker_{tracker_id}"))
        self.endInsertRows()
        return True

    def remove_tracker(self, row: int) -> None:
        if not 0 <= row < len(self.rows):
            return
        self.beginRemoveRows(QModelIndex(), row, row)
        del self.rows[row]
        self.endRemoveRows()

    # -- Qt model API ------------------------------------------------------
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(SEND_COLUMNS)

    def headerData(self, section: int, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return SEND_COLUMNS[section]
        return None

    def flags(self, index: QModelIndex):
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEditable

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or role not in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            return None
        # EditRole returns plain strings so Qt uses a line edit (the default
        # double-spinbox editor is limited to 0..99.99 with 2 decimals).
        editing = role == Qt.ItemDataRole.EditRole
        t = self.rows[index.row()]
        col = index.column()

        if col == COL_ID:
            return str(t.tracker_id)
        if col == COL_NAME:
            return t.name
        if 2 <= col <= 16:  # 5 vectors x 3 axes
            vec_idx, axis = divmod(col - 2, 3)
            value = getattr(t, V3_FIELDS[vec_idx])[axis]
            return repr(value) if editing else f"{value:.3f}"
        if col == COL_STATUS:
            return repr(t.status) if editing else f"{t.status:g}"
        if col == COL_TIMESTAMP:
            if t.timestamp is None:
                return "" if editing else "auto"
            return str(t.timestamp)
        return None

    def setData(self, index: QModelIndex, value, role=Qt.ItemDataRole.EditRole) -> bool:
        if not index.isValid() or role != Qt.ItemDataRole.EditRole:
            return False
        t = self.rows[index.row()]
        col = index.column()
        text = str(value).strip()
        try:
            if col == COL_ID:
                tracker_id = int(text)
                if not 0 <= tracker_id <= 0xFFFF:  # uint16 on the wire
                    return False
                t.tracker_id = tracker_id
            elif col == COL_NAME:
                t.name = text
            elif 2 <= col <= 16:
                vec_idx, axis = divmod(col - 2, 3)
                fname = V3_FIELDS[vec_idx]
                vec = list(getattr(t, fname))
                vec[axis] = float(text)
                setattr(t, fname, tuple(vec))
            elif col == COL_STATUS:
                t.status = float(text)
            elif col == COL_TIMESTAMP:
                if text in ("", "auto"):
                    t.timestamp = None
                else:
                    timestamp = int(text)
                    if timestamp < 0:
                        return False
                    t.timestamp = timestamp
            else:
                return False
        except ValueError:
            return False
        self.dataChanged.emit(index, index)
        return True


class SendDialog(QDialog):
    """Non-modal window to compose and send PSN INFO/DATA packets."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Send PSN")
        self.setModal(False)
        self.resize(1100, 420)

        # Not "self.sender": QObject.sender() is a method.
        self.psn_sender = PsnSender(self)
        self.model = SendTrackerTableModel(self.psn_sender.trackers, self)

        layout = QVBoxLayout(self)
        layout.addLayout(self._build_connection_row())
        layout.addWidget(self._build_table(), 1)
        layout.addLayout(self._build_tracker_row())
        layout.addLayout(self._build_send_row())
        self._connect_signals()

        self.model.add_tracker()
        self._apply_settings()
        self._update_buttons()

    # -- UI construction ---------------------------------------------------
    def _build_connection_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(QLabel("Interface:"))
        self.iface_combo = QComboBox()
        # 0.0.0.0 cannot be a transmit interface; loopback feeds a local viewer.
        ips = ["127.0.0.1"] + [ip for ip in list_interface_ips() if ip not in ("0.0.0.0", "127.0.0.1")]
        self.iface_combo.addItems(ips)
        self.iface_combo.setMinimumWidth(140)
        row.addWidget(self.iface_combo)

        row.addWidget(QLabel("  Multicast:"))
        row.addWidget(QLabel(PSN_DEFAULT_MCAST_IP))

        row.addWidget(QLabel("  Port:"))
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(PSN_DEFAULT_PORT)
        row.addWidget(self.port_spin)

        row.addWidget(QLabel("  System name:"))
        self.name_edit = QLineEdit("PSNView")
        row.addWidget(self.name_edit, 1)
        return row

    def _build_table(self) -> QTableView:
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setDefaultSectionSize(78)
        header.setStretchLastSection(True)
        self.table.setColumnWidth(COL_NAME, 140)
        return self.table

    def _build_tracker_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self.add_button = QPushButton("Add tracker")
        row.addWidget(self.add_button)
        self.remove_button = QPushButton("Remove tracker")
        row.addWidget(self.remove_button)
        row.addStretch(1)

        self.animate_check = QCheckBox("Animate")
        row.addWidget(self.animate_check)
        self.effect_combo = QComboBox()
        self.effect_combo.addItems(EFFECTS)
        row.addWidget(self.effect_combo)

        row.addWidget(QLabel("Amplitude (m):"))
        self.amplitude_spin = QDoubleSpinBox()
        self.amplitude_spin.setRange(0.0, 100.0)
        self.amplitude_spin.setSingleStep(0.1)
        self.amplitude_spin.setValue(1.0)
        row.addWidget(self.amplitude_spin)

        row.addWidget(QLabel("Period (s):"))
        self.period_spin = QDoubleSpinBox()
        self.period_spin.setRange(0.1, 60.0)
        self.period_spin.setSingleStep(0.5)
        self.period_spin.setValue(4.0)
        row.addWidget(self.period_spin)
        return row

    def _build_send_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(QLabel("Rate (Hz):"))
        self.rate_spin = QSpinBox()
        self.rate_spin.setRange(1, MAX_RATE_HZ)
        self.rate_spin.setValue(DEFAULT_RATE_HZ)
        row.addWidget(self.rate_spin)

        self.send_once_button = QPushButton("Send once")
        row.addWidget(self.send_once_button)
        self.start_button = QPushButton("Start")
        row.addWidget(self.start_button)

        self.status_label = QLabel("Idle")
        self.status_label.setContentsMargins(6, 0, 6, 0)
        row.addWidget(self.status_label, 1)
        return row

    def _connect_signals(self) -> None:
        # Connected after construction: QComboBox.addItems already emits
        # currentTextChanged, before the other widgets exist.
        self.iface_combo.currentTextChanged.connect(self._apply_settings)
        self.port_spin.valueChanged.connect(self._apply_settings)
        self.name_edit.textChanged.connect(self._apply_settings)
        self.animate_check.toggled.connect(self._apply_settings)
        self.effect_combo.currentTextChanged.connect(self._apply_settings)
        self.amplitude_spin.valueChanged.connect(self._apply_settings)
        self.period_spin.valueChanged.connect(self._apply_settings)

        self.add_button.clicked.connect(self._on_add)
        self.remove_button.clicked.connect(self._on_remove)
        self.send_once_button.clicked.connect(self._on_send_once)
        self.start_button.clicked.connect(self._on_start_stop)

        self.model.rowsInserted.connect(self._update_buttons)
        self.model.rowsRemoved.connect(self._update_buttons)
        self.psn_sender.sent.connect(self._on_sent)
        self.psn_sender.error.connect(self._on_error)

    # -- settings ----------------------------------------------------------
    def _apply_settings(self, *_args) -> None:
        s = self.psn_sender
        s.iface_ip = self.iface_combo.currentText()
        s.port = self.port_spin.value()
        s.system_name = self.name_edit.text()
        anim = s.animation
        anim.enabled = self.animate_check.isChecked()
        anim.effect = self.effect_combo.currentText()
        anim.amplitude = self.amplitude_spin.value()
        anim.period_s = self.period_spin.value()
        for w in (self.effect_combo, self.amplitude_spin, self.period_spin):
            w.setEnabled(anim.enabled)

    def _update_buttons(self, *_args) -> None:
        has_rows = self.model.rowCount() > 0
        self.send_once_button.setEnabled(has_rows)
        self.start_button.setEnabled(has_rows or self.psn_sender.running)
        self.add_button.setEnabled(self.model.rowCount() < MAX_TRACKERS_PER_PACKET)
        self.remove_button.setEnabled(has_rows)

    def _set_streaming_ui(self, streaming: bool) -> None:
        self.start_button.setText("Stop" if streaming else "Start")
        for w in (self.iface_combo, self.port_spin, self.rate_spin):
            w.setEnabled(not streaming)

    # -- actions -----------------------------------------------------------
    def _on_add(self) -> None:
        self.model.add_tracker()

    def _on_remove(self) -> None:
        selected = self.table.selectionModel().selectedRows()
        row = selected[0].row() if selected else self.model.rowCount() - 1
        self.model.remove_tracker(row)

    def _on_send_once(self) -> None:
        self.psn_sender.send_once()

    def _on_start_stop(self) -> None:
        s = self.psn_sender
        if s.running:
            s.stop()
            self._set_streaming_ui(False)
            self.status_label.setText("Stopped")
        elif s.start(self.rate_spin.value()):
            self._set_streaming_ui(True)
            self.status_label.setText(f"Streaming {self.rate_spin.value()} Hz")

    # -- sender callbacks --------------------------------------------------
    def _on_sent(self, frame_id: int) -> None:
        s = self.psn_sender
        total = s.data_packet_count + s.info_packet_count
        if s.running:
            self.status_label.setText(f"Streaming {self.rate_spin.value()} Hz - frame {frame_id} - {total} pkts")
        else:
            self.status_label.setText(f"Sent once - frame {frame_id} - {total} pkts")

    def _on_error(self, message: str) -> None:
        self.status_label.setText(f"Error: {message}")
        if not self.psn_sender.running:
            self._set_streaming_ui(False)

    # -- shutdown ----------------------------------------------------------
    def closeEvent(self, event) -> None:
        self.psn_sender.stop()
        self._set_streaming_ui(False)
        super().closeEvent(event)
