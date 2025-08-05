import asyncio
import contextlib
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


async def _get_bluetoothctl_version() -> Optional[re.Match]:
    """Get the version of bluetoothctl."""
    with contextlib.suppress(Exception):
        proc = await asyncio.create_subprocess_exec(
            "bluetoothctl", "--version", stdout=asyncio.subprocess.PIPE
        )
        out = await proc.stdout.read()
        version = re.search(b"(\\d+).(\\d+)", out.strip(b"'"))
        await proc.wait()
        return version
    return None


class BlueZFeatures:
    """Check which features are supported by the BlueZ backend."""

    checked_bluez_version = False
    supported_version = True
    can_write_without_response = True
    write_without_response_workaround_needed = False
    hides_battery_characteristic = True
    hides_device_name_characteristic = True
    _check_bluez_event: Optional[asyncio.Event] = None

    @classmethod
    async def check_bluez_version(cls) -> None:
        """Check the bluez version."""
        if cls._check_bluez_event:
            # If there is already a check in progress
            # it wins, wait for it instead
            await cls._check_bluez_event.wait()
            return
        cls._check_bluez_event = asyncio.Event()
        version_output = await _get_bluetoothctl_version()
        if version_output:
            major, minor = tuple(map(int, version_output.groups()))
            cls.supported_version = major == 5 and minor >= 34
            cls.can_write_without_response = major == 5 and minor >= 46
            cls.write_without_response_workaround_needed = not (
                major == 5 and minor >= 51
            )
            cls.hides_battery_characteristic = major == 5 and minor >= 48 and minor < 55
            cls.hides_device_name_characteristic = major == 5 and minor >= 48
        else:
            # Its possible they may be running inside a container where
            # bluetoothctl is not available and they only have access to the
            # BlueZ D-Bus API.
            logging.warning(
                "Could not determine BlueZ version, bluetoothctl not available, assuming 5.51+"
            )

        cls._check_bluez_event.set()
        cls.checked_bluez_version = True
