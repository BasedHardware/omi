"""
CentralManagerDelegate will implement the CBCentralManagerDelegate protocol to
manage CoreBluetooth services and resources on the Central End

Created on June, 25 2019 by kevincar <kevincarrolldavis@gmail.com>

"""

import asyncio
import logging
import sys
import threading
from typing import Any, Callable, Dict, List, Optional

if sys.version_info < (3, 11):
    from async_timeout import timeout as async_timeout
else:
    from asyncio import timeout as async_timeout

import objc
from CoreBluetooth import (
    CBUUID,
    CBCentralManager,
    CBManagerStatePoweredOff,
    CBManagerStatePoweredOn,
    CBManagerStateResetting,
    CBManagerStateUnauthorized,
    CBManagerStateUnknown,
    CBManagerStateUnsupported,
    CBPeripheral,
)
from Foundation import (
    NSUUID,
    NSArray,
    NSDictionary,
    NSError,
    NSKeyValueChangeNewKey,
    NSKeyValueObservingOptionNew,
    NSNumber,
    NSObject,
    NSString,
)
from libdispatch import DISPATCH_QUEUE_SERIAL, dispatch_queue_create

from ...exc import BleakError

logger = logging.getLogger(__name__)
CBCentralManagerDelegate = objc.protocolNamed("CBCentralManagerDelegate")


DisconnectCallback = Callable[[], None]


