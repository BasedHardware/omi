# -*- coding: utf-8 -*-
import sys

if sys.version_info >= (3, 12):
    from winrt.windows.devices.bluetooth.genericattributeprofile import GattDescriptor
else:
    from bleak_winrt.windows.devices.bluetooth.genericattributeprofile import (
        GattDescriptor,
    )

from ..descriptor import BleakGATTDescriptor


class BleakGATTDescriptorWinRT(BleakGATTDescriptor):
    """GATT Descriptor implementation for .NET backend, implemented with WinRT"""

    def __init__(
        self, obj: GattDescriptor, characteristic_uuid: str, characteristic_handle: int
    ):
        super(BleakGATTDescriptorWinRT, self).__init__(obj)
        self.obj = obj
        self.__characteristic_uuid = characteristic_uuid
        self.__characteristic_handle = characteristic_handle

    @property
    def characteristic_handle(self) -> int:
        """handle for the characteristic that this descriptor belongs to"""
        return self.__characteristic_handle

    @property
    def characteristic_uuid(self) -> str:
        """UUID for the characteristic that this descriptor belongs to"""
        return self.__characteristic_uuid

    @property
    def uuid(self) -> str:
        """UUID for this descriptor"""
        return str(self.obj.uuid)

    @property
    def handle(self) -> int:
        """Integer handle for this descriptor"""
        return self.obj.attribute_handle
