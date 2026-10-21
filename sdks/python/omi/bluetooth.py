import asyncio
from typing import Callable, Any
from bleak import BleakScanner, BleakClient

# Re-export for callers that want the default Omi audio stream UUID.
from .constants import AUDIO_DATA_UUID  # noqa: F401


def print_devices() -> None:
    """Scan for and print all nearby Bluetooth devices."""
    devices = asyncio.run(BleakScanner.discover())
    for i, d in enumerate(devices):
        print(f"{i}. {d.name} [{d.address}]")


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

    Raises:
        ConnectionError: if the device disconnects while listening.
    """
    disconnected = asyncio.Event()

    def _on_disconnect(_client: BleakClient) -> None:
        disconnected.set()

    async with BleakClient(mac_address, disconnected_callback=_on_disconnect) as client:
        print(f"Connected to {mac_address}")
        await client.start_notify(char_uuid, data_handler)
        print("Listening for data...")
        while not disconnected.is_set():
            await asyncio.sleep(1)
    raise ConnectionError(f"Device {mac_address} disconnected")
