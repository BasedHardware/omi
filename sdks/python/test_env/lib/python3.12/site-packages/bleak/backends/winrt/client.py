# -*- coding: utf-8 -*-
"""
BLE Client for Windows 10 systems, implemented with WinRT.

Created on 2020-08-19 by hbldh <henrik.blidh@nedomkull.com>
"""

import asyncio
import logging
import sys
import uuid
import warnings
from ctypes import WinError
from typing import (
    Any,
    Dict,
    List,
    Literal,
    Optional,
    Protocol,
    Sequence,
    Set,
    TypedDict,
    Union,
    cast,
)

if sys.version_info < (3, 12):
    from typing_extensions import Buffer
else:
    from collections.abc import Buffer

if sys.version_info < (3, 11):
    from async_timeout import timeout as async_timeout
else:
    from asyncio import timeout as async_timeout

if sys.version_info >= (3, 12):
    from winrt.windows.devices.bluetooth import (
        BluetoothAddressType,
        BluetoothCacheMode,
        BluetoothError,
        BluetoothLEDevice,
    )
    from winrt.windows.devices.bluetooth.genericattributeprofile import (
        GattCharacteristic,
        GattCharacteristicProperties,
        GattClientCharacteristicConfigurationDescriptorValue,
        GattCommunicationStatus,
        GattDescriptor,
        GattDeviceService,
        GattSession,
        GattSessionStatus,
        GattSessionStatusChangedEventArgs,
        GattValueChangedEventArgs,
        GattWriteOption,
    )
    from winrt.windows.devices.enumeration import (
        DeviceInformation,
        DevicePairingKinds,
        DevicePairingResultStatus,
        DeviceUnpairingResultStatus,
    )
    from winrt.windows.foundation import (
        AsyncStatus,
        EventRegistrationToken,
        IAsyncOperation,
    )
    from winrt.windows.storage.streams import Buffer as WinBuffer
else:
    from bleak_winrt.windows.devices.bluetooth import (
        BluetoothAddressType,
        BluetoothCacheMode,
        BluetoothError,
        BluetoothLEDevice,
    )
    from bleak_winrt.windows.devices.bluetooth.genericattributeprofile import (
        GattCharacteristic,
        GattCharacteristicProperties,
        GattClientCharacteristicConfigurationDescriptorValue,
        GattCommunicationStatus,
        GattDescriptor,
        GattDeviceService,
        GattSession,
        GattSessionStatus,
        GattSessionStatusChangedEventArgs,
        GattValueChangedEventArgs,
        GattWriteOption,
    )
    from bleak_winrt.windows.devices.enumeration import (
        DeviceInformation,
        DevicePairingKinds,
        DevicePairingResultStatus,
        DeviceUnpairingResultStatus,
    )
    from bleak_winrt.windows.foundation import (
        AsyncStatus,
        EventRegistrationToken,
        IAsyncOperation,
    )
    from bleak_winrt.windows.storage.streams import Buffer as WinBuffer

from ... import BleakScanner
from ...exc import (
    PROTOCOL_ERROR_CODES,
    BleakCharacteristicNotFoundError,
    BleakDeviceNotFoundError,
    BleakError,
)
from ..characteristic import BleakGATTCharacteristic
from ..client import BaseBleakClient, NotifyCallback
from ..device import BLEDevice
from ..service import BleakGATTServiceCollection
from .characteristic import BleakGATTCharacteristicWinRT
from .descriptor import BleakGATTDescriptorWinRT
from .scanner import BleakScannerWinRT
from .service import BleakGATTServiceWinRT

logger = logging.getLogger(__name__)


class _Result(Protocol):
    status: GattCommunicationStatus
    protocol_error: int


def _address_to_int(address: str) -> int:
    """Converts the Bluetooth device address string to its representing integer

    Args:
        address (str): Bluetooth device address to convert

    Returns:
        int: integer representation of the given Bluetooth device address
    """
    _address_separators = [":", "-"]
    for char in _address_separators:
        address = address.replace(char, "")

    return int(address, base=16)


