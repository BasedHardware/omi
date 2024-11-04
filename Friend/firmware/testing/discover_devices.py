import asyncio
from bleak import BleakScanner
from typing import Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

FRIEND_NAME = "Friend"
FRIEND_SERVICE_UUID = "19B10000-E8F2-537E-4F6C-D104768A1214"

async def find_friend_device(timeout: int = 5) -> Optional[str]:
    """Specifically scan for Friend devices."""
    logger.info(f"Scanning for {FRIEND_NAME} devices...")

    try:
        devices = await BleakScanner.discover(
            timeout=timeout,
            return_adv=True,
            service_uuids=[FRIEND_SERVICE_UUID]
        )

        for d, adv_data in devices.values():
            logger.debug(f"Found device: {d.name} ({d.address})")

            if d.name and FRIEND_NAME in d.name:
                logger.info("\nFound Friend Device!")
                logger.info("─" * 40)
                logger.info(f"Name: {d.name}")
                logger.info(f"Address: {d.address}")
                logger.info(f"RSSI: {adv_data.rssi}dBm")
                logger.info("\nServices:")
                for uuid in adv_data.service_uuids:
                    logger.info(f"  • {uuid}")
                logger.info("─" * 40)
                return d.address

        logger.warning(f"No {FRIEND_NAME} devices found")
        return None

    except Exception as e:
        logger.error(f"Error during device discovery: {e}")
        return None

async def scan_all_devices(timeout: int = 5):
    """Scan and display all available BLE devices"""
    logger.info("Scanning for all BLE devices...")

    try:
        devices = await BleakScanner.discover(
            timeout=timeout,
            return_adv=True
        )

        if not devices:
            logger.info("No BLE devices found")
            return

        logger.info("\nDiscovered Devices:")
        for d, adv_data in devices.values():
            logger.info("─" * 40)
            logger.info(f"Name: {d.name or 'Unknown'}")
            logger.info(f"Address: {d.address}")
            logger.info(f"RSSI: {adv_data.rssi}dBm")
            if adv_data.service_uuids:
                logger.info("\nServices:")
                for uuid in adv_data.service_uuids:
                    logger.info(f"  • {uuid}")
            logger.info("─" * 40)

    except Exception as e:
        logger.error(f"Error during device discovery: {e}")

async def main():
    """Main function with menu for different scanning options"""
    while True:
        print("\nBLE Scanner Menu:")
        print("1. Find Friend device")
        print("2. Scan all BLE devices")
        print("3. Exit")

        choice = input("Select an option (1-3): ")

        if choice == "1":
            await find_friend_device()
        elif choice == "2":
            await scan_all_devices()
        elif choice == "3":
            print("Exiting...")
            break
        else:
            print("Invalid choice. Please select 1-3")

if __name__ == "__main__":
    asyncio.run(main())
