"""
Interface class for the Bleak representation of a GATT Characteristic

Created on 2019-06-28 by kevincar <kevincarrolldavis@gmail.com>

"""

from enum import Enum
from typing import Callable, Dict, List, Optional, Tuple, Union

from CoreBluetooth import CBCharacteristic

from ..characteristic import BleakGATTCharacteristic
from ..descriptor import BleakGATTDescriptor
from .descriptor import BleakGATTDescriptorCoreBluetooth
from .utils import cb_uuid_to_str


class CBCharacteristicProperties(Enum):
    BROADCAST = 0x1
    READ = 0x2
    WRITE_WITHOUT_RESPONSE = 0x4
    WRITE = 0x8
    NOTIFY = 0x10
    INDICATE = 0x20
    AUTHENTICATED_SIGNED_WRITES = 0x40
    EXTENDED_PROPERTIES = 0x80
    NOTIFY_ENCRYPTION_REQUIRED = 0x100
    INDICATE_ENCRYPTION_REQUIRED = 0x200


_GattCharacteristicsPropertiesEnum: Dict[Optional[int], Tuple[str, str]] = {
    None: ("None", "The characteristic doesn’t have any properties that apply"),
    1: ("Broadcast".lower(), "The characteristic supports broadcasting"),
    2: ("Read".lower(), "The characteristic is readable"),
    4: (
        "Write-Without-Response".lower(),
        "The characteristic supports Write Without Response",
    ),
    8: ("Write".lower(), "The characteristic is writable"),
    16: ("Notify".lower(), "The characteristic is notifiable"),
    32: ("Indicate".lower(), "The characteristic is indicatable"),
    64: (
        "Authenticated-Signed-Writes".lower(),
        "The characteristic supports signed writes",
    ),
    128: (
        "Extended-Properties".lower(),
        "The ExtendedProperties Descriptor is present",
    ),
    256: ("Reliable-Writes".lower(), "The characteristic supports reliable writes"),
    512: (
        "Writable-Auxiliaries".lower(),
        "The characteristic has writable auxiliaries",
    ),
}


class BleakGATTCharacteristicCoreBluetooth(BleakGATTCharacteristic):
    """GATT Characteristic implementation for the CoreBluetooth backend"""

    def __init__(
        self, obj: CBCharacteristic, max_write_without_response_size: Callable[[], int]
    ):
        super().__init__(obj, max_write_without_response_size)
        self.__descriptors: List[BleakGATTDescriptorCoreBluetooth] = []
        # self.__props = obj.properties()
        self.__props: List[str] = [
            _GattCharacteristicsPropertiesEnum[v][0]
            for v in [2**n for n in range(10)]
            if (self.obj.properties() & v)
        ]
        self._uuid: str = cb_uuid_to_str(self.obj.UUID())

    @property
    def service_uuid(self) -> str:
        """The uuid of the Service containing this characteristic"""
        return cb_uuid_to_str(self.obj.service().UUID())

    @property
    def service_handle(self) -> int:
        return int(self.obj.service().startHandle())

    @property
    def handle(self) -> int:
        """Integer handle for this characteristic"""
        return int(self.obj.handle())

    @property
    def uuid(self) -> str:
        """The uuid of this characteristic"""
        return self._uuid

    @property
    def properties(self) -> List[str]:
        """Properties of this characteristic"""
        return self.__props

    @property
    def descriptors(self) -> List[BleakGATTDescriptor]:
        """List of descriptors for this service"""
        return self.__descriptors

    def get_descriptor(self, specifier) -> Union[BleakGATTDescriptor, None]:
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
