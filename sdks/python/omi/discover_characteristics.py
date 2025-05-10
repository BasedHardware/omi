import asyncio
from bleak import BleakClient

OMI_MAC = "7F52EC55-50C9-D1B9-E8D7-19B83217C97D"  # Replace with your actual MAC

async def main():
    async with BleakClient(OMI_MAC) as client:
        services = client.services
        print("Listing all services and characteristics...\n")

        for service in services:
            print(f"[Service] {service.uuid} - {service.description}")
            for char in service.characteristics:
                print(f"  [Characteristic] {char.uuid} - {char.description}")
                print(f"    Properties: {char.properties}")
                if "notify" in char.properties:
                    print("    ✅ Notifiable (can stream data)")

asyncio.run(main())
