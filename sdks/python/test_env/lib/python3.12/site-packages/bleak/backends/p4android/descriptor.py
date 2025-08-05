from ..descriptor import BleakGATTDescriptor


class BleakGATTDescriptorP4Android(BleakGATTDescriptor):
    """GATT Descriptor implementation for python-for-android backend"""

    def __init__(
        self, java, characteristic_uuid: str, characteristic_handle: int, index: int
    ):
        super(BleakGATTDescriptorP4Android, self).__init__(java)
        self.__uuid = self.obj.getUuid().toString()
        self.__characteristic_uuid = characteristic_uuid
        self.__characteristic_handle = characteristic_handle
        # many devices have sequential handles and this formula will mysteriously work for them
        # it's possible this formula could make duplicate handles on other devices.
        self.__fake_handle = self.__characteristic_handle + 1 + index

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
        return self.__uuid

    @property
    def handle(self) -> int:
        """Integer handle for this descriptor"""
        # 2021-01 The Android Bluetooth API does not appear to provide access to descriptor handles.
        return self.__fake_handle
