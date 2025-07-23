#!/usr/bin/env python3
"""
OMI Glass UF2 Builder
Standalone script to build firmware and generate UF2 files

Usage:
    python3 build_uf2.py                    # Build default environment
    python3 build_uf2.py --env release      # Build release environment
    python3 build_uf2.py --convert-only     # Convert existing binary to UF2
"""

import os
import sys
import struct
import subprocess
import argparse
import shutil
from pathlib import Path

def create_uf2_file(binary_path, uf2_path, family_id=0x1c5f21b0, base_address=0x10000):
    """
    Convert binary file to UF2 format for ESP32-S3
    
    Args:
        binary_path: Path to input binary file
        uf2_path: Path to output UF2 file
        family_id: ESP32-S3 family ID (0x1c5f21b0)
        base_address: Flash base address (0x10000 for app partition)
    """
    
    # UF2 constants
    UF2_MAGIC_START0 = 0x0A324655  # "UF2\n"
    UF2_MAGIC_START1 = 0x9E5D5157  # Random magic
    UF2_MAGIC_END = 0x0AB16F30     # Final magic
    UF2_FLAG_FAMILY_ID_PRESENT = 0x00002000
    UF2_DATA_SIZE = 256
    
    if not os.path.exists(binary_path):
        print(f"❌ Error: Binary file not found: {binary_path}")
        return False
    
    # Read binary file
    with open(binary_path, 'rb') as f:
        binary_data = f.read()
    
    binary_size = len(binary_data)
    print(f"📄 Converting {binary_size} bytes from {binary_path}")
    
    # Calculate number of blocks needed
    num_blocks = (binary_size + UF2_DATA_SIZE - 1) // UF2_DATA_SIZE
    
    # Create UF2 file
    with open(uf2_path, 'wb') as uf2_file:
        for block_no in range(num_blocks):
            # Calculate data for this block
            data_start = block_no * UF2_DATA_SIZE
            data_end = min(data_start + UF2_DATA_SIZE, binary_size)
            block_data = binary_data[data_start:data_end]
            
            # Pad block to 256 bytes
            if len(block_data) < UF2_DATA_SIZE:
                block_data += b'\x00' * (UF2_DATA_SIZE - len(block_data))
            
            # Calculate target address
            target_addr = base_address + data_start
            
            # Create UF2 block (512 bytes total)
            uf2_block = struct.pack('<I', UF2_MAGIC_START0)      # Magic start 0
            uf2_block += struct.pack('<I', UF2_MAGIC_START1)     # Magic start 1
            uf2_block += struct.pack('<I', UF2_FLAG_FAMILY_ID_PRESENT)  # Flags
            uf2_block += struct.pack('<I', target_addr)          # Target address
            uf2_block += struct.pack('<I', UF2_DATA_SIZE)        # Payload size
            uf2_block += struct.pack('<I', block_no)             # Block number
            uf2_block += struct.pack('<I', num_blocks)           # Total blocks
            uf2_block += struct.pack('<I', family_id)            # Family ID
            uf2_block += block_data                              # Data (256 bytes)
            uf2_block += struct.pack('<I', UF2_MAGIC_END)        # Magic end
            
            # Pad to 512 bytes
            padding_size = 512 - len(uf2_block)
            uf2_block += b'\x00' * padding_size
            
            uf2_file.write(uf2_block)
    
    file_size = os.path.getsize(uf2_path)
    print(f"✅ UF2 file created: {uf2_path}")
    print(f"   📊 Blocks: {num_blocks}")
    print(f"   📏 Size: {file_size:,} bytes ({file_size/1024:.1f} KB)")
    return True

