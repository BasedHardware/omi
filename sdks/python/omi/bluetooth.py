import argparse
import asyncio
import json
import math
import sys
from typing import Any, Callable, Optional

from bleak import BleakClient, BleakScanner

# Re-export for callers that want the default Omi audio stream UUID.
from .constants import AUDIO_DATA_UUID  # noqa: F401


def _positive_timeout(value: str) -> float:
    """Parse a finite, positive scan timeout for the command line."""
    try:
        timeout = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("timeout must be a number") from exc
    if not math.isfinite(timeout) or timeout <= 0:
        raise argparse.ArgumentTypeError("timeout must be finite and greater than zero")
    return timeout


def _discover(timeout: Optional[float]) -> Any:
    """Run a discovery, forwarding ``timeout`` only when one was requested.

    ``None`` calls ``BleakScanner.discover()`` exactly as before, keeping the
    library's own default scan window.
    """
    if timeout is None:
        return asyncio.run(BleakScanner.discover())
    return asyncio.run(BleakScanner.discover(timeout=timeout))


def print_devices(json_output: bool = False, timeout: Optional[float] = None) -> None:
    """Scan for nearby Bluetooth devices and print them in the requested format.

    The human-readable listing is unchanged. ``json_output`` prints a single
    JSON array of ``{"name", "id"}`` objects, where ``id`` is the device's
    Bluetooth address.
    """
    devices = _discover(timeout)
    if json_output:
        print(json.dumps([{"name": d.name, "id": d.address} for d in devices]))
        return

    for i, d in enumerate(devices):
        print(f"{i}. {d.name} [{d.address}]")


def main() -> int:
    """Run the ``omi-scan`` command-line interface.

    Returns the process status: ``0`` on success, ``1`` when the scan fails,
    ``2`` on invalid arguments (argparse). Diagnostics go to stderr so the
    ``--json`` stdout stays parseable.
    """
    parser = argparse.ArgumentParser(
        description="Scan for nearby Omi Bluetooth devices"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help='print a JSON array of {"name", "id"} objects',
    )
    parser.add_argument(
        "--timeout",
        type=_positive_timeout,
        default=None,
        help="scan duration in seconds (default: Bleak's own timeout)",
    )
    args = parser.parse_args()

    try:
        print_devices(json_output=args.json_output, timeout=args.timeout)
    except Exception as exc:  # adapter missing, powered off, or permission denied
        print(f"omi-scan: error: Bluetooth scan failed: {exc}", file=sys.stderr)
        return 1
    return 0


async def listen_to_omi(
    mac_address: str,
    char_uuid: str,
    data_handler: Callable[[Any, bytes], None],
) -> None:
    """
    Connect to Omi device and listen for audio data.

    Args:
        mac_address: Bluetooth MAC address of the Omi device
        char_uuid: UUID of the audio characteristic (use AUDIO_DATA_UUID)
        data_handler: Callback function to handle incoming audio data
    """
    async with BleakClient(mac_address) as client:
        print(f"Connected to {mac_address}")
        await client.start_notify(char_uuid, data_handler)
        print("Listening for data...")
        await asyncio.sleep(99999)
