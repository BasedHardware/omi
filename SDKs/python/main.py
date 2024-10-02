import asyncio
import uuid
from bleak import BleakScanner, BleakClient
from datetime import datetime

class Friend:
    def __init__(self, device):
        self.id = device.address
        self.name = device.name

class OmiManager:
    @staticmethod
    async def start_scan(callback):
        def detection_callback(device, advertisement_data):
            if device.name and "Omi" in device.name:
                friend = Friend(device)
                asyncio.create_task(callback(friend, None))

        scanner = BleakScanner()
        scanner.register_detection_callback(detection_callback)
        await scanner.start()

    @staticmethod
    async def end_scan():
        scanner = BleakScanner()
        await scanner.stop()

    @staticmethod
    async def connect_to_device(device):
        client = BleakClient(device.id)
        await client.connect()
        return client

    @staticmethod
    async def connection_updated(client, callback):
        def disconnected_callback(client):
            asyncio.create_task(callback(False))

        client.set_disconnected_callback(disconnected_callback)

    @staticmethod
    async def get_live_transcription(client, callback):
        # Assuming the characteristic UUID for transcription
        TRANSCRIPTION_UUID = "12345678-1234-5678-1234-56789abcdef0"
        
        def notification_handler(sender, data):
            transcription = data.decode()
            asyncio.create_task(callback(transcription))

        await client.start_notify(TRANSCRIPTION_UUID, notification_handler)

    @staticmethod
    async def get_live_audio(client, callback):
        # Assuming the characteristic UUID for audio
        AUDIO_UUID = "87654321-4321-8765-4321-fedcba987654"
        
        def notification_handler(sender, data):
            # Here you'd need to implement logic to save the audio data to a file
            # and return the file URL
            file_url = f"/tmp/audio_{uuid.uuid4()}.wav"
            with open(file_url, "wb") as f:
                f.write(data)
            asyncio.create_task(callback(file_url))

        await client.start_notify(AUDIO_UUID, notification_handler)

class RootVC:
    def __init__(self):
        self.full_transcript = ""
        self.client = None

    async def look_for_device(self):
        await OmiManager.start_scan(self.on_device_found)

    async def look_for_specific_device(self, device_id):
        async def callback(device, error):
            if device.id == device_id:
                await self.connect_to_omi_device(device)

        await OmiManager.start_scan(callback)

    async def on_device_found(self, device, error):
        if device:
            print(f"Got device {device.id}")
            await self.connect_to_omi_device(device)
            await OmiManager.end_scan()

    async def connect_to_omi_device(self, device):
        self.client = await OmiManager.connect_to_device(device)
        await self.reconnect_if_disconnects()

    async def reconnect_if_disconnects(self):
        async def on_disconnect(connected):
            if not connected:
                await self.look_for_device()

        await OmiManager.connection_updated(self.client, on_disconnect)

    async def listen_to_live_transcript(self):
        async def on_transcription(transcription):
            timestamp = self.get_formatted_timestamp(datetime.now())
            self.full_transcript += f"{timestamp}: {transcription}\n\n"
            print(self.full_transcript)
            # Here you'd update your UI or store the transcript

        await OmiManager.get_live_transcription(self.client, on_transcription)

    async def listen_to_live_audio(self):
        async def on_audio(file_url):
            print(f"File URL: {file_url}")

        await OmiManager.get_live_audio(self.client, on_audio)

    @staticmethod
    def get_formatted_timestamp(date):
        return date.strftime("%Y-%m-%d %H:%M:%S")

async def main():
    root_vc = RootVC()
    await root_vc.look_for_device()
    # Keep the program running
    while True:
        await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
