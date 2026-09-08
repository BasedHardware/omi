"""sdks/python/omi/bluetooth.py — omi-scan CLI with --json and --timeout."""

import argparse
import asyncio
import json
import math
import sys
from typing import Any, Callable, List, Optional

from bleak import BleakScanner, BleakClient

# Re-export for callers that want the default Omi audio stream UUID.
from .constants import AUDIO_DATA_UUID  # noqa: F401


def scan_devices(timeout: Optional[float] = None) -> List[Any]:
    """Run a Bleak discovery, optionally bounded by ``timeout`` seconds.

    Kept as a thin seam so entry-point tests can mock ``BleakScanner.discover``
    without a physical adapter.
    """
    if timeout is None:
        return asyncio.run(BleakScanner.discover())
    return asyncio.run(BleakScanner.discover(timeout=timeout))


def print_devices(timeout: Optional[float] = None) -> None:
    """Scan for and print all nearby Bluetooth devices.

    Preserves the historical callable behavior: numbered ``name [address]``
    lines on stdout. ``timeout`` is optional and forwarded to Bleak.
    """
    devices = scan_devices(timeout)
    for i, d in enumerate(devices):
        print(f"{i}. {d.name} [{d.address}]")


def devices_to_json(devices: List[Any]) -> str:
    """Serialize discovered devices as a JSON array of ``{"name", "id"}`` objects."""
    return json.dumps([{"name": d.name, "id": d.address} for d in devices])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="omi-scan",
        description="Scan for nearby Bluetooth devices using the Omi Python SDK.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help='Emit results as a JSON array of {"name", "id"} objects.',
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=None,
        metavar="SECONDS",
        help="Discovery timeout in seconds; must be finite and positive. "
        "Defaults to Bleak's built-in timeout.",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Console entry point for ``omi-scan`` (see pyproject ``[project.scripts]``).

    Returns a process exit code: 0 on success, 1 on adapter failure, 2 on
    invalid arguments (argparse default).
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.timeout is not None and not (math.isfinite(args.timeout) and args.timeout > 0):
        parser.error(
            f"--timeout must be a finite, positive number of seconds (got {args.timeout!r})"
        )

    try:
        devices = scan_devices(args.timeout)
    except Exception as exc:  # Bleak raises on missing/broken adapters
        print(f"omi-scan: error: Bluetooth scan failed: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(devices_to_json(devices))
    else:
        for i, d in enumerate(devices):
            print(f"{i}. {d.name} [{d.address}]")
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
