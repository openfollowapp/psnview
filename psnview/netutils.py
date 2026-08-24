# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 The OpenFollow Project
"""Network helpers for PSNView."""

from __future__ import annotations

import socket

PSN_DEFAULT_MCAST_IP = "236.10.10.10"
PSN_DEFAULT_PORT = 56565


def list_interface_ips() -> list[str]:
    """Return local IPv4 addresses usable for joining the multicast group.

    Always includes "0.0.0.0" (any interface) as the first entry.
    """
    ips: list[str] = ["0.0.0.0"]
    seen = set(ips)

    # getaddrinfo on the hostname catches most configured interfaces.
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if ip not in seen:
                seen.add(ip)
                ips.append(ip)
    except OSError:
        pass

    # UDP "connect" trick finds the IP of the default route interface,
    # which getaddrinfo can miss on some systems.
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            if ip not in seen:
                seen.add(ip)
                ips.append(ip)
    except OSError:
        pass

    return ips
