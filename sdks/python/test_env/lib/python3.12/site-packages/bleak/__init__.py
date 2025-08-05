# -*- coding: utf-8 -*-

"""Top-level package for bleak."""

from __future__ import annotations

__author__ = """Henrik Blidh"""
__email__ = "henrik.blidh@gmail.com"

import asyncio
import functools
import inspect
import logging
import os
import sys
import uuid
from types import TracebackType
from typing import (
    TYPE_CHECKING,
    AsyncGenerator,
    Awaitable,
    Callable,
    Dict,
    Iterable,
    List,
    Literal,
    Optional,
    Set,
    Tuple,
    Type,
    TypedDict,
    Union,
    overload,
)
from warnings import warn

if sys.version_info < (3, 12):
    from typing_extensions import Buffer
else:
    from collections.abc import Buffer

if sys.version_info < (3, 11):
    from async_timeout import timeout as async_timeout
    from typing_extensions import Unpack
else:
    from asyncio import timeout as async_timeout
    from typing import Unpack

from .backends.characteristic import BleakGATTCharacteristic
from .backends.client import BaseBleakClient, get_platform_client_backend_type
from .backends.device import BLEDevice
from .backends.scanner import (
    AdvertisementData,
    AdvertisementDataCallback,
    AdvertisementDataFilter,
    BaseBleakScanner,
    get_platform_scanner_backend_type,
)
from .backends.service import BleakGATTServiceCollection
from .exc import BleakCharacteristicNotFoundError, BleakError
from .uuids import normalize_uuid_str

if TYPE_CHECKING:
    from .backends.bluezdbus.scanner import BlueZScannerArgs
    from .backends.corebluetooth.scanner import CBScannerArgs
    from .backends.winrt.client import WinRTClientArgs


_logger = logging.getLogger(__name__)
_logger.addHandler(logging.NullHandler())
if bool(os.environ.get("BLEAK_LOGGING", False)):
    FORMAT = "%(asctime)-15s %(name)-8s %(threadName)s %(levelname)s: %(message)s"
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter(fmt=FORMAT))
    _logger.addHandler(handler)
    _logger.setLevel(logging.DEBUG)


# prevent tasks from being garbage collected
_background_tasks: Set[asyncio.Task] = set()


