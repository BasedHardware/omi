import asyncio
from bleak import BleakScanner

async def main():
    print("Trying to trigger Bluetooth access prompt...")
    devices = await BleakScanner.discover(timeout=5.0)
    print(f"Found {len(devices)} devices.")

asyncio.run(main())
