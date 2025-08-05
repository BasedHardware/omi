# -*- coding: utf-8 -*-
import sys
from typing import Callable, List, Union
from uuid import UUID

if sys.version_info >= (3, 12):
    from winrt.windows.devices.bluetooth.genericattributeprofile import (
        GattCharacteristic,
        GattCharacteristicProperties,
    )
else:
    from bleak_winrt.windows.devices.bluetooth.genericattributeprofile import (
        GattCharacteristic,
        GattCharacteristicProperties,
    )

from ..characteristic import BleakGATTCharacteristic
from ..descriptor import BleakGATTDescriptor

_GattCharacteristicsPropertiesMap = {
    GattCharacteristicProperties.NONE: (
        "None",
        "The characteristic doesn’t have any properties that apply",
    ),
    GattCharacteristicProperties.BROADCAST: (
        "Broadcast".lower(),
        "The characteristic supports broadcasting",
    ),
    GattCharacteristicProperties.READ: (
        "Read".lower(),
        "The characteristic is readable",
    ),
    GattCharacteristicProperties.WRITE_WITHOUT_RESPONSE: (
        "Write-Without-Response".lower(),
        "The characteristic supports Write Without Response",
    ),
    GattCharacteristicProperties.WRITE: (
        "Write".lower(),
        "The characteristic is writable",
    ),
    GattCharacteristicProperties.NOTIFY: (
        "Notify".lower(),
        "The characteristic is notifiable",
    ),
    GattCharacteristicProperties.INDICATE: (
        "Indicate".lower(),
        "The characteristic is indicatable",
    ),
    GattCharacteristicProperties.AUTHENTICATED_SIGNED_WRITES: (
        "Authenticated-Signed-Writes".lower(),
        "The characteristic supports signed writes",
    ),
    GattCharacteristicProperties.EXTENDED_PROPERTIES: (
        "Extended-Properties".lower(),
        "The ExtendedProperties Descriptor is present",
    ),
    GattCharacteristicProperties.RELIABLE_WRITES: (
        "Reliable-Writes".lower(),
        "The characteristic supports reliable writes",
    ),
    GattCharacteristicProperties.WRITABLE_AUXILIARIES: (
        "Writable-Auxiliaries".lower(),
        "The characteristic has writable auxiliaries",
    ),
}


class BleakGATTCharacteristicWinRT(BleakGATTCharacteristic):
    """GATT Characteristic implementation for the .NET backend, implemented with WinRT"""

    def __init__(
        self,
        obj: GattCharacteristic,
        max_write_without_response_size: Callable[[], int],
    ):
        super().__init__(obj, max_write_without_response_size)
        self.__descriptors = []
        self.__props = [
            _GattCharacteristicsPropertiesMap[v][0]
            for v in [2**n for n in range(10)]
            if (self.obj.characteristic_properties & v)
        ]

    @property
    def service_uuid(self) -> str:
        """The uuid of the Service containing this characteristic"""
        return str(self.obj.service.uuid)

    @property
    def service_handle(self) -> int:
        """The integer handle of the Service containing this characteristic"""
        return int(self.obj.service.attribute_handle)

    @property
    def handle(self) -> int:
        """The handle of this characteristic"""
        return int(self.obj.attribute_handle)

    @property
    def uuid(self) -> str:
        """The uuid of this characteristic"""
        return str(self.obj.uuid)

    @property
    def description(self) -> str:
        """Description for this characteristic"""
        return (
            self.obj.user_description
            if self.obj.user_description
            else super().description
        )

    @property
    def properties(self) -> List[str]:
        """Properties of this characteristic"""
        return self.__props

    @property
    def descriptors(self) -> List[BleakGATTDescriptor]:
        """List of descriptors for this characteristic"""
        return self.__descriptors

    def get_descriptor(
        self, specifier: Union[int, str, UUID]
    ) -> Union[BleakGATTDescriptor, None]:
        """Get a descriptor by handle (int) or UUID (str or uuid.UUID)"""
        try:
            if isinstance(specifier, int):
                return next(filter(lambda x: x.handle == specifier, self.descriptors))
            else:
                return next(
                    filter(lambda x: x.uuid == str(specifier), self.descriptors)
                )
        except StopIteration:
            return None

    def add_descriptor(self, descriptor: BleakGATTDescriptor):
        """Add a :py:class:`~BleakGATTDescriptor` to the characteristic.

        Should not be used by end user, but rather by `bleak` itself.
        """
        self.__descriptors.append(descriptor)