class BleakScanner:
    """
    Interface for Bleak Bluetooth LE Scanners.

    The scanner will listen for BLE advertisements, optionally filtering on advertised services or
    other conditions, and collect a list of :class:`BLEDevice` objects. These can subsequently be used to
    connect to the corresponding BLE server.

    A :class:`BleakScanner` can be used as an asynchronous context manager in which case it automatically
    starts and stops scanning.

    Args:
        detection_callback:
            Optional function that will be called each time a device is
            discovered or advertising data has changed.
        service_uuids:
            Optional list of service UUIDs to filter on. Only advertisements
            containing this advertising data will be received. Required on
            macOS >= 12.0, < 12.3 (unless you create an app with ``py2app``).
        scanning_mode:
            Set to ``"passive"`` to avoid the ``"active"`` scanning mode.
            Passive scanning is not supported on macOS! Will raise
            :class:`BleakError` if set to ``"passive"`` on macOS.
        bluez:
            Dictionary of arguments specific to the BlueZ backend.
        cb:
            Dictionary of arguments specific to the CoreBluetooth backend.
        backend:
            Used to override the automatically selected backend (i.e. for a
            custom backend).
        **kwargs:
            Additional args for backwards compatibility.

    .. tip:: The first received advertisement in ``detection_callback`` may or
        may not include scan response data if the remote device supports it.
        Be sure to take this into account when handing the callback. For example,
        the scan response often contains the local name of the device so if you
        are matching a device based on other data but want to display the local
        name to the user, be sure to wait for ``adv_data.local_name is not None``.

    .. versionchanged:: 0.15
        ``detection_callback``, ``service_uuids`` and ``scanning_mode`` are no longer keyword-only.
        Added ``bluez`` parameter.

    .. versionchanged:: 0.18
        No longer is alias for backend type and no longer inherits from :class:`BaseBleakScanner`.
        Added ``backend`` parameter.
    """

    def __init__(
        self,
        detection_callback: Optional[AdvertisementDataCallback] = None,
        service_uuids: Optional[List[str]] = None,
        scanning_mode: Literal["active", "passive"] = "active",
        *,
        bluez: BlueZScannerArgs = {},
        cb: CBScannerArgs = {},
        backend: Optional[Type[BaseBleakScanner]] = None,
        **kwargs,
    ) -> None:
        PlatformBleakScanner = (
            get_platform_scanner_backend_type() if backend is None else backend
        )

        self._backend = PlatformBleakScanner(
            detection_callback,
            service_uuids,
            scanning_mode,
            bluez=bluez,
            cb=cb,
            **kwargs,
        )

    async def __aenter__(self) -> BleakScanner:
        await self._backend.start()
        return self

    async def __aexit__(
        self,
        exc_type: Type[BaseException],
        exc_val: BaseException,
        exc_tb: TracebackType,
    ) -> None:
        await self._backend.stop()

    def register_detection_callback(
        self, callback: Optional[AdvertisementDataCallback]
    ) -> None:
        """
        Register a callback that is called when a device is discovered or has a property changed.

        .. deprecated:: 0.17.0
            This method will be removed in a future version of Bleak. Pass
            the callback directly to the :class:`BleakScanner` constructor instead.

        Args:
            callback: A function, coroutine or ``None``.


        """
        warn(
            "This method will be removed in a future version of Bleak. Use the detection_callback of the BleakScanner constructor instead.",
            FutureWarning,
            stacklevel=2,
        )

        try:
            unregister = getattr(self, "_unregister_")
        except AttributeError:
            pass
        else:
            unregister()

        if callback is not None:
            unregister = self._backend.register_detection_callback(callback)
            setattr(self, "_unregister_", unregister)

    async def start(self) -> None:
        """Start scanning for devices"""
        await self._backend.start()

    async def stop(self) -> None:
        """Stop scanning for devices"""
        await self._backend.stop()

    def set_scanning_filter(self, **kwargs) -> None:
        """
        Set scanning filter for the BleakScanner.

        .. deprecated:: 0.17.0
            This method will be removed in a future version of Bleak. Pass
            arguments directly to the :class:`BleakScanner` constructor instead.

        Args:
            **kwargs: The filter details.

        """
        warn(
            "This method will be removed in a future version of Bleak. Use BleakScanner constructor args instead.",
            FutureWarning,
            stacklevel=2,
        )
        self._backend.set_scanning_filter(**kwargs)

    async def advertisement_data(
        self,
    ) -> AsyncGenerator[Tuple[BLEDevice, AdvertisementData], None]:
        """
        Yields devices and associated advertising data packets as they are discovered.

        .. note::
            Ensure that scanning is started before calling this method.

        Returns:
            An async iterator that yields tuples (:class:`BLEDevice`, :class:`AdvertisementData`).

        .. versionadded:: 0.21
        """
        devices = asyncio.Queue()

        unregister_callback = self._backend.register_detection_callback(
            lambda bd, ad: devices.put_nowait((bd, ad))
        )
        try:
            while True:
                yield await devices.get()
        finally:
            unregister_callback()

    class ExtraArgs(TypedDict, total=False):
        """
        Keyword args from :class:`~bleak.BleakScanner` that can be passed to
        other convenience methods.
        """

        service_uuids: List[str]
        """
        Optional list of service UUIDs to filter on. Only advertisements
        containing this advertising data will be received. Required on
        macOS >= 12.0, < 12.3 (unless you create an app with ``py2app``).
        """
        scanning_mode: Literal["active", "passive"]
        """
        Set to ``"passive"`` to avoid the ``"active"`` scanning mode.
        Passive scanning is not supported on macOS! Will raise
        :class:`BleakError` if set to ``"passive"`` on macOS.
        """
        bluez: BlueZScannerArgs
        """
        Dictionary of arguments specific to the BlueZ backend.
        """
        cb: CBScannerArgs
        """
        Dictionary of arguments specific to the CoreBluetooth backend.
        """
        backend: Type[BaseBleakScanner]
        """
        Used to override the automatically selected backend (i.e. for a
            custom backend).
        """

    @overload
    @classmethod
    async def discover(
        cls, timeout: float = 5.0, *, return_adv: Literal[False] = False, **kwargs
    ) -> List[BLEDevice]: ...

    @overload
    @classmethod
    async def discover(
        cls, timeout: float = 5.0, *, return_adv: Literal[True], **kwargs
    ) -> Dict[str, Tuple[BLEDevice, AdvertisementData]]: ...

    @classmethod
    async def discover(
        cls, timeout=5.0, *, return_adv=False, **kwargs: Unpack[ExtraArgs]
    ):
        """
        Scan continuously for ``timeout`` seconds and return discovered devices.

        Args:
            timeout:
                Time, in seconds, to scan for.
            return_adv:
                If ``True``, the return value will include advertising data.
            **kwargs:
                Additional arguments will be passed to the :class:`BleakScanner`
                constructor.

        Returns:
            The value of :attr:`discovered_devices_and_advertisement_data` if
            ``return_adv`` is ``True``, otherwise the value of :attr:`discovered_devices`.

        .. versionchanged:: 0.19
            Added ``return_adv`` parameter.
        """
        async with cls(**kwargs) as scanner:
            await asyncio.sleep(timeout)

        if return_adv:
            return scanner.discovered_devices_and_advertisement_data

        return scanner.discovered_devices

    @property
    def discovered_devices(self) -> List[BLEDevice]:
        """
        Gets list of the devices that the scanner has discovered during the scanning.

        If you also need advertisement data, use :attr:`discovered_devices_and_advertisement_data` instead.
        """
        return [d for d, _ in self._backend.seen_devices.values()]

    @property
    def discovered_devices_and_advertisement_data(
        self,
    ) -> Dict[str, Tuple[BLEDevice, AdvertisementData]]:
        """
        Gets a map of device address to tuples of devices and the most recently
        received advertisement data for that device.

        The address keys are useful to compare the discovered devices to a set
        of known devices. If you don't need to do that, consider using
        ``discovered_devices_and_advertisement_data.values()`` to just get the
        values instead.

        .. versionadded:: 0.19
        """
        return self._backend.seen_devices

    async def get_discovered_devices(self) -> List[BLEDevice]:
        """Gets the devices registered by the BleakScanner.

        .. deprecated:: 0.11.0
            This method will be removed in a future version of Bleak. Use the
            :attr:`.discovered_devices` property instead.

        Returns:
            A list of the devices that the scanner has discovered during the scanning.

        """
        warn(
            "This method will be removed in a future version of Bleak. Use the `discovered_devices` property instead.",
            FutureWarning,
            stacklevel=2,
        )
        return self.discovered_devices

    @classmethod
    async def find_device_by_address(
        cls, device_identifier: str, timeout: float = 10.0, **kwargs: Unpack[ExtraArgs]
    ) -> Optional[BLEDevice]:
        """Obtain a ``BLEDevice`` for a BLE server specified by Bluetooth address or (macOS) UUID address.

        Args:
            device_identifier: The Bluetooth/UUID address of the Bluetooth peripheral sought.
            timeout: Optional timeout to wait for detection of specified peripheral before giving up. Defaults to 10.0 seconds.
            **kwargs: additional args passed to the :class:`BleakScanner` constructor.

        Returns:
            The ``BLEDevice`` sought or ``None`` if not detected.

        """
        device_identifier = device_identifier.lower()
        return await cls.find_device_by_filter(
            lambda d, ad: d.address.lower() == device_identifier,
            timeout=timeout,
            **kwargs,
        )

    @classmethod
    async def find_device_by_name(
        cls, name: str, timeout: float = 10.0, **kwargs: Unpack[ExtraArgs]
    ) -> Optional[BLEDevice]:
        """Obtain a ``BLEDevice`` for a BLE server specified by the local name in the advertising data.

        Args:
            name: The name sought.
            timeout: Optional timeout to wait for detection of specified peripheral before giving up. Defaults to 10.0 seconds.
            **kwargs: additional args passed to the :class:`BleakScanner` constructor.

        Returns:
            The ``BLEDevice`` sought or ``None`` if not detected.

        .. versionadded:: 0.20
        """
        return await cls.find_device_by_filter(
            lambda d, ad: ad.local_name == name,
            timeout=timeout,
            **kwargs,
        )

    @classmethod
    async def find_device_by_filter(
        cls,
        filterfunc: AdvertisementDataFilter,
        timeout: float = 10.0,
        **kwargs: Unpack[ExtraArgs],
    ) -> Optional[BLEDevice]:
        """Obtain a ``BLEDevice`` for a BLE server that matches a given filter function.

        This can be used to find a BLE server by other identifying information than its address,
        for example its name.

        Args:
            filterfunc:
                A function that is called for every BLEDevice found. It should
                return ``True`` only for the wanted device.
            timeout:
                Optional timeout to wait for detection of specified peripheral
                before giving up. Defaults to 10.0 seconds.
            **kwargs:
                Additional arguments to be passed to the :class:`BleakScanner`
                constructor.

        Returns:
            The :class:`BLEDevice` sought or ``None`` if not detected before
            the timeout.

        """
        async with cls(**kwargs) as scanner:
            try:
                async with async_timeout(timeout):
                    async for bd, ad in scanner.advertisement_data():
                        if filterfunc(bd, ad):
                            return bd
            except asyncio.TimeoutError:
                return None


