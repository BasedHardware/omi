import argparse
import os
from dotenv import load_dotenv
import wave
from deepgram import DeepgramClient, SpeakOptions
import asyncio
from bleak import BleakClient
import numpy as np

load_dotenv()

filename = "output2.wav"
device_id = "B9ED2D51-9A40-9329-EB32-10FD2F6FF7A5"  # Enter your device ID here
deepgram_api_id = "f2e9ebf2f223ae423c88bf601ce1a157699d3005"  # Enter your Deepgram API key here
audio_write_characteristic_uuid = "19B10003-E8F2-537E-4F6C-D104768A1214"
SAMPLE_RATE = 8000  # Set sample rate to 8000 Hz

async def main():
    parser = argparse.ArgumentParser(description="Convert a string to speech")
    parser.add_argument("input_string", type=str, help="The string to convert to speech")
    args = parser.parse_args()
    SPEAK_OPTIONS = {"text": args.input_string}

    # Generate audio at 8000 Hz using Deepgram
    try:
        deepgram = DeepgramClient(api_key=deepgram_api_id)
        options = SpeakOptions(
            model="aura-stella-en",
            encoding="linear16",
            sample_rate=SAMPLE_RATE,
            container="wav"
        )
        response = deepgram.speak.v("1").save(filename, SPEAK_OPTIONS, options)
        print(response.to_json(indent=4))

    except Exception as e:
        print(f"Exception: {e}")
        return

    # Read audio data from the WAV file, skipping the 44-byte header
    with open(filename, 'rb') as wav_file:
        wav_file.seek(44)  # Skip the 44-byte header
        frames = wav_file.read()  # Read the rest of the file as raw PCM data
        audio_data = np.frombuffer(frames, dtype=np.int16)
        audio_data_bytes = audio_data.tobytes()

    # Calculate the delay between packets for real-time playback
    packet_size = 400
    bytes_per_second = SAMPLE_RATE * 2
    delay_per_packet = packet_size / bytes_per_second

    # Send audio data in packets with an is_first_packet flag
    async with BleakClient(device_id) as client:
        print("Connected to Bluetooth device:", client.address)
        offset = 0
        is_first_packet = True

        # Send packets of audio data
        while offset < len(audio_data_bytes):
            end = offset + packet_size
            is_last_packet = end >= len(audio_data_bytes)
            packet = audio_data_bytes[offset:end]

            # Append flags for is_first_packet and is_last_packet
            flags = (b'\x02' if is_first_packet else b'\x00') + (b'\x01' if is_last_packet else b'\x00')
            packet += flags  # Append both flags to the packet

            print(f"Sending bytes {offset} to {end} (is_first_packet={is_first_packet}, is_last_packet={is_last_packet})")
            await client.write_gatt_char(audio_write_characteristic_uuid, packet, response=True)
            offset = end
            is_first_packet = False  # Reset after first packet

            # Delay to simulate real-time playback speed
            await asyncio.sleep(delay_per_packet)

        print("Audio transmission complete.")

if __name__ == "__main__":
    asyncio.run(main())
