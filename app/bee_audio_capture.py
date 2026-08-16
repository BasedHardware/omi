#!/usr/bin/env python3
"""
BLE Audio Capture Tool for Bee Device v4
Based on reverse engineering of Bee iOS app (bee.c decompiled)

Protocol (new firmware, isNewFirmware=true):
- Commands sent via control characteristic as: [2 bytes LE command code] + [payload data]
- All commands go through FUN_1003e6ad0 which wraps: [cmd_code LE 2B] + [payload]
- Responses arrive on control characteristic as notifications
- Response format: [0x00 0x80] (0x8000 LE) + [cmd_code LE 2B] + [payload bytes]
- Event notifications: 0x8001-0x8003 prefix
- Old firmware response: 0xA005 prefix (mute state at byte 2)

Payload indexing (from full response data[]):
  data[0..1] = 0x8000 (response marker)
  data[2..3] = echoed command code
  data[4+]   = command-specific payload

Audio frames arrive on the audio characteristic as notifications.
"""

import asyncio
import struct
from bleak import BleakClient, BleakScanner
from datetime import datetime
import sys

# UUIDs (from iOS app analysis)
SERVICE_UUID = "03d5d5c4-a86c-11ee-9d89-8f2089a49e7e"
CONTROL_CHARACTERISTIC_UUID = "05e1f93c-d8d0-5ed8-dd88-379e4c1a3e3e"
AUDIO_CHARACTERISTIC_UUID = "b189a505-a86c-11ee-a5fb-8f2089a49e7e"

# Command codes (from bee.c response dispatch at line 787123+)
# Sent as little-endian uint16
CMD_SET_TRANSMISSION_SPEED = 0xC001  # 1 byte payload: speed index
CMD_GET_CODEC_INFO         = 0xC002  # no payload; response has codec details
CMD_GET_FIRMWARE_VERSION   = 0xC005  # no payload; response: [patch, minor, major] at data[4..6]
CMD_SET_DEVICE_STATE       = 0xC006  # 1 byte: 0=mute, 1=unmute
CMD_POWER_SAVING_CONFIG    = 0xC008  # 4 bytes payload
CMD_GET_BITRATE            = 0xC009  # no payload; response: uint32 LE at data[4..7]
CMD_GET_DEVICE_STATE       = 0xC00A  # no payload; response: state=data[4], codec=data[5]
CMD_GET_DEVICE_ID          = 0xC00E  # no payload; response: uint32 LE at data[4..7] + uint32 LE at data[8..11]
CMD_GET_BATTERY            = 0xC00F  # no payload; response: level=data[4], charging=data[5]
CMD_FORCE_STOP             = 0xC010  # no payload
CMD_HOLD_EVENT             = 0xC016  # 1 byte at data[4]
CMD_DOUBLE_PRESS           = 0xC017  # 1 byte at data[4]
CMD_SESSION_ID             = 0xC019  # response: 16-byte UUID at data[4..19]
CMD_UNKNOWN_1B             = 0xC01B  # seen in dispatch, purpose TBD

# Response markers
RESPONSE_WRAPPER = 0x8000   # New firmware response prefix
OLD_FW_MUTE_RESP = 0xA005   # Old firmware mute state response

# Device states (from iOS app dispatch at ~787345)
DEVICE_STATES = {
    0: "MUTE",
    1: "RECORDING",
    2: "SLEEP_HW_VAD",
    3: "POWER_OFF",
    4: "SLEEP_SW_VAD"
}

# Codec types
CODEC_TYPES = {
    0: "OPUS",
    1: "AAC"
}


