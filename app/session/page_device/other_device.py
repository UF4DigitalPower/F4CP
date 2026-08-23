# -*- coding: utf-8 -*-
from __future__ import annotations


def listSerialPorts() -> list[str]:
    """Return currently available serial device names.

    Keep enumeration in one place so Device, Power and ADP training pages use
    the same pyserial view of the host.  Descriptions are deliberately not
    returned: localized driver descriptions can contain broken text and are
    not valid values for ``serial.Serial``.
    """
    try:
        from serial.tools import list_ports
        return sorted(
            {port.device for port in list_ports.comports() if port.device},
            key=lambda value: (value.upper().startswith("COM"), value.upper()),
        )
    except Exception:
        return []