def check_dependencies():
    """Check if PlatformIO is available"""
    try:
        result = subprocess.run(['pio', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ PlatformIO found: {result.stdout.strip()}")
            return True
        else:
            print("❌ PlatformIO not working properly")
            return False
    except FileNotFoundError:
        print("❌ PlatformIO not found. Please install it with: pip install platformio")
        return False

def build_firmware(environment="seeed_xiao_esp32s3"):
    """Build firmware using PlatformIO"""
    print(f"🔨 Building firmware for environment: {environment}")
    
    try:
        # Build the firmware
        result = subprocess.run(['pio', 'run', '-e', environment], 
                              capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ Build successful!")
            return True
        else:
            print("❌ Build failed!")
            print("Error output:")
            print(result.stderr)
            return False
            
    except Exception as e:
        print(f"❌ Build error: {e}")
        return False

def find_binary_file(environment="seeed_xiao_esp32s3"):
    """Find the built binary file"""
    possible_paths = [
        f".pio/build/{environment}/firmware.bin",
        f".pio/build/{environment}/firmware.elf.bin",
        f"build/{environment}/firmware.bin",
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            return path
    
    return None

def main():
    parser = argparse.ArgumentParser(description='OMI Glass UF2 Builder')
    parser.add_argument('--env', default='seeed_xiao_esp32s3', 
                       choices=['seeed_xiao_esp32s3', 'seeed_xiao_esp32s3_slow', 'uf2_release'],
                       help='PlatformIO environment to build')
    parser.add_argument('--convert-only', action='store_true',
                       help='Only convert existing binary to UF2 (skip build)')
    parser.add_argument('--binary', type=str,
                       help='Specific binary file to convert')
    parser.add_argument('--output', type=str,
                       help='Output UF2 filename')
    
    args = parser.parse_args()
    
    print("🚀 OMI Glass UF2 Builder")
    print("=" * 40)
    
    # Check if we're in the right directory
    if not os.path.exists('platformio.ini'):
        print("❌ Error: platformio.ini not found. Please run this script from the firmware directory.")
        sys.exit(1)
    
    if not args.convert_only:
        # Check dependencies
        if not check_dependencies():
            sys.exit(1)
        
        # Build firmware
        if not build_firmware(args.env):
            sys.exit(1)
    
    # Find binary file
    if args.binary:
        binary_path = args.binary
    else:
        binary_path = find_binary_file(args.env)
    
    if not binary_path:
        print(f"❌ Error: Could not find binary file for environment {args.env}")
        print("Available files in .pio/build/:")
        try:
            for env_dir in os.listdir('.pio/build'):
                env_path = f'.pio/build/{env_dir}'
                if os.path.isdir(env_path):
                    print(f"  {env_dir}/:")
                    for file in os.listdir(env_path):
                        if file.endswith('.bin'):
                            print(f"    {file}")
        except:
            pass
        sys.exit(1)
    
    # Generate output filename
    if args.output:
        uf2_path = args.output
    else:
        base_name = os.path.splitext(os.path.basename(binary_path))[0]
        uf2_path = f"omi_glass_{base_name}.uf2"
    
    # Convert to UF2
    print(f"\n🔄 Converting to UF2 format...")
    if create_uf2_file(binary_path, uf2_path):
        print(f"\n🎉 Success! UF2 file ready: {uf2_path}")
        
        # Create flashing instructions
        print("\n📋 Flashing Instructions:")
        print("1. Put your ESP32-S3 in bootloader mode:")
        print("   - Hold BOOT button")
        print("   - Press and release RESET button") 
        print("   - Release BOOT button")
        print("   - Device should appear as 'ESP32S3' USB drive")
        print()
        print(f"2. Copy {uf2_path} to the ESP32S3 drive")
        print("3. Device will automatically flash and reboot")
        print()
        print("🔍 Monitor with: pio device monitor --baud 115200")
        
        # Show file info
        file_size = os.path.getsize(uf2_path)
        binary_size = os.path.getsize(binary_path)
        print(f"\n📊 File sizes:")
        print(f"   Binary: {binary_size:,} bytes ({binary_size/1024:.1f} KB)")
        print(f"   UF2:    {file_size:,} bytes ({file_size/1024:.1f} KB)")
        
    else:
        print("❌ UF2 conversion failed!")
        sys.exit(1)

if __name__ == "__main__":
    main() 