class BeeAudioCapture:
    def __init__(self, device_address=None):
        self.device_address = device_address
        self.client = None
        self.audio_buffer = bytearray()
        self.current_frame_id = -1
        self.expected_size = 0
        self.frame_count = 0
        self.total_bytes = 0
        self.output_file = None
        self.is_new_firmware = False
        self.firmware_version = None
        self.device_state = None
        self.codec_type = None
        self.session_nonce = None
        self.secure_ids = None
        self.is_sealed = None
        self._pending_responses = {}

    def encode_command(self, command_code, data=b''):
        """
        Encode command for the control characteristic.
        From FUN_1003e6ad0: the command is built as [cmd_code LE 2B] + [payload].
        Data is then serialized via FUN_1003cf318 (Data init from buffer).
        """
        return struct.pack('<H', command_code) + data

    async def find_device(self):
        """Scan for Bee device"""
        print("Scanning for Bee devices...")
        print("(Make sure Bee app on iPhone is CLOSED and iPhone Bluetooth is OFF)")
        print("")

        devices = await BleakScanner.discover(
            timeout=10.0,
            return_adv=True,
            service_uuids=[SERVICE_UUID]
        )

        bee_devices = []
        for device, adv_data in devices.values():
            bee_devices.append((device, adv_data))
            print(f"Found: {device.name or 'Unknown'} ({device.address}) RSSI: {adv_data.rssi}")

        if not bee_devices:
            print("\nNo devices found with service UUID filter, trying broader scan...")
            devices = await BleakScanner.discover(timeout=10.0, return_adv=True)
            for device, adv_data in devices.values():
                if device.name and "bee" in device.name.lower():
                    bee_devices.append((device, adv_data))
                    print(f"Found: {device.name} ({device.address}) RSSI: {adv_data.rssi}")

        if not bee_devices:
            print("\nNo Bee devices found!")
            print("\nTroubleshooting:")
            print("1. Is the Bee device powered ON? (LED should be visible)")
            print("2. Is the Bee app CLOSED on your iPhone?")
            print("3. Is Bluetooth DISABLED on your iPhone?")
            print("4. Try pressing the button on the Bee device to wake it up")
            return None

        bee_devices.sort(key=lambda x: x[1].rssi, reverse=True)
        selected = bee_devices[0][0]
        print(f"\nSelecting: {selected.name or 'Bee'} ({selected.address})")
        return selected.address

    async def send_command(self, command_code, data=b'', description=""):
        """Send command to control characteristic with write-with-response (type=0)"""
        cmd_bytes = self.encode_command(command_code, data)
        label = description or f"0x{command_code:04X}"
        print(f"[TX] {label}: {cmd_bytes.hex()}")
        # iOS app uses writeValue:forCharacteristic:type: with type=0 (write with response)
        await self.client.write_gatt_char(CONTROL_CHARACTERISTIC_UUID, cmd_bytes, response=True)
        await asyncio.sleep(0.1)

    def control_notification_handler(self, sender, data):
        """
        Handle control characteristic notifications.

        New firmware (isNewFirmware=true) response dispatch from bee.c:787115+:
          - 0x8000: standard response → data[2..3] = echoed cmd, data[4+] = payload
          - 0x8001-0x8003: event notifications → data[2+] = event payload
          - 0xA005: old firmware mute state → data[2] = mute bool

        The iOS app reads the first 2 bytes as uint16 LE, then dispatches.
        """
        if len(data) < 2:
            return

        response_code = struct.unpack('<H', data[0:2])[0]
        print(f"[RX] 0x{response_code:04X} | len={len(data)} | {data.hex()}")

        if response_code == RESPONSE_WRAPPER and len(data) >= 4:
            # Standard response: [0x8000 LE] [cmd LE] [payload...]
            echoed_cmd = struct.unpack('<H', data[2:4])[0]
            self._parse_new_fw_response(echoed_cmd, data)

        elif 0x8001 <= response_code <= 0x8003:
            # Event notifications (hold, double-press, etc.)
            payload = data[2:]
            print(f"       Event 0x{response_code:04X}: {payload.hex()}")

        elif response_code == 0xA001:
            # bee.c:786960 → FUN_1003de478 → double-press event (no payload)
            print(f"       [Event] Double press detected")

        elif response_code == 0xA002:
            # bee.c:786967 → FUN_1003de210(data[2] != 0) → charging state change
            if len(data) >= 3:
                charging = data[2] != 0
                print(f"       [Event] Charging state: {'charging' if charging else 'not charging'}")

        elif response_code == 0xA003:
            # bee.c:787004 → FUN_1003dedb0 → device state + codec update
            # needs ≥4 bytes: data[2] = state, data[3] = codec
            if len(data) >= 4:
                state = data[2]
                codec = data[3]
                self.device_state = state
                self.codec_type = codec
                state_name = DEVICE_STATES.get(state, f"UNKNOWN({state})")
                codec_name = CODEC_TYPES.get(codec, f"UNKNOWN({codec})")
                print(f"       [Event] State: {state_name}, Codec: {codec_name}")

        elif response_code == 0xA004:
            # bee.c:787011 → FUN_1003ddd14(data[2]) → battery level update
            if len(data) >= 3:
                level = data[2]
                print(f"       [Event] Battery: {level}%")

        elif response_code == OLD_FW_MUTE_RESP:
            # bee.c:787047 → FUN_1003ddf90(data[2] != 0) → mute state
            if len(data) >= 3:
                muted = data[2] != 0
                print(f"       [Event] Mute state: {'muted' if muted else 'unmuted'}")

        elif response_code == 0x0101:
            # Special case from bee.c:787161 - firmware reports as v1.0.1
            self.firmware_version = "1.0.1"
            self.is_new_firmware = False
            print(f"       Legacy firmware v1.0.1 detected")

    def _parse_new_fw_response(self, cmd, data):
        """
        Parse response for specific commands.
        All indices reference the full data[] array (not just payload after cmd).
        Matches the dispatch tree at bee.c:787123-787590.
        """

        if cmd == CMD_GET_FIRMWARE_VERSION:
            # bee.c:787226 - needs >6 bytes total
            # Reads data[6] (major), data[5] (minor), data[4] (patch)
            # Version string built as: data[6].data[5].data[4]
            if len(data) > 6:
                patch = data[4]
                minor = data[5]
                major = data[6]
                self.firmware_version = f"{major}.{minor}.{patch}"
                print(f"       Firmware: v{self.firmware_version}")
                self.is_new_firmware = True
                print(f"       New firmware protocol active")

        elif cmd in (CMD_SET_TRANSMISSION_SPEED, CMD_GET_CODEC_INFO):
            # bee.c:787126 - handles 0xC001 and 0xC002 together
            # needs >4 bytes, reads data[4]
            if len(data) > 4:
                value = data[4]
                if cmd == CMD_SET_TRANSMISSION_SPEED:
                    print(f"       Transmission speed: {value}")
                else:
                    print(f"       Codec info: {value}")

        elif cmd == CMD_SET_DEVICE_STATE:
            # bee.c:787274 - needs >4 bytes, reads data[4]
            # Value is capped: if data[4] > 4, set to 1
            # Response also includes codec at data[5] (same format as 0xC00A)
            if len(data) > 4:
                raw_state = data[4]
                state = 1 if raw_state > 4 else raw_state
                self.device_state = state
                state_str = DEVICE_STATES.get(state, f"STATE_{state}")
                extra = ""
                if len(data) > 5:
                    codec = data[5]
                    self.codec_type = codec
                    codec_name = CODEC_TYPES.get(codec, f"UNKNOWN({codec})")
                    extra = f", Codec: {codec_name}"
                print(f"       Device state set: {state_str}{extra}")

        elif cmd in (CMD_POWER_SAVING_CONFIG, CMD_GET_BITRATE):
            # bee.c:787173 - handles 0xC008 and 0xC009 together
            # needs >7 bytes, reads uint32 LE from data[4..7]
            if len(data) > 7:
                value = struct.unpack('<I', data[4:8])[0]
                if cmd == CMD_GET_BITRATE:
                    print(f"       Bitrate: {value} bps")
                else:
                    print(f"       Power saving config: 0x{value:08X}")

        elif cmd == CMD_GET_DEVICE_STATE:
            # bee.c:787345 - needs >5 bytes
            # data[4] = state, data[5] = codec
            # Then calls FUN_1003dedb0 to process further
            if len(data) > 5:
                state = data[4]
                codec = data[5]
                self.device_state = state
                self.codec_type = codec
                state_name = DEVICE_STATES.get(state, f"UNKNOWN({state})")
                codec_name = CODEC_TYPES.get(codec, f"UNKNOWN({codec})")
                print(f"       State: {state_name}, Codec: {codec_name}")

        elif cmd == CMD_GET_DEVICE_ID:
            # bee.c:787437 - needs >0xB (11) bytes
            # Reads uint32 LE from data[4..7] and uint32 LE from data[8..11]
            # Formats as "%08X%08X" (two 32-bit values)
            if len(data) > 11:
                id_hi = struct.unpack('<I', data[4:8])[0]
                id_lo = struct.unpack('<I', data[8:12])[0]
                device_id = f"{id_hi:08X}{id_lo:08X}"
                print(f"       Device ID: {device_id}")

        elif cmd == CMD_GET_BATTERY:
            # bee.c:787485 - needs >5 bytes
            # data[4] = battery level, data[5] = charging state
            if len(data) > 5:
                level = data[4]
                charging = data[5]
                print(f"       Battery: {level}%, Charging: {'Yes' if charging else 'No'}")

        elif cmd in (CMD_HOLD_EVENT, CMD_DOUBLE_PRESS):
            # bee.c:787515 - handles 0xC016 and 0xC017 together
            # needs >4 bytes, reads data[4]
            if len(data) > 4:
                value = data[4]
                event_name = "Hold" if cmd == CMD_HOLD_EVENT else "Double press"
                print(f"       {event_name} event: {value}")

        elif cmd == CMD_SESSION_ID:
            # Android: b5/g0.java p() - 12-byte session nonce for AES-128-CTR
            if len(data) >= 16:
                self.session_nonce = data[4:16]
                print(f"       Session Nonce (12B): {self.session_nonce.hex()}")
                print(f"       Encryption ready! Device should now respond to button presses.")
            else:
                print(f"       Session nonce too short: {data[4:].hex()}")

        elif cmd == CMD_UNKNOWN_1B:
            # Android: b5/AbstractC2235e.java h class - SecureIds
            # Format: data[4..12] = 8-byte device ID, data[12] = isSealed
            if len(data) >= 13:
                device_id_bytes = data[4:12]
                self.is_sealed = data[12] != 0
                self.secure_ids = device_id_bytes
                device_id_hex = device_id_bytes.hex()
                print(f"       Secure IDs: device={device_id_hex}, isSealed={self.is_sealed}")
                if self.is_sealed:
                    print(f"       Key already on device (sealed). Just need session nonce.")
                else:
                    print(f"       NOT sealed - key needs to be sent via SetEncryptionKey (0xC018)")
            else:
                payload = data[4:] if len(data) > 4 else b''
                print(f"       SecureIds raw: {payload.hex()}")

        elif cmd == CMD_FORCE_STOP:
            print(f"       Force stop acknowledged")

        else:
            payload = data[4:] if len(data) > 4 else b''
            print(f"       Response 0x{cmd:04X}: {payload.hex()}")

    def audio_notification_handler(self, sender, data):
        """
        Handle audio characteristic notifications.

        From Android app (b5/l0.java):
        Audio packets are AES-128-CTR encrypted.
        Format: [4-byte counter BE] + [encrypted audio data]
        Decryption IV: [12-byte session nonce] + [4-byte counter]
        """
        self.total_bytes += len(data)
        self.frame_count += 1

        # Log first 10 packets with encrypted structure info
        if self.frame_count <= 10:
            if len(data) >= 4:
                counter = struct.unpack('>I', data[0:4])[0]
                print(f"[AUDIO] pkt#{self.frame_count} len={len(data)} counter={counter} | {data[:20].hex()}{'...' if len(data) > 20 else ''}")
            else:
                print(f"[AUDIO] pkt#{self.frame_count} len={len(data)} | {data.hex()}")

        # Save raw encrypted data
        if self.output_file:
            self.output_file.write(data)
            self.output_file.flush()

    async def set_unmute(self):
        """
        Unmute the device to start recording.

        Confirmed by device response: sending 0x01 via CMD_SET_DEVICE_STATE (0xC006)
        sets state to RECORDING (1). The XOR inversion at bee.c:779513 only applies
        to the old-firmware muteCharacteristic write path, NOT the 0xC006 command.
        """
        await self.send_command(CMD_SET_DEVICE_STATE, b'\x01', "Unmute (start recording)")

    async def set_mute(self):
        """Mute the device to stop recording. 0x00 = MUTE state."""
        await self.send_command(CMD_SET_DEVICE_STATE, b'\x00', "Mute (stop recording)")

    async def set_transmission_speed(self, speed_index=0):
        """
        Set audio transmission speed.
        From bee.c:795086 - sends 0xC001 with 1-byte speed value.
        """
        await self.send_command(CMD_SET_TRANSMISSION_SPEED, bytes([speed_index]),
                                f"Set transmission speed: {speed_index}")

    async def capture(self, duration=10, output_filename=None):
        """Connect and capture audio"""

        if not self.device_address:
            self.device_address = await self.find_device()
            if not self.device_address:
                return

        if not output_filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"bee_audio_{timestamp}.raw"

        print(f"\nConnecting to {self.device_address}...")
        print("(A pairing request may appear - please accept it)")

        client = BleakClient(
            self.device_address,
            timeout=60.0,
            disconnected_callback=lambda c: print("\n[!] Device disconnected")
        )

        try:
            print("Initiating connection...")
            await client.connect()
            print("Connection established, discovering services...")

        except asyncio.TimeoutError:
            print(f"\nConnection timed out!")
            print("\nThis usually means:")
            print("1. The device is connected to another device (iPhone?)")
            print("2. The device is in deep sleep - press the button to wake it")
            print("3. Bluetooth needs to be reset on this Mac")
            print("\nTry: Turn OFF Bluetooth on your iPhone, then retry")
            return
        except Exception as e:
            print(f"\nConnection failed: {e}")
            return

        try:
            self.client = client

            if not client.is_connected:
                print("Failed to connect!")
                return

            print("Connected!\n")

            # Print discovered services
            print("=== Services ===")
            for service in client.services:
                if "d5c4" in service.uuid.lower() or "03d5" in service.uuid.lower():
                    print(f"[Service] {service.uuid}")
                    for char in service.characteristics:
                        props = ', '.join(char.properties)
                        print(f"  [Char] {char.uuid}")
                        print(f"         Handle: 0x{char.handle:04X}, Props: {props}")

            self.output_file = open(output_filename, 'wb')
            print(f"\n[FILE] Saving to: {output_filename}")

            # Subscribe to notifications FIRST (iOS app does this immediately after
            # service/characteristic discovery via setNotifyValue:forCharacteristic:
            # at bee.c:798784)
            print("\n=== Subscribing to Notifications ===")
            await client.start_notify(CONTROL_CHARACTERISTIC_UUID, self.control_notification_handler)
            print("Control notifications enabled")

            await client.start_notify(AUDIO_CHARACTERISTIC_UUID, self.audio_notification_handler)
            print("Audio notifications enabled")

            await asyncio.sleep(0.5)

            # Startup sequence from BLEManager init (bee.c:781236-781246):
            #   1. CMD_GET_FIRMWARE_VERSION (0xC005) - always first
            #   2. CMD_GET_DEVICE_STATE (0xC00A) - if new firmware
            #   3. CMD_GET_BATTERY (0xC00F) - if new firmware
            #   4. CMD_GET_DEVICE_ID (0xC00E) - if new firmware
            # After connection established (bee.c:798922-798923):
            #   5. CMD_GET_CODEC_INFO (0xC002)
            #   6. CMD_GET_BITRATE (0xC009)
            print("\n=== Device Info (startup sequence) ===")

            await self.send_command(CMD_GET_FIRMWARE_VERSION, description="Get Firmware Version")
            await asyncio.sleep(0.3)

            await self.send_command(CMD_GET_DEVICE_STATE, description="Get Device State")
            await asyncio.sleep(0.2)

            await self.send_command(CMD_GET_BATTERY, description="Get Battery Level")
            await asyncio.sleep(0.2)

            await self.send_command(CMD_GET_DEVICE_ID, description="Get Device ID")
            await asyncio.sleep(0.2)

            await self.send_command(CMD_GET_CODEC_INFO, description="Get Codec Info")
            await asyncio.sleep(0.2)

            await self.send_command(CMD_GET_BITRATE, description="Get Bitrate")
            await asyncio.sleep(0.3)

            # Encryption handshake (from Android app: b5/g0.java)
            # The device won't stream audio or respond to button presses
            # until the encryption handshake is complete.
            #
            # Flow: GetSecureIds → (SetEncryptionKey if not sealed) → GetSessionNonce
            # Audio is AES-128-CTR encrypted: [4B counter BE] + [ciphertext]
            # Key = 16 bytes from backend, Nonce = 12 bytes from device
            # IV = [nonce 12B] + [counter 4B]
            print("\n=== Encryption Handshake ===")

            await self.send_command(CMD_UNKNOWN_1B, description="Get Secure IDs (0xC01B)")
            await asyncio.sleep(0.5)

            # If device isSealed (key already installed from iOS app pairing),
            # we just need to request the session nonce to activate the device.
            await self.send_command(CMD_SESSION_ID, description="Get Session Nonce (0xC019)")
            await asyncio.sleep(0.5)

            # Passive listen mode - wait for button press on device
            print(f"\n=== Listening for {duration} seconds ===")
            print("Press the button on the Bee device to start recording.")
            print("All notifications on both characteristics will be logged.\n")

            for i in range(duration):
                await asyncio.sleep(1)
                status = f"[{i+1}/{duration}s]"
                if self.total_bytes > 0:
                    print(f"{status} Audio bytes: {self.total_bytes}")
                else:
                    print(f"{status} Waiting... (press device button)")

            print(f"\n=== Capture Complete ===")
            print(f"Total audio bytes: {self.total_bytes}")
            print(f"Total frames: {self.frame_count}")
            print(f"Output file: {output_filename}")

            if self.frame_count == 0 and self.total_bytes == 0:
                print("\nNo audio data received.")
                print("  - Device may need a button press to wake up")
                print("  - Check if device is paired to another host")

        finally:
            if self.output_file:
                self.output_file.close()
            try:
                await client.stop_notify(CONTROL_CHARACTERISTIC_UUID)
                await client.stop_notify(AUDIO_CHARACTERISTIC_UUID)
            except Exception:
                pass
            try:
                await client.disconnect()
            except Exception:
                pass


async def main():
    import argparse
    parser = argparse.ArgumentParser(description='Bee Audio Capture v4 (from bee.c RE)')
    parser.add_argument('--address', '-a', help='Device Bluetooth address')
    parser.add_argument('--duration', '-d', type=int, default=30, help='Listen duration in seconds')
    parser.add_argument('--output', '-o', help='Output filename (default: bee_audio_TIMESTAMP.raw)')
    args = parser.parse_args()

    capturer = BeeAudioCapture(device_address=args.address)

    try:
        await capturer.capture(
            duration=args.duration,
            output_filename=args.output
        )
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
