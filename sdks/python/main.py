import asyncio
import os
from omi.bluetooth import listen_to_omi
from omi.transcribe import transcribe
from omi.decoder import OmiOpusDecoder
from asyncio import Queue

OMI_MAC = "8680354F-04B6-6281-8CA4-D987E07D1065"
OMI_CHAR_UUID = "19B10001-E8F2-537E-4F6C-D104768A1214"

def main():
    api_key = os.getenv("DEEPGRAM_API_KEY")
    if not api_key:
        print("Set your Deepgram API Key in the DEEPGRAM_API_KEY environment variable.")
        return

    audio_queue = Queue()
    decoder = OmiOpusDecoder()

    def handle_ble_data(sender, data):
        decoded_pcm = decoder.decode_packet(data)
        if decoded_pcm:
            try:
                audio_queue.put_nowait(decoded_pcm)
            except Exception as e:
                print("Queue Error:", e)

    async def run():
        await asyncio.gather(
            listen_to_omi(OMI_MAC, OMI_CHAR_UUID, handle_ble_data),
            transcribe(audio_queue, api_key)
        )

    asyncio.run(run())

if __name__ == '__main__':
    main()