def _ensure_success(result: _Result, attr: Optional[str], fail_msg: str) -> Any:
    """
    Ensures that *status* is ``GattCommunicationStatus.SUCCESS``, otherwise
    raises ``BleakError``.

    Args:
        result: The result returned by a WinRT API method.
        attr: The name of the attribute containing the result.
        fail_msg: A message to include in the exception.
    """
    status = result.status if hasattr(result, "status") else result

    if status == GattCommunicationStatus.SUCCESS:
        return None if attr is None else getattr(result, attr)

    if status == GattCommunicationStatus.PROTOCOL_ERROR:
        err = PROTOCOL_ERROR_CODES.get(result.protocol_error, "Unknown")
        raise BleakError(
            f"{fail_msg}: Protocol Error 0x{result.protocol_error:02X}: {err}"
        )

    if status == GattCommunicationStatus.ACCESS_DENIED:
        raise BleakError(f"{fail_msg}: Access Denied")

    if status == GattCommunicationStatus.UNREACHABLE:
        raise BleakError(f"{fail_msg}: Unreachable")

    raise BleakError(f"{fail_msg}: Unexpected status code 0x{status:02X}")


class WinRTClientArgs(TypedDict, total=False):
    """
    Windows-specific arguments for :class:`BleakClient`.
    """

    address_type: Literal["public", "random"]
    """
    Can either be ``"public"`` or ``"random"``, depending on the required address
    type needed to connect to your device.
    """

    use_cached_services: bool
    """
    ``True`` allows Windows to fetch the services, characteristics and descriptors
    from the Windows cache instead of reading them from the device. Can be very
    much faster for known, unchanging devices, but not recommended for DIY peripherals
    where the GATT layout can change between connections.

    ``False`` will force the attribute database to be read from the remote device
    instead of using the OS cache.

    If omitted, the OS Bluetooth stack will do what it thinks is best.
    """


