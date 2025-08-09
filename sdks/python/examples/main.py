import asyncio
import os
from typing import Any
from omi.bluetooth import listen_to_omi
from omi.transcribe import transcribe
from omi.decoder import OmiOpusDecoder
from asyncio import Queue

# Replace with your Omi device's MAC address (get it by running: omi-scan)
OMI_MAC = "C9DDDACB-CA1E-CDD6-7A17-59A2A5303CDA"  
# Standard Omi audio characteristic UUID
OMI_CHAR_UUID = "19B10001-E8F2-537E-4F6C-D104768A1214"

def main() -> None:
    api_key: str | None = os.getenv("DEEPGRAM_API_KEY")
    if not api_key:
        print("Set your Deepgram API Key in the DEEPGRAM_API_KEY environment variable.")
        return

    audio_queue: Queue[bytes] = Queue()
    decoder = OmiOpusDecoder()

    def handle_ble_data(sender: Any, data: bytes) -> None:
        decoded_pcm: bytes = decoder.decode_packet(data)
        if decoded_pcm:
            try:
                audio_queue.put_nowait(decoded_pcm)
            except Exception as e:
                print("Queue Error:", e)
                

    async def run() -> None:
        await asyncio.gather(
            listen_to_omi(OMI_MAC, OMI_CHAR_UUID, handle_ble_data),
            transcribe(audio_queue, api_key)  # Uses default console output
        )

    asyncio.run(run())

if __name__ == '__main__':
    main()
