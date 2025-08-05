import abc
import asyncio
import inspect
import os
import platform
from typing import (
    Any,
    Callable,
    Coroutine,
    Dict,
    Hashable,
    List,
    NamedTuple,
    Optional,
    Set,
    Tuple,
    Type,
)

from ..exc import BleakError
from .device import BLEDevice

# prevent tasks from being garbage collected
_background_tasks: Set[asyncio.Task] = set()


class AdvertisementData(NamedTuple):
    """
    Wrapper around the advertisement data that each platform returns upon discovery
    """

    local_name: Optional[str]
    """
    The local name of the device or ``None`` if not included in advertising data.
    """

    manufacturer_data: Dict[int, bytes]
    """
    Dictionary of manufacturer data in bytes from the received advertisement data or empty dict if not present.

    The keys are Bluetooth SIG assigned Company Identifiers and the values are bytes.

    https://www.bluetooth.com/specifications/assigned-numbers/company-identifiers/
    """

    service_data: Dict[str, bytes]
    """
    Dictionary of service data from the received advertisement data or empty dict if not present.
    """

    service_uuids: List[str]
    """
    List of service UUIDs from the received advertisement data or empty list if not present.
    """

    tx_power: Optional[int]
    """
    TX Power Level of the remote device from the received advertising data or ``None`` if not present.

    .. versionadded:: 0.17
    """

    rssi: int
    """
    The Radio Receive Signal Strength (RSSI) in dBm.

    .. versionadded:: 0.19
    """

    platform_data: Tuple
    """
    Tuple of platform specific data.

    This is not a stable API. The actual values may change between releases.
    """

    def __repr__(self) -> str:
        kwargs = []
        if self.local_name:
            kwargs.append(f"local_name={repr(self.local_name)}")
        if self.manufacturer_data:
            kwargs.append(f"manufacturer_data={repr(self.manufacturer_data)}")
        if self.service_data:
            kwargs.append(f"service_data={repr(self.service_data)}")
        if self.service_uuids:
            kwargs.append(f"service_uuids={repr(self.service_uuids)}")
        if self.tx_power is not None:
            kwargs.append(f"tx_power={repr(self.tx_power)}")
        kwargs.append(f"rssi={repr(self.rssi)}")
        return f"AdvertisementData({', '.join(kwargs)})"


AdvertisementDataCallback = Callable[
    [BLEDevice, AdvertisementData],
    Optional[Coroutine[Any, Any, None]],
]
"""
Type alias for callback called when advertisement data is received.
"""

AdvertisementDataFilter = Callable[
    [BLEDevice, AdvertisementData],
    bool,
]
"""
Type alias for an advertisement data filter function.

Implementations should return ``True`` for matches, otherwise ``False``.
"""


