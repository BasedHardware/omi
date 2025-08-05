# -*- coding: utf-8 -*-
"""
Interface class for the Bleak representation of a GATT Characteristic

Created on 2019-03-19 by hbldh <henrik.blidh@nedomkull.com>

"""
import abc
import enum
from typing import Any, Callable, List, Union
from uuid import UUID

from ..uuids import uuidstr_to_str
from .descriptor import BleakGATTDescriptor


class GattCharacteristicsFlags(enum.Enum):
    broadcast = 0x0001
    read = 0x0002
    write_without_response = 0x0004
    write = 0x0008
    notify = 0x0010
    indicate = 0x0020
    authenticated_signed_writes = 0x0040
    extended_properties = 0x0080
    reliable_write = 0x0100
    writable_auxiliaries = 0x0200


class BleakGATTCharacteristic(abc.ABC):
    """Interface for the Bleak representation of a GATT Characteristic"""

    def __init__(self, obj: Any, max_write_without_response_size: Callable[[], int]):
        """
        Args:
            obj:
                A platform-specific object for this characteristic.
            max_write_without_response_size:
                The maximum size in bytes that can be written to the
                characteristic in a single write without response command.
        """
        self.obj = obj
        self._max_write_without_response_size = max_write_without_response_size

    def __str__(self):
        return f"{self.uuid} (Handle: {self.handle}): {self.description}"

    @property
    @abc.abstractmethod
    def service_uuid(self) -> str:
        """The UUID of the Service containing this characteristic"""
        raise NotImplementedError()

    @property
    @abc.abstractmethod
    def service_handle(self) -> int:
        """The integer handle of the Service containing this characteristic"""
        raise NotImplementedError()

    @property
    @abc.abstractmethod
    def handle(self) -> int:
        """The handle for this characteristic"""
        raise NotImplementedError()

    @property
    @abc.abstractmethod
    def uuid(self) -> str:
        """The UUID for this characteristic"""
        raise NotImplementedError()

    @property
    def description(self) -> str:
        """Description for this characteristic"""
        return uuidstr_to_str(self.uuid)

    @property
    @abc.abstractmethod
    def properties(self) -> List[str]:
        """Properties of this characteristic"""
        raise NotImplementedError()

    @property
    def max_write_without_response_size(self) -> int:
        """
        Gets the maximum size in bytes that can be used for the *data* argument
        of :meth:`BleakClient.write_gatt_char()` when ``response=False``.

        In rare cases, a device may take a long time to update this value, so
        reading this property may return the default value of ``20`` and reading
        it again after a some time may return the expected higher value.

        If you *really* need to wait for a higher value, you can do something
        like this:

        .. code-block:: python

            async with asyncio.timeout(10):
                while char.max_write_without_response_size == 20:
                    await asyncio.sleep(0.5)

        .. warning:: Linux quirk: For BlueZ versions < 5.62, this property
            will always return ``20``.

        .. versionadded:: 0.16
        """

        # for backwards compatibility
        if isinstance(self._max_write_without_response_size, int):
            return self._max_write_without_response_size

        return self._max_write_without_response_size()

    @property
    @abc.abstractmethod
    def descriptors(self) -> List[BleakGATTDescriptor]:
        """List of descriptors for this service"""
        raise NotImplementedError()

    @abc.abstractmethod
    def get_descriptor(
        self, specifier: Union[int, str, UUID]
    ) -> Union[BleakGATTDescriptor, None]:
        """Get a descriptor by handle (int) or UUID (str or uuid.UUID)"""
        raise NotImplementedError()

    @abc.abstractmethod
    def add_descriptor(self, descriptor: BleakGATTDescriptor) -> None:
        """Add a :py:class:`~BleakGATTDescriptor` to the characteristic.

        Should not be used by end user, but rather by `bleak` itself.
        """
        raise NotImplementedError()
