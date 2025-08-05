from typing import Callable, List, Union
from uuid import UUID

from ..characteristic import BleakGATTCharacteristic
from ..descriptor import BleakGATTDescriptor
from .defs import GattCharacteristic1
from .utils import extract_service_handle_from_path

_GattCharacteristicsFlagsEnum = {
    0x0001: "broadcast",
    0x0002: "read",
    0x0004: "write-without-response",
    0x0008: "write",
    0x0010: "notify",
    0x0020: "indicate",
    0x0040: "authenticated-signed-writes",
    0x0080: "extended-properties",
    0x0100: "reliable-write",
    0x0200: "writable-auxiliaries",
    # "encrypt-read"
    # "encrypt-write"
    # "encrypt-authenticated-read"
    # "encrypt-authenticated-write"
    # "secure-read" #(Server only)
    # "secure-write" #(Server only)
    # "authorize"
}


class BleakGATTCharacteristicBlueZDBus(BleakGATTCharacteristic):
    """GATT Characteristic implementation for the BlueZ DBus backend"""

    def __init__(
        self,
        obj: GattCharacteristic1,
        object_path: str,
        service_uuid: str,
        service_handle: int,
        max_write_without_response_size: Callable[[], int],
    ):
        super(BleakGATTCharacteristicBlueZDBus, self).__init__(
            obj, max_write_without_response_size
        )
        self.__descriptors = []
        self.__path = object_path
        self.__service_uuid = service_uuid
        self.__service_handle = service_handle
        self._handle = extract_service_handle_from_path(object_path)

    @property
    def service_uuid(self) -> str:
        """The uuid of the Service containing this characteristic"""
        return self.__service_uuid

    @property
    def service_handle(self) -> int:
        """The handle of the Service containing this characteristic"""
        return self.__service_handle

    @property
    def handle(self) -> int:
        """The handle of this characteristic"""
        return self._handle

    @property
    def uuid(self) -> str:
        """The uuid of this characteristic"""
        return self.obj.get("UUID")

    @property
    def properties(self) -> List[str]:
        """Properties of this characteristic

        Returns the characteristics `Flags` present in the DBus API.
        """
        return self.obj["Flags"]

    @property
    def descriptors(self) -> List[BleakGATTDescriptor]:
        """List of descriptors for this service"""
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

    def add_descriptor(self, descriptor: BleakGATTDescriptor) -> None:
        """Add a :py:class:`~BleakGATTDescriptor` to the characteristic.

        Should not be used by end user, but rather by `bleak` itself.
        """
        self.__descriptors.append(descriptor)

    @property
    def path(self) -> str:
        """The DBus path. Mostly needed by `bleak`, not by end user"""
        return self.__path