class BleakClientWinRT(BaseBleakClient):
    """Native Windows Bleak Client.

    Args:
        address_or_ble_device (str or BLEDevice): The Bluetooth address of the BLE peripheral
            to connect to or the ``BLEDevice`` object representing it.
        services: Optional set of service UUIDs that will be used.
        winrt (dict): A dictionary of Windows-specific configuration values.
        **timeout (float): Timeout for required ``BleakScanner.find_device_by_address`` call. Defaults to 10.0.
    """

    def __init__(
        self,
        address_or_ble_device: Union[BLEDevice, str],
        services: Optional[Set[str]] = None,
        *,
        winrt: WinRTClientArgs,
        **kwargs,
    ):
        super(BleakClientWinRT, self).__init__(address_or_ble_device, **kwargs)

        # Backend specific. WinRT objects.
        if isinstance(address_or_ble_device, BLEDevice):
            data = address_or_ble_device.details
            self._device_info = (data.adv or data.scan).bluetooth_address
        else:
            self._device_info = None
        self._requested_services = (
            [uuid.UUID(s) for s in services] if services else None
        )
        self._requester: Optional[BluetoothLEDevice] = None
        self._services_changed_events: List[asyncio.Event] = []
        self._session_active_events: List[asyncio.Event] = []
        self._session_closed_events: List[asyncio.Event] = []
        self._session: GattSession = None
        self._notification_callbacks: Dict[int, NotifyCallback] = {}

        if "address_type" in kwargs:
            warnings.warn(
                "The address_type keyword arg will in a future version be moved into the win dict input instead.",
                PendingDeprecationWarning,
                stacklevel=2,
            )

        # os-specific options
        self._use_cached_services = winrt.get("use_cached_services")
        self._address_type = winrt.get("address_type", kwargs.get("address_type"))
        self._retry_on_services_changed = False

        self._session_services_changed_token: Optional[EventRegistrationToken] = None
        self._session_status_changed_token: Optional[EventRegistrationToken] = None
        self._max_pdu_size_changed_token: Optional[EventRegistrationToken] = None

    def __str__(self):
        return f"{type(self).__name__} ({self.address})"

    # Connectivity methods

    async def _create_requester(self, bluetooth_address: int) -> BluetoothLEDevice:
        args = [
            bluetooth_address,
        ]
        if self._address_type is not None:
            args.append(
                BluetoothAddressType.PUBLIC
                if self._address_type == "public"
                else BluetoothAddressType.RANDOM
            )
        requester = await BluetoothLEDevice.from_bluetooth_address_async(*args)

        # https://github.com/microsoft/Windows-universal-samples/issues/1089#issuecomment-487586755
        if requester is None:
            raise BleakDeviceNotFoundError(
                self.address, f"Device with address {self.address} was not found."
            )
        return requester

    async def connect(self, **kwargs) -> bool:
        """Connect to the specified GATT server.

        Keyword Args:
            timeout (float): Timeout for required ``BleakScanner.find_device_by_address`` call. Defaults to 10.0.

        Returns:
            Boolean representing connection status.

        """
        # Try to find the desired device.
        timeout = kwargs.get("timeout", self._timeout)
        if self._device_info is None:
            device = await BleakScanner.find_device_by_address(
                self.address, timeout=timeout, backend=BleakScannerWinRT
            )

            if device is None:
                raise BleakDeviceNotFoundError(
                    self.address, f"Device with address {self.address} was not found."
                )

            data = device.details
            self._device_info = (data.adv or data.scan).bluetooth_address

        logger.debug("Connecting to BLE device @ %s", self.address)

        loop = asyncio.get_running_loop()

        self._requester = await self._create_requester(self._device_info)

        def handle_services_changed():
            if not self._services_changed_events:
                logger.warning("%s: unhandled services changed event", self.address)
            else:
                for event in self._services_changed_events:
                    event.set()

        def services_changed_handler(sender, args):
            logger.debug("%s: services changed", self.address)
            loop.call_soon_threadsafe(handle_services_changed)

        self._services_changed_token = self._requester.add_gatt_services_changed(
            services_changed_handler
        )

        # Called on disconnect event or on failure to connect.
        def handle_disconnect():
            if self._requester:
                if self._services_changed_token:
                    self._requester.remove_gatt_services_changed(
                        self._services_changed_token
                    )
                    self._services_changed_token = None

                logger.debug("closing requester")
                self._requester.close()
                self._requester = None

            if self._session:
                if self._session_status_changed_token:
                    self._session.remove_session_status_changed(
                        self._session_status_changed_token
                    )
                    self._session_status_changed_token = None

                if self._max_pdu_size_changed_token:
                    self._session.remove_max_pdu_size_changed(
                        self._max_pdu_size_changed_token
                    )
                    self._max_pdu_size_changed_token = None

                logger.debug("closing session")
                self._session.close()
                self._session = None

        is_connect_complete = False

        def handle_session_status_changed(
            args: GattSessionStatusChangedEventArgs,
        ):
            if args.error != BluetoothError.SUCCESS:
                logger.error("Unhandled GATT error %r", args.error)

            if args.status == GattSessionStatus.ACTIVE:
                for e in self._session_active_events:
                    e.set()

            # Don't run this if we have not exited from the connect method yet.
            # Cleanup is handled by the connect method in that case.
            elif args.status == GattSessionStatus.CLOSED and is_connect_complete:
                if self._disconnected_callback:
                    self._disconnected_callback()

                for e in self._session_closed_events:
                    e.set()

                handle_disconnect()

        # this is the WinRT event handler will be called on another thread
        def session_status_changed_event_handler(
            sender: GattSession, args: GattSessionStatusChangedEventArgs
        ):
            logger.debug(
                "session_status_changed_event_handler: id: %s, error: %r, status: %r",
                sender.device_id.id,
                args.error,
                args.status,
            )
            loop.call_soon_threadsafe(handle_session_status_changed, args)

        def max_pdu_size_changed_handler(sender: GattSession, args):
            try:
                max_pdu_size = sender.max_pdu_size
            except OSError:
                # There is a race condition where this event was already
                # queued when the GattSession object was closed. In that
                # case, we get a Windows error which we can just ignore.
                return

            logger.debug("max_pdu_size_changed_handler: %d", max_pdu_size)

        # Start a GATT Session to connect
        event = asyncio.Event()
        self._session_active_events.append(event)
        try:
            self._session = await GattSession.from_device_id_async(
                self._requester.bluetooth_device_id
            )

            if not self._session.can_maintain_connection:
                raise BleakError("device does not support GATT sessions")

            self._session_status_changed_token = (
                self._session.add_session_status_changed(
                    session_status_changed_event_handler
                )
            )

            self._max_pdu_size_changed_token = self._session.add_max_pdu_size_changed(
                max_pdu_size_changed_handler
            )

            services_changed_event = asyncio.Event()
            self._services_changed_events.append(services_changed_event)

            try:
                # Windows does not support explicitly connecting to a device.
                # Instead it has the concept of a GATT session that is owned
                # by the calling program.
                self._session.maintain_connection = True
                # This keeps the device connected until we set maintain_connection = False.

                cache_mode = None

                if self._use_cached_services is not None:
                    cache_mode = (
                        BluetoothCacheMode.CACHED
                        if self._use_cached_services
                        else BluetoothCacheMode.UNCACHED
                    )

                # if we receive a services changed event before get_gatt_services_async()
                # finishes, we need to call it again with BluetoothCacheMode.CACHED
                # to ensure we have the correct services as described in
                # https://learn.microsoft.com/en-us/uwp/api/windows.devices.bluetooth.bluetoothledevice.gattserviceschanged
                service_cache_mode = cache_mode

                async with async_timeout(timeout):
                    if self._retry_on_services_changed:
                        while True:
                            services_changed_event.clear()
                            services_changed_event_task = asyncio.create_task(
                                services_changed_event.wait()
                            )

                            get_services_task = asyncio.create_task(
                                self.get_services(
                                    service_cache_mode=service_cache_mode,
                                    cache_mode=cache_mode,
                                )
                            )

                            _, pending = await asyncio.wait(
                                [services_changed_event_task, get_services_task],
                                return_when=asyncio.FIRST_COMPLETED,
                            )

                            for p in pending:
                                p.cancel()

                            if not services_changed_event.is_set():
                                # services did not change while getting services,
                                # so this is the final result
                                self.services = get_services_task.result()
                                break

                            logger.debug(
                                "%s: restarting get services due to services changed event",
                                self.address,
                            )
                            service_cache_mode = BluetoothCacheMode.CACHED

                            # ensure the task ran to completion to avoid OSError
                            # on next call to get_services()
                            try:
                                await get_services_task
                            except OSError:
                                pass
                            except asyncio.CancelledError:
                                pass
                    else:
                        self.services = await self.get_services(
                            service_cache_mode=service_cache_mode,
                            cache_mode=cache_mode,
                        )

                # a connection may not be made until we request info from the
                # device, so we have to get services before the GATT session
                # is set to active
                await event.wait()
                is_connect_complete = True
            finally:
                self._services_changed_events.remove(services_changed_event)

        except BaseException:
            handle_disconnect()
            raise
        finally:
            self._session_active_events.remove(event)

        return True

    async def disconnect(self) -> bool:
        """Disconnect from the specified GATT server.

        Returns:
            Boolean representing if device is disconnected.

        """
        logger.debug("Disconnecting from BLE device...")
        # Remove notifications.
        for handle, event_handler_token in list(self._notification_callbacks.items()):
            char = self.services.get_characteristic(handle)
            char.obj.remove_value_changed(event_handler_token)
        self._notification_callbacks.clear()

        # Dispose all service components that we have requested and created.
        if self.services:
            # HACK: sometimes GattDeviceService.Close() hangs forever, so we
            # add a delay to give the Windows Bluetooth stack some time to
            # "settle" before closing the services
            await asyncio.sleep(0.1)

            for service in self.services:
                service.obj.close()
            self.services = None

        # Without this, disposing the BluetoothLEDevice won't disconnect it
        if self._session:
            self._session.maintain_connection = False
            # calling self._session.close() here prevents any further GATT
            # session status events, so we defer that until after the session
            # is no longer active

        # Dispose of the BluetoothLEDevice and see that the session
        # status is now closed.
        if self._requester:
            event = asyncio.Event()
            self._session_closed_events.append(event)
            try:
                self._requester.close()
                # sometimes it can take over one minute before Windows decides
                # to end the GATT session/disconnect the device
                async with async_timeout(120):
                    await event.wait()
            finally:
                self._session_closed_events.remove(event)

        return True

    @property
    def is_connected(self) -> bool:
        """Check connection status between this client and the server.

        Returns:
            Boolean representing connection status.

        """
        return self._DeprecatedIsConnectedReturn(
            False
            if self._session is None
            else self._session.session_status == GattSessionStatus.ACTIVE
        )

    @property
    def mtu_size(self) -> int:
        """Get ATT MTU size for active connection"""
        return self._session.max_pdu_size

    async def pair(self, protection_level: int = None, **kwargs) -> bool:
        """Attempts to pair with the device.

        Keyword Args:
            protection_level (int): A ``DevicePairingProtectionLevel`` enum value:

                1. None - Pair the device using no levels of protection.
                2. Encryption - Pair the device using encryption.
                3. EncryptionAndAuthentication - Pair the device using
                   encryption and authentication. (This will not work in Bleak...)

        Returns:
            Boolean regarding success of pairing.

        """
        # New local device information object created since the object from the requester isn't updated
        device_information = await DeviceInformation.create_from_id_async(
            self._requester.device_information.id
        )
        if (
            device_information.pairing.can_pair
            and not device_information.pairing.is_paired
        ):
            # Currently only supporting Just Works solutions...
            ceremony = DevicePairingKinds.CONFIRM_ONLY
            custom_pairing = device_information.pairing.custom

            def handler(sender, args):
                args.accept()

            pairing_requested_token = custom_pairing.add_pairing_requested(handler)
            try:
                if protection_level:
                    pairing_result = await custom_pairing.pair_async(
                        ceremony, protection_level
                    )
                else:
                    pairing_result = await custom_pairing.pair_async(ceremony)

            except Exception as e:
                raise BleakError("Failure trying to pair with device!") from e
            finally:
                custom_pairing.remove_pairing_requested(pairing_requested_token)

            if pairing_result.status not in (
                DevicePairingResultStatus.PAIRED,
                DevicePairingResultStatus.ALREADY_PAIRED,
            ):
                raise BleakError(f"Could not pair with device: {pairing_result.status}")
            else:
                logger.info(
                    "Paired to device with protection level %r.",
                    pairing_result.protection_level_used,
                )
                return True
        else:
            return device_information.pairing.is_paired

    async def unpair(self) -> bool:
        """Attempts to unpair from the device.

        N.B. unpairing also leads to disconnection in the Windows backend.

        Returns:
            Boolean on whether the unparing was successful.

        """
        device = await self._create_requester(
            self._device_info
            if self._device_info is not None
            else _address_to_int(self.address)
        )

        try:
            unpairing_result = await device.device_information.pairing.unpair_async()
            if unpairing_result.status not in (
                DeviceUnpairingResultStatus.UNPAIRED,
                DeviceUnpairingResultStatus.ALREADY_UNPAIRED,
            ):
                raise BleakError(
                    f"Could not unpair with device: {unpairing_result.status}"
                )
            logger.info("Unpaired with device.")
        finally:
            device.close()

        return True

    # GATT services methods

    async def get_services(
        self,
        *,
        service_cache_mode: Optional[BluetoothCacheMode] = None,
        cache_mode: Optional[BluetoothCacheMode] = None,
        **kwargs,
    ) -> BleakGATTServiceCollection:
        """Get all services registered for this GATT server.

        Returns:
           A :py:class:`bleak.backends.service.BleakGATTServiceCollection` with this device's services tree.

        """

        # Return the Service Collection.
        if self.services is not None:
            return self.services

        logger.debug(
            "getting services (service_cache_mode=%r, cache_mode=%r)...",
            service_cache_mode,
            cache_mode,
        )

        new_services = BleakGATTServiceCollection()

        # Each of the get_serv/char/desc_async() methods has two forms, one
        # with no args and one with a cache_mode argument
        srv_args = []
        args = []

        # If the os-specific use_cached_services arg was given when BleakClient
        # was created, the we use the second form with explicit cache mode.
        # Otherwise we use the first form with no explicit cache mode which
        # allows the OS Bluetooth stack to decide what is best.

        if service_cache_mode is not None:
            srv_args.append(service_cache_mode)

        if cache_mode is not None:
            args.append(cache_mode)

        def dispose_on_cancel(future):
            if future._cancel_requested and future._result is not None:
                logger.debug("disposing services object because of cancel")
                for service in future._result:
                    service.close()

        services: Sequence[GattDeviceService]

        if self._requested_services is None:
            future = FutureLike(self._requester.get_gatt_services_async(*srv_args))
            future.add_done_callback(dispose_on_cancel)

            services = _ensure_success(
                await FutureLike(self._requester.get_gatt_services_async(*srv_args)),
                "services",
                "Could not get GATT services",
            )
        else:
            services = []
            # REVISIT: should properly dispose services on cancel or protect from cancellation

            for s in self._requested_services:
                services.extend(
                    _ensure_success(
                        await FutureLike(
                            self._requester.get_gatt_services_for_uuid_async(
                                s, *srv_args
                            )
                        ),
                        "services",
                        "Could not get GATT services",
                    )
                )

        try:
            for service in services:
                result = await FutureLike(service.get_characteristics_async(*args))

                if result.status == GattCommunicationStatus.ACCESS_DENIED:
                    # Windows does not allow access to services "owned" by the
                    # OS. This includes services like HID and Bond Manager.
                    logger.debug(
                        "skipping service %s due to access denied", service.uuid
                    )
                    continue

                characteristics: Sequence[GattCharacteristic] = _ensure_success(
                    result,
                    "characteristics",
                    f"Could not get GATT characteristics for service {service.uuid} ({service.attribute_handle})",
                )

                new_services.add_service(BleakGATTServiceWinRT(service))

                for characteristic in characteristics:
                    descriptors: Sequence[GattDescriptor] = _ensure_success(
                        await FutureLike(characteristic.get_descriptors_async(*args)),
                        "descriptors",
                        f"Could not get GATT descriptors for characteristic {characteristic.uuid} ({characteristic.attribute_handle})",
                    )

                    new_services.add_characteristic(
                        BleakGATTCharacteristicWinRT(
                            characteristic, lambda: self._session.max_pdu_size - 3
                        )
                    )

                    for descriptor in descriptors:
                        new_services.add_descriptor(
                            BleakGATTDescriptorWinRT(
                                descriptor,
                                str(characteristic.uuid),
                                characteristic.attribute_handle,
                            )
                        )

            return new_services
        except BaseException:
            # Don't leak services. WinRT is quite particular about services
            # being closed.
            logger.debug("disposing service objects")

            # HACK: sometimes GattDeviceService.Close() hangs forever, so we
            # add a delay to give the Windows Bluetooth stack some time to
            # "settle" before closing the services
            await asyncio.sleep(0.1)

            for service in services:
                service.close()
            raise

    # I/O methods

    async def read_gatt_char(
        self,
        char_specifier: Union[BleakGATTCharacteristic, int, str, uuid.UUID],
        **kwargs,
    ) -> bytearray:
        """Perform read operation on the specified GATT characteristic.

        Args:
            char_specifier (BleakGATTCharacteristic, int, str or UUID): The characteristic to read from,
                specified by either integer handle, UUID or directly by the
                BleakGATTCharacteristic object representing it.

        Keyword Args:
            use_cached (bool): ``False`` forces Windows to read the value from the
                device again and not use its own cached value. Defaults to ``False``.

        Returns:
            (bytearray) The read data.

        """
        if not self.is_connected:
            raise BleakError("Not connected")

        use_cached = kwargs.get("use_cached", False)

        if not isinstance(char_specifier, BleakGATTCharacteristic):
            characteristic = self.services.get_characteristic(char_specifier)
        else:
            characteristic = char_specifier
        if not characteristic:
            raise BleakCharacteristicNotFoundError(char_specifier)

        value = bytearray(
            _ensure_success(
                await characteristic.obj.read_value_async(
                    BluetoothCacheMode.CACHED
                    if use_cached
                    else BluetoothCacheMode.UNCACHED
                ),
                "value",
                f"Could not read characteristic handle {characteristic.handle}",
            )
        )

        logger.debug("Read Characteristic %04X : %s", characteristic.handle, value)

        return value

    async def read_gatt_descriptor(self, handle: int, **kwargs) -> bytearray:
        """Perform read operation on the specified GATT descriptor.

        Args:
            handle (int): The handle of the descriptor to read from.

        Keyword Args:
            use_cached (bool): `False` forces Windows to read the value from the
                device again and not use its own cached value. Defaults to `False`.

        Returns:
            (bytearray) The read data.

        """
        if not self.is_connected:
            raise BleakError("Not connected")

        use_cached = kwargs.get("use_cached", False)

        descriptor = self.services.get_descriptor(handle)
        if not descriptor:
            raise BleakError(f"Descriptor with handle {handle} was not found!")

        value = bytearray(
            _ensure_success(
                await descriptor.obj.read_value_async(
                    BluetoothCacheMode.CACHED
                    if use_cached
                    else BluetoothCacheMode.UNCACHED
                ),
                "value",
                f"Could not read Descriptor value for {handle:04X}",
            )
        )

        logger.debug("Read Descriptor %04X : %s", handle, value)

        return value

    async def write_gatt_char(
        self,
        characteristic: BleakGATTCharacteristic,
        data: Buffer,
        response: bool,
    ) -> None:
        if not self.is_connected:
            raise BleakError("Not connected")

        response = (
            GattWriteOption.WRITE_WITH_RESPONSE
            if response
            else GattWriteOption.WRITE_WITHOUT_RESPONSE
        )
        buf = WinBuffer(len(data))
        buf.length = buf.capacity
        with memoryview(buf) as mv:
            mv[:] = data
        _ensure_success(
            await characteristic.obj.write_value_with_result_async(buf, response),
            None,
            f"Could not write value {data} to characteristic {characteristic.handle:04X}",
        )

    async def write_gatt_descriptor(self, handle: int, data: Buffer) -> None:
        """Perform a write operation on the specified GATT descriptor.

        Args:
            handle: The handle of the descriptor to read from.
            data: The data to send (any bytes-like object).

        """
        if not self.is_connected:
            raise BleakError("Not connected")

        descriptor = self.services.get_descriptor(handle)
        if not descriptor:
            raise BleakError(f"Descriptor with handle {handle} was not found!")

        buf = WinBuffer(len(data))
        buf.length = buf.capacity
        with memoryview(buf) as mv:
            mv[:] = data
        _ensure_success(
            await descriptor.obj.write_value_with_result_async(buf),
            None,
            f"Could not write value {data!r} to descriptor {handle:04X}",
        )

        logger.debug("Write Descriptor %04X : %s", handle, data)

    async def start_notify(
        self,
        characteristic: BleakGATTCharacteristic,
        callback: NotifyCallback,
        **kwargs,
    ) -> None:
        """
        Activate notifications/indications on a characteristic.

        Keyword Args:
            force_indicate (bool): If this is set to True, then Bleak will set up a indication request instead of a
                notification request, given that the characteristic supports notifications as well as indications.
        """
        winrt_char = cast(GattCharacteristic, characteristic.obj)

        # If we want to force indicate even when notify is available, also check if the device
        # actually supports indicate as well.
        if not kwargs.get("force_indicate", False) and (
            winrt_char.characteristic_properties & GattCharacteristicProperties.NOTIFY
        ):
            cccd = GattClientCharacteristicConfigurationDescriptorValue.NOTIFY
        elif (
            winrt_char.characteristic_properties & GattCharacteristicProperties.INDICATE
        ):
            cccd = GattClientCharacteristicConfigurationDescriptorValue.INDICATE
        else:
            raise BleakError(
                "characteristic does not support notifications or indications"
            )

        loop = asyncio.get_running_loop()

        def handle_value_changed(
            sender: GattCharacteristic, args: GattValueChangedEventArgs
        ):
            value = bytearray(args.characteristic_value)
            return loop.call_soon_threadsafe(callback, value)

        event_handler_token = winrt_char.add_value_changed(handle_value_changed)
        self._notification_callbacks[characteristic.handle] = event_handler_token

        try:
            _ensure_success(
                await winrt_char.write_client_characteristic_configuration_descriptor_async(
                    cccd
                ),
                None,
                f"Could not start notify on {characteristic.handle:04X}",
            )
        except BaseException:
            # This usually happens when a device reports that it supports indicate,
            # but it actually doesn't.
            if characteristic.handle in self._notification_callbacks:
                event_handler_token = self._notification_callbacks.pop(
                    characteristic.handle
                )
                winrt_char.remove_value_changed(event_handler_token)

            raise

    async def stop_notify(
        self, char_specifier: Union[BleakGATTCharacteristic, int, str, uuid.UUID]
    ) -> None:
        """Deactivate notification/indication on a specified characteristic.

        Args:
            char_specifier (BleakGATTCharacteristic, int, str or UUID): The characteristic to deactivate
                notification/indication on, specified by either integer handle, UUID or
                directly by the BleakGATTCharacteristic object representing it.

        """
        if not self.is_connected:
            raise BleakError("Not connected")

        if not isinstance(char_specifier, BleakGATTCharacteristic):
            characteristic = self.services.get_characteristic(char_specifier)
        else:
            characteristic = char_specifier
        if not characteristic:
            raise BleakCharacteristicNotFoundError(char_specifier)

        _ensure_success(
            await characteristic.obj.write_client_characteristic_configuration_descriptor_async(
                GattClientCharacteristicConfigurationDescriptorValue.NONE
            ),
            None,
            f"Could not stop notify on {characteristic.handle:04X}",
        )

        event_handler_token = self._notification_callbacks.pop(characteristic.handle)
        characteristic.obj.remove_value_changed(event_handler_token)