class BaseBleakScanner(abc.ABC):
    """
    Interface for Bleak Bluetooth LE Scanners

    Args:
        detection_callback:
            Optional function that will be called each time a device is
            discovered or advertising data has changed.
        service_uuids:
            Optional list of service UUIDs to filter on. Only advertisements
            containing this advertising data will be received.
    """

    seen_devices: Dict[str, Tuple[BLEDevice, AdvertisementData]]
    """
    Map of device identifier to BLEDevice and most recent advertisement data.

    This map must be cleared when scanning starts.
    """

    def __init__(
        self,
        detection_callback: Optional[AdvertisementDataCallback],
        service_uuids: Optional[List[str]],
    ):
        super(BaseBleakScanner, self).__init__()

        self._ad_callbacks: Dict[
            Hashable, Callable[[BLEDevice, AdvertisementData], None]
        ] = {}
        """
        List of callbacks to call when an advertisement is received.
        """

        if detection_callback is not None:
            self.register_detection_callback(detection_callback)

        self._service_uuids: Optional[List[str]] = (
            [u.lower() for u in service_uuids] if service_uuids is not None else None
        )

        self.seen_devices = {}

    def register_detection_callback(
        self, callback: Optional[AdvertisementDataCallback]
    ) -> Callable[[], None]:
        """
        Register a callback that is called when an advertisement event from the
        OS is received.

        The ``callback`` is a function or coroutine that takes two arguments: :class:`BLEDevice`
        and :class:`AdvertisementData`.

        Args:
            callback: A function, coroutine or ``None``.

        Returns:
            A method that can be called to unregister the callback.
        """
        error_text = "callback must be callable with 2 parameters"

        if not callable(callback):
            raise TypeError(error_text)

        handler_signature = inspect.signature(callback)

        if len(handler_signature.parameters) != 2:
            raise TypeError(error_text)

        if inspect.iscoroutinefunction(callback):

            def detection_callback(s: BLEDevice, d: AdvertisementData) -> None:
                task = asyncio.create_task(callback(s, d))
                _background_tasks.add(task)
                task.add_done_callback(_background_tasks.discard)

        else:
            detection_callback = callback

        token = object()

        self._ad_callbacks[token] = detection_callback

        def remove() -> None:
            self._ad_callbacks.pop(token, None)

        return remove

    def is_allowed_uuid(self, service_uuids: Optional[List[str]]) -> bool:
        """
        Check if the advertisement data contains any of the service UUIDs
        matching the filter. If no filter is set, this will always return
        ``True``.

        Args:
            service_uuids: The service UUIDs from the advertisement data.

        Returns:
            ``True`` if the advertisement data should be allowed or ``False``
             if the advertisement data should be filtered out.
        """
        # Backends will make best effort to filter out advertisements that
        # don't match the service UUIDs, but if other apps are scanning at the
        # same time or something like that, we may still receive advertisements
        # that don't match. So we need to do more filtering here to get the
        # expected behavior.

        if not self._service_uuids:
            # if there is no filter, everything is allowed
            return True

        if not service_uuids:
            # if there is a filter the advertisement data doesn't contain any
            # service UUIDs, filter it out
            return False

        for uuid in service_uuids:
            if uuid in self._service_uuids:
                # match was found, keep this advertisement
                return True

        # there were no matching service uuids, filter this one out
        return False

    def call_detection_callbacks(
        self, device: BLEDevice, advertisement_data: AdvertisementData
    ) -> None:
        """
        Calls all registered detection callbacks.

        Backend implementations should call this method when an advertisement
        event is received from the OS.
        """

        for callback in self._ad_callbacks.values():
            callback(device, advertisement_data)

    def create_or_update_device(
        self, address: str, name: str, details: Any, adv: AdvertisementData
    ) -> BLEDevice:
        """
        Creates or updates a device in :attr:`seen_devices`.

        Args:
            address: The Bluetooth address of the device (UUID on macOS).
            name: The OS display name for the device.
            details: The platform-specific handle for the device.
            adv: The most recent advertisement data received.

        Returns:
            The updated device.
        """

        # for backwards compatibility, see https://github.com/hbldh/bleak/issues/1025
        metadata = dict(
            uuids=adv.service_uuids,
            manufacturer_data=adv.manufacturer_data,
        )

        try:
            device, _ = self.seen_devices[address]

            device.name = name
            device._rssi = adv.rssi
            device._metadata = metadata
        except KeyError:
            device = BLEDevice(
                address,
                name,
                details,
                adv.rssi,
                **metadata,
            )

        self.seen_devices[address] = (device, adv)

        return device

    @abc.abstractmethod
    async def start(self) -> None:
        """Start scanning for devices"""
        raise NotImplementedError()

    @abc.abstractmethod
    async def stop(self) -> None:
        """Stop scanning for devices"""
        raise NotImplementedError()

    @abc.abstractmethod
    def set_scanning_filter(self, **kwargs) -> None:
        """Set scanning filter for the BleakScanner.

        Args:
            **kwargs: The filter details. This will differ a lot between backend implementations.

        """
        raise NotImplementedError()


def get_platform_scanner_backend_type() -> Type[BaseBleakScanner]:
    """
    Gets the platform-specific :class:`BaseBleakScanner` type.
    """
    if os.environ.get("P4A_BOOTSTRAP") is not None:
        from bleak.backends.p4android.scanner import BleakScannerP4Android

        return BleakScannerP4Android

    if platform.system() == "Linux":
        from bleak.backends.bluezdbus.scanner import BleakScannerBlueZDBus

        return BleakScannerBlueZDBus

    if platform.system() == "Darwin":
        from bleak.backends.corebluetooth.scanner import BleakScannerCoreBluetooth

        return BleakScannerCoreBluetooth

    if platform.system() == "Windows":
        from bleak.backends.winrt.scanner import BleakScannerWinRT

        return BleakScannerWinRT

    raise BleakError(f"Unsupported platform: {platform.system()}")
