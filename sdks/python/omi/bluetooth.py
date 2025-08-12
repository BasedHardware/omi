import asyncio
from typing import Callable, Any
from bleak import BleakScanner, BleakClient

def print_devices() -> None:
    """Scan for and print all nearby Bluetooth devices."""
    devices = asyncio.run(BleakScanner.discover())
    for i, d in enumerate(devices):
        print(f"{i}. {d.name} [{d.address}]")

async def listen_to_omi(
    mac_address: str, 
    char_uuid: str, 
    data_handler: Callable[[Any, bytes], None]
) -> None:
    """
    Connect to Omi device and listen for audio data.
    
    Args:
        mac_address: Bluetooth MAC address of the Omi device
        char_uuid: UUID of the audio characteristic
        data_handler: Callback function to handle incoming audio data
    """
    async with BleakClient(mac_address) as client:
        print(f"Connected to {mac_address}")
        await client.start_notify(char_uuid, data_handler)
        print("Listening for data...")
        await asyncio.sleep(99999)
