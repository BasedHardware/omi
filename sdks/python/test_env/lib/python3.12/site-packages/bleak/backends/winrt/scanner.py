import asyncio
import logging
import sys
from typing import Dict, List, Literal, NamedTuple, Optional
from uuid import UUID

from .util import assert_mta

if sys.version_info >= (3, 12):
    from winrt.windows.devices.bluetooth.advertisement import (
        BluetoothLEAdvertisementReceivedEventArgs,
        BluetoothLEAdvertisementType,
        BluetoothLEAdvertisementWatcher,
        BluetoothLEAdvertisementWatcherStatus,
        BluetoothLEScanningMode,
    )
else:
    from bleak_winrt.windows.devices.bluetooth.advertisement import (
        BluetoothLEAdvertisementReceivedEventArgs,
        BluetoothLEAdvertisementType,
        BluetoothLEAdvertisementWatcher,
        BluetoothLEAdvertisementWatcherStatus,
        BluetoothLEScanningMode,
    )

from ...assigned_numbers import AdvertisementDataType
from ...exc import BleakError
from ...uuids import normalize_uuid_str
from ..scanner import AdvertisementData, AdvertisementDataCallback, BaseBleakScanner

logger = logging.getLogger(__name__)


def _format_bdaddr(a: int) -> str:
    return ":".join(f"{x:02X}" for x in a.to_bytes(6, byteorder="big"))


def _format_event_args(e: BluetoothLEAdvertisementReceivedEventArgs) -> str:
    try:
        return f"{_format_bdaddr(e.bluetooth_address)}: {e.advertisement.local_name}"
    except Exception:
        return _format_bdaddr(e.bluetooth_address)


class _RawAdvData(NamedTuple):
    """
    Platform-specific advertisement data.

    Windows does not combine advertising data with type SCAN_RSP with other
    advertising data like other platforms, so se have to do it ourselves.
    """

    adv: Optional[BluetoothLEAdvertisementReceivedEventArgs]
    """
    The advertisement data received from the BluetoothLEAdvertisementWatcher.Received event.
    """
    scan: Optional[BluetoothLEAdvertisementReceivedEventArgs]
    """
    The scan response for the same device as *adv*.
    """


