import asyncio
import wave
import os
from datetime import datetime
from bleak import BleakClient, BleakScanner
import opuslib
import sounddevice as sd
import soundfile as sf

# Device settings
DEVICE_NAME = "Friend"

# UUIDs from the Dart code
SERVICE_UUID = "19b10000-e8f2-537e-4f6c-d104768a1214"
AUDIO_DATA_SEND_STREAM_UUID = "19b10001-e8f2-537e-4f6c-d104768a1214"
AUDIO_DATA_RECEIVE_STREAM_UUID = "19b10003-e8f2-537e-4f6c-d104768a1214"
AUDIO_CODEC_UUID = "19b10002-e8f2-537e-4f6c-d104768a1214"

# Audio settings
SAMPLE_RATE = 16000  # Adjust as per your device's specifications
CHANNELS = 1  # Adjust as per your device's specifications
SAMPLE_WIDTH = 2  # Adjust as per your device's specifications
DURATION = 10  # Duration in seconds
RECORD_DIR = "records"

if not os.path.exists(RECORD_DIR):
    os.makedirs(RECORD_DIR)

audio_frames = []


class FrameProcessor:
    def __init__(self, sample_rate, channels):
        self.opus_decoder = opuslib.Decoder(sample_rate, channels)
        self.opus_encoder = opuslib.Encoder(sample_rate, channels, opuslib.APPLICATION_AUDIO)
        self.last_packet_index = -1
        self.last_frame_id = -1
        self.pending = bytearray()
        self.lost = 0

    def store_frame_packet(self, data):
        index = data[0] + (data[1] << 8)
        internal = data[2]
        content = data[3:]

        if self.last_packet_index == -1 and internal == 0:
            self.last_packet_index = index
            self.last_frame_id = internal
            self.pending = content
            return

        if self.last_packet_index == -1:
            return

        if index != self.last_packet_index + 1 or (
            internal != 0 and internal != self.last_frame_id + 1
        ):
            print("Lost frame")
            self.last_packet_index = -1
            self.pending = bytearray()
            self.lost += 1
            return

        if internal == 0:
            audio_frames.append(self.pending)  # Save frame
            self.pending = content  # Start new frame
            self.last_frame_id = internal  # Update internal frame id
            self.last_packet_index = index  # Update packet id
            return

        self.pending.extend(content)
        self.last_frame_id = internal  # Update internal frame id
        self.last_packet_index = index  # Update packet id

    def decode_frames(self):
        pcm_data = bytearray()
        frame_size = 960  # Adjust frame size as per Opus settings (e.g., 960 for 20ms frames at 48kHz)

        for frame in audio_frames:
            try:
                decoded_frame = self.opus_decoder.decode(bytes(frame), frame_size)
                pcm_data.extend(decoded_frame)
            except Exception as e:
                print(f"Error decoding frame: {e}")
        return pcm_data

    def encode_audio(self, pcm_data):
        try:
            encoded_data = self.opus_encoder.encode(pcm_data, frame_size=960)
            return encoded_data
        except Exception as e:
            print(f"Error encoding frame: {e}")
            return None


frame_processor = FrameProcessor(SAMPLE_RATE, CHANNELS)


async def find_device_by_name(name=DEVICE_NAME):
    devices = await BleakScanner.discover()
    if not devices:
        print("No Bluetooth devices found.")
        return None

    print("Found devices:")
    for device in devices:
        print(f"Name: {device.name}, Address: {device.address}")

    for device in devices:
        if name in device.name:
            return device
    return None


async def audio_data_handler(sender, data):
    frame_processor.store_frame_packet(data)
    pcm_data = frame_processor.decode_frames()
    if pcm_data:
        try:
            sd.play(pcm_data, samplerate=SAMPLE_RATE, channels=CHANNELS)
        except Exception as e:
            print(f"Playback error: {e}")


async def receive_and_play(client):
    await client.start_notify(AUDIO_DATA_SEND_STREAM_UUID, audio_data_handler)

    try:
        while True:
            await asyncio.sleep(DURATION)
    finally:
        await client.stop_notify(AUDIO_DATA_SEND_STREAM_UUID)


async def record_and_send(client):
    while True:
        # Record audio in small chunks for continuous streaming
        recording = sd.rec(int(SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=CHANNELS, dtype='int16')
        sd.wait()  # Wait for the recording to finish
        pcm_data = recording.tobytes()
        encoded_data = frame_processor.encode_audio(pcm_data)

        if encoded_data:
            await client.write_gatt_char(AUDIO_DATA_RECEIVE_STREAM_UUID, encoded_data)

        # Save the PCM data to a WAV file periodically
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        audio_file = os.path.join(RECORD_DIR, f"audio_data_{timestamp}.wav")
        with wave.open(audio_file, "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(SAMPLE_WIDTH)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(pcm_data)
        print(f"Audio data saved to {audio_file}")

        await asyncio.sleep(1)  # Adjust the delay for pacing


async def connect_to_device(device):
    def disconnect_handler(client):
        print("Device disconnected")
        asyncio.get_event_loop().stop()

    async with BleakClient(device, disconnected_callback=disconnect_handler) as client:
        print(f"Connected: {client.is_connected}")

        # Run both tasks concurrently
        await asyncio.gather(receive_and_play(client), record_and_send(client))


async def main():
    device = await find_device_by_name()
    if device is None:
        print("Device with the name 'Friend' not found.")
        return

    await connect_to_device(device)


try:
    asyncio.run(main())
except Exception as e:
    print(f"Error: {e}")
