"""

PeripheralDelegate

Created by kevincar <kevincarrolldavis@gmail.com>

"""

from __future__ import annotations

import asyncio
import itertools
import logging
import sys
from typing import Any, Dict, Iterable, NewType, Optional

if sys.version_info < (3, 11):
    from async_timeout import timeout as async_timeout
else:
    from asyncio import timeout as async_timeout

import objc
from CoreBluetooth import (
    CBCharacteristic,
    CBCharacteristicWriteWithResponse,
    CBDescriptor,
    CBPeripheral,
    CBService,
)
from Foundation import NSUUID, NSArray, NSData, NSError, NSNumber, NSObject, NSString

from ...exc import BleakError
from ..client import NotifyCallback

# logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

CBPeripheralDelegate = objc.protocolNamed("CBPeripheralDelegate")

CBCharacteristicWriteType = NewType("CBCharacteristicWriteType", int)


class PeripheralDelegate(NSObject):
    """macOS conforming python class for managing the PeripheralDelegate for BLE"""

    ___pyobjc_protocols__ = [CBPeripheralDelegate]

    def initWithPeripheral_(
        self, peripheral: CBPeripheral
    ) -> Optional[PeripheralDelegate]:
        """macOS init function for NSObject"""
        self = objc.super(PeripheralDelegate, self).init()

        if self is None:
            return None

        self.peripheral = peripheral
        self.peripheral.setDelegate_(self)

        self._event_loop = asyncio.get_running_loop()
        self._services_discovered_future = self._event_loop.create_future()

        self._service_characteristic_discovered_futures: Dict[int, asyncio.Future] = {}
        self._characteristic_descriptor_discover_futures: Dict[int, asyncio.Future] = {}

        self._characteristic_read_futures: Dict[int, asyncio.Future] = {}
        self._characteristic_write_futures: Dict[int, asyncio.Future] = {}

        self._descriptor_read_futures: Dict[int, asyncio.Future] = {}
        self._descriptor_write_futures: Dict[int, asyncio.Future] = {}

        self._characteristic_notify_change_futures: Dict[int, asyncio.Future] = {}
        self._characteristic_notify_callbacks: Dict[int, NotifyCallback] = {}

        self._read_rssi_futures: Dict[NSUUID, asyncio.Future] = {}

        return self

    @objc.python_method
    def futures(self) -> Iterable[asyncio.Future]:
        """
        Gets all futures for this delegate.

        These can be used to handle any pending futures when a peripheral is disconnected.
        """
        services_discovered_future = (
            (self._services_discovered_future,)
            if hasattr(self, "_services_discovered_future")
            else ()
        )

        return itertools.chain(
            services_discovered_future,
            self._service_characteristic_discovered_futures.values(),
            self._characteristic_descriptor_discover_futures.values(),
            self._characteristic_read_futures.values(),
            self._characteristic_write_futures.values(),
            self._descriptor_read_futures.values(),
            self._descriptor_write_futures.values(),
            self._characteristic_notify_change_futures.values(),
            self._read_rssi_futures.values(),
        )

    @objc.python_method
    async def discover_services(self, services: Optional[NSArray]) -> NSArray:
        future = self._event_loop.create_future()

        self._services_discovered_future = future
        try:
            self.peripheral.discoverServices_(services)
            return await future
        finally:
            del self._services_discovered_future

    @objc.python_method
    async def discover_characteristics(self, service: CBService) -> NSArray:
        future = self._event_loop.create_future()

        self._service_characteristic_discovered_futures[service.startHandle()] = future
        try:
            self.peripheral.discoverCharacteristics_forService_(None, service)
            return await future
        finally:
            del self._service_characteristic_discovered_futures[service.startHandle()]

    @objc.python_method
    async def discover_descriptors(self, characteristic: CBCharacteristic) -> NSArray:
        future = self._event_loop.create_future()

        self._characteristic_descriptor_discover_futures[characteristic.handle()] = (
            future
        )
        try:
            self.peripheral.discoverDescriptorsForCharacteristic_(characteristic)
            await future
        finally:
            del self._characteristic_descriptor_discover_futures[
                characteristic.handle()
            ]

        return characteristic.descriptors()

    @objc.python_method
    async def read_characteristic(
        self,
        characteristic: CBCharacteristic,
        use_cached: bool = True,
        timeout: int = 20,
    ) -> NSData:
        if characteristic.value() is not None and use_cached:
            return characteristic.value()

        future = self._event_loop.create_future()

        self._characteristic_read_futures[characteristic.handle()] = future
        try:
            self.peripheral.readValueForCharacteristic_(characteristic)
            async with async_timeout(timeout):
                return await future
        finally:
            del self._characteristic_read_futures[characteristic.handle()]

    @objc.python_method
    async def read_descriptor(
        self, descriptor: CBDescriptor, use_cached: bool = True
    ) -> Any:
        if descriptor.value() is not None and use_cached:
            return descriptor.value()

        future = self._event_loop.create_future()

        self._descriptor_read_futures[descriptor.handle()] = future
        try:
            self.peripheral.readValueForDescriptor_(descriptor)
            return await future
        finally:
            del self._descriptor_read_futures[descriptor.handle()]

    @objc.python_method
    async def write_characteristic(
        self,
        characteristic: CBCharacteristic,
        value: NSData,
        response: CBCharacteristicWriteType,
    ) -> None:
        # in CoreBluetooth there is no indication of success or failure of
        # CBCharacteristicWriteWithoutResponse
        if response == CBCharacteristicWriteWithResponse:
            future = self._event_loop.create_future()

            self._characteristic_write_futures[characteristic.handle()] = future
            try:
                self.peripheral.writeValue_forCharacteristic_type_(
                    value, characteristic, response
                )
                await future
            finally:
                del self._characteristic_write_futures[characteristic.handle()]
        else:
            self.peripheral.writeValue_forCharacteristic_type_(
                value, characteristic, response
            )

    @objc.python_method
    async def write_descriptor(self, descriptor: CBDescriptor, value: NSData) -> None:
        future = self._event_loop.create_future()

        self._descriptor_write_futures[descriptor.handle()] = future
        try:
            self.peripheral.writeValue_forDescriptor_(value, descriptor)
            await future
        finally:
            del self._descriptor_write_futures[descriptor.handle()]

    @objc.python_method
    async def start_notifications(
        self, characteristic: CBCharacteristic, callback: NotifyCallback
    ) -> None:
        c_handle = characteristic.handle()
        if c_handle in self._characteristic_notify_callbacks:
            raise ValueError("Characteristic notifications already started")

        self._characteristic_notify_callbacks[c_handle] = callback

        future = self._event_loop.create_future()

        self._characteristic_notify_change_futures[c_handle] = future
        try:
            self.peripheral.setNotifyValue_forCharacteristic_(True, characteristic)
            await future
        finally:
            del self._characteristic_notify_change_futures[c_handle]

    @objc.python_method
    async def stop_notifications(self, characteristic: CBCharacteristic) -> None:
        c_handle = characteristic.handle()
        if c_handle not in self._characteristic_notify_callbacks:
            raise ValueError("Characteristic notification never started")

        future = self._event_loop.create_future()

        self._characteristic_notify_change_futures[c_handle] = future
        try:
            self.peripheral.setNotifyValue_forCharacteristic_(False, characteristic)
            await future
        finally:
            del self._characteristic_notify_change_futures[c_handle]

        self._characteristic_notify_callbacks.pop(c_handle)

    @objc.python_method
    async def read_rssi(self) -> NSNumber:
        future = self._event_loop.create_future()

        self._read_rssi_futures[self.peripheral.identifier()] = future
        try:
            self.peripheral.readRSSI()
            return await future
        finally:
            del self._read_rssi_futures[self.peripheral.identifier()]

    # Protocol Functions

    @objc.python_method
    def did_discover_services(
        self, peripheral: CBPeripheral, services: NSArray, error: Optional[NSError]
    ) -> None:
        future = self._services_discovered_future
        if error is not None:
            exception = BleakError(f"Failed to discover services {error}")
            future.set_exception(exception)
        else:
            logger.debug("Services discovered")
            future.set_result(services)

    def peripheral_didDiscoverServices_(
        self, peripheral: CBPeripheral, error: Optional[NSError]
    ) -> None:
        logger.debug("peripheral_didDiscoverServices_")
        self._event_loop.call_soon_threadsafe(
            self.did_discover_services,
            peripheral,
            peripheral.services(),
            error,
        )

    @objc.python_method
    def did_discover_characteristics_for_service(
        self,
        peripheral: CBPeripheral,
        service: CBService,
        characteristics: NSArray,
        error: Optional[NSError],
    ) -> None:
        future = self._service_characteristic_discovered_futures.get(
            service.startHandle()
        )
        if not future:
            logger.debug(
                f"Unexpected event didDiscoverCharacteristicsForService for {service.startHandle()}"
            )
            return
        if error is not None:
            exception = BleakError(
                f"Failed to discover characteristics for service {service.startHandle()}: {error}"
            )
            future.set_exception(exception)
        else:
            logger.debug("Characteristics discovered")
            future.set_result(characteristics)

    def peripheral_didDiscoverCharacteristicsForService_error_(
        self, peripheral: CBPeripheral, service: CBService, error: Optional[NSError]
    ) -> None:
        logger.debug("peripheral_didDiscoverCharacteristicsForService_error_")
        self._event_loop.call_soon_threadsafe(
            self.did_discover_characteristics_for_service,
            peripheral,
            service,
            service.characteristics(),
            error,
        )

    @objc.python_method
    def did_discover_descriptors_for_characteristic(
        self,
        peripheral: CBPeripheral,
        characteristic: CBCharacteristic,
        error: Optional[NSError],
    ) -> None:
        future = self._characteristic_descriptor_discover_futures.get(
            characteristic.handle()
        )
        if not future:
            logger.warning(
                f"Unexpected event didDiscoverDescriptorsForCharacteristic for {characteristic.handle()}"
            )
            return
        if error is not None:
            exception = BleakError(
                f"Failed to discover descriptors for characteristic {characteristic.handle()}: {error}"
            )
            future.set_exception(exception)
        else:
            logger.debug(f"Descriptor discovered {characteristic.handle()}")
            future.set_result(None)

    def peripheral_didDiscoverDescriptorsForCharacteristic_error_(
        self,
        peripheral: CBPeripheral,
        characteristic: CBCharacteristic,
        error: Optional[NSError],
    ) -> None:
        logger.debug("peripheral_didDiscoverDescriptorsForCharacteristic_error_")
        self._event_loop.call_soon_threadsafe(
            self.did_discover_descriptors_for_characteristic,
            peripheral,
            characteristic,
            error,
        )

    @objc.python_method
    def did_update_value_for_characteristic(
        self,
        peripheral: CBPeripheral,
        characteristic: CBCharacteristic,
        value: NSData,
        error: Optional[NSError],
    ) -> None:
        c_handle = characteristic.handle()

        future = self._characteristic_read_futures.get(c_handle)

        # If there is no pending read request, then this must be a notification
        # (the same delegate callback is used by both).
        if not future:
            if error is None:
                notify_callback = self._characteristic_notify_callbacks.get(c_handle)

                if notify_callback:
                    notify_callback(bytearray(value))
            return

        if error is not None:
            exception = BleakError(f"Failed to read characteristic {c_handle}: {error}")
            future.set_exception(exception)
        else:
            logger.debug("Read characteristic value")
            future.set_result(value)

    def peripheral_didUpdateValueForCharacteristic_error_(
        self,
        peripheral: CBPeripheral,
        characteristic: CBCharacteristic,
        error: Optional[NSError],
    ) -> None:
        logger.debug("peripheral_didUpdateValueForCharacteristic_error_")
        self._event_loop.call_soon_threadsafe(
            self.did_update_value_for_characteristic,
            peripheral,
            characteristic,
            characteristic.value(),
            error,
        )

    @objc.python_method
    def did_update_value_for_descriptor(
        self,
        peripheral: CBPeripheral,
        descriptor: CBDescriptor,
        value: NSObject,
        error: Optional[NSError],
    ) -> None:
        future = self._descriptor_read_futures.get(descriptor.handle())
        if not future:
            logger.warning("Unexpected event didUpdateValueForDescriptor")
            return
        if error is not None:
            exception = BleakError(
                f"Failed to read descriptor {descriptor.handle()}: {error}"
            )
            future.set_exception(exception)
        else:
            logger.debug("Read descriptor value")
            future.set_result(value)

    def peripheral_didUpdateValueForDescriptor_error_(
        self,
        peripheral: CBPeripheral,
        descriptor: CBDescriptor,
        error: Optional[NSError],
    ) -> None:
        logger.debug("peripheral_didUpdateValueForDescriptor_error_")
        self._event_loop.call_soon_threadsafe(
            self.did_update_value_for_descriptor,
            peripheral,
            descriptor,
            descriptor.value(),
            error,
        )

    @objc.python_method
    def did_write_value_for_characteristic(
        self,
        peripheral: CBPeripheral,
        characteristic: CBCharacteristic,
        error: Optional[NSError],
    ) -> None:
        future = self._characteristic_write_futures.get(characteristic.handle(), None)
        if not future:
            return  # event only expected on write with response
        if error is not None:
            exception = BleakError(
                f"Failed to write characteristic {characteristic.handle()}: {error}"
            )
            future.set_exception(exception)
        else:
            logger.debug("Write Characteristic Value")
            future.set_result(None)

    def peripheral_didWriteValueForCharacteristic_error_(
        self,
        peripheral: CBPeripheral,
        characteristic: CBCharacteristic,
        error: Optional[NSError],
    ) -> None:
        logger.debug("peripheral_didWriteValueForCharacteristic_error_")
        self._event_loop.call_soon_threadsafe(
            self.did_write_value_for_characteristic,
            peripheral,
            characteristic,
            error,
        )

    @objc.python_method
    def did_write_value_for_descriptor(
        self,
        peripheral: CBPeripheral,
        descriptor: CBDescriptor,
        error: Optional[NSError],
    ) -> None:
        future = self._descriptor_write_futures.get(descriptor.handle())
        if not future:
            logger.warning("Unexpected event didWriteValueForDescriptor")
            return
        if error is not None:
            exception = BleakError(
                f"Failed to write descriptor {descriptor.handle()}: {error}"
            )
            future.set_exception(exception)
        else:
            logger.debug("Write Descriptor Value")
            future.set_result(None)

    def peripheral_didWriteValueForDescriptor_error_(
        self,
        peripheral: CBPeripheral,
        descriptor: CBDescriptor,
        error: Optional[NSError],
    ) -> None:
        logger.debug("peripheral_didWriteValueForDescriptor_error_")
        self._event_loop.call_soon_threadsafe(
            self.did_write_value_for_descriptor,
            peripheral,
            descriptor,
            error,
        )

    @objc.python_method
    def did_update_notification_for_characteristic(
        self,
        peripheral: CBPeripheral,
        characteristic: CBCharacteristic,
        error: Optional[NSError],
    ) -> None:
        c_handle = characteristic.handle()
        future = self._characteristic_notify_change_futures.get(c_handle)
        if not future:
            logger.warning(
                "Unexpected event didUpdateNotificationStateForCharacteristic"
            )
            return
        if error is not None:
            exception = BleakError(
                f"Failed to update the notification status for characteristic {c_handle}: {error}"
            )
            future.set_exception(exception)
        else:
            logger.debug("Character Notify Update")
            future.set_result(None)

    def peripheral_didUpdateNotificationStateForCharacteristic_error_(
        self,
        peripheral: CBPeripheral,
        characteristic: CBCharacteristic,
        error: Optional[NSError],
    ) -> None:
        logger.debug("peripheral_didUpdateNotificationStateForCharacteristic_error_")
        self._event_loop.call_soon_threadsafe(
            self.did_update_notification_for_characteristic,
            peripheral,
            characteristic,
            error,
        )

    @objc.python_method
    def did_read_rssi(
        self, peripheral: CBPeripheral, rssi: NSNumber, error: Optional[NSError]
    ) -> None:
        future = self._read_rssi_futures.get(peripheral.identifier(), None)

        if not future:
            logger.warning("Unexpected event did_read_rssi")
            return

        if error is not None:
            exception = BleakError(f"Failed to read RSSI: {error}")
            future.set_exception(exception)
        else:
            future.set_result(rssi)

    # peripheral_didReadRSSI_error_ method is added dynamically later

    # Bleak currently doesn't use the callbacks below other than for debug logging

    @objc.python_method
    def did_update_name(self, peripheral: CBPeripheral, name: NSString) -> None:
        logger.debug(f"name of {peripheral.identifier()} changed to {name}")

    def peripheralDidUpdateName_(self, peripheral: CBPeripheral) -> None:
        logger.debug("peripheralDidUpdateName_")
        self._event_loop.call_soon_threadsafe(
            self.did_update_name, peripheral, peripheral.name()
        )

    @objc.python_method
    def did_modify_services(
        self, peripheral: CBPeripheral, invalidated_services: NSArray
    ) -> None:
        logger.debug(
            f"{peripheral.identifier()} invalidated services: {invalidated_services}"
        )

    def peripheral_didModifyServices_(
        self, peripheral: CBPeripheral, invalidatedServices: NSArray
    ) -> None:
        logger.debug("peripheral_didModifyServices_")
        self._event_loop.call_soon_threadsafe(
            self.did_modify_services, peripheral, invalidatedServices
        )


# peripheralDidUpdateRSSI:error: was deprecated and replaced with
# peripheral:didReadRSSI:error: in macOS 10.13
if objc.macos_available(10, 13):

    def peripheral_didReadRSSI_error_(
        self: PeripheralDelegate,
        peripheral: CBPeripheral,
        rssi: NSNumber,
        error: Optional[NSError],
    ) -> None:
        logger.debug("peripheral_didReadRSSI_error_")
        self._event_loop.call_soon_threadsafe(
            self.did_read_rssi, peripheral, rssi, error
        )

    objc.classAddMethod(
        PeripheralDelegate,
        b"peripheral:didReadRSSI:error:",
        peripheral_didReadRSSI_error_,
    )


else:

    def peripheralDidUpdateRSSI_error_(
        self: PeripheralDelegate, peripheral: CBPeripheral, error: Optional[NSError]
    ) -> None:
        logger.debug("peripheralDidUpdateRSSI_error_")
        self._event_loop.call_soon_threadsafe(
            self.did_read_rssi, peripheral, peripheral.RSSI(), error
        )

    objc.classAddMethod(
        PeripheralDelegate,
        b"peripheralDidUpdateRSSI:error:",
        peripheralDidUpdateRSSI_error_,
    )
