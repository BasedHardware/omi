import asyncio
import argparse
import logging
import sys
import time
import subprocess # Added for running external commands
from pathlib import Path
from bleak import BleakClient, BleakScanner
from bleak.exc import BleakError

# --- Constants ---
DFU_SERVICE_UUID = "0000fe59-0000-1000-8000-00805f9b34fb" # Nordic Secure DFU Service

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
# Set nordicsemi logger level
logging.getLogger('nordicsemi').setLevel(logging.WARNING)

# --- Main DFU Logic (using adafruit-nrfutil) ---
async def perform_dfu(device_address: str, zip_file_path: str):
    logger.info(f"Starting DFU process for {device_address} with {zip_file_path} using adafruit-nrfutil")

    # Construct the command for adafruit-nrfutil
    # We assume nRF53 family based on the initial request.
    # Adjust '-ic' if your specific NRF53 variant needs a different identifier
    # or if adafruit-nrfutil handles NRF53 differently.
    # We use '-a' for the address. The tool should handle the connection.
    command = [
        "adafruit-nrfutil",
        "dfu",
        "ble",
        "-ic", "NRF53", # Specify chip family
        "-pkg", zip_file_path,
        "-a", device_address,
        # Add '-v' for verbose nrfutil output if script's verbose flag is set
        # We'll handle this based on the logger level later
    ]

    # Add verbose flags to nrfutil if script is run with -v
    if logger.getEffectiveLevel() <= logging.DEBUG:
        command.append("-v") # nrfutil's own verbose flag
        command.append("-v") # Often requires -v -v or -v -v -v for max detail
        command.append("-v")

    logger.info(f"Executing command: {' '.join(command)}")

    try:
        # Run the command
        # Using subprocess.run which is simpler for commands that finish
        # We capture output to log it.
        result = subprocess.run(command, capture_output=True, text=True, check=False) # check=False allows us to handle errors

        # Log stdout and stderr
        if result.stdout:
            logger.info("adafruit-nrfutil stdout:")
            for line in result.stdout.strip().split('\n'):
                logger.info(f"  {line}")
        if result.stderr:
            # nrfutil often prints progress to stderr, so log as INFO unless error code is non-zero
            log_level = logging.ERROR if result.returncode != 0 else logging.INFO
            logger.log(log_level, "adafruit-nrfutil stderr:")
            for line in result.stderr.strip().split('\n'):
                logger.log(log_level, f"  {line}")

        # Check return code
        if result.returncode == 0:
            logger.info("adafruit-nrfutil DFU process completed successfully.")
        else:
            logger.error(f"adafruit-nrfutil failed with exit code {result.returncode}")

    except FileNotFoundError:
        logger.error("Error: 'adafruit-nrfutil' command not found.")
        logger.error("Please ensure it's installed and in your system's PATH or virtual environment.")
    except Exception as e:
        logger.error(f"An unexpected error occurred while running adafruit-nrfutil: {e}")
        logger.exception("Detailed traceback:")

    # Remove the old implementation based on nordicsemi library
    # backend = None
    # scanner = BleakScanner()
    # try:
    #     logger.info(f"Scanning for device {device_address}...")
    #     device = await scanner.find_device_by_address(device_address, timeout=20.0)
    #     if not device:
    #         logger.error(f"Device with address {device_address} not found after 20 seconds.")
    #         return
    #
    #     logger.info(f"Found device: {device.name} ({device.address})")
    #
    #     # Nordic DFU library expects the backend instance
    #     backend = DfuTransportBle(target_device_identifier=device.address)
    #
    #     # Configure DFU options
    #     # Note: nordicsemi-dfu logs progress internally
    #     dfu_proc = Dfu(zip_file_path=zip_file_path, dfu_transport=backend)
    #
    #     logger.info("Initiating DFU...")
    #     dfu_proc.dfu_send_images()
    #     logger.info("DFU process completed successfully.")
    #
    # except BleakError as e:
    #     logger.error(f"BLE Error: {e}")
    # except Exception as e:
    #     logger.error(f"An unexpected error occurred during DFU: {e}")
    #     logger.exception("Detailed traceback:") # Log full traceback for debugging
    # finally:
    #     if backend:
    #         logger.debug("Closing DFU transport backend.")
    #         # The nordicsemi library handles BLE disconnection internally within DfuTransportBle
    #         # No explicit client.disconnect() needed here unless we manage the client separately
    #         pass # backend.close() might be needed in some backend implementations or future versions

    pass # Replace with actual DFU implementation

# --- Argument Parser ---
def parse_args():
    parser = argparse.ArgumentParser(description="Perform Nordic Secure DFU over BLE.")
    parser.add_argument("zip_file", help="Path to the DFU package (.zip file).", type=Path)
    parser.add_argument("-a", "--address", help="MAC address of the target BLE device.", required=True)
    # parser.add_argument("-n", "--name", help="Name of the target BLE device (alternative to address).") # TODO: Add name-based discovery
    parser.add_argument("-v", "--verbose", help="Enable debug logging.", action="store_true")
    return parser.parse_args()

# --- Main Execution ---
async def main():
    args = parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.setLevel(logging.DEBUG)
        logging.getLogger('nordicsemi').setLevel(logging.INFO) # More verbose DFU logs

    if not args.zip_file.is_file():
        logger.error(f"Error: DFU file not found at {args.zip_file}")
        sys.exit(1)

    # TODO: Validate address format?

    start_time = time.monotonic()
    await perform_dfu(args.address, str(args.zip_file))
    end_time = time.monotonic()
    logger.info(f"DFU process finished in {end_time - start_time:.2f} seconds.")


if __name__ == "__main__":
    asyncio.run(main()) 