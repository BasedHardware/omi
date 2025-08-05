"""
BLE Client for CoreBluetooth on macOS

Created on 2019-06-26 by kevincar <kevincarrolldavis@gmail.com>
"""

import asyncio
import logging
import sys
import uuid
from typing import Optional, Set, Union

if sys.version_info < (3, 12):
    from typing_extensions import Buffer
else:
    from collections.abc import Buffer

from CoreBluetooth import (
    CBUUID,
    CBCharacteristicWriteWithoutResponse,
    CBCharacteristicWriteWithResponse,
    CBPeripheral,
    CBPeripheralStateConnected,
)
from Foundation import NSArray, NSData

from ... import BleakScanner
from ...exc import (
    BleakCharacteristicNotFoundError,
    BleakDeviceNotFoundError,
    BleakError,
)
from ..characteristic import BleakGATTCharacteristic
from ..client import BaseBleakClient, NotifyCallback
from ..device import BLEDevice
from ..service import BleakGATTServiceCollection
from .CentralManagerDelegate import CentralManagerDelegate
from .characteristic import BleakGATTCharacteristicCoreBluetooth
from .descriptor import BleakGATTDescriptorCoreBluetooth
from .PeripheralDelegate import PeripheralDelegate
from .scanner import BleakScannerCoreBluetooth
from .service import BleakGATTServiceCoreBluetooth
from .utils import cb_uuid_to_str

logger = logging.getLogger(__name__)


