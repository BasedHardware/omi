from ..descriptor import BleakGATTDescriptor
from .defs import GattDescriptor1


class BleakGATTDescriptorBlueZDBus(BleakGATTDescriptor):
    """GATT Descriptor implementation for BlueZ DBus backend"""

    def __init__(
        self,
        obj: GattDescriptor1,
        object_path: str,
        characteristic_uuid: str,
        characteristic_handle: int,
    ):
        super(BleakGATTDescriptorBlueZDBus, self).__init__(obj)
        self.__path = object_path
        self.__characteristic_uuid = characteristic_uuid
        self.__characteristic_handle = characteristic_handle
        self.__handle = int(self.path.split("/")[-1].replace("desc", ""), 16)

    @property
    def characteristic_handle(self) -> int:
        """Handle for the characteristic that this descriptor belongs to"""
        return self.__characteristic_handle

    @property
    def characteristic_uuid(self) -> str:
        """UUID for the characteristic that this descriptor belongs to"""
        return self.__characteristic_uuid

    @property
    def uuid(self) -> str:
        """UUID for this descriptor"""
        return self.obj["UUID"]

    @property
    def handle(self) -> int:
        """Integer handle for this descriptor"""
        return self.__handle

    @property
    def path(self) -> str:
        """The DBus path. Mostly needed by `bleak`, not by end user"""
        return self.__path