class CentralManagerDelegate(NSObject):
    """macOS conforming python class for managing the CentralManger for BLE"""

    ___pyobjc_protocols__ = [CBCentralManagerDelegate]

    def init(self) -> Optional["CentralManagerDelegate"]:
        """macOS init function for NSObject"""
        self = objc.super(CentralManagerDelegate, self).init()

        if self is None:
            return None

        self.event_loop = asyncio.get_running_loop()
        self._connect_futures: Dict[NSUUID, asyncio.Future] = {}

        self.callbacks: Dict[
            int, Callable[[CBPeripheral, Dict[str, Any], int], None]
        ] = {}
        self._disconnect_callbacks: Dict[NSUUID, DisconnectCallback] = {}
        self._disconnect_futures: Dict[NSUUID, asyncio.Future] = {}

        self._did_update_state_event = threading.Event()
        self.central_manager = CBCentralManager.alloc().initWithDelegate_queue_(
            self, dispatch_queue_create(b"bleak.corebluetooth", DISPATCH_QUEUE_SERIAL)
        )

        # according to CoreBluetooth docs, it is not valid to call CBCentral
        # methods until the centralManagerDidUpdateState_() delegate method
        # is called and the current state is CBManagerStatePoweredOn.
        # It doesn't take long for the callback to occur, so we should be able
        # to do a blocking wait here without anyone complaining.
        self._did_update_state_event.wait(1)

        if self.central_manager.state() == CBManagerStateUnsupported:
            raise BleakError("BLE is unsupported")

        if self.central_manager.state() == CBManagerStateUnauthorized:
            raise BleakError("BLE is not authorized - check macOS privacy settings")

        if self.central_manager.state() != CBManagerStatePoweredOn:
            raise BleakError("Bluetooth device is turned off")

        # isScanning property was added in 10.13
        if objc.macos_available(10, 13):
            self.central_manager.addObserver_forKeyPath_options_context_(
                self, "isScanning", NSKeyValueObservingOptionNew, 0
            )
            self._did_start_scanning_event: Optional[asyncio.Event] = None
            self._did_stop_scanning_event: Optional[asyncio.Event] = None

        return self

    def __del__(self) -> None:
        if objc.macos_available(10, 13):
            try:
                self.central_manager.removeObserver_forKeyPath_(self, "isScanning")
            except IndexError:
                # If self.init() raised an exception before calling
                # addObserver_forKeyPath_options_context_, attempting
                # to remove the observer will fail with IndexError
                pass

    # User defined functions

    @objc.python_method
    async def start_scan(self, service_uuids: Optional[List[str]]) -> None:
        service_uuids = (
            NSArray.alloc().initWithArray_(
                list(map(CBUUID.UUIDWithString_, service_uuids))
            )
            if service_uuids
            else None
        )

        self.central_manager.scanForPeripheralsWithServices_options_(
            service_uuids, None
        )

        # The `isScanning` property was added in macOS 10.13, so before that
        # just waiting some will have to do.
        if objc.macos_available(10, 13):
            event = asyncio.Event()
            self._did_start_scanning_event = event
            if not self.central_manager.isScanning():
                await event.wait()
        else:
            await asyncio.sleep(0.1)

    @objc.python_method
    async def stop_scan(self) -> None:
        self.central_manager.stopScan()

        # The `isScanning` property was added in macOS 10.13, so before that
        # just waiting some will have to do.
        if objc.macos_available(10, 13):
            event = asyncio.Event()
            self._did_stop_scanning_event = event
            if self.central_manager.isScanning():
                await event.wait()
        else:
            await asyncio.sleep(0.1)

    @objc.python_method
    async def connect(
        self,
        peripheral: CBPeripheral,
        disconnect_callback: DisconnectCallback,
        timeout: float = 10.0,
    ) -> None:
        try:
            self._disconnect_callbacks[peripheral.identifier()] = disconnect_callback
            future = self.event_loop.create_future()

            self._connect_futures[peripheral.identifier()] = future
            try:
                self.central_manager.connectPeripheral_options_(peripheral, None)
                async with async_timeout(timeout):
                    await future
            finally:
                del self._connect_futures[peripheral.identifier()]

        except asyncio.TimeoutError:
            logger.debug(f"Connection timed out after {timeout} seconds.")
            del self._disconnect_callbacks[peripheral.identifier()]
            future = self.event_loop.create_future()

            self._disconnect_futures[peripheral.identifier()] = future
            try:
                self.central_manager.cancelPeripheralConnection_(peripheral)
                await future
            finally:
                del self._disconnect_futures[peripheral.identifier()]

            raise

    @objc.python_method
    async def disconnect(self, peripheral: CBPeripheral) -> None:
        future = self.event_loop.create_future()

        self._disconnect_futures[peripheral.identifier()] = future
        try:
            self.central_manager.cancelPeripheralConnection_(peripheral)
            await future
        finally:
            del self._disconnect_futures[peripheral.identifier()]

    @objc.python_method
    def _changed_is_scanning(self, is_scanning: bool) -> None:
        if is_scanning:
            if self._did_start_scanning_event:
                self._did_start_scanning_event.set()
        else:
            if self._did_stop_scanning_event:
                self._did_stop_scanning_event.set()

    def observeValueForKeyPath_ofObject_change_context_(
        self, keyPath: NSString, object: Any, change: NSDictionary, context: int
    ) -> None:
        logger.debug("'%s' changed", keyPath)

        if keyPath != "isScanning":
            return

        is_scanning = bool(change[NSKeyValueChangeNewKey])
        self.event_loop.call_soon_threadsafe(self._changed_is_scanning, is_scanning)

    # Protocol Functions

    def centralManagerDidUpdateState_(self, centralManager: CBCentralManager) -> None:
        logger.debug("centralManagerDidUpdateState_")
        if centralManager.state() == CBManagerStateUnknown:
            logger.debug("Cannot detect bluetooth device")
        elif centralManager.state() == CBManagerStateResetting:
            logger.debug("Bluetooth is resetting")
        elif centralManager.state() == CBManagerStateUnsupported:
            logger.debug("Bluetooth is unsupported")
        elif centralManager.state() == CBManagerStateUnauthorized:
            logger.debug("Bluetooth is unauthorized")
        elif centralManager.state() == CBManagerStatePoweredOff:
            logger.debug("Bluetooth powered off")
        elif centralManager.state() == CBManagerStatePoweredOn:
            logger.debug("Bluetooth powered on")

        self._did_update_state_event.set()

    @objc.python_method
    def did_discover_peripheral(
        self,
        central: CBCentralManager,
        peripheral: CBPeripheral,
        advertisementData: NSDictionary,
        RSSI: NSNumber,
    ) -> None:
        # Note: this function might be called several times for same device.
        # This can happen for instance when an active scan is done, and the
        # second call with contain the data from the BLE scan response.
        # Example a first time with the following keys in advertisementData:
        # ['kCBAdvDataLocalName', 'kCBAdvDataIsConnectable', 'kCBAdvDataChannel']
        # ... and later a second time with other keys (and values) such as:
        # ['kCBAdvDataServiceUUIDs', 'kCBAdvDataIsConnectable', 'kCBAdvDataChannel']
        #
        # i.e it is best not to trust advertisementData for later use and data
        # from it should be copied.
        #
        # This behaviour could be affected by the
        # CBCentralManagerScanOptionAllowDuplicatesKey global setting.

        uuid_string = peripheral.identifier().UUIDString()

        for callback in self.callbacks.values():
            if callback:
                callback(peripheral, advertisementData, RSSI)

        logger.debug(
            "Discovered device %s: %s @ RSSI: %d (kCBAdvData %r) and Central: %r",
            uuid_string,
            peripheral.name(),
            RSSI,
            advertisementData.keys(),
            central,
        )

    def centralManager_didDiscoverPeripheral_advertisementData_RSSI_(
        self,
        central: CBCentralManager,
        peripheral: CBPeripheral,
        advertisementData: NSDictionary,
        RSSI: NSNumber,
    ) -> None:
        logger.debug("centralManager_didDiscoverPeripheral_advertisementData_RSSI_")
        self.event_loop.call_soon_threadsafe(
            self.did_discover_peripheral,
            central,
            peripheral,
            advertisementData,
            RSSI,
        )

    @objc.python_method
    def did_connect_peripheral(
        self, central: CBCentralManager, peripheral: CBPeripheral
    ) -> None:
        future = self._connect_futures.get(peripheral.identifier(), None)
        if future is not None:
            future.set_result(True)

    def centralManager_didConnectPeripheral_(
        self, central: CBCentralManager, peripheral: CBPeripheral
    ) -> None:
        logger.debug("centralManager_didConnectPeripheral_")
        self.event_loop.call_soon_threadsafe(
            self.did_connect_peripheral,
            central,
            peripheral,
        )

    @objc.python_method
    def did_fail_to_connect_peripheral(
        self,
        centralManager: CBCentralManager,
        peripheral: CBPeripheral,
        error: Optional[NSError],
    ) -> None:
        future = self._connect_futures.get(peripheral.identifier(), None)
        if future is not None:
            if error is not None:
                future.set_exception(BleakError(f"failed to connect: {error}"))
            else:
                future.set_result(False)

    def centralManager_didFailToConnectPeripheral_error_(
        self,
        centralManager: CBCentralManager,
        peripheral: CBPeripheral,
        error: Optional[NSError],
    ) -> None:
        logger.debug("centralManager_didFailToConnectPeripheral_error_")
        self.event_loop.call_soon_threadsafe(
            self.did_fail_to_connect_peripheral,
            centralManager,
            peripheral,
            error,
        )

    @objc.python_method
    def did_disconnect_peripheral(
        self,
        central: CBCentralManager,
        peripheral: CBPeripheral,
        error: Optional[NSError],
    ) -> None:
        logger.debug("Peripheral Device disconnected!")

        future = self._disconnect_futures.get(peripheral.identifier(), None)
        if future is not None:
            if error is not None:
                future.set_exception(BleakError(f"disconnect failed: {error}"))
            else:
                future.set_result(None)

        callback = self._disconnect_callbacks.pop(peripheral.identifier(), None)

        if callback is not None:
            callback()

    def centralManager_didDisconnectPeripheral_error_(
        self,
        central: CBCentralManager,
        peripheral: CBPeripheral,
        error: Optional[NSError],
    ) -> None:
        logger.debug("centralManager_didDisconnectPeripheral_error_")
        self.event_loop.call_soon_threadsafe(
            self.did_disconnect_peripheral,
            central,
            peripheral,
            error,
        )
