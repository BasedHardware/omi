"""
Bluetooth Assigned Numbers
--------------------------

This module contains useful assigned numbers from the Bluetooth spec.

See <https://www.bluetooth.com/specifications/assigned-numbers/>.
"""

from enum import IntEnum


class AdvertisementDataType(IntEnum):
    """
    Generic Access Profile advertisement data types.

    `Source <https://btprodspecificationrefs.blob.core.windows.net/assigned-numbers/Assigned%20Number%20Types/Generic%20Access%20Profile.pdf>`.

    .. versionadded:: 0.15
    """

    FLAGS = 0x01
    INCOMPLETE_LIST_SERVICE_UUID16 = 0x02
    COMPLETE_LIST_SERVICE_UUID16 = 0x03
    INCOMPLETE_LIST_SERVICE_UUID32 = 0x04
    COMPLETE_LIST_SERVICE_UUID32 = 0x05
    INCOMPLETE_LIST_SERVICE_UUID128 = 0x06
    COMPLETE_LIST_SERVICE_UUID128 = 0x07
    SHORTENED_LOCAL_NAME = 0x08
    COMPLETE_LOCAL_NAME = 0x09
    TX_POWER_LEVEL = 0x0A
    CLASS_OF_DEVICE = 0x0D

    SERVICE_DATA_UUID16 = 0x16
    SERVICE_DATA_UUID32 = 0x20
    SERVICE_DATA_UUID128 = 0x21

    MANUFACTURER_SPECIFIC_DATA = 0xFF
