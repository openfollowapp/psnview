# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 The OpenFollow Project
"""Tracker state store and Qt table model for PSNView.

INFO packets contribute tracker names and the server/system name;
DATA packets contribute position, speed, orientation, acceleration,
target position, status and timestamp. Both are merged per tracker id.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QBrush, QColor

STALE_AFTER_S = 2.0

_V3_FIELDS = ("pos", "speed", "ori", "accel", "trgtpos")

COLUMNS: list[str] = (
    ["ID", "Name"]
    + [f"{label} {axis}" for label in ("Pos", "Speed", "Ori", "Accel", "Target") for axis in "XYZ"]
    + ["Status", "Timestamp", "Age (s)"]
)


@dataclass
class TrackerState:
    tracker_id: int
    name: str = ""
    vectors: dict[str, tuple[float, float, float] | None] = field(default_factory=lambda: dict.fromkeys(_V3_FIELDS))
    status: float | None = None
    timestamp: int | None = None
    last_seen: float = 0.0  # monotonic time of last DATA update

    def age(self, now: float) -> float | None:
        if self.last_seen == 0.0:
            return None
        return now - self.last_seen

    def is_stale(self, now: float) -> bool:
        a = self.age(now)
        return a is None or a > STALE_AFTER_S


class TrackerStore:
    """Plain-Python store, updated from receiver signals (GUI thread)."""

    def __init__(self) -> None:
        self.trackers: dict[int, TrackerState] = {}
        self.server_name: str = ""
        self.psn_version: str = ""
        self.last_frame_id: int | None = None
        self.data_packet_count: int = 0
        self.info_packet_count: int = 0
        self.last_packet_time: float = 0.0

    def _get(self, tracker_id: int) -> TrackerState:
        state = self.trackers.get(tracker_id)
        if state is None:
            state = TrackerState(tracker_id)
            self.trackers[tracker_id] = state
        return state

    def apply_info(self, packet) -> None:
        """Merge a pypsn PsnInfoPacket."""
        self.info_packet_count += 1
        self.last_packet_time = time.monotonic()
        name = packet.name
        if isinstance(name, bytes):
            name = name.decode("utf-8", errors="replace")
        self.server_name = name
        self.psn_version = f"{packet.info.version_high}.{packet.info.version_low}"
        for t in packet.trackers:
            tname = t.tracker_name
            if isinstance(tname, bytes):
                tname = tname.decode("utf-8", errors="replace")
            self._get(t.tracker_id).name = tname

    def apply_data(self, packet) -> None:
        """Merge a pypsn PsnDataPacket."""
        self.data_packet_count += 1
        now = time.monotonic()
        self.last_packet_time = now
        self.last_frame_id = packet.info.frame_id
        for t in packet.trackers:
            state = self._get(t.tracker_id)
            for fname in _V3_FIELDS:
                vec = getattr(t, fname, None)
                if vec is not None:
                    state.vectors[fname] = (vec.x, vec.y, vec.z)
            if t.status is not None:
                state.status = t.status
            state.timestamp = t.timestamp
            state.last_seen = now

    def clear(self) -> None:
        self.trackers.clear()
        self.server_name = ""
        self.psn_version = ""
        self.last_frame_id = None
        self.data_packet_count = 0
        self.info_packet_count = 0
        self.last_packet_time = 0.0


class TrackerTableModel(QAbstractTableModel):
    """Read-only table over a TrackerStore, refreshed by a GUI timer."""

    def __init__(self, store: TrackerStore, parent=None) -> None:
        super().__init__(parent)
        self._store = store
        self._rows: list[TrackerState] = []
        self._now: float = time.monotonic()

    # -- refresh -----------------------------------------------------------
    def refresh(self) -> None:
        """Re-snapshot the store; called at GUI rate (~15 Hz)."""
        self._now = time.monotonic()
        new_rows = sorted(self._store.trackers.values(), key=lambda t: t.tracker_id)
        if len(new_rows) != len(self._rows):
            self.beginResetModel()
            self._rows = new_rows
            self.endResetModel()
        else:
            self._rows = new_rows
            if self._rows:
                top_left = self.index(0, 0)
                bottom_right = self.index(len(self._rows) - 1, len(COLUMNS) - 1)
                self.dataChanged.emit(top_left, bottom_right)

    # -- Qt model API ------------------------------------------------------
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(COLUMNS)

    def headerData(self, section: int, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return COLUMNS[section]
        return None

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        state = self._rows[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.ForegroundRole:
            if state.is_stale(self._now):
                return QBrush(QColor(150, 150, 150))
            return None

        if role != Qt.ItemDataRole.DisplayRole:
            return None

        if col == 0:
            return str(state.tracker_id)
        if col == 1:
            return state.name
        if 2 <= col <= 16:  # 5 vectors x 3 axes
            vec_idx, axis = divmod(col - 2, 3)
            vec = state.vectors[_V3_FIELDS[vec_idx]]
            if vec is None:
                return "-"
            return f"{vec[axis]:.3f}"
        if col == 17:
            return "-" if state.status is None else f"{state.status:g}"
        if col == 18:
            return "-" if state.timestamp is None else str(state.timestamp)
        if col == 19:
            a = state.age(self._now)
            return "-" if a is None else f"{a:.1f}"
        return None
