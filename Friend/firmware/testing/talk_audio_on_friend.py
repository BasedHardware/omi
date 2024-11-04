import asyncio
import bleak
import wave
import numpy as np
from bleak import BleakClient
from deepgram import DeepgramClient, SpeakOptions
import os
from dotenv import load_dotenv

load_dotenv()

# Configuration
DEVICE_ID = "817D48F6-FAF0-A566-D013-D05916B5D7B8"  # Your device ID
DEEPGRAM_API_KEY = "f2e9ebf2f223ae423c88bf601ce1a157699d3005"  # Your Deepgram API key
BUTTON_READ_UUID = "23BA7925-0000-1000-7450-346EAC492E92"  # Button characteristic

# Updated UUIDs to match firmware
VOICE_INTERACTION_UUID = "19B10004-E8F2-537E-4F6C-D104768A1214"  # Voice data characteristic for sending audio to cloud
VOICE_INTERACTION_RX_UUID = "19B10005-E8F2-537E-4F6C-D104768A1214"  # Voice response characteristic for receiving TTS audio

# Button states
SINGLE_TAP = 1
DOUBLE_TAP = 2
LONG_TAP = 3
BUTTON_PRESS = 4
BUTTON_RELEASE = 5

# Audio settings
MAX_ALLOWED_SAMPLES = 50000
GAIN = 5
PACKET_SIZE = 400

class VoiceInteractionClient:
    def __init__(self):
        self.audio_data = bytearray()
        self.is_recording = False
        self.deepgram = DeepgramClient(api_key=DEEPGRAM_API_KEY)
        self.client = None
        self.is_connected = False

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
        print(f"Button state: {button_state}")

        if button_state == DOUBLE_TAP:
            print("Starting voice recording...")
            self.is_recording = True
            self.audio_data = bytearray()
        elif button_state == BUTTON_RELEASE and self.is_recording:
            print("Stopping voice recording...")
            self.is_recording = False
            asyncio.create_task(self.process_voice_command())

    def on_voice_data(self, sender, data):
        if self.is_recording:
            # Skip the first 3 bytes (header)
            self.audio_data.extend(data[3:])
            print(f"Received {len(data)} bytes of audio data")

    async def process_voice_command(self):
        if len(self.audio_data) == 0:
            print("No audio data recorded")
            return

        # Save audio data to temporary WAV file
        with wave.open('temp_input.wav', 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(8000)
            wav_file.writeframes(self.audio_data)

        # Process with Deepgram
        try:
            # First, convert audio to text
            # TODO: Add Deepgram STT here
            text_prompt = "This is a test response"  # Replace with actual STT result
            print(f"Processing voice command: {text_prompt}")

            # Generate response audio
            options = SpeakOptions(
                model="aura-stella-en",
                encoding="linear16",
                container="wav"
            )

            print("Generating audio response...")
            response = self.deepgram.speak.v("1").save("temp_output.wav",
                                                      {"text": f"You said: {text_prompt}"},
                                                      options)

            # Process and send the audio response
            print("Sending audio response...")
            await self.send_audio_response("temp_output.wav")

        except Exception as e:
            print(f"Error processing voice command: {e}")

    async def send_audio_response(self, filename):
        # Read and process the audio file
        with wave.open(filename, 'rb') as wav_file:
            frames = wav_file.readframes(wav_file.getnframes())
            audio_data = np.frombuffer(frames, dtype=np.int16)

            # Downsample to 8kHz
            third_samples = audio_data[::3] * GAIN
            audio_bytes = third_samples.tobytes()

            try:
                # Send size first
                size_bytes = len(audio_bytes).to_bytes(4, byteorder='little')
                await self.client.write_gatt_char(VOICE_INTERACTION_RX_UUID, size_bytes, response=True)
                await asyncio.sleep(0.1)

                # Send audio data in chunks
                for i in range(0, len(audio_bytes), PACKET_SIZE):
                    chunk = audio_bytes[i:i + PACKET_SIZE]
                    await self.client.write_gatt_char(VOICE_INTERACTION_RX_UUID, chunk, response=True)
                    print(f"Sent chunk of {len(chunk)} bytes")
                    await asyncio.sleep(0.01)

            except Exception as e:
                print(f"Error sending audio response: {e}")
                if not self.is_connected:
                    await self.reconnect()

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

async def main():
    client = VoiceInteractionClient()
    await client.run()

if __name__ == "__main__":
    asyncio.run(main())
