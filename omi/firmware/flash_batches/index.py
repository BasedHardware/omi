import os
import time
import glob
import shutil
import platform
import json
from datetime import datetime

# Constants and configurations
UF2_FILES = [
    "omi/firmware/bootloader/bootloader0.9.0.uf2",
    "omi/firmware/firmware1.0.4.uf2"
    # Add more UF2 file paths as needed
]

WAIT_FOR_DRIVE_TIMEOUT = 0  # seconds, 0 means wait indefinitely
WAIT_FOR_DRIVE_DISAPPEAR_TIMEOUT = 10  # seconds
PRE_COPY_WAIT_TIME = 2  # seconds
FLASHING_RESULTS_FILE = 'flashing_results.json'

def find_uf2_drive():
    possible_drives = glob.glob('/Volumes/XIAO*')
    return possible_drives[0] if possible_drives else None

def wait_for_drive_disconnection():
    print("Ensuring the device is disconnected...")
    while find_uf2_drive():
        time.sleep(0.5)
    print("Device disconnected.")

def wait_for_drive_connection(timeout=WAIT_FOR_DRIVE_TIMEOUT):
    print("Waiting for XIAO-SENSE drive to appear...")
    start_time = time.time()
    while True:
        drive = find_uf2_drive()
        if drive:
            print(f"Found XIAO-SENSE drive at: {drive}")
            return drive
        time.sleep(0.5)
        if timeout > 0 and time.time() - start_time >= timeout:
            print("Timeout reached while waiting for the device.")
            return None

def wait_for_drive_to_disappear(drive_path, timeout=WAIT_FOR_DRIVE_DISAPPEAR_TIMEOUT):
    print("Waiting for device to reset...")
    start_time = time.time()
    while os.path.exists(drive_path) and (timeout == 0 or time.time() - start_time < timeout):
        time.sleep(0.1)
    if not os.path.exists(drive_path):
        print("Device reset detected.")
        return True
    else:
        print("Warning: Device did not reset as expected.")
        return False

def flash_device(uf2_file_path):
    print(f"\nPreparing to flash: {os.path.basename(uf2_file_path)}")
    print(f"File size: {os.path.getsize(uf2_file_path)} bytes")

    # Ensure the device is disconnected before starting
    wait_for_drive_disconnection()

    # Prompt the user to put the device into bootloader mode
    print("\nPlease put the device into bootloader mode now.")
    target_drive = wait_for_drive_connection()
    if not target_drive:
        print("Error: XIAO-SENSE drive not detected. Skipping this file.")
        return False

    print(f"Waiting {PRE_COPY_WAIT_TIME} seconds before copying...")
    time.sleep(PRE_COPY_WAIT_TIME)

    try:
        print(f"Copying {uf2_file_path} to {target_drive}")
        shutil.copy2(uf2_file_path, target_drive)
        print("File copied successfully.")

        wait_for_drive_to_disappear(target_drive)
        return True

    except OSError as e:
        if e.errno == 5:  # Input/output error
            print("Device reset during copy operation (expected behavior). Assuming flash was successful.")
            # Wait for the device to disappear to confirm the reset
            wait_for_drive_to_disappear(target_drive)
            return True
        else:
            print(f"An unexpected error occurred during flashing: {e}")
            return False

def main():
    print(f"Python version: {platform.python_version()}")
    print(f"Operating System: {platform.system()} {platform.release()}")

    device_count = 0
    results = []

    try:
        while True:
            device_count += 1
            print(f"\n--- Ready to flash Device #{device_count} ---")
            device_result = {
                "device_number": device_count,
                "timestamp": datetime.now().isoformat(),
                "files": []
            }

            for i, uf2_file in enumerate(UF2_FILES, 1):
                if not os.path.exists(uf2_file):
                    print(f"Error: UF2 file not found at {uf2_file}")
                    continue

                print(f"\nFlashing UF2 File {i}/{len(UF2_FILES)}")

                success = flash_device(uf2_file)

                file_result = {
                    "file_name": os.path.basename(uf2_file),
                    "success": success
                }
                device_result["files"].append(file_result)

                if not success:
                    print(f"Flashing failed for {os.path.basename(uf2_file)}.")
                else:
                    print(f"Successfully flashed {os.path.basename(uf2_file)}")

            results.append(device_result)

            # Save results to JSON file after each device
            with open(FLASHING_RESULTS_FILE, 'w') as f:
                json.dump(results, f, indent=2)

            print(f"\nDevice #{device_count} flashing completed. Results saved to {FLASHING_RESULTS_FILE}")
            print("\nWaiting for next device...")

    except KeyboardInterrupt:
        print("\nProcess interrupted by user. Saving final results...")
        with open(FLASHING_RESULTS_FILE, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"Final results saved to {FLASHING_RESULTS_FILE}")

if __name__ == "__main__":
    main()
