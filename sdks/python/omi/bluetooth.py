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
    """
    disconnected_event = asyncio.Event()

    def _on_disconnect(_client: BleakClient) -> None:
        disconnected_event.set()

    try:
        client = BleakClient(mac_address, disconnected_callback=_on_disconnect)
    except TypeError:
        client = BleakClient(mac_address)
        if hasattr(client, "set_disconnected_callback"):
            client.set_disconnected_callback(_on_disconnect)

    async with client:
        print(f"Connected to {mac_address}")
        await client.start_notify(char_uuid, data_handler)
        print("Listening for data...")
        while not disconnected_event.is_set():
            disconnect_task = asyncio.create_task(disconnected_event.wait())
            sleep_task = asyncio.create_task(asyncio.sleep(99999))
            done, pending = await asyncio.wait(
                [disconnect_task, sleep_task],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for p in pending:
                p.cancel()
            for d in done:
                if d is sleep_task and d.exception():
                    raise d.exception()
        raise ConnectionError(f"Device {mac_address} disconnected")
