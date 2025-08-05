# -*- coding: utf-8 -*-
"""
BLE Client for BlueZ on Linux
"""
import asyncio
import logging
import os
import sys
import warnings
from typing import Callable, Dict, Optional, Set, Union, cast
from uuid import UUID

if sys.version_info < (3, 12):
    from typing_extensions import Buffer
else:
    from collections.abc import Buffer

if sys.version_info < (3, 11):
    from async_timeout import timeout as async_timeout
else:
    from asyncio import timeout as async_timeout

from dbus_fast.aio import MessageBus
from dbus_fast.constants import BusType, ErrorType, MessageType
from dbus_fast.message import Message
from dbus_fast.signature import Variant

from ... import BleakScanner
from ...exc import (
    BleakCharacteristicNotFoundError,
    BleakDBusError,
    BleakDeviceNotFoundError,
    BleakError,
)
from ..characteristic import BleakGATTCharacteristic
from ..client import BaseBleakClient, NotifyCallback
from ..device import BLEDevice
from ..service import BleakGATTServiceCollection
from . import defs
from .characteristic import BleakGATTCharacteristicBlueZDBus
from .manager import get_global_bluez_manager
from .scanner import BleakScannerBlueZDBus
from .utils import assert_reply, get_dbus_authenticator
from .version import BlueZFeatures

logger = logging.getLogger(__name__)

# prevent tasks from being garbage collected
_background_tasks: Set[asyncio.Task] = set()


