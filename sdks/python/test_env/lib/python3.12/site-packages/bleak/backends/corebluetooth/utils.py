from CoreBluetooth import CBUUID
from Foundation import NSData

from ...uuids import normalize_uuid_str


def cb_uuid_to_str(uuid: CBUUID) -> str:
    """Converts a CoreBluetooth UUID to a Python string.

    If ``uuid`` is a 16-bit UUID, it is assumed to be a Bluetooth GATT UUID
    (``0000xxxx-0000-1000-8000-00805f9b34fb``).

    Args
        uuid: The UUID.

    Returns:
        The UUID as a lower case Python string (``xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxx``)
    """
    return normalize_uuid_str(uuid.UUIDString())


def _is_uuid_16bit_compatible(_uuid: str) -> bool:
    test_uuid = "0000ffff-0000-1000-8000-00805f9b34fb"
    test_int = _convert_uuid_to_int(test_uuid)
    uuid_int = _convert_uuid_to_int(_uuid)
    result_int = uuid_int & test_int
    return uuid_int == result_int


def _convert_uuid_to_int(_uuid: str) -> int:
    UUID_cb = CBUUID.alloc().initWithString_(_uuid)
    UUID_data = UUID_cb.data()
    UUID_bytes = UUID_data.getBytes_length_(None, len(UUID_data))
    UUID_int = int.from_bytes(UUID_bytes, byteorder="big")
    return UUID_int


def _convert_int_to_uuid(i: int) -> str:
    UUID_bytes = i.to_bytes(length=16, byteorder="big")
    UUID_data = NSData.alloc().initWithBytes_length_(UUID_bytes, len(UUID_bytes))
    UUID_cb = CBUUID.alloc().initWithData_(UUID_data)
    return UUID_cb.UUIDString().lower()