class BleakScannerWinRT(BaseBleakScanner):
    """The native Windows Bleak BLE Scanner.

    Implemented using `Python/WinRT <https://github.com/Microsoft/xlang/tree/master/src/package/pywinrt/projection/>`_.

    Args:
        detection_callback:
            Optional function that will be called each time a device is
            discovered or advertising data has changed.
        service_uuids:
            Optional list of service UUIDs to filter on. Only advertisements
            containing this advertising data will be received.
        scanning_mode:
            Set to ``"passive"`` to avoid the ``"active"`` scanning mode.

    """

    def __init__(
        self,
        detection_callback: Optional[AdvertisementDataCallback],
        service_uuids: Optional[List[str]],
        scanning_mode: Literal["active", "passive"],
        **kwargs,
    ):
        super(BleakScannerWinRT, self).__init__(detection_callback, service_uuids)

        self.watcher: Optional[BluetoothLEAdvertisementWatcher] = None
        self._advertisement_pairs: Dict[int, _RawAdvData] = {}
        self._stopped_event = None

        # case insensitivity is for backwards compatibility on Windows only
        if scanning_mode.lower() == "passive":
            self._scanning_mode = BluetoothLEScanningMode.PASSIVE
        else:
            self._scanning_mode = BluetoothLEScanningMode.ACTIVE

        # Unfortunately, due to the way Windows handles filtering, we can't
        # make use of the service_uuids filter here. If we did we would only
        # get the advertisement data or the scan data, but not both, so would
        # miss out on other essential data. Advanced users can pass their own
        # filters though if they want to.
        self._signal_strength_filter = kwargs.get("SignalStrengthFilter", None)
        self._advertisement_filter = kwargs.get("AdvertisementFilter", None)

        self._received_token = None
        self._stopped_token = None

    def _received_handler(
        self,
        sender: BluetoothLEAdvertisementWatcher,
        event_args: BluetoothLEAdvertisementReceivedEventArgs,
    ):
        """Callback for AdvertisementWatcher.Received"""
        # TODO: Cannot check for if sender == self.watcher in winrt?
        logger.debug("Received %s.", _format_event_args(event_args))

        # REVISIT: if scanning filters with BluetoothSignalStrengthFilter.OutOfRangeTimeout
        # are in place, an RSSI of -127 means that the device has gone out of range and should
        # be removed from the list of seen devices instead of processing the advertisement data.
        # https://learn.microsoft.com/en-us/uwp/api/windows.devices.bluetooth.bluetoothsignalstrengthfilter.outofrangetimeout

        bdaddr = _format_bdaddr(event_args.bluetooth_address)

        # Unlike other platforms, Windows does not combine advertising data for
        # us (regular advertisement + scan response) so we have to do it manually.

        # get the previous advertising data/scan response pair or start a new one
        raw_data = self._advertisement_pairs.get(bdaddr, _RawAdvData(None, None))

        # update the advertising data depending on the advertising data type
        if event_args.advertisement_type == BluetoothLEAdvertisementType.SCAN_RESPONSE:
            raw_data = _RawAdvData(raw_data.adv, event_args)
        else:
            raw_data = _RawAdvData(event_args, raw_data.scan)

        self._advertisement_pairs[bdaddr] = raw_data

        uuids = []
        mfg_data = {}
        service_data = {}
        local_name = None
        tx_power = None

        for args in filter(lambda d: d is not None, raw_data):
            for u in args.advertisement.service_uuids:
                uuids.append(str(u))

            for m in args.advertisement.manufacturer_data:
                mfg_data[m.company_id] = bytes(m.data)

            # local name is empty string rather than None if not present
            if args.advertisement.local_name:
                local_name = args.advertisement.local_name

            try:
                if args.transmit_power_level_in_d_bm is not None:
                    tx_power = args.transmit_power_level_in_d_bm
            except AttributeError:
                # the transmit_power_level_in_d_bm property was introduce in
                # Windows build 19041 so we have a fallback for older versions
                for section in args.advertisement.get_sections_by_type(
                    AdvertisementDataType.TX_POWER_LEVEL
                ):
                    tx_power = bytes(section.data)[0]

            # Decode service data
            for section in args.advertisement.get_sections_by_type(
                AdvertisementDataType.SERVICE_DATA_UUID16
            ):
                data = bytes(section.data)
                service_data[normalize_uuid_str(f"{data[1]:02x}{data[0]:02x}")] = data[
                    2:
                ]
            for section in args.advertisement.get_sections_by_type(
                AdvertisementDataType.SERVICE_DATA_UUID32
            ):
                data = bytes(section.data)
                service_data[
                    normalize_uuid_str(
                        f"{data[3]:02x}{data[2]:02x}{data[1]:02x}{data[0]:02x}"
                    )
                ] = data[4:]
            for section in args.advertisement.get_sections_by_type(
                AdvertisementDataType.SERVICE_DATA_UUID128
            ):
                data = bytes(section.data)
                service_data[str(UUID(bytes=bytes(data[15::-1])))] = data[16:]

        if not self.is_allowed_uuid(uuids):
            return

        # Use the BLEDevice to populate all the fields for the advertisement data to return
        advertisement_data = AdvertisementData(
            local_name=local_name,
            manufacturer_data=mfg_data,
            service_data=service_data,
            service_uuids=uuids,
            tx_power=tx_power,
            rssi=event_args.raw_signal_strength_in_d_bm,
            platform_data=(sender, raw_data),
        )

        device = self.create_or_update_device(
            bdaddr, local_name, raw_data, advertisement_data
        )

        self.call_detection_callbacks(device, advertisement_data)

    def _stopped_handler(self, sender, e):
        logger.debug(
            "%s devices found. Watcher status: %r.",
            len(self.seen_devices),
            sender.status,
        )
        self._stopped_event.set()

    async def start(self) -> None:
        if self.watcher:
            raise BleakError("Scanner already started")

        # Callbacks for WinRT async methods will never happen in STA mode if
        # there is nothing pumping a Windows message loop.
        await assert_mta()

        # start with fresh list of discovered devices
        self.seen_devices = {}
        self._advertisement_pairs.clear()

        self.watcher = BluetoothLEAdvertisementWatcher()
        self.watcher.scanning_mode = self._scanning_mode

        event_loop = asyncio.get_running_loop()
        self._stopped_event = asyncio.Event()

        self._received_token = self.watcher.add_received(
            lambda s, e: event_loop.call_soon_threadsafe(self._received_handler, s, e)
        )
        self._stopped_token = self.watcher.add_stopped(
            lambda s, e: event_loop.call_soon_threadsafe(self._stopped_handler, s, e)
        )

        if self._signal_strength_filter is not None:
            self.watcher.signal_strength_filter = self._signal_strength_filter
        if self._advertisement_filter is not None:
            self.watcher.advertisement_filter = self._advertisement_filter

        self.watcher.start()

        # no events for status changes, so we have to poll :-(
        while self.watcher.status == BluetoothLEAdvertisementWatcherStatus.CREATED:
            await asyncio.sleep(0.01)

        if self.watcher.status == BluetoothLEAdvertisementWatcherStatus.ABORTED:
            raise BleakError("Failed to start scanner. Is Bluetooth turned on?")

        if self.watcher.status != BluetoothLEAdvertisementWatcherStatus.STARTED:
            raise BleakError(f"Unexpected watcher status: {self.watcher.status.name}")

    async def stop(self) -> None:
        self.watcher.stop()

        if self.watcher.status == BluetoothLEAdvertisementWatcherStatus.STOPPING:
            await self._stopped_event.wait()
        else:
            logger.debug(
                "skipping waiting for stop because status is %r",
                self.watcher.status,
            )

        try:
            self.watcher.remove_received(self._received_token)
            self.watcher.remove_stopped(self._stopped_token)
        except Exception as e:
            logger.debug("Could not remove event handlers: %s", e)

        self._stopped_token = None
        self._received_token = None

        self.watcher = None

    def set_scanning_filter(self, **kwargs) -> None:
        """Set a scanning filter for the BleakScanner.

        Keyword Args:
          SignalStrengthFilter (``Windows.Devices.Bluetooth.BluetoothSignalStrengthFilter``): A
            BluetoothSignalStrengthFilter object used for configuration of Bluetooth
            LE advertisement filtering that uses signal strength-based filtering.
          AdvertisementFilter (Windows.Devices.Bluetooth.Advertisement.BluetoothLEAdvertisementFilter): A
            BluetoothLEAdvertisementFilter object used for configuration of Bluetooth LE
            advertisement filtering that uses payload section-based filtering.

        """
        if "SignalStrengthFilter" in kwargs:
            # TODO: Handle SignalStrengthFilter parameters
            self._signal_strength_filter = kwargs["SignalStrengthFilter"]
        if "AdvertisementFilter" in kwargs:
            # TODO: Handle AdvertisementFilter parameters
            self._advertisement_filter = kwargs["AdvertisementFilter"]
