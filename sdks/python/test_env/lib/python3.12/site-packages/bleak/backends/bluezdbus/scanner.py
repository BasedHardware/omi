import logging
from typing import Callable, Coroutine, Dict, List, Literal, Optional, TypedDict
from warnings import warn

from dbus_fast import Variant

from ...exc import BleakError
from ..scanner import AdvertisementData, AdvertisementDataCallback, BaseBleakScanner
from .advertisement_monitor import OrPatternLike
from .defs import Device1
from .manager import get_global_bluez_manager
from .utils import bdaddr_from_device_path

logger = logging.getLogger(__name__)


class BlueZDiscoveryFilters(TypedDict, total=False):
    """
    Dictionary of arguments for the ``org.bluez.Adapter1.SetDiscoveryFilter``
    D-Bus method.

    https://github.com/bluez/bluez/blob/master/doc/org.bluez.Adapter.rst#void-setdiscoveryfilterdict-filter
    """

    UUIDs: List[str]
    """
    Filter by service UUIDs, empty means match _any_ UUID.

    Normally, the ``service_uuids`` argument of :class:`bleak.BleakScanner`
    is used instead.
    """
    RSSI: int
    """
    RSSI threshold value.
    """
    Pathloss: int
    """
    Pathloss threshold value.
    """
    Transport: str
    """
    Transport parameter determines the type of scan.

    This should not be used since it is required to be set to ``"le"``.
    """
    DuplicateData: bool
    """
    Disables duplicate detection of advertisement data.

    This does not affect the ``Filter Duplicates`` parameter of the ``LE Set Scan Enable``
    HCI command to the Bluetooth adapter!

    Although the default value for BlueZ is ``True``, Bleak sets this to ``False`` by default.
    """
    Discoverable: bool
    """
    Make adapter discoverable while discovering,
    if the adapter is already discoverable setting
    this filter won't do anything.
    """
    Pattern: str
    """
    Discover devices where the pattern matches
    either the prefix of the address or
    device name which is convenient way to limited
    the number of device objects created during a
    discovery.
    """


class BlueZScannerArgs(TypedDict, total=False):
    """
    :class:`BleakScanner` args that are specific to the BlueZ backend.
    """

    filters: BlueZDiscoveryFilters
    """
    Filters to pass to the adapter SetDiscoveryFilter D-Bus method.

    Only used for active scanning.
    """

    or_patterns: List[OrPatternLike]
    """
    Or patterns to pass to the AdvertisementMonitor1 D-Bus interface.

    Only used for passive scanning.
    """


