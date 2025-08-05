# -*- coding: utf-8 -*-
"""
Wrapper class for Bluetooth LE servers returned from calling
:py:meth:`bleak.discover`.

Created on 2018-04-23 by hbldh <henrik.blidh@nedomkull.com>

"""


from typing import Any, Optional
from warnings import warn


class BLEDevice:
    """
    A simple wrapper class representing a BLE server detected during scanning.
    """

    __slots__ = ("address", "name", "details", "_rssi", "_metadata")

    def __init__(
        self, address: str, name: Optional[str], details: Any, rssi: int, **kwargs
    ):
        #: The Bluetooth address of the device on this machine (UUID on macOS).
        self.address = address
        #: The operating system name of the device (not necessarily the local name
        #: from the advertising data), suitable for display to the user.
        self.name = name
        #: The OS native details required for connecting to the device.
        self.details = details

        # for backwards compatibility
        self._rssi = rssi
        self._metadata = kwargs

    @property
    def rssi(self) -> int:
        """
        Gets the RSSI of the last received advertisement.

        .. deprecated:: 0.19.0
            Use :class:`AdvertisementData` from detection callback or
            :attr:`BleakScanner.discovered_devices_and_advertisement_data` instead.
        """
        warn(
            "BLEDevice.rssi is deprecated and will be removed in a future version of Bleak, use AdvertisementData.rssi instead",
            FutureWarning,
            stacklevel=2,
        )
        return self._rssi

    @property
    def metadata(self) -> dict:
        """
        Gets additional advertisement data for the device.

        .. deprecated:: 0.19.0
            Use :class:`AdvertisementData` from detection callback or
            :attr:`BleakScanner.discovered_devices_and_advertisement_data` instead.
        """
        warn(
            "BLEDevice.metadata is deprecated and will be removed in a future version of Bleak, use AdvertisementData instead",
            FutureWarning,
            stacklevel=2,
        )
        return self._metadata

    def __str__(self):
        return f"{self.address}: {self.name}"

    def __repr__(self):
        return f"BLEDevice({self.address}, {self.name})"
