# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 The OpenFollow Project
"""End-to-end smoke test: run the real MainWindow offscreen, feed it real
PSN INFO/DATA packets over loopback multicast, and check the model state.

Run directly: python tests/test_smoke.py
"""

import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pypsn
from PySide6.QtWidgets import QApplication

from psnview.mainwindow import MainWindow

MCAST_IP = "236.10.10.10"
IFACE_IP = "127.0.0.1"
PORT = 56565


def send_packets() -> None:
    info = pypsn.PsnInfoPacket(
        info=pypsn.PsnInfo(timestamp=1000, version_high=2, version_low=3, frame_id=1, packet_count=1),
        name="smoke_test_server",
        trackers=[pypsn.PsnTrackerInfo(tracker_id=i, tracker_name=f"tracker_{i}") for i in range(3)],
    )
    pypsn.send_psn_packet(
        psn_packet=pypsn.prepare_psn_info_packet_bytes(info),
        mcast_ip=MCAST_IP,
        ip_addr=IFACE_IP,
        port=PORT,
    )

    data = pypsn.PsnDataPacket(
        info=pypsn.PsnInfo(timestamp=2000, version_high=2, version_low=3, frame_id=2, packet_count=1),
        trackers=[
            pypsn.PsnTracker(
                tracker_id=i,
                pos=pypsn.PsnVector3(1.0 + i, 2.0, 3.5),
                speed=pypsn.PsnVector3(0.1, 0.2, 0.3),
                ori=pypsn.PsnVector3(0.0, 1.57, 0.0),
                accel=pypsn.PsnVector3(0.01, 0.02, 0.03),
                trgtpos=pypsn.PsnVector3(5.0, 6.0, 7.0),
                status=1,
                timestamp=2000,
            )
            for i in range(3)
        ],
    )
    pypsn.send_psn_packet(
        psn_packet=pypsn.prepare_psn_data_packet_bytes(data),
        mcast_ip=MCAST_IP,
        ip_addr=IFACE_IP,
        port=PORT,
    )


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    win = MainWindow()
    win.show()

    # start receiver on loopback
    win.iface_combo.addItem(IFACE_IP)
    win.iface_combo.setCurrentText(IFACE_IP)
    win._on_start_stop()
    assert win.receiver.running, "receiver did not start"

    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline and win.store.data_packet_count == 0:
        send_packets()
        app.processEvents()
        time.sleep(0.1)

    win.table_model.refresh()
    app.processEvents()

    store = win.store
    assert store.info_packet_count > 0, "no INFO packet received"
    assert store.data_packet_count > 0, "no DATA packet received"
    assert store.server_name == "smoke_test_server", store.server_name
    assert store.psn_version == "2.3", store.psn_version
    assert len(store.trackers) == 3, store.trackers
    t1 = store.trackers[1]
    assert t1.name == "tracker_1", t1.name
    assert t1.vectors["pos"] == (2.0, 2.0, 3.5), t1.vectors["pos"]
    assert t1.vectors["trgtpos"] == (5.0, 6.0, 7.0), t1.vectors["trgtpos"]
    assert t1.status == 1

    # table renders all columns
    m = win.table_model
    assert m.rowCount() == 3 and m.columnCount() == 20
    row1 = [m.data(m.index(1, c)) for c in range(m.columnCount())]
    assert row1[0] == "1" and row1[1] == "tracker_1"
    assert row1[2] == "2.000"  # pos X
    assert row1[14] == "5.000"  # target X

    # clean stop
    win._on_start_stop()
    assert not win.receiver.running
    win.close()

    print("SMOKE TEST PASSED")
    print("row 1:", row1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def test_end_to_end_loopback():
    """pytest entry point wrapping the runnable smoke test."""
    assert main() == 0
