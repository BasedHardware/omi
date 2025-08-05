# -*- coding: utf-8 -*-
"""
Gatt Service Collection class and interface class for the Bleak representation of a GATT Service.

Created on 2019-03-19 by hbldh <henrik.blidh@nedomkull.com>

"""
import abc
import logging
from typing import Any, Dict, Iterator, List, Optional, Union
from uuid import UUID

from ..exc import BleakError
from ..uuids import normalize_uuid_str, uuidstr_to_str
from .characteristic import BleakGATTCharacteristic
from .descriptor import BleakGATTDescriptor

logger = logging.getLogger(__name__)


class BleakGATTService(abc.ABC):
    """Interface for the Bleak representation of a GATT Service."""

    def __init__(self, obj: Any) -> None:
        self.obj = obj

    def __str__(self) -> str:
        return f"{self.uuid} (Handle: {self.handle}): {self.description}"

    @property
    @abc.abstractmethod
    def handle(self) -> int:
        """The handle of this service"""
        raise NotImplementedError()

    @property
    @abc.abstractmethod
    def uuid(self) -> str:
        """The UUID to this service"""
        raise NotImplementedError()

    @property
    def description(self) -> str:
        """String description for this service"""
        return uuidstr_to_str(self.uuid)

    @property
    @abc.abstractmethod
    def characteristics(self) -> List[BleakGATTCharacteristic]:
        """List of characteristics for this service"""
        raise NotImplementedError()

    @abc.abstractmethod
    def add_characteristic(self, characteristic: BleakGATTCharacteristic) -> None:
        """Add a :py:class:`~BleakGATTCharacteristic` to the service.

        Should not be used by end user, but rather by `bleak` itself.
        """
        raise NotImplementedError()

    def get_characteristic(
        self, uuid: Union[str, UUID]
    ) -> Union[BleakGATTCharacteristic, None]:
        """Get a characteristic by UUID.

        Args:
            uuid: The UUID to match.

        Returns:
            The first characteristic matching ``uuid`` or ``None`` if no
            matching characteristic was found.
        """
        uuid = normalize_uuid_str(str(uuid))

        try:
            return next(filter(lambda x: x.uuid == uuid, self.characteristics))
        except StopIteration:
            return None


class BleakGATTServiceCollection:
    """Simple data container for storing the peripheral's service complement."""

    def __init__(self) -> None:
        self.__services = {}
        self.__characteristics = {}
        self.__descriptors = {}

    def __getitem__(
        self, item: Union[str, int, UUID]
    ) -> Optional[
        Union[BleakGATTService, BleakGATTCharacteristic, BleakGATTDescriptor]
    ]:
        """Get a service, characteristic or descriptor from uuid or handle"""
        return (
            self.get_service(item)
            or self.get_characteristic(item)
            or self.get_descriptor(item)
        )

    def __iter__(self) -> Iterator[BleakGATTService]:
        """Returns an iterator over all BleakGATTService objects"""
        return iter(self.services.values())

    @property
    def services(self) -> Dict[int, BleakGATTService]:
        """Returns dictionary of handles mapping to BleakGATTService"""
        return self.__services

    @property
    def characteristics(self) -> Dict[int, BleakGATTCharacteristic]:
        """Returns dictionary of handles mapping to BleakGATTCharacteristic"""
        return self.__characteristics

    @property
    def descriptors(self) -> Dict[int, BleakGATTDescriptor]:
        """Returns a dictionary of integer handles mapping to BleakGATTDescriptor"""
        return self.__descriptors

    def add_service(self, service: BleakGATTService) -> None:
        """Add a :py:class:`~BleakGATTService` to the service collection.

        Should not be used by end user, but rather by `bleak` itself.
        """
        if service.handle not in self.__services:
            self.__services[service.handle] = service
        else:
            logger.error(
                "The service '%s' is already present in this BleakGATTServiceCollection!",
                service.handle,
            )

    def get_service(
        self, specifier: Union[int, str, UUID]
    ) -> Optional[BleakGATTService]:
        """Get a service by handle (int) or UUID (str or uuid.UUID)"""
        if isinstance(specifier, int):
            return self.services.get(specifier)

        uuid = normalize_uuid_str(str(specifier))

        x = list(
            filter(
                lambda x: x.uuid == uuid,
                self.services.values(),
            )
        )

        if len(x) > 1:
            raise BleakError(
                "Multiple Services with this UUID, refer to your desired service by the `handle` attribute instead."
            )

        return x[0] if x else None

    def add_characteristic(self, characteristic: BleakGATTCharacteristic) -> None:
        """Add a :py:class:`~BleakGATTCharacteristic` to the service collection.

        Should not be used by end user, but rather by `bleak` itself.
        """
        if characteristic.handle not in self.__characteristics:
            self.__characteristics[characteristic.handle] = characteristic
            self.__services[characteristic.service_handle].add_characteristic(
                characteristic
            )
        else:
            logger.error(
                "The characteristic '%s' is already present in this BleakGATTServiceCollection!",
                characteristic.handle,
            )

    def get_characteristic(
        self, specifier: Union[int, str, UUID]
    ) -> Optional[BleakGATTCharacteristic]:
        """Get a characteristic by handle (int) or UUID (str or uuid.UUID)"""
        if isinstance(specifier, int):
            return self.characteristics.get(specifier)

        uuid = normalize_uuid_str(str(specifier))

        # Assume uuid usage.
        x = list(
            filter(
                lambda x: x.uuid == uuid,
                self.characteristics.values(),
            )
        )

        if len(x) > 1:
            raise BleakError(
                "Multiple Characteristics with this UUID, refer to your desired characteristic by the `handle` attribute instead."
            )

        return x[0] if x else None

    def add_descriptor(self, descriptor: BleakGATTDescriptor) -> None:
        """Add a :py:class:`~BleakGATTDescriptor` to the service collection.

        Should not be used by end user, but rather by `bleak` itself.
        """
        if descriptor.handle not in self.__descriptors:
            self.__descriptors[descriptor.handle] = descriptor
            self.__characteristics[descriptor.characteristic_handle].add_descriptor(
                descriptor
            )
        else:
            logger.error(
                "The descriptor '%s' is already present in this BleakGATTServiceCollection!",
                descriptor.handle,
            )

    def get_descriptor(self, handle: int) -> Optional[BleakGATTDescriptor]:
        """Get a descriptor by integer handle"""
        return self.descriptors.get(handle)