class BleakScannerBlueZDBus(BaseBleakScanner):
    """The native Linux Bleak BLE Scanner.

    For possible values for `filters`, see the parameters to the
    ``SetDiscoveryFilter`` method in the `BlueZ docs
    <https://github.com/bluez/bluez/blob/master/doc/org.bluez.Adapter.rst#void-setdiscoveryfilterdict-filter>`_

    Args:
        detection_callback:
            Optional function that will be called each time a device is
            discovered or advertising data has changed.
        service_uuids:
            Optional list of service UUIDs to filter on. Only advertisements
            containing this advertising data will be received. Specifying this
            also enables scanning while the screen is off on Android.
        scanning_mode:
            Set to ``"passive"`` to avoid the ``"active"`` scanning mode.
        **bluez:
            Dictionary of arguments specific to the BlueZ backend.
        **adapter (str):
            Bluetooth adapter to use for discovery.
    """

    def __init__(
        self,
        detection_callback: Optional[AdvertisementDataCallback],
        service_uuids: Optional[List[str]],
        scanning_mode: Literal["active", "passive"],
        *,
        bluez: BlueZScannerArgs,
        **kwargs,
    ):
        super(BleakScannerBlueZDBus, self).__init__(detection_callback, service_uuids)

        self._scanning_mode = scanning_mode

        # kwarg "device" is for backwards compatibility
        self._adapter: Optional[str] = kwargs.get("adapter", kwargs.get("device"))

        # callback from manager for stopping scanning if it has been started
        self._stop: Optional[Callable[[], Coroutine]] = None

        # Discovery filters

        self._filters: Dict[str, Variant] = {}

        self._filters["Transport"] = Variant("s", "le")
        self._filters["DuplicateData"] = Variant("b", False)

        if self._service_uuids:
            self._filters["UUIDs"] = Variant("as", self._service_uuids)

        filters = kwargs.get("filters")

        if filters is None:
            filters = bluez.get("filters")
        else:
            warn(
                "the 'filters' kwarg is deprecated, use 'bluez' kwarg instead",
                FutureWarning,
                stacklevel=2,
            )

        if filters is not None:
            self.set_scanning_filter(filters=filters)

        self._or_patterns = bluez.get("or_patterns")

        if self._scanning_mode == "passive" and service_uuids:
            logger.warning(
                "service uuid filtering is not implemented for passive scanning, use bluez or_patterns as a workaround"
            )

        if self._scanning_mode == "passive" and not self._or_patterns:
            raise BleakError("passive scanning mode requires bluez or_patterns")

    async def start(self) -> None:
        manager = await get_global_bluez_manager()

        if self._adapter:
            adapter_path = f"/org/bluez/{self._adapter}"
        else:
            adapter_path = manager.get_default_adapter()

        self.seen_devices = {}

        if self._scanning_mode == "passive":
            self._stop = await manager.passive_scan(
                adapter_path,
                self._or_patterns,
                self._handle_advertising_data,
                self._handle_device_removed,
            )
        else:
            self._stop = await manager.active_scan(
                adapter_path,
                self._filters,
                self._handle_advertising_data,
                self._handle_device_removed,
            )

    async def stop(self) -> None:
        if self._stop:
            # avoid reentrancy
            stop, self._stop = self._stop, None

            await stop()

    def set_scanning_filter(self, **kwargs) -> None:
        """Sets OS level scanning filters for the BleakScanner.

        For possible values for `filters`, see the parameters to the
        ``SetDiscoveryFilter`` method in the `BlueZ docs
        <https://github.com/bluez/bluez/blob/master/doc/org.bluez.Adapter.rst#void-setdiscoveryfilterdict-filter>`_

        See variant types here: <https://python-dbus-next.readthedocs.io/en/latest/type-system/>

        Keyword Args:
            filters (dict): A dict of filters to be applied on discovery.

        """
        for k, v in kwargs.get("filters", {}).items():
            if k == "UUIDs":
                self._filters[k] = Variant("as", v)
            elif k == "RSSI":
                self._filters[k] = Variant("n", v)
            elif k == "Pathloss":
                self._filters[k] = Variant("n", v)
            elif k == "Transport":
                self._filters[k] = Variant("s", v)
            elif k == "DuplicateData":
                self._filters[k] = Variant("b", v)
            elif k == "Discoverable":
                self._filters[k] = Variant("b", v)
            elif k == "Pattern":
                self._filters[k] = Variant("s", v)
            else:
                logger.warning("Filter '%s' is not currently supported." % k)

    # Helper methods

    def _handle_advertising_data(self, path: str, props: Device1) -> None:
        """
        Handles advertising data received from the BlueZ manager instance.

        Args:
            path: The D-Bus object path of the device.
            props: The D-Bus object properties of the device.
        """
        _service_uuids = props.get("UUIDs", [])

        if not self.is_allowed_uuid(_service_uuids):
            return

        # Get all the information wanted to pack in the advertisement data
        _local_name = props.get("Name")
        _manufacturer_data = {
            k: bytes(v) for k, v in props.get("ManufacturerData", {}).items()
        }
        _service_data = {k: bytes(v) for k, v in props.get("ServiceData", {}).items()}

        # Get tx power data
        tx_power = props.get("TxPower")

        # Pack the advertisement data
        advertisement_data = AdvertisementData(
            local_name=_local_name,
            manufacturer_data=_manufacturer_data,
            service_data=_service_data,
            service_uuids=_service_uuids,
            tx_power=tx_power,
            rssi=props.get("RSSI", -127),
            platform_data=(path, props),
        )

        device = self.create_or_update_device(
            props["Address"],
            props["Alias"],
            {"path": path, "props": props},
            advertisement_data,
        )

        self.call_detection_callbacks(device, advertisement_data)

    def _handle_device_removed(self, device_path: str) -> None:
        """
        Handles a device being removed from BlueZ.
        """
        try:
            bdaddr = bdaddr_from_device_path(device_path)
            del self.seen_devices[bdaddr]
        except KeyError:
            # The device will not have been added to self.seen_devices if no
            # advertising data was received, so this is expected to happen
            # occasionally.
            pass
