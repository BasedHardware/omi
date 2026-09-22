#!/usr/bin/env python3
"""
ESP32 S3 XIAO Flash Script (Python version)
This script helps flash firmware to an ESP32 S3 XIAO board using PlatformIO
"""

import os
import sys
import time
import glob
import subprocess
import platform

def find_serial_ports():
    """Find available serial ports"""
    system = platform.system()
    ports = []
    
    if system == 'Darwin':  # macOS
        ports = glob.glob('/dev/tty.*') + glob.glob('/dev/cu.*')
        # Filter for likely ESP32 devices
        ports = [p for p in ports if any(x in p.lower() for x in ['usb', 'wchusb', 'slab', 'cp210', 'acm'])]
    elif system == 'Linux':
        ports = glob.glob('/dev/ttyUSB*') + glob.glob('/dev/ttyACM*')
    elif system == 'Windows':
        # Requires pyserial to be installed
        try:
            import serial.tools.list_ports
            ports = [p.device for p in serial.tools.list_ports.comports()]
        except ImportError:
            print("pyserial not found. On Windows, install it with: pip install pyserial")
            ports = ['COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8']
    
    return ports

def check_platformio():
    """Check if PlatformIO is installed"""
    try:
        subprocess.run(['platformio', '--version'], 
                      stdout=subprocess.PIPE, 
                      stderr=subprocess.PIPE,
                      check=True)
        return True
    except (subprocess.SubprocessError, FileNotFoundError):
        return False

def main():
    """Main function"""
    print("ESP32 S3 XIAO Flash Script (Python Version)")
    print("------------------------------------------")
    
    # Check PlatformIO installation
    if not check_platformio():
        print("Error: PlatformIO is not installed or not in your PATH.")
        print("Install it using: pip install platformio or brew install platformio")
        sys.exit(1)
    
    # Change to the script's directory
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    # Find available ports
    print("\nSearching for ESP32 S3 XIAO board...")
    ports = find_serial_ports()
    
    if not ports:
        print("No serial ports found. Connect your ESP32 S3 XIAO and try again.")
        sys.exit(1)
    
    # Display available ports
    print("\nAvailable serial ports:")
    for i, port in enumerate(ports):
        print(f"{i+1}. {port}")
    
    # Let user select a port
    selection = 0
    while selection < 1 or selection > len(ports):
        try:
            selection = int(input(f"\nSelect a port (1-{len(ports)}): "))
        except ValueError:
            print("Please enter a number.")
    
    selected_port = ports[selection-1]
    print(f"\nSelected port: {selected_port}")
    
    # Bootloader instructions
    print("\n" + "="*70)
    print("IMPORTANT: Enter bootloader mode before flashing:")
    print("1. Press and hold the BOOT button on your ESP32 S3 XIAO")
    print("2. Press the RESET button while holding BOOT")
    print("3. Release the RESET button first, then release the BOOT")
    print("="*70)
    
    input("\nPress Enter when your device is in bootloader mode...")
    
    # Try different environments (from fastest to slowest upload speed)
    environments = ["seeed_xiao_esp32s3", "seeed_xiao_esp32s3_slow"]
    success = False
    
    for env in environments:
        print(f"\nAttempting to flash with environment: {env}")
        try:
            result = subprocess.run(
                ['platformio', 'run', '-e', env, '--target', 'upload', 
                 '--upload-port', selected_port],
                check=False
            )
            if result.returncode == 0:
                success = True
                break
            print(f"Failed with environment {env}, trying next environment...")
        except subprocess.SubprocessError as e:
            print(f"Error during upload: {e}")
    
    if success:
        print("\nFirmware successfully uploaded to the ESP32 S3 XIAO board!")
        
        # Ask to monitor serial output
        monitor = input("\nDo you want to monitor the serial output? (y/n): ").lower()
        if monitor.startswith('y'):
            print("Starting serial monitor...")
            try:
                subprocess.run(['platformio', 'device', 'monitor', '-p', selected_port, '-b', '115200'])
            except KeyboardInterrupt:
                print("\nMonitor stopped.")
        
        print("\nDone!")
    else:
        print("\nFailed to upload the firmware after multiple attempts.")
        print("\nTroubleshooting tips:")
        print("1. Try a different USB cable")
        print("2. Connect directly to the computer (not through a hub)")
        print("3. Make sure your board is properly in bootloader mode")
        print("4. Try manually running: platformio run -e seeed_xiao_esp32s3_slow --target upload")
        print("5. Check if your board needs specific drivers installed")
        print("6. Try pressing BOOT button again during upload")

if __name__ == "__main__":
    main() 