class BleakClientBlueZDBus(BaseBleakClient):
    """A native Linux Bleak Client

    Implemented by using the `BlueZ DBUS API <https://docs.ubuntu.com/core/en/stacks/bluetooth/bluez/docs/reference/dbus-api>`_.

    Args:
        address_or_ble_device (`BLEDevice` or str): The Bluetooth address of the BLE peripheral to connect to or the `BLEDevice` object representing it.
        services: Optional list of service UUIDs that will be used.

    Keyword Args:
        timeout (float): Timeout for required ``BleakScanner.find_device_by_address`` call. Defaults to 10.0.
        disconnected_callback (callable): Callback that will be scheduled in the
            event loop when the client is disconnected. The callable must take one
            argument, which will be this client object.
        adapter (str): Bluetooth adapter to use for discovery.
    """

    def __init__(
        self,
        address_or_ble_device: Union[BLEDevice, str],
        services: Optional[Set[str]] = None,
        **kwargs,
    ):
        super(BleakClientBlueZDBus, self).__init__(address_or_ble_device, **kwargs)
        # kwarg "device" is for backwards compatibility
        self._adapter: Optional[str] = kwargs.get("adapter", kwargs.get("device"))

        # Backend specific, D-Bus objects and data
        if isinstance(address_or_ble_device, BLEDevice):
            self._device_path = address_or_ble_device.details["path"]
            self._device_info = address_or_ble_device.details.get("props")
        else:
            self._device_path = None
            self._device_info = None

        self._requested_services = services

        # D-Bus message bus
        self._bus: Optional[MessageBus] = None
        # tracks device watcher subscription
        self._remove_device_watcher: Optional[Callable] = None
        # private backing for is_connected property
        self._is_connected = False
        # indicates disconnect request in progress when not None
        self._disconnecting_event: Optional[asyncio.Event] = None
        # used to ensure device gets disconnected if event loop crashes
        self._disconnect_monitor_event: Optional[asyncio.Event] = None
        # map of characteristic D-Bus object path to notification callback
        self._notification_callbacks: Dict[str, NotifyCallback] = {}

        # used to override mtu_size property
        self._mtu_size: Optional[int] = None

    # Connectivity methods

    async def connect(self, dangerous_use_bleak_cache: bool = False, **kwargs) -> bool:
        """Connect to the specified GATT server.

        Keyword Args:
            timeout (float): Timeout for required ``BleakScanner.find_device_by_address`` call. Defaults to 10.0.

        Returns:
            Boolean representing connection status.

        Raises:
            BleakError: If the device is already connected or if the device could not be found.
            BleakDBusError: If there was a D-Bus error
            asyncio.TimeoutError: If the connection timed out
        """
        logger.debug("Connecting to device @ %s", self.address)

        if self.is_connected:
            raise BleakError("Client is already connected")

        if not BlueZFeatures.checked_bluez_version:
            await BlueZFeatures.check_bluez_version()
        if not BlueZFeatures.supported_version:
            raise BleakError("Bleak requires BlueZ >= 5.43.")
        # A Discover must have been run before connecting to any devices.
        # Find the desired device before trying to connect.
        timeout = kwargs.get("timeout", self._timeout)
        if self._device_path is None:
            device = await BleakScanner.find_device_by_address(
                self.address,
                timeout=timeout,
                adapter=self._adapter,
                backend=BleakScannerBlueZDBus,
            )

            if device:
                self._device_info = device.details.get("props")
                self._device_path = device.details["path"]
            else:
                raise BleakDeviceNotFoundError(
                    self.address, f"Device with address {self.address} was not found."
                )

        manager = await get_global_bluez_manager()

        async with async_timeout(timeout):
            while True:
                # Each BLE connection session needs a new D-Bus connection to avoid a
                # BlueZ quirk where notifications are automatically enabled on reconnect.
                self._bus = await MessageBus(
                    bus_type=BusType.SYSTEM,
                    negotiate_unix_fd=True,
                    auth=get_dbus_authenticator(),
                ).connect()

                def on_connected_changed(connected: bool) -> None:
                    if not connected:
                        logger.debug("Device disconnected (%s)", self._device_path)

                        self._is_connected = False

                        if self._disconnect_monitor_event:
                            self._disconnect_monitor_event.set()
                            self._disconnect_monitor_event = None

                        self._cleanup_all()
                        if self._disconnected_callback is not None:
                            self._disconnected_callback()
                        disconnecting_event = self._disconnecting_event
                        if disconnecting_event:
                            disconnecting_event.set()

                def on_value_changed(char_path: str, value: bytes) -> None:
                    callback = self._notification_callbacks.get(char_path)

                    if callback:
                        callback(bytearray(value))

                watcher = manager.add_device_watcher(
                    self._device_path, on_connected_changed, on_value_changed
                )
                self._remove_device_watcher = lambda: manager.remove_device_watcher(
                    watcher
                )

                self._disconnect_monitor_event = local_disconnect_monitor_event = (
                    asyncio.Event()
                )

                try:
                    try:
                        #
                        # The BlueZ backend does not disconnect devices when the
                        # application closes or crashes. This can cause problems
                        # when trying to reconnect to the same device. To work
                        # around this, we check if the device is already connected.
                        #
                        # For additional details see https://github.com/bluez/bluez/issues/89
                        #
                        if manager.is_connected(self._device_path):
                            logger.debug(
                                'skipping calling "Connect" since %s is already connected',
                                self._device_path,
                            )
                        else:
                            logger.debug(
                                "Connecting to BlueZ path %s", self._device_path
                            )
                            reply = await self._bus.call(
                                Message(
                                    destination=defs.BLUEZ_SERVICE,
                                    interface=defs.DEVICE_INTERFACE,
                                    path=self._device_path,
                                    member="Connect",
                                )
                            )

                            assert reply is not None

                            if reply.message_type == MessageType.ERROR:
                                # This error is often caused by RF interference
                                # from other Bluetooth or Wi-Fi devices. In many
                                # cases, retrying will connect successfully.
                                # Note: this error was added in BlueZ 6.62.
                                if (
                                    reply.error_name == "org.bluez.Error.Failed"
                                    and reply.body
                                    and reply.body[0] == "le-connection-abort-by-local"
                                ):
                                    logger.debug(
                                        "retry due to le-connection-abort-by-local"
                                    )

                                    # When this error occurs, BlueZ actually
                                    # connected so we get "Connected" property changes
                                    # that we need to wait for before attempting
                                    # to connect again.
                                    await local_disconnect_monitor_event.wait()

                                    # Jump way back to the `while True:`` to retry.
                                    continue

                                if reply.error_name == ErrorType.UNKNOWN_OBJECT.value:
                                    raise BleakDeviceNotFoundError(
                                        self.address,
                                        f"Device with address {self.address} was not found. It may have been removed from BlueZ when scanning stopped.",
                                    )

                            assert_reply(reply)

                        self._is_connected = True

                        # Create a task that runs until the device is disconnected.
                        task = asyncio.create_task(
                            self._disconnect_monitor(
                                self._bus,
                                self._device_path,
                                local_disconnect_monitor_event,
                            )
                        )
                        _background_tasks.add(task)
                        task.add_done_callback(_background_tasks.discard)

                        #
                        # We will try to use the cache if it exists and `dangerous_use_bleak_cache`
                        # is True.
                        #
                        await self.get_services(
                            dangerous_use_bleak_cache=dangerous_use_bleak_cache
                        )

                        return True
                    except BaseException:
                        # Calling Disconnect cancels any pending connect request. Also,
                        # if connection was successful but get_services() raises (e.g.
                        # because task was cancelled), the we still need to disconnect
                        # before passing on the exception.
                        if self._bus:
                            # If disconnected callback already fired, this will be a no-op
                            # since self._bus will be None and the _cleanup_all call will
                            # have already disconnected.
                            try:
                                reply = await self._bus.call(
                                    Message(
                                        destination=defs.BLUEZ_SERVICE,
                                        interface=defs.DEVICE_INTERFACE,
                                        path=self._device_path,
                                        member="Disconnect",
                                    )
                                )
                                try:
                                    assert_reply(reply)
                                except BleakDBusError as e:
                                    # if the object no longer exists, then we know we
                                    # are disconnected for sure, so don't need to log a
                                    # warning about it
                                    if e.dbus_error != ErrorType.UNKNOWN_OBJECT.value:
                                        raise
                            except Exception as e:
                                logger.warning(
                                    f"Failed to cancel connection ({self._device_path}): {e}"
                                )

                        raise
                except BaseException:
                    # this effectively cancels the disconnect monitor in case the event
                    # was not triggered by a D-Bus callback
                    local_disconnect_monitor_event.set()
                    self._cleanup_all()
                    raise

    @staticmethod
    async def _disconnect_monitor(
        bus: MessageBus, device_path: str, disconnect_monitor_event: asyncio.Event
    ) -> None:
        # This task runs until the device is disconnected. If the task is
        # cancelled, it probably means that the event loop crashed so we
        # try to disconnected the device. Otherwise BlueZ will keep the device
        # connected even after Python exits. This will only work if the event
        # loop is called with asyncio.run() or otherwise runs pending tasks
        # after the original event loop stops. This will also cause an exception
        # if a run loop is stopped before the device is disconnected since this
        # task will still be running and asyncio complains if a loop with running
        # tasks is stopped.
        try:
            await disconnect_monitor_event.wait()
        except asyncio.CancelledError:
            try:
                # by using send() instead of call(), we ensure that the message
                # gets sent, but we don't wait for a reply, which could take
                # over one second while the device disconnects.
                await bus.send(
                    Message(
                        destination=defs.BLUEZ_SERVICE,
                        path=device_path,
                        interface=defs.DEVICE_INTERFACE,
                        member="Disconnect",
                    )
                )
            except Exception:
                pass

    def _cleanup_all(self) -> None:
        """
        Free all the allocated resource in DBus. Use this method to
        eventually cleanup all otherwise leaked resources.
        """
        logger.debug("_cleanup_all(%s)", self._device_path)

        if self._remove_device_watcher:
            self._remove_device_watcher()
            self._remove_device_watcher = None

        if not self._bus:
            logger.debug("already disconnected (%s)", self._device_path)
            return

        # Try to disconnect the System Bus.
        try:
            self._bus.disconnect()
        except Exception as e:
            logger.error(
                "Attempt to disconnect system bus failed (%s): %s",
                self._device_path,
                e,
            )
        else:
            # Critical to remove the `self._bus` object here to since it was
            # closed above. If not, calls made to it later could lead to
            # a stuck client.
            self._bus = None

            # Reset all stored services.
            self.services = None

    async def disconnect(self) -> bool:
        """Disconnect from the specified GATT server.

        Returns:
            Boolean representing if device is disconnected.

        Raises:
            BleakDBusError: If there was a D-Bus error
            asyncio.TimeoutError if the device was not disconnected within 10 seconds
        """
        logger.debug("Disconnecting ({%s})", self._device_path)

        if self._bus is None:
            # No connection exists. Either one hasn't been created or
            # we have already called disconnect and closed the D-Bus
            # connection.
            logger.debug("already disconnected ({%s})", self._device_path)
            return True

        if self._disconnecting_event:
            # another call to disconnect() is already in progress
            logger.debug("already in progress ({%s})", self._device_path)
            async with async_timeout(10):
                await self._disconnecting_event.wait()
        elif self.is_connected:
            self._disconnecting_event = asyncio.Event()
            try:
                # Try to disconnect the actual device/peripheral
                reply = await self._bus.call(
                    Message(
                        destination=defs.BLUEZ_SERVICE,
                        path=self._device_path,
                        interface=defs.DEVICE_INTERFACE,
                        member="Disconnect",
                    )
                )
                assert_reply(reply)
                async with async_timeout(10):
                    await self._disconnecting_event.wait()
            finally:
                self._disconnecting_event = None

        # sanity check to make sure _cleanup_all() was triggered by the
        # "PropertiesChanged" signal handler and that it completed successfully
        assert self._bus is None

        return True

    async def pair(self, *args, **kwargs) -> bool:
        """Pair with the peripheral.

        You can use ConnectDevice method if you already know the MAC address of the device.
        Else you need to StartDiscovery, Trust, Pair and Connect in sequence.

        Returns:
            Boolean regarding success of pairing.

        """
        # See if it is already paired.
        reply = await self._bus.call(
            Message(
                destination=defs.BLUEZ_SERVICE,
                path=self._device_path,
                interface=defs.PROPERTIES_INTERFACE,
                member="Get",
                signature="ss",
                body=[defs.DEVICE_INTERFACE, "Paired"],
            )
        )
        assert_reply(reply)
        if reply.body[0].value:
            logger.debug("BLE device @ %s is already paired", self.address)
            return True

        # Set device as trusted.
        reply = await self._bus.call(
            Message(
                destination=defs.BLUEZ_SERVICE,
                path=self._device_path,
                interface=defs.PROPERTIES_INTERFACE,
                member="Set",
                signature="ssv",
                body=[defs.DEVICE_INTERFACE, "Trusted", Variant("b", True)],
            )
        )
        assert_reply(reply)

        logger.debug("Pairing to BLE device @ %s", self.address)

        reply = await self._bus.call(
            Message(
                destination=defs.BLUEZ_SERVICE,
                path=self._device_path,
                interface=defs.DEVICE_INTERFACE,
                member="Pair",
            )
        )
        assert_reply(reply)

        reply = await self._bus.call(
            Message(
                destination=defs.BLUEZ_SERVICE,
                path=self._device_path,
                interface=defs.PROPERTIES_INTERFACE,
                member="Get",
                signature="ss",
                body=[defs.DEVICE_INTERFACE, "Paired"],
            )
        )
        assert_reply(reply)

        return reply.body[0].value

    async def unpair(self) -> bool:
        """Unpair with the peripheral.

        Returns:
            Boolean regarding success of unpairing.

        """
        adapter_path = await self._get_adapter_path()
        device_path = await self._get_device_path()
        manager = await get_global_bluez_manager()

        logger.debug(
            "Removing BlueZ device path %s from adapter path %s",
            device_path,
            adapter_path,
        )

        # If this client object wants to connect again, BlueZ needs the device
        # to follow Discovery process again - so reset the local connection
        # state.
        #
        # (This is true even if the request to RemoveDevice fails,
        # so clear it before.)
        self._device_path = None
        self._device_info = None
        self._is_connected = False

        try:
            reply = await manager._bus.call(
                Message(
                    destination=defs.BLUEZ_SERVICE,
                    path=adapter_path,
                    interface=defs.ADAPTER_INTERFACE,
                    member="RemoveDevice",
                    signature="o",
                    body=[device_path],
                )
            )
            assert_reply(reply)
        except BleakDBusError as e:
            if e.dbus_error == "org.bluez.Error.DoesNotExist":
                raise BleakDeviceNotFoundError(
                    self.address, f"Device with address {self.address} was not found."
                ) from e
            raise

        return True

    @property
    def is_connected(self) -> bool:
        """Check connection status between this client and the server.

        Returns:
            Boolean representing connection status.

        """
        return self._DeprecatedIsConnectedReturn(
            False if self._bus is None else self._is_connected
        )

    async def _acquire_mtu(self) -> None:
        """Acquires the MTU for this device by calling the "AcquireWrite" or
        "AcquireNotify" method of the first characteristic that has such a method.

        This method only needs to be called once, after connecting to the device
        but before accessing the ``mtu_size`` property.

        If a device uses encryption on characteristics, it will need to be bonded
        first before calling this method.
        """
        # This will try to get the "best" characteristic for getting the MTU.
        # We would rather not start notifications if we don't have to.
        try:
            method = "AcquireWrite"
            char = next(
                c
                for c in self.services.characteristics.values()
                if "write-without-response" in c.properties
            )
        except StopIteration:
            method = "AcquireNotify"
            char = next(
                c
                for c in self.services.characteristics.values()
                if "notify" in c.properties
            )

        reply = await self._bus.call(
            Message(
                destination=defs.BLUEZ_SERVICE,
                path=char.path,
                interface=defs.GATT_CHARACTERISTIC_INTERFACE,
                member=method,
                signature="a{sv}",
                body=[{}],
            )
        )
        assert_reply(reply)

        # we aren't actually using the write or notify, we just want the MTU
        os.close(reply.unix_fds[0])
        self._mtu_size = reply.body[1]

    async def _get_adapter_path(self) -> str:
        """Private coroutine to return the BlueZ path to the adapter this client is assigned to.

        Can be called even if no connection has been established yet.
        """
        if self._device_info:
            # If we have a BlueZ DBus object with _device_info, use what it tell us
            return self._device_info["Adapter"]
        if self._adapter:
            # If the adapter name was set in the constructor, convert to a BlueZ path
            return f"/org/bluez/{self._adapter}"

        # Fall back to the system's default Bluetooth adapter
        manager = await get_global_bluez_manager()
        return manager.get_default_adapter()

    async def _get_device_path(self) -> str:
        """Private coroutine to return the BlueZ path to the device address this client is assigned to.

        Unlike the _device_path property, this function can be called even if discovery process has not
        started and/or connection has not been established yet.
        """
        if self._device_path:
            # If we have a BlueZ DBus object, return its device path
            return self._device_path

        # Otherwise, build a new path using the adapter path and the BLE address
        adapter_path = await self._get_adapter_path()
        bluez_address = self.address.upper().replace(":", "_")
        return f"{adapter_path}/dev_{bluez_address}"

    @property
    def mtu_size(self) -> int:
        """Get ATT MTU size for active connection"""
        if self._mtu_size is None:
            warnings.warn(
                "Using default MTU value. Call _acquire_mtu() or set _mtu_size first to avoid this warning."
            )
            return 23

        return self._mtu_size

    # GATT services methods

    async def get_services(
        self, dangerous_use_bleak_cache: bool = False, **kwargs
    ) -> BleakGATTServiceCollection:
        """Get all services registered for this GATT server.

        Args:
            dangerous_use_bleak_cache (bool): Use cached services if available.

        Returns:
           A :py:class:`bleak.backends.service.BleakGATTServiceCollection` with this device's services tree.

        """
        if not self.is_connected:
            raise BleakError("Not connected")

        if self.services is not None:
            return self.services

        manager = await get_global_bluez_manager()

        self.services = await manager.get_services(
            self._device_path, dangerous_use_bleak_cache, self._requested_services
        )

        return self.services

    # IO methods

    async def read_gatt_char(
        self,
        char_specifier: Union[BleakGATTCharacteristicBlueZDBus, int, str, UUID],
        **kwargs,
    ) -> bytearray:
        """Perform read operation on the specified GATT characteristic.

        Args:
            char_specifier (BleakGATTCharacteristicBlueZDBus, int, str or UUID): The characteristic to read from,
                specified by either integer handle, UUID or directly by the
                BleakGATTCharacteristicBlueZDBus object representing it.

        Returns:
            (bytearray) The read data.

        """
        if not self.is_connected:
            raise BleakError("Not connected")

        if not isinstance(char_specifier, BleakGATTCharacteristicBlueZDBus):
            characteristic = self.services.get_characteristic(char_specifier)
        else:
            characteristic = char_specifier

        if not characteristic:
            # Special handling for BlueZ >= 5.48, where Battery Service (0000180f-0000-1000-8000-00805f9b34fb:)
            # has been moved to interface org.bluez.Battery1 instead of as a regular service.
            if (
                str(char_specifier) == "00002a19-0000-1000-8000-00805f9b34fb"
                and BlueZFeatures.hides_battery_characteristic
            ):
                reply = await self._bus.call(
                    Message(
                        destination=defs.BLUEZ_SERVICE,
                        path=self._device_path,
                        interface=defs.PROPERTIES_INTERFACE,
                        member="GetAll",
                        signature="s",
                        body=[defs.BATTERY_INTERFACE],
                    )
                )
                assert_reply(reply)
                # Simulate regular characteristics read to be consistent over all platforms.
                value = bytearray([reply.body[0]["Percentage"].value])
                logger.debug(
                    "Read Battery Level {0} | {1}: {2}".format(
                        char_specifier, self._device_path, value
                    )
                )
                return value
            if (
                str(char_specifier) == "00002a00-0000-1000-8000-00805f9b34fb"
                and BlueZFeatures.hides_device_name_characteristic
            ):
                # Simulate regular characteristics read to be consistent over all platforms.
                manager = await get_global_bluez_manager()
                value = bytearray(manager.get_device_name(self._device_path).encode())
                logger.debug(
                    "Read Device Name {0} | {1}: {2}".format(
                        char_specifier, self._device_path, value
                    )
                )
                return value

            raise BleakCharacteristicNotFoundError(char_specifier)

        while True:
            assert self._bus

            reply = await self._bus.call(
                Message(
                    destination=defs.BLUEZ_SERVICE,
                    path=characteristic.path,
                    interface=defs.GATT_CHARACTERISTIC_INTERFACE,
                    member="ReadValue",
                    signature="a{sv}",
                    body=[{}],
                )
            )

            assert reply

            if reply.error_name == "org.bluez.Error.InProgress":
                logger.debug("retrying characteristic ReadValue due to InProgress")
                # Avoid calling in a tight loop. There is no dbus signal to
                # indicate ready, so unfortunately, we have to poll.
                await asyncio.sleep(0.01)
                continue

            assert_reply(reply)
            break

        value = bytearray(reply.body[0])

        logger.debug(
            "Read Characteristic {0} | {1}: {2}".format(
                characteristic.uuid, characteristic.path, value
            )
        )
        return value

    async def read_gatt_descriptor(self, handle: int, **kwargs) -> bytearray:
        """Perform read operation on the specified GATT descriptor.

        Args:
            handle (int): The handle of the descriptor to read from.

        Returns:
            (bytearray) The read data.

        """
        if not self.is_connected:
            raise BleakError("Not connected")

        descriptor = self.services.get_descriptor(handle)
        if not descriptor:
            raise BleakError("Descriptor with handle {0} was not found!".format(handle))

        while True:
            assert self._bus

            reply = await self._bus.call(
                Message(
                    destination=defs.BLUEZ_SERVICE,
                    path=descriptor.path,
                    interface=defs.GATT_DESCRIPTOR_INTERFACE,
                    member="ReadValue",
                    signature="a{sv}",
                    body=[{}],
                )
            )

            assert reply

            if reply.error_name == "org.bluez.Error.InProgress":
                logger.debug("retrying descriptor ReadValue due to InProgress")
                # Avoid calling in a tight loop. There is no dbus signal to
                # indicate ready, so unfortunately, we have to poll.
                await asyncio.sleep(0.01)
                continue

            assert_reply(reply)
            break

        value = bytearray(reply.body[0])

        logger.debug("Read Descriptor %s | %s: %s", handle, descriptor.path, value)
        return value

    async def write_gatt_char(
        self,
        characteristic: BleakGATTCharacteristic,
        data: Buffer,
        response: bool,
    ) -> None:
        if not self.is_connected:
            raise BleakError("Not connected")

        # See docstring for details about this handling.
        if not response and not BlueZFeatures.can_write_without_response:
            raise BleakError("Write without response requires at least BlueZ 5.46")

        if response or not BlueZFeatures.write_without_response_workaround_needed:
            while True:
                assert self._bus

                reply = await self._bus.call(
                    Message(
                        destination=defs.BLUEZ_SERVICE,
                        path=characteristic.path,
                        interface=defs.GATT_CHARACTERISTIC_INTERFACE,
                        member="WriteValue",
                        signature="aya{sv}",
                        body=[
                            bytes(data),
                            {
                                "type": Variant(
                                    "s", "request" if response else "command"
                                )
                            },
                        ],
                    )
                )

                assert reply

                if reply.error_name == "org.bluez.Error.InProgress":
                    logger.debug("retrying characteristic WriteValue due to InProgress")
                    # Avoid calling in a tight loop. There is no dbus signal to
                    # indicate ready, so unfortunately, we have to poll.
                    await asyncio.sleep(0.01)
                    continue

                assert_reply(reply)
                break
        else:
            # Older versions of BlueZ don't have the "type" option, so we have
            # to write the hard way. This isn't the most efficient way of doing
            # things, but it works.
            reply = await self._bus.call(
                Message(
                    destination=defs.BLUEZ_SERVICE,
                    path=characteristic.path,
                    interface=defs.GATT_CHARACTERISTIC_INTERFACE,
                    member="AcquireWrite",
                    signature="a{sv}",
                    body=[{}],
                )
            )
            assert_reply(reply)
            fd = reply.unix_fds[0]
            try:
                os.write(fd, data)
            finally:
                os.close(fd)

        logger.debug(
            "Write Characteristic %s | %s: %s",
            characteristic.uuid,
            characteristic.path,
            data,
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

        while True:
            assert self._bus

            reply = await self._bus.call(
                Message(
                    destination=defs.BLUEZ_SERVICE,
                    path=descriptor.path,
                    interface=defs.GATT_DESCRIPTOR_INTERFACE,
                    member="WriteValue",
                    signature="aya{sv}",
                    body=[bytes(data), {"type": Variant("s", "command")}],
                )
            )

            assert reply

            if reply.error_name == "org.bluez.Error.InProgress":
                logger.debug("retrying descriptor WriteValue due to InProgress")
                # Avoid calling in a tight loop. There is no dbus signal to
                # indicate ready, so unfortunately, we have to poll.
                await asyncio.sleep(0.01)
                continue

            assert_reply(reply)
            break

        logger.debug("Write Descriptor %s | %s: %s", handle, descriptor.path, data)

    async def start_notify(
        self,
        characteristic: BleakGATTCharacteristic,
        callback: NotifyCallback,
        **kwargs,
    ) -> None:
        """
        Activate notifications/indications on a characteristic.
        """
        characteristic = cast(BleakGATTCharacteristicBlueZDBus, characteristic)

        self._notification_callbacks[characteristic.path] = callback

        assert self._bus is not None

        reply = await self._bus.call(
            Message(
                destination=defs.BLUEZ_SERVICE,
                path=characteristic.path,
                interface=defs.GATT_CHARACTERISTIC_INTERFACE,
                member="StartNotify",
            )
        )
        assert_reply(reply)

    async def stop_notify(
        self,
        char_specifier: Union[BleakGATTCharacteristicBlueZDBus, int, str, UUID],
    ) -> None:
        """Deactivate notification/indication on a specified characteristic.

        Args:
            char_specifier (BleakGATTCharacteristicBlueZDBus, int, str or UUID): The characteristic to deactivate
                notification/indication on, specified by either integer handle, UUID or
                directly by the BleakGATTCharacteristicBlueZDBus object representing it.

        """
        if not self.is_connected:
            raise BleakError("Not connected")

        if not isinstance(char_specifier, BleakGATTCharacteristicBlueZDBus):
            characteristic = self.services.get_characteristic(char_specifier)
        else:
            characteristic = char_specifier
        if not characteristic:
            raise BleakCharacteristicNotFoundError(char_specifier)

        reply = await self._bus.call(
            Message(
                destination=defs.BLUEZ_SERVICE,
                path=characteristic.path,
                interface=defs.GATT_CHARACTERISTIC_INTERFACE,
                member="StopNotify",
            )
        )
        assert_reply(reply)

        self._notification_callbacks.pop(characteristic.path, None)
