import asyncio
import logging
import os
import time
import wave
from asyncio import Queue

import numpy as np
from omi.bluetooth import listen_to_omi
from omi.decoder import OmiOpusDecoder
from omi.transcribe import transcribe, transcribe_wyoming

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# OMI_MAC = "8680354F-04B6-6281-8CA4-D987E07D1065"
OMI_MAC = "C67EDFB1-56C8-7A6F-0776-7303E8F697AF"
OMI_CHAR_UUID = "19B10001-E8F2-537E-4F6C-D104768A1214"

# --- Audio Saving Constants ---
SAVE_INTERVAL = 10  # seconds
SAVE_DIR = "saved_audio"
SAMPLE_RATE = 16000 # Assuming 16kHz
CHANNELS = 1
SAMPLE_WIDTH = 2 # Assuming 16-bit = 2 bytes
# --- End Audio Saving Constants ---

os.makedirs(SAVE_DIR, exist_ok=True) # Create save directory

# Global buffer and timer for saving audio
audio_save_buffer: list[np.ndarray] = []
last_save_time = time.monotonic()
save_lock = asyncio.Lock() # Lock to prevent race condition in saving

async def save_audio_periodically():
    """Periodically saves buffered audio chunks to a WAV file."""
    global audio_save_buffer, last_save_time
    print("Starting periodic audio saving task...")
    while True:
        await asyncio.sleep(0.5) # Check less frequently
        current_time = time.monotonic()
        
        if current_time - last_save_time >= SAVE_INTERVAL:
            async with save_lock:
                # Double-check condition inside lock
                if current_time - last_save_time >= SAVE_INTERVAL and audio_save_buffer:
                    logger.info(f"Save interval reached. Current audio_save_buffer size: {len(audio_save_buffer)}") # DEBUG
                    # Grab the current buffer and reset
                    buffer_to_save = audio_save_buffer.copy()
                    audio_save_buffer.clear()
                    last_save_time = current_time # Reset timer only when saving

                    logger.info(f"Saving {len(buffer_to_save)} audio chunks...")
                    try:
                        # Concatenate PCM data (assuming it's numpy arrays)
                        pcm_data_to_save = np.concatenate(buffer_to_save)
                        logger.info(f"Concatenated PCM data shape: {pcm_data_to_save.shape}") # DEBUG
                        
                        # Generate filename
                        timestamp = time.strftime("%Y%m%d_%H%M%S")
                        filename = os.path.join(SAVE_DIR, f"audio_{timestamp}.wav")
                        
                        # Save as WAV file
                        with wave.open(filename, 'wb') as wf:
                            wf.setnchannels(CHANNELS)
                            wf.setsampwidth(SAMPLE_WIDTH)
                            wf.setframerate(SAMPLE_RATE)
                            wf.writeframes(pcm_data_to_save.tobytes())
                        logger.info(f"Saved audio to {filename}")
                        
                    except Exception as e:
                        logger.error(f"Error saving audio chunk: {e}")
                elif not audio_save_buffer:
                        # Reset timer even if buffer is empty to avoid immediate re-check
                        last_save_time = current_time 
                        logger.debug("Save interval reached, but no audio data to save.")

def main():
    # api_key = os.getenv("DEEPGRAM_API_KEY")
    # if not api_key:
    #     print("Set your Deepgram API Key in the DEEPGRAM_API_KEY environment variable.")
    #     return

    audio_queue = Queue()
    decoder = OmiOpusDecoder()

    def handle_ble_data(sender, data):
        global audio_save_buffer # Need to modify the global buffer
        decoded_pcm = decoder.decode_packet(data)
        if decoded_pcm is not None: # Check if decoding was successful
            # Put data into queue for transcription
            try:
                audio_queue.put_nowait(decoded_pcm)
            except asyncio.QueueFull:
                logger.warning("Audio queue full, dropping packet for transcription.")
            except Exception as e:
                logger.error(f"Queue Error putting to audio_queue: {e}")
            
            # Append data to buffer for saving
            audio_save_buffer.append(np.frombuffer(decoded_pcm, dtype=np.int16))
        else: # DEBUG
            logger.warning("Decoded PCM is None, not adding to save buffer.") # DEBUG

    async def run():
        await asyncio.gather(
            listen_to_omi(OMI_MAC, OMI_CHAR_UUID, handle_ble_data),
            # transcribe_wyoming(audio_queue, "tcp://192.168.0.110:10300"),
            transcribe_wyoming(audio_queue, "tcp://0.tcp.in.ngrok.io:13156"),
            save_audio_periodically()
        )

    asyncio.run(run())

if __name__ == '__main__':
    main()
