import asyncio
import wave
import numpy as np
from bleak import BleakClient
from deepgram import Deepgram
import os
from dotenv import load_dotenv
import time
import struct
import logging
import sys

load_dotenv()

# Configuration
DEVICE_ID = "05D815C6-697E-EAAB-2CAC-DCAB39DB7655"  # Your device ID
DEEPGRAM_API_KEY = "f2e9ebf2f223ae423c88bf601ce1a157699d3005"  # Your Deepgram API key
BUTTON_READ_UUID = "23BA7925-0000-1000-7450-346EAC492E92"  # Button characteristic

# Updated UUIDs to match firmware
VOICE_INTERACTION_UUID = "19B10004-E8F2-537E-4F6C-D104768A1214"  # Voice data characteristic for sending audio to cloud
VOICE_INTERACTION_RX_UUID = "19B10005-E8F2-537E-4F6C-D104768A1214"  # Voice response characteristic for receiving TTS audio
VOICE_CONTROL_UUID = "19B10006-E8F2-537E-4F6C-D104768A1214"  # Control characteristic for speaker mode

# Audio service UUID from firmware
AUDIO_SERVICE_UUID = "19B10000-E8F2-537E-4F6C-D104768A1214"

# Button states
SINGLE_TAP = 1
DOUBLE_TAP = 2
LONG_TAP = 3
BUTTON_PRESS = 4
BUTTON_RELEASE = 5

# Audio settings
MAX_ALLOWED_SAMPLES = 50000
GAIN = 3  # Reduce gain to prevent audio clipping
PACKET_SIZE = 160

VOICE_CHAR_UUID = "19B10005-E8F2-537E-4F6C-D104768A1214"  # Matching firmware's voice response characteristic.

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s:%(message)s')

class VoiceInteractionClient:
    def __init__(self):
        self.audio_data = bytearray()
        self.is_recording = False
        # Initialize Deepgram with v2 style
        self.deepgram = Deepgram(DEEPGRAM_API_KEY)
        self.client = None
        self.is_connected = False
        # For logging button events and timing.
        self.last_event_time = 0
        self.recording_start_time = None

    async def connect(self):
        while True:
            try:
                if not self.is_connected:
                    print("Attempting to connect...")
                    self.client = BleakClient(DEVICE_ID, disconnected_callback=self.handle_disconnect)
                    await self.client.connect()
                    self.is_connected = True
                    print(f"Connected to {self.client.address}")
                    await self.setup_notifications()
                    print("Ready for voice interaction. Double-tap to start recording.")
                return
            except Exception as e:
                print(f"Connection failed: {e}")
                await asyncio.sleep(5)  # Wait before retrying

    def handle_disconnect(self, client):
        print("Device disconnected!")
        self.is_connected = False
        asyncio.create_task(self.reconnect())

    async def reconnect(self):
        print("Attempting to reconnect...")
        await self.connect()

    async def setup_notifications(self):
        try:
            # Button notifications
            await self.client.start_notify(BUTTON_READ_UUID, self.on_button_change)
            print("Button notifications set up")

            # Voice data notifications
            await self.client.start_notify(VOICE_INTERACTION_UUID, self.on_voice_data)
            print("Voice notifications set up")

        except Exception as e:
            print(f"Error setting up notifications: {e}")

    def on_button_change(self, sender, data):
        button_state = int.from_bytes(data, byteorder='little')
        logging.info("Button state received: %d", button_state)

        if button_state == SINGLE_TAP:
            logging.info("Single tap detected (voice mode toggle)")
            # Immediately trigger host-initiated streaming.
            logging.info("Initiating audio stream from host...")
            asyncio.create_task(stream_audio(self, VOICE_CHAR_UUID))
        elif button_state == BUTTON_RELEASE:
            logging.info("BUTTON_RELEASE event received")
        elif button_state == BUTTON_PRESS:
            logging.info("Button pressed")
        else:
            logging.info("Other button event received")

    def on_voice_data(self, sender, data):
        if self.is_recording:
            # Skip the first 3 bytes (header)
            self.audio_data.extend(data[3:])
            print(f"Received {len(data)} bytes of audio data")

    async def process_voice_command(self):
        logging.info("Simulated transcription processing... (mock)")
        if not self.audio_data:
            logging.error("No audio data recorded!")
            return

        # Simulate processing delay.
        await asyncio.sleep(1)
        transcript = "Simulated Transcript: Hello World!"
        logging.info("Transcription result (simulated): %s", transcript)

        # Optionally, send a TTS audio response back to the device.
        # This simulates the normal flow where the device sends a recording and
        # the Python client responds with TTS audio.
        response_audio_path = "output2.wav"
        if os.path.exists(response_audio_path):
            logging.info("Sending TTS audio response to device using: %s", response_audio_path)
            await self.send_audio_response(response_audio_path)
        else:
            logging.warning("TTS audio response file not found: %s", response_audio_path)

    async def send_audio_response(self, filename):
        # Read and process the audio file
        with wave.open(filename, 'rb') as wav_file:
            # Log WAV file details
            logging.info("WAV file details: channels=%d, width=%d, rate=%d, frames=%d",
                        wav_file.getnchannels(), wav_file.getsampwidth(),
                        wav_file.getframerate(), wav_file.getnframes())

            frames = wav_file.readframes(wav_file.getnframes())
            audio_data = np.frombuffer(frames, dtype=np.int16)

            # Downsample to 8kHz
            third_samples = audio_data[::3] * GAIN
            logging.info("Processed audio: length=%d samples, min=%d, max=%d",
                        len(third_samples), third_samples.min(), third_samples.max())
            audio_bytes = third_samples.tobytes()

            try:
                # Send size first (use response=False)
                size_bytes = len(audio_bytes).to_bytes(4, byteorder='little')
                logging.info("Sending audio header: total_size=%d bytes", len(audio_bytes))
                await self.client.write_gatt_char(VOICE_INTERACTION_RX_UUID, size_bytes, response=False)
                await asyncio.sleep(0.05)

                # Send audio data in chunks (using response=False)
                for i in range(0, len(audio_bytes), PACKET_SIZE):
                    chunk = audio_bytes[i:i + PACKET_SIZE]
                    await self.client.write_gatt_char(VOICE_INTERACTION_RX_UUID, chunk, response=False)
                    logging.debug("Sent chunk of %d bytes", len(chunk))
                    await asyncio.sleep(0.01)  # Faster sends, but still paced

                    # Add extra delay every N chunks to prevent buffer overflow
                    if i % (PACKET_SIZE * 8) == 0:
                        await asyncio.sleep(0.02)

            except Exception as e:
                print(f"Error sending audio response: {e}")
                if not self.is_connected:
                    await self.reconnect()

    async def activate_speaker_mode(self):
        """Tell the device to switch to speaker mode."""
        try:
            logging.info("Activating speaker mode...")
            await self.client.write_gatt_char(VOICE_CONTROL_UUID, b'\x01', response=True)
            await asyncio.sleep(0.1)  # Small delay to let device switch modes
            logging.info("Speaker mode activated")
        except Exception as e:
            logging.error(f"Failed to activate speaker mode: {e}")
            raise

    async def run(self):
        try:
            await self.connect()
            while True:
                if not self.is_connected:
                    await self.connect()
                await asyncio.sleep(1)
        except Exception as e:
            print(f"Error: {e}")
        finally:
            if self.client and self.client.is_connected:
                await self.client.disconnect()