class FutureLike:
    """
    Wraps a WinRT IAsyncOperation in a "future-like" object so that it can
    be passed to Python APIs.

    Needed until https://github.com/pywinrt/pywinrt/issues/14
    """

    _asyncio_future_blocking = False

    def __init__(self, op: IAsyncOperation) -> None:
        self._op = op
        self._callbacks = []
        self._loop = asyncio.get_running_loop()
        self._cancel_requested = False
        self._result = None

        def call_callbacks():
            for c in self._callbacks:
                c(self)

        def call_callbacks_threadsafe(op: IAsyncOperation, status: AsyncStatus):
            if status == AsyncStatus.COMPLETED:
                # have to get result on this thread, otherwise it may not return correct value
                self._result = op.get_results()

            self._loop.call_soon_threadsafe(call_callbacks)

        op.completed = call_callbacks_threadsafe

    def result(self) -> Any:
        if self._op.status == AsyncStatus.STARTED:
            raise asyncio.InvalidStateError

        if self._op.status == AsyncStatus.COMPLETED:
            if self._cancel_requested:
                raise asyncio.CancelledError

            return self._result

        if self._op.status == AsyncStatus.CANCELED:
            raise asyncio.CancelledError

        if self._op.status == AsyncStatus.ERROR:
            if self._cancel_requested:
                raise asyncio.CancelledError

            error_code = self._op.error_code.value
            raise WinError(error_code)

    def done(self) -> bool:
        return self._op.status != AsyncStatus.STARTED

    def cancelled(self) -> bool:
        return self._cancel_requested or self._op.status == AsyncStatus.CANCELED

    def add_done_callback(self, callback, *, context=None) -> None:
        self._callbacks.append(callback)

    def remove_done_callback(self, callback) -> None:
        self._callbacks.remove(callback)

    def cancel(self, msg=None) -> bool:
        if self._cancel_requested or self._op.status != AsyncStatus.STARTED:
            return False

        self._cancel_requested = True
        self._op.cancel()

        return True

    def exception(self) -> Optional[Exception]:
        if self._op.status == AsyncStatus.STARTED:
            raise asyncio.InvalidStateError

        if self._op.status == AsyncStatus.COMPLETED:
            if self._cancel_requested:
                raise asyncio.CancelledError

            return None

        if self._op.status == AsyncStatus.CANCELED:
            raise asyncio.CancelledError

        if self._op.status == AsyncStatus.ERROR:
            if self._cancel_requested:
                raise asyncio.CancelledError

            error_code = self._op.error_code.value

            return WinError(error_code)

    def get_loop(self) -> asyncio.AbstractEventLoop:
        return self._loop

    def __await__(self):
        if not self.done():
            self._asyncio_future_blocking = True
            yield self  # This tells Task to wait for completion.

        if not self.done():
            raise RuntimeError("await wasn't used with future")

        return self.result()  # May raise too.
