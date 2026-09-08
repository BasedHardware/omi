import argparse
import asyncio
import json
import math
from typing import Any, Callable

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


def print_devices(json_output: bool = False, timeout: float = 5.0) -> None:
    """Scan for nearby Bluetooth devices and print them in the requested format."""
    devices = asyncio.run(BleakScanner.discover(timeout=timeout))
    if json_output:
        print(json.dumps([{"name": d.name, "address": d.address} for d in devices]))
        return

    for i, d in enumerate(devices):
        print(f"{i}. {d.name} [{d.address}]")


def main() -> None:
    """Run the ``omi-scan`` command-line interface."""
    parser = argparse.ArgumentParser(
        description="Scan for nearby Omi Bluetooth devices"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="print a JSON array instead of human-readable lines",
    )
    parser.add_argument(
        "--timeout",
        type=_positive_timeout,
        default=5.0,
        help="scan duration in seconds (default: 5)",
    )
    args = parser.parse_args()
    print_devices(json_output=args.json_output, timeout=args.timeout)


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
