import asyncio
import bleak
from bleak import BleakClient
import wave
from datetime import datetime
import numpy as np
import time

DEVICE_ID = "8901A373-2BC5-AEDB-077B-C2786C3F3C43"
SERVICE_UUID = "19B10000-E8F2-537E-4F6C-D104768A1214"
CHARACTERISTIC_UUID = "19B10001-E8F2-537E-4F6C-D104768A1214"
SAMPLE_RATE = 4000  # Sample rate for the audio
SAMPLE_WIDTH = 2  # 16-bit audio
CHANNELS = 1  # Mono audio


async def main():
    print("Discovering AudioRecorder...")
    devices = await bleak.discover(timeout=2.0)
    audio_recorder = None
    for device in devices:
        if device.name:
            print(device.name, device.address)
        if device.address == DEVICE_ID:
            audio_recorder = device
            break
    
    if not audio_recorder:
        print("AudioRecorder not found")
        return
    def handle_ble_disconnect(client):
        print("Disconnected from AudioRecorder")

    def filter_audio_data(audio_data):
        audio_data = np.frombuffer(audio_data, dtype=np.uint16)
        audio_data -= 32768
        scaling_factor = 2*32768 / (max(0, np.max(audio_data)) - min(0, np.min(audio_data)))
        return (audio_data * scaling_factor).astype(np.int16)
    
    def export_audio_data(filtered_audio_data, file_extension):
        filename = datetime.now().strftime("%H-%M-%S-%f") + file_extension
        print(filename)
        if file_extension == ".txt":
            with open(filename, "w") as file:
                file.write(str(list(filtered_audio_data)))
        else:
            # Directly use the filename with wave.open for .wav files
            with wave.open(filename, "wb") as wav_file:
                wav_file.setnchannels(CHANNELS)
                wav_file.setsampwidth(SAMPLE_WIDTH)
                wav_file.setframerate(SAMPLE_RATE)
                wav_file.writeframes(filtered_audio_data.tobytes())  # Ensure data is in bytes format

    async with BleakClient(audio_recorder.address, services=[SERVICE_UUID], disconnect_callback=handle_ble_disconnect) as client:
        print("Connected to AudioRecorder")
        services = await client.get_services()
        audio_service = services.get_service(SERVICE_UUID)
        audio_characteristic = audio_service.get_characteristic(CHARACTERISTIC_UUID)

        audio_data = bytearray()
        end_signal = b"\xFF"

        def handle_audio_data(sender, data):
            print(f"Received {len(data)} bytes at {time.time()}")
            audio_data.extend(data)
            if data == [end_signal]:
                print(f"End signal received after {len(audio_data)} bytes")
            

        await client.start_notify(audio_characteristic.uuid, handle_audio_data)
        print("Recording audio...")
        await asyncio.sleep(60)  # Wait for 10 seconds
        await client.stop_notify(audio_characteristic.uuid)
        print("Recording stopped")
    
    filtered_audio_data = filter_audio_data(audio_data)
    export_audio_data(filtered_audio_data, ".wav")
    export_audio_data(filtered_audio_data, ".txt")
    audio_data.clear()

asyncio.run(main())

