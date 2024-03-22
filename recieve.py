import asyncio
from bleak import BleakClient, BleakScanner
import wave

device_name = "AudioRecorder"  # The name of your BLE device
uuid = "19B10001-E8F2-537E-4F6C-D104768A1214"  # Audio characteristic UUID
sample_rate = 16000  # Must match the Arduino code
channels = 1  # Mono audio
sampwidth = 2  # Sample width in bytes, matches short in Arduino

async def handle_notification(sender, data):
    # This function will be called on receiving data from the BLE device.
    # Convert binary string back to bytes
    data_bytes = bytearray(int(b, 2) for b in data.decode().split(','))
    frames.append(data_bytes)

async def main():
    while True:
        device = await find_device(device_name)
        if device:
            break
        else:
            print(f"Device {device_name} not found")

    async with BleakClient(device.address) as client:
        # Connect to the device
        await client.connect()
        print(f"Connected to {device_name}")

        # Start notification listener
        await client.start_notify(uuid, handle_notification)

        # Wait for data to be collected
        print("Collecting audio data...")
        await asyncio.sleep(5)  # Adjust as needed based on recording duration

        # Stop notification listener
        await client.stop_notify(uuid)
        print("Stopped listening for notifications.")

        # Save received data as WAV file
        save_wav("output.wav", frames)
        print("Audio data saved as output.wav")

async def find_device(name):
    devices = await BleakScanner.discover()
    for device in devices:
        if device.name == name:
            return device
    return None

def save_wav(filename, frames):
    with wave.open(filename, 'wb') as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sampwidth)
        wf.setframerate(sample_rate)
        for frame in frames:
            wf.writeframes(frame)

frames = []  # List to hold received audio frames
loop = asyncio.get_event_loop()
loop.run_until_complete(main())
