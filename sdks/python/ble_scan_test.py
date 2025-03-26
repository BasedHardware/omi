import asyncio
from bleak import BleakScanner

async def main():
    print("Scanning for BLE devices...")
    devices = await BleakScanner.discover()
    for i, d in enumerate(devices):
        print(f"{i}. {d.name} [{d.address}]")

asyncio.run(main())
