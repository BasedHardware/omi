import asyncio
import uuid
from bleak import BleakScanner, BleakClient
from .models import Friend

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