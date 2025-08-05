from typing import Callable, List, Union
from uuid import UUID

from ...exc import BleakError
from ..characteristic import BleakGATTCharacteristic
from ..descriptor import BleakGATTDescriptor
from . import defs


class BleakGATTCharacteristicP4Android(BleakGATTCharacteristic):
    """GATT Characteristic implementation for the python-for-android backend"""

    def __init__(
        self,
        java,
        service_uuid: str,
        service_handle: int,
        max_write_without_response_size: Callable[[], int],
    ):
        super(BleakGATTCharacteristicP4Android, self).__init__(
            java, max_write_without_response_size
        )
        self.__uuid = self.obj.getUuid().toString()
        self.__handle = self.obj.getInstanceId()
        self.__service_uuid = service_uuid
        self.__service_handle = service_handle
        self.__descriptors = []
        self.__notification_descriptor = None

        self.__properties = [
            name
            for flag, name in defs.CHARACTERISTIC_PROPERTY_DBUS_NAMES.items()
            if flag & self.obj.getProperties()
        ]

    @property
    def service_uuid(self) -> str:
        """The uuid of the Service containing this characteristic"""
        return self.__service_uuid

    @property
    def service_handle(self) -> int:
        """The integer handle of the Service containing this characteristic"""
        return int(self.__service_handle)

    @property
    def handle(self) -> int:
        """The handle of this characteristic"""
        return self.__handle

    @property
    def uuid(self) -> str:
        """The uuid of this characteristic"""
        return self.__uuid

    @property
    def properties(self) -> List[str]:
        """Properties of this characteristic"""
        return self.__properties

    @property
    def descriptors(self) -> List[BleakGATTDescriptor]:
        """List of descriptors for this service"""
        return self.__descriptors

    def get_descriptor(
        self, specifier: Union[str, UUID]
    ) -> Union[BleakGATTDescriptor, None]:
        """Get a descriptor by UUID (str or uuid.UUID)"""
        if isinstance(specifier, int):
            raise BleakError(
                "The Android Bluetooth API does not provide access to descriptor handles."
            )

        matches = [
            descriptor
            for descriptor in self.descriptors
            if descriptor.uuid == str(specifier)
        ]
        if len(matches) == 0:
            return None
        return matches[0]

    def add_descriptor(self, descriptor: BleakGATTDescriptor):
        """Add a :py:class:`~BleakGATTDescriptor` to the characteristic.

        Should not be used by end user, but rather by `bleak` itself.
        """
        self.__descriptors.append(descriptor)
        if descriptor.uuid == defs.CLIENT_CHARACTERISTIC_CONFIGURATION_UUID:
            self.__notification_descriptor = descriptor

    @property
    def notification_descriptor(self) -> BleakGATTDescriptor:
        """The notification descriptor.  Mostly needed by `bleak`, not by end user"""
        return self.__notification_descriptor