class BleakClientCoreBluetooth(BaseBleakClient):
    """CoreBluetooth class interface for BleakClient

    Args:
        address_or_ble_device (`BLEDevice` or str): The Bluetooth address of the BLE peripheral to connect to or the `BLEDevice` object representing it.
        services: Optional set of service UUIDs that will be used.

    Keyword Args:
        timeout (float): Timeout for required ``BleakScanner.find_device_by_address`` call. Defaults to 10.0.

    """

    def __init__(
        self,
        address_or_ble_device: Union[BLEDevice, str],
        services: Optional[Set[str]] = None,
        **kwargs,
    ):
        super(BleakClientCoreBluetooth, self).__init__(address_or_ble_device, **kwargs)

        self._peripheral: Optional[CBPeripheral] = None
        self._delegate: Optional[PeripheralDelegate] = None
        self._central_manager_delegate: Optional[CentralManagerDelegate] = None

        if isinstance(address_or_ble_device, BLEDevice):
            (
                self._peripheral,
                self._central_manager_delegate,
            ) = address_or_ble_device.details

        self._requested_services = (
            NSArray.alloc().initWithArray_(list(map(CBUUID.UUIDWithString_, services)))
            if services
            else None
        )

    def __str__(self) -> str:
        return "BleakClientCoreBluetooth ({})".format(self.address)

    async def connect(self, **kwargs) -> bool:
        """Connect to a specified Peripheral

        Keyword Args:
            timeout (float): Timeout for required ``BleakScanner.find_device_by_address`` call. Defaults to 10.0.

        Returns:
            Boolean representing connection status.

        """
        timeout = kwargs.get("timeout", self._timeout)
        if self._peripheral is None:
            device = await BleakScanner.find_device_by_address(
                self.address, timeout=timeout, backend=BleakScannerCoreBluetooth
            )

            if device:
                self._peripheral, self._central_manager_delegate = device.details
            else:
                raise BleakDeviceNotFoundError(
                    self.address, f"Device with address {self.address} was not found"
                )

        if self._delegate is None:
            self._delegate = PeripheralDelegate.alloc().initWithPeripheral_(
                self._peripheral
            )

        def disconnect_callback() -> None:
            # Ensure that `get_services` retrieves services again, rather
            # than using the cached object
            self.services = None

            # If there are any pending futures waiting for delegate callbacks, we
            # need to raise an exception since the callback will no longer be
            # called because the device is disconnected.
            for future in self._delegate.futures():
                try:
                    future.set_exception(BleakError("disconnected"))
                except asyncio.InvalidStateError:
                    # the future was already done
                    pass

            if self._disconnected_callback:
                self._disconnected_callback()

        manager = self._central_manager_delegate
        logger.debug("CentralManagerDelegate  at {}".format(manager))
        logger.debug("Connecting to BLE device @ {}".format(self.address))
        await manager.connect(self._peripheral, disconnect_callback, timeout=timeout)

        # Now get services
        await self.get_services()

        return True

    async def disconnect(self) -> bool:
        """Disconnect from the peripheral device"""
        if (
            self._peripheral is None
            or self._peripheral.state() != CBPeripheralStateConnected
        ):
            return True

        await self._central_manager_delegate.disconnect(self._peripheral)

        return True

    @property
    def is_connected(self) -> bool:
        """Checks for current active connection"""
        return self._DeprecatedIsConnectedReturn(
            False
            if self._peripheral is None
            else self._peripheral.state() == CBPeripheralStateConnected
        )

    @property
    def mtu_size(self) -> int:
        """Get ATT MTU size for active connection"""
        # Use type CBCharacteristicWriteWithoutResponse to get maximum write
        # value length based on the negotiated ATT MTU size. Add the ATT header
        # length (+3) to get the actual ATT MTU size.
        return (
            self._peripheral.maximumWriteValueLengthForType_(
                CBCharacteristicWriteWithoutResponse
            )
            + 3
        )

    async def pair(self, *args, **kwargs) -> bool:
        """Attempt to pair with a peripheral.

        .. note::

            This is not available on macOS since there is not explicit method to do a pairing, Instead the docs
            state that it "auto-pairs" when trying to read a characteristic that requires encryption, something
            Bleak cannot do apparently.

        Reference:

            - `Apple Docs <https://developer.apple.com/library/archive/documentation/NetworkingInternetWeb/Conceptual/CoreBluetooth_concepts/BestPracticesForSettingUpYourIOSDeviceAsAPeripheral/BestPracticesForSettingUpYourIOSDeviceAsAPeripheral.html#//apple_ref/doc/uid/TP40013257-CH5-SW1>`_
            - `Stack Overflow post #1 <https://stackoverflow.com/questions/25254932/can-you-pair-a-bluetooth-le-device-in-an-ios-app>`_
            - `Stack Overflow post #2 <https://stackoverflow.com/questions/47546690/ios-bluetooth-pairing-request-dialog-can-i-know-the-users-choice>`_

        Returns:
            Boolean regarding success of pairing.

        """
        raise NotImplementedError("Pairing is not available in Core Bluetooth.")

    async def unpair(self) -> bool:
        """

        Returns:

        """
        raise NotImplementedError("Pairing is not available in Core Bluetooth.")

    async def get_services(self, **kwargs) -> BleakGATTServiceCollection:
        """Get all services registered for this GATT server.

        Returns:
           A :py:class:`bleak.backends.service.BleakGATTServiceCollection` with this device's services tree.

        """
        if self.services is not None:
            return self.services

        services = BleakGATTServiceCollection()

        logger.debug("Retrieving services...")
        cb_services = await self._delegate.discover_services(self._requested_services)

        for service in cb_services:
            serviceUUID = service.UUID().UUIDString()
            logger.debug(
                "Retrieving characteristics for service {}".format(serviceUUID)
            )
            characteristics = await self._delegate.discover_characteristics(service)

            services.add_service(BleakGATTServiceCoreBluetooth(service))

            for characteristic in characteristics:
                cUUID = characteristic.UUID().UUIDString()
                logger.debug(
                    "Retrieving descriptors for characteristic {}".format(cUUID)
                )
                descriptors = await self._delegate.discover_descriptors(characteristic)

                services.add_characteristic(
                    BleakGATTCharacteristicCoreBluetooth(
                        characteristic,
                        lambda: self._peripheral.maximumWriteValueLengthForType_(
                            CBCharacteristicWriteWithoutResponse
                        ),
                    )
                )
                for descriptor in descriptors:
                    services.add_descriptor(
                        BleakGATTDescriptorCoreBluetooth(
                            descriptor,
                            cb_uuid_to_str(characteristic.UUID()),
                            int(characteristic.handle()),
                        )
                    )
        logger.debug("Services resolved for %s", str(self))
        self.services = services
        return self.services

    async def read_gatt_char(
        self,
        char_specifier: Union[BleakGATTCharacteristic, int, str, uuid.UUID],
        use_cached: bool = False,
        **kwargs,
    ) -> bytearray:
        """Perform read operation on the specified GATT characteristic.

        Args:
            char_specifier (BleakGATTCharacteristic, int, str or UUID): The characteristic to read from,
                specified by either integer handle, UUID or directly by the
                BleakGATTCharacteristic object representing it.
            use_cached (bool): `False` forces macOS to read the value from the
                device again and not use its own cached value. Defaults to `False`.

        Returns:
            (bytearray) The read data.

        """
        if not isinstance(char_specifier, BleakGATTCharacteristic):
            characteristic = self.services.get_characteristic(char_specifier)
        else:
            characteristic = char_specifier
        if not characteristic:
            raise BleakCharacteristicNotFoundError(char_specifier)

        output = await self._delegate.read_characteristic(
            characteristic.obj, use_cached=use_cached
        )
        value = bytearray(output)
        logger.debug("Read Characteristic {0} : {1}".format(characteristic.uuid, value))
        return value

    async def read_gatt_descriptor(
        self, handle: int, use_cached: bool = False, **kwargs
    ) -> bytearray:
        """Perform read operation on the specified GATT descriptor.

        Args:
            handle (int): The handle of the descriptor to read from.
            use_cached (bool): `False` forces Windows to read the value from the
                device again and not use its own cached value. Defaults to `False`.

        Returns:
            (bytearray) The read data.
        """
        descriptor = self.services.get_descriptor(handle)
        if not descriptor:
            raise BleakError("Descriptor {} was not found!".format(handle))

        output = await self._delegate.read_descriptor(
            descriptor.obj, use_cached=use_cached
        )
        if isinstance(
            output, str
        ):  # Sometimes a `pyobjc_unicode`or `__NSCFString` is returned and they can be used as regular Python strings.
            value = bytearray(output.encode("utf-8"))
        else:  # _NSInlineData
            value = bytearray(output)  # value.getBytes_length_(None, len(value))
        logger.debug("Read Descriptor {0} : {1}".format(handle, value))
        return value

    async def write_gatt_char(
        self,
        characteristic: BleakGATTCharacteristic,
        data: Buffer,
        response: bool,
    ) -> None:
        value = NSData.alloc().initWithBytes_length_(data, len(data))
        await self._delegate.write_characteristic(
            characteristic.obj,
            value,
            (
                CBCharacteristicWriteWithResponse
                if response
                else CBCharacteristicWriteWithoutResponse
            ),
        )
        logger.debug(f"Write Characteristic {characteristic.uuid} : {data}")

    async def write_gatt_descriptor(self, handle: int, data: Buffer) -> None:
        """Perform a write operation on the specified GATT descriptor.

        Args:
            handle: The handle of the descriptor to read from.
            data: The data to send (any bytes-like object).

        """
        descriptor = self.services.get_descriptor(handle)
        if not descriptor:
            raise BleakError("Descriptor {} was not found!".format(handle))

        value = NSData.alloc().initWithBytes_length_(data, len(data))
        await self._delegate.write_descriptor(descriptor.obj, value)
        logger.debug("Write Descriptor {0} : {1}".format(handle, data))

    async def start_notify(
        self,
        characteristic: BleakGATTCharacteristic,
        callback: NotifyCallback,
        **kwargs,
    ) -> None:
        """
        Activate notifications/indications on a characteristic.
        """
        assert self._delegate is not None

        await self._delegate.start_notifications(characteristic.obj, callback)

    async def stop_notify(
        self, char_specifier: Union[BleakGATTCharacteristic, int, str, uuid.UUID]
    ) -> None:
        """Deactivate notification/indication on a specified characteristic.

        Args:
            char_specifier (BleakGATTCharacteristic, int, str or UUID): The characteristic to deactivate
                notification/indication on, specified by either integer handle, UUID or
                directly by the BleakGATTCharacteristic object representing it.


        """
        if not isinstance(char_specifier, BleakGATTCharacteristic):
            characteristic = self.services.get_characteristic(char_specifier)
        else:
            characteristic = char_specifier
        if not characteristic:
            raise BleakCharacteristicNotFoundError(char_specifier)

        await self._delegate.stop_notifications(characteristic.obj)

    async def get_rssi(self) -> int:
        """To get RSSI value in dBm of the connected Peripheral"""
        return int(await self._delegate.read_rssi())
