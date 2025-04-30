import asyncio
import logging
from asyncio import Queue

from bleak.exc import BleakDeviceNotFoundError
from easy_audio_interfaces.extras.local_audio import OutputSpeakerStream
from easy_audio_interfaces.types.common import AudioSegment
from omi.bluetooth import listen_to_omi
from omi.decoder import OmiOpusDecoder

logger = logging.getLogger(__name__)

OMI_MAC = "C67EDFB1-56C8-7A6F-0776-7303E8F697AF"
OMI_CHAR_UUID = "19B10001-E8F2-537E-4F6C-D104768A1214"


def main():
    audio_queue: Queue[bytes] = Queue()
    decoder = OmiOpusDecoder()

    def handle_ble_data(sender, data):
        decoded_pcm = decoder.decode_packet(data)
        if decoded_pcm is not None: # Check if decoding was successful
            try:
                audio_queue.put_nowait(decoded_pcm)
            except asyncio.QueueFull:
                logger.warning("Audio queue full, dropping packet for transcription.")
            except Exception as e:
                logger.error(f"Queue Error putting to audio_queue: {e}")

    async def start_server(audio_queue: Queue[bytes]):
        output_speaker = OutputSpeakerStream()

        async with output_speaker:
            while True:
                audio = await audio_queue.get()
                output_speaker.write(AudioSegment(audio, frame_rate=16000, sample_width=2, channels=1))
                
    async def run():
        try:
            await asyncio.gather(
                listen_to_omi(OMI_MAC, OMI_CHAR_UUID, handle_ble_data),
                start_server(audio_queue)
            )
        except BleakDeviceNotFoundError as e:
            logger.error(f"Device not found: {e}")
            exit(1)
        except Exception as e:
            logger.error(f"Error in run: {e}")
            raise e


    asyncio.run(run())


if __name__ == "__main__":
    main()
