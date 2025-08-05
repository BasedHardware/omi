from typing import List

from ..service import BleakGATTService
from .characteristic import BleakGATTCharacteristicP4Android


class BleakGATTServiceP4Android(BleakGATTService):
    """GATT Service implementation for the python-for-android backend"""

    def __init__(self, java):
        super().__init__(java)
        self.__uuid = self.obj.getUuid().toString()
        self.__handle = self.obj.getInstanceId()
        self.__characteristics = []

    @property
    def uuid(self) -> str:
        """The UUID to this service"""
        return self.__uuid

    @property
    def handle(self) -> int:
        """A unique identifier for this service"""
        return self.__handle

    @property
    def characteristics(self) -> List[BleakGATTCharacteristicP4Android]:
        """List of characteristics for this service"""
        return self.__characteristics

    def add_characteristic(self, characteristic: BleakGATTCharacteristicP4Android):
        """Add a :py:class:`~BleakGATTCharacteristicP4Android` to the service.

        Should not be used by end user, but rather by `bleak` itself.
        """
        self.__characteristics.append(characteristic)