async def stream_audio(voice_client: VoiceInteractionClient, voice_char: str):
    # Get the low-level BleakClient from voice_client.
    client = voice_client.client

    # Simulate a total audio length (in bytes) for the audio stream.
    total_length = 32000
    # Create header packet: 4-byte little-endian integer.
    header = struct.pack("<I", total_length)
    logging.info("Sending header, expecting %u bytes", total_length)
    await client.write_gatt_char(voice_char, header, response=False)

    # Now send audio data in chunks.
    chunk_size = 500  # adjust as needed
    dummy_audio = b'\x00' * chunk_size  # simulate audio data (in a real scenario, use real audio)
    bytes_sent = 0
    while bytes_sent < total_length:
        await client.write_gatt_char(voice_char, dummy_audio, response=False)
        bytes_sent += chunk_size
        logging.info("Sent %u of %u bytes", bytes_sent, total_length)
        await asyncio.sleep(0.1)  # pacing delay; adjust based on actual streaming rate

    logging.info("Audio stream complete. Initiating simulated transcription...")
    # Simulate that the host "records" the sent audio.
    voice_client.audio_data = dummy_audio * (total_length // chunk_size)
    await asyncio.sleep(0.5)
    await voice_client.process_voice_command()

async def main():
    voice_client = VoiceInteractionClient()
    await voice_client.connect()

    try:
        print("\nTesting TTS playback flow:")
        print("1. Activate speaker mode")
        print("2. Send TTS audio (output2.wav)")
        input("Press ENTER to start...")

        # First activate speaker mode
        await voice_client.activate_speaker_mode()

        # Then send the TTS audio
        await voice_client.send_audio_response("output2.wav")

        print("Test complete. Check device logs for playback confirmation.")
        await asyncio.sleep(2)
    except Exception as e:
        print(f"Error during test: {e}")
    finally:
        if voice_client.client and voice_client.client.is_connected:
            await voice_client.client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
