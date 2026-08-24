# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 The OpenFollow Project
"""Send PSN test mode: animation math, pypsn round trip, and an end-to-end
loopback run where the SendDialog feeds the real MainWindow's receiver.
"""

import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pypsn
import pytest
from PySide6.QtWidgets import QApplication

from psnview.mainwindow import MainWindow
from psnview.sender import Animation, PsnSender, SendTracker, animate_position

IFACE_IP = "127.0.0.1"


def test_animate_position():
    base = (1.0, 2.0, 3.0)
    assert animate_position(base, Animation(enabled=False), 1.0) == base

    sine = Animation(enabled=True, effect="Sine", amplitude=0.5, period_s=4.0)
    assert animate_position(base, sine, 0.0) == pytest.approx((1.5, 2.0, 3.0))
    assert animate_position(base, sine, 1.0) == pytest.approx((1.0, 2.5, 3.0))
    assert animate_position(base, sine, 0.0, phase_offset=0.5) == pytest.approx((0.5, 2.0, 3.0))

    ramp = Animation(enabled=True, effect="Ramp", amplitude=2.0, period_s=4.0)
    assert animate_position(base, ramp, 2.0) == pytest.approx((2.0, 2.0, 3.0))


def test_tracker_roundtrip():
    t7 = SendTracker(7, "t7", pos=(1.0, 2.0, 3.0), ori=(0.0, 1.5, 0.0))
    t8 = SendTracker(8, timestamp=5)
    packet = pypsn.PsnDataPacket(
        info=pypsn.PsnInfo(timestamp=0, version_high=2, version_low=3, frame_id=9, packet_count=1),
        trackers=[t7.to_psn_data(now_ms=42), t8.to_psn_data(now_ms=42)],
    )
    parsed = pypsn.parse_psn_packet(pypsn.prepare_psn_data_packet_bytes(packet))
    assert isinstance(parsed, pypsn.PsnDataPacket)
    assert parsed.info.frame_id == 9
    p7, p8 = parsed.trackers
    assert p7.tracker_id == 7
    assert (p7.pos.x, p7.pos.y, p7.pos.z) == (1.0, 2.0, 3.0)
    assert (p7.ori.x, p7.ori.y, p7.ori.z) == (0.0, 1.5, 0.0)
    assert (p7.speed.x, p7.speed.y, p7.speed.z) == (0.0, 0.0, 0.0)
    assert p7.status == 1.0
    assert p7.timestamp == 42  # auto
    assert p8.timestamp == 5  # user-set


def test_frame_wrap():
    QApplication.instance() or QApplication(sys.argv)
    s = PsnSender()
    s.frame_id = 255
    assert s._next_frame() == 255
    assert s._next_frame() == 0


def _pump(app, seconds: float, until) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline and not until():
        app.processEvents()
        time.sleep(0.02)
    return until()


def test_send_dialog_feeds_viewer_over_loopback():
    app = QApplication.instance() or QApplication(sys.argv)
    win = MainWindow()
    win.show()
    win.iface_combo.addItem(IFACE_IP)
    win.iface_combo.setCurrentText(IFACE_IP)
    win._on_start_stop()
    assert win.receiver.running, "receiver did not start"

    win._on_send()
    dlg = win.send_dialog
    assert dlg is not None and dlg.isVisible()
    dlg.iface_combo.setCurrentText(IFACE_IP)
    dlg.name_edit.setText("psnview_send_test")
    assert dlg.model.add_tracker()  # ids 1 and 2
    assert dlg.model.setData(dlg.model.index(1, 2), "2.5")  # tracker 2, Pos X
    dlg.animate_check.setChecked(True)
    dlg.effect_combo.setCurrentText("Sine")
    dlg.amplitude_spin.setValue(1.0)

    # stream
    dlg._on_start_stop()
    assert dlg.psn_sender.running, dlg.status_label.text()
    store = win.store
    assert _pump(app, 5.0, lambda: store.data_packet_count >= 5 and store.info_packet_count >= 1), (
        "no packets over loopback: " + dlg.status_label.text()
    )
    dlg._on_start_stop()
    assert not dlg.psn_sender.running

    win.table_model.refresh()
    assert store.server_name == "psnview_send_test", store.server_name
    assert store.psn_version == "2.3", store.psn_version
    assert set(store.trackers) == {1, 2}, store.trackers
    t2 = store.trackers[2]
    assert t2.name == "tracker_2", t2.name
    assert abs(t2.vectors["pos"][0] - 2.5) <= 1.0 + 1e-3, t2.vectors["pos"]  # sine orbit, amplitude 1
    assert t2.status == 1
    assert isinstance(store.last_frame_id, int)

    # send once
    before = store.data_packet_count
    dlg._on_send_once()
    assert _pump(app, 5.0, lambda: store.data_packet_count > before), "send once did not arrive"
    assert dlg.status_label.text().startswith("Sent once"), dlg.status_label.text()

    win._on_start_stop()
    assert not win.receiver.running
    win.close()
