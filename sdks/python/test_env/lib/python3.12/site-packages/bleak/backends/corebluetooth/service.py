from typing import List

from CoreBluetooth import CBService

from ..service import BleakGATTService
from .characteristic import BleakGATTCharacteristicCoreBluetooth
from .utils import cb_uuid_to_str


class BleakGATTServiceCoreBluetooth(BleakGATTService):
    """GATT Characteristic implementation for the CoreBluetooth backend"""

    def __init__(self, obj: CBService):
        super().__init__(obj)
        self.__characteristics: List[BleakGATTCharacteristicCoreBluetooth] = []
        # N.B. the `startHandle` method of the CBService is an undocumented Core Bluetooth feature,
        # which Bleak takes advantage of in order to have a service handle to use.
        self.__handle: int = int(self.obj.startHandle())

    @property
    def handle(self) -> int:
        """The integer handle of this service"""
        return self.__handle

    @property
    def uuid(self) -> str:
        """UUID for this service."""
        return cb_uuid_to_str(self.obj.UUID())

    @property
    def characteristics(self) -> List[BleakGATTCharacteristicCoreBluetooth]:
        """List of characteristics for this service"""
        return self.__characteristics

    def add_characteristic(
        self, characteristic: BleakGATTCharacteristicCoreBluetooth
    ) -> None:
        """Add a :py:class:`~BleakGATTCharacteristicCoreBluetooth` to the service.

        Should not be used by end user, but rather by `bleak` itself.
        """
        self.__characteristics.append(characteristic)