class BleakClient:
    """The Client interface for connecting to a specific BLE GATT server and communicating with it.

    A BleakClient can be used as an asynchronous context manager in which case it automatically
    connects and disconnects.

    How many BLE connections can be active simultaneously, and whether connections can be active while
    scanning depends on the Bluetooth adapter hardware.

    Args:
        address_or_ble_device:
            A :class:`BLEDevice` received from a :class:`BleakScanner` or a
            Bluetooth address (device UUID on macOS).
        disconnected_callback:
            Callback that will be scheduled in the event loop when the client is
            disconnected. The callable must take one argument, which will be
            this client object.
        services:
            Optional list of services to filter. If provided, only these services
            will be resolved. This may or may not reduce the time needed to
            enumerate the services depending on if the OS supports such filtering
            in the Bluetooth stack or not (should affect Windows and Mac).
            These can be 16-bit or 128-bit UUIDs.
        timeout:
            Timeout in seconds passed to the implicit ``discover`` call when
            ``address_or_ble_device`` is not a :class:`BLEDevice`. Defaults to 10.0.
        winrt:
            Dictionary of WinRT/Windows platform-specific options.
        backend:
            Used to override the automatically selected backend (i.e. for a
            custom backend).
        **kwargs:
            Additional keyword arguments for backwards compatibility.

    .. warning:: Although example code frequently initializes :class:`BleakClient`
        with a Bluetooth address for simplicity, it is not recommended to do so
        for more complex use cases. There are several known issues with providing
        a Bluetooth address as the ``address_or_ble_device`` argument.

        1.  macOS does not provide access to the Bluetooth address for privacy/
            security reasons. Instead it creates a UUID for each Bluetooth
            device which is used in place of the address on this platform.
        2.  Providing an address or UUID instead of a :class:`BLEDevice` causes
            the :meth:`connect` method to implicitly call :meth:`BleakScanner.discover`.
            This is known to cause problems when trying to connect to multiple
            devices at the same time.

    .. versionchanged:: 0.15
        ``disconnected_callback`` is no longer keyword-only. Added ``winrt`` parameter.

    .. versionchanged:: 0.18
        No longer is alias for backend type and no longer inherits from :class:`BaseBleakClient`.
        Added ``backend`` parameter.
    """

    def __init__(
        self,
        address_or_ble_device: Union[BLEDevice, str],
        disconnected_callback: Optional[Callable[[BleakClient], None]] = None,
        services: Optional[Iterable[str]] = None,
        *,
        timeout: float = 10.0,
        winrt: WinRTClientArgs = {},
        backend: Optional[Type[BaseBleakClient]] = None,
        **kwargs,
    ) -> None:
        PlatformBleakClient = (
            get_platform_client_backend_type() if backend is None else backend
        )

        self._backend = PlatformBleakClient(
            address_or_ble_device,
            disconnected_callback=(
                None
                if disconnected_callback is None
                else functools.partial(disconnected_callback, self)
            ),
            services=(
                None if services is None else set(map(normalize_uuid_str, services))
            ),
            timeout=timeout,
            winrt=winrt,
            **kwargs,
        )

    # device info

    @property
    def address(self) -> str:
        """
        Gets the Bluetooth address of this device (UUID on macOS).
        """
        return self._backend.address

    @property
    def mtu_size(self) -> int:
        """
        Gets the negotiated MTU size in bytes for the active connection.

        Consider using :attr:`bleak.backends.characteristic.BleakGATTCharacteristic.max_write_without_response_size` instead.

        .. warning:: The BlueZ backend will always return 23 (the minimum MTU size).
            See the ``mtu_size.py`` example for a way to hack around this.

        """
        return self._backend.mtu_size

    def __str__(self) -> str:
        return f"{self.__class__.__name__}, {self.address}"

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}, {self.address}, {type(self._backend)}>"

    # Async Context managers

    async def __aenter__(self) -> BleakClient:
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: Type[BaseException],
        exc_val: BaseException,
        exc_tb: TracebackType,
    ) -> None:
        await self.disconnect()

    # Connectivity methods

    def set_disconnected_callback(
        self, callback: Optional[Callable[[BleakClient], None]], **kwargs
    ) -> None:
        """Set the disconnect callback.

        .. deprecated:: 0.17.0
            This method will be removed in a future version of Bleak.
            Pass the callback to the :class:`BleakClient` constructor instead.

        Args:
            callback: callback to be called on disconnection.

        """
        warn(
            "This method will be removed future version, pass the callback to the BleakClient constructor instead.",
            FutureWarning,
            stacklevel=2,
        )
        self._backend.set_disconnected_callback(
            None if callback is None else functools.partial(callback, self), **kwargs
        )

    async def connect(self, **kwargs) -> bool:
        """Connect to the specified GATT server.

        Args:
            **kwargs: For backwards compatibility - should not be used.

        Returns:
            Always returns ``True`` for backwards compatibility.

        """
        return await self._backend.connect(**kwargs)

    async def disconnect(self) -> bool:
        """Disconnect from the specified GATT server.

        Returns:
            Always returns ``True`` for backwards compatibility.

        """
        return await self._backend.disconnect()

    async def pair(self, *args, **kwargs) -> bool:
        """
        Pair with the specified GATT server.

        This method is not available on macOS. Instead of manually initiating
        paring, the user will be prompted to pair the device the first time
        that a characteristic that requires authentication is read or written.
        This method may have backend-specific additional keyword arguments.

        Returns:
            Always returns ``True`` for backwards compatibility.

        """
        return await self._backend.pair(*args, **kwargs)

    async def unpair(self) -> bool:
        """
        Unpair from the specified GATT server.

        Unpairing will also disconnect the device.

        This method is only available on Windows and Linux and will raise an
        exception on other platforms.

        Returns:
            Always returns ``True`` for backwards compatibility.
        """
        return await self._backend.unpair()

    @property
    def is_connected(self) -> bool:
        """
        Check connection status between this client and the GATT server.

        Returns:
            Boolean representing connection status.

        """
        return self._backend.is_connected

    # GATT services methods

    async def get_services(self, **kwargs) -> BleakGATTServiceCollection:
        """Get all services registered for this GATT server.

        .. deprecated:: 0.17.0
            This method will be removed in a future version of Bleak.
            Use the :attr:`services` property instead.

        Returns:
           A :class:`bleak.backends.service.BleakGATTServiceCollection` with this device's services tree.

        """
        warn(
            "This method will be removed future version, use the services property instead.",
            FutureWarning,
            stacklevel=2,
        )
        return await self._backend.get_services(**kwargs)

    @property
    def services(self) -> BleakGATTServiceCollection:
        """
        Gets the collection of GATT services available on the device.

        The returned value is only valid as long as the device is connected.

        Raises:
            BleakError: if service discovery has not been performed yet during this connection.
        """
        if not self._backend.services:
            raise BleakError("Service Discovery has not been performed yet")

        return self._backend.services

    # I/O methods

    async def read_gatt_char(
        self,
        char_specifier: Union[BleakGATTCharacteristic, int, str, uuid.UUID],
        **kwargs,
    ) -> bytearray:
        """
        Perform read operation on the specified GATT characteristic.

        Args:
            char_specifier:
                The characteristic to read from, specified by either integer
                handle, UUID or directly by the BleakGATTCharacteristic object
                representing it.

        Returns:
            The read data.

        """
        return await self._backend.read_gatt_char(char_specifier, **kwargs)

    async def write_gatt_char(
        self,
        char_specifier: Union[BleakGATTCharacteristic, int, str, uuid.UUID],
        data: Buffer,
        response: bool = None,
    ) -> None:
        """
        Perform a write operation on the specified GATT characteristic.

        There are two possible kinds of writes. *Write with response* (sometimes
        called a *Request*) will write the data then wait for a response from
        the remote device. *Write without response* (sometimes called *Command*)
        will queue data to be written and return immediately.

        Each characteristic may support one kind or the other or both or neither.
        Consult the device's documentation or inspect the properties of the
        characteristic to find out which kind of writes are supported.

        .. tip:: Explicit is better than implicit. Best practice is to always
            include an explicit ``response=True`` or ``response=False``
            when calling this method.

        Args:
            char_specifier:
                The characteristic to write to, specified by either integer
                handle, UUID or directly by the :class:`~bleak.backends.characteristic.BleakGATTCharacteristic`
                object representing it. If a device has more than one characteristic
                with the same UUID, then attempting to use the UUID wil fail and
                a characteristic object must be used instead.
            data:
                The data to send. When a write-with-response operation is used,
                the length of the data is limited to 512 bytes. When a
                write-without-response operation is used, the length of the
                data is limited to :attr:`~bleak.backends.characteristic.BleakGATTCharacteristic.max_write_without_response_size`.
                Any type that supports the buffer protocol can be passed.
            response:
                If ``True``, a write-with-response operation will be used. If
                ``False``, a write-without-response operation will be used.
                If omitted or ``None``, the "best" operation will be used
                based on the reported properties of the characteristic.

        .. versionchanged:: 0.21
            The default behavior when ``response=`` is omitted was changed.

        Example::

            MY_CHAR_UUID = "1234"
            ...
            await client.write_gatt_char(MY_CHAR_UUID, b"\x00\x01\x02\x03", response=True)
        """
        if isinstance(char_specifier, BleakGATTCharacteristic):
            characteristic = char_specifier
        else:
            characteristic = self.services.get_characteristic(char_specifier)

        if not characteristic:
            raise BleakCharacteristicNotFoundError(char_specifier)

        if response is None:
            # if not specified, prefer write-with-response over write-without-
            # response if it is available since it is the more reliable write.
            response = "write" in characteristic.properties

        await self._backend.write_gatt_char(characteristic, data, response)

    async def start_notify(
        self,
        char_specifier: Union[BleakGATTCharacteristic, int, str, uuid.UUID],
        callback: Callable[
            [BleakGATTCharacteristic, bytearray], Union[None, Awaitable[None]]
        ],
        **kwargs,
    ) -> None:
        """
        Activate notifications/indications on a characteristic.

        Callbacks must accept two inputs. The first will be the characteristic
        and the second will be a ``bytearray`` containing the data received.

        .. code-block:: python

            def callback(sender: BleakGATTCharacteristic, data: bytearray):
                print(f"{sender}: {data}")

            client.start_notify(char_uuid, callback)

        Args:
            char_specifier:
                The characteristic to activate notifications/indications on a
                characteristic, specified by either integer handle,
                UUID or directly by the BleakGATTCharacteristic object representing it.
            callback:
                The function to be called on notification. Can be regular
                function or async function.


        .. versionchanged:: 0.18
            The first argument of the callback is now a :class:`BleakGATTCharacteristic`
            instead of an ``int``.
        """
        if not self.is_connected:
            raise BleakError("Not connected")

        if not isinstance(char_specifier, BleakGATTCharacteristic):
            characteristic = self.services.get_characteristic(char_specifier)
        else:
            characteristic = char_specifier

        if not characteristic:
            raise BleakCharacteristicNotFoundError(char_specifier)

        if inspect.iscoroutinefunction(callback):

            def wrapped_callback(data: bytearray) -> None:
                task = asyncio.create_task(callback(characteristic, data))
                _background_tasks.add(task)
                task.add_done_callback(_background_tasks.discard)

        else:
            wrapped_callback = functools.partial(callback, characteristic)

        await self._backend.start_notify(characteristic, wrapped_callback, **kwargs)

    async def stop_notify(
        self, char_specifier: Union[BleakGATTCharacteristic, int, str, uuid.UUID]
    ) -> None:
        """
        Deactivate notification/indication on a specified characteristic.

        Args:
            char_specifier:
                The characteristic to deactivate notification/indication on,
                specified by either integer handle, UUID or directly by the
                BleakGATTCharacteristic object representing it.

        .. tip:: Notifications are stopped automatically on disconnect, so this
            method does not need to be called unless notifications need to be
            stopped some time before the device disconnects.
        """
        await self._backend.stop_notify(char_specifier)

    async def read_gatt_descriptor(self, handle: int, **kwargs) -> bytearray:
        """
        Perform read operation on the specified GATT descriptor.

        Args:
            handle: The handle of the descriptor to read from.

        Returns:
            The read data.

        """
        return await self._backend.read_gatt_descriptor(handle, **kwargs)

    async def write_gatt_descriptor(self, handle: int, data: Buffer) -> None:
        """
        Perform a write operation on the specified GATT descriptor.

        Args:
            handle:
                The handle of the descriptor to read from.
            data:
                The data to send.

        """
        await self._backend.write_gatt_descriptor(handle, data)


# for backward compatibility
def discover(*args, **kwargs):
    """
    .. deprecated:: 0.17.0
        This method will be removed in a future version of Bleak.
        Use :meth:`BleakScanner.discover` instead.
    """
    warn(
        "The discover function will removed in a future version, use BleakScanner.discover instead.",
        FutureWarning,
        stacklevel=2,
    )
    return BleakScanner.discover(*args, **kwargs)


def cli() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Perform Bluetooth Low Energy device scan"
    )
    parser.add_argument("-i", dest="adapter", default=None, help="HCI device")
    parser.add_argument(
        "-t", dest="timeout", type=int, default=5, help="Duration to scan for"
    )
    args = parser.parse_args()

    out = asyncio.run(discover(adapter=args.adapter, timeout=float(args.timeout)))
    for o in out:
        print(str(o))


if __name__ == "__main__":
    cli()
