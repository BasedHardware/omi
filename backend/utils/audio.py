import wave
import logging
from pydub import AudioSegment

# Import our PyOgg wrapper
from utils.pyogg_wrapper import get_opus_decoder

# Try to import PyOgg, and if it fails, create a mock implementation
try:
    # Use our wrapper to get a patched OpusDecoder
    OpusDecoder = get_opus_decoder().__class__
    PYOGG_AVAILABLE = True
    print("✅ PyOgg OpusDecoder successfully imported and available for use")
except (ImportError, AttributeError, TypeError) as e:
    logging.warning(f"PyOgg import failed: {e}. Opus codec will not be available.")
    print(f"❌ PyOgg import failed: {e}. Opus codec will not be available.")
    PYOGG_AVAILABLE = False

    # Mock OpusDecoder class
    class OpusDecoder:
        def __init__(self):
            logging.warning("Using mock OpusDecoder. Opus codec functionality is limited.")

        def set_channels(self, channels):
            pass

        def set_sampling_frequency(self, freq):
            pass

        def decode(self, packet):
            # Return empty bytes as we can't actually decode
            return b''


def merge_wav_files(dest_file_path: str, source_files: [str], silent_seconds: [int]):
    if len(source_files) == 0 or not dest_file_path:
        return

    combined_sounds = AudioSegment.empty()
    for i in range(len(source_files)):
        file_path = source_files[i]
        sound = AudioSegment.from_wav(file_path)
        silent_sec = silent_seconds[i]
        combined_sounds = combined_sounds + sound + AudioSegment.silent(duration=silent_sec)
    combined_sounds.export(dest_file_path, format="wav")


# frames is 2darray
def create_wav_from_bytes(
        file_path: str, frames: [], codec: str, frame_rate: int = 16000, channels: int = 1, sample_width: int = 2
):
    # opus
    if codec == "opus":
        if not PYOGG_AVAILABLE:
            logging.error("Cannot process opus codec: PyOgg is not available")
            raise Exception("Opus codec is not available due to PyOgg import issues")

        # Create an Opus decoder
        opus_decoder = OpusDecoder()
        opus_decoder.set_channels(channels)
        opus_decoder.set_sampling_frequency(frame_rate)

        wave_write = wave.open(file_path, "wb")
        # Save the wav's specification
        wave_write.setnchannels(channels)
        wave_write.setframerate(frame_rate)
        wave_write.setsampwidth(sample_width)

        encoded_packets = []
        for frame in frames:
            encoded_packets.append(memoryview(bytearray(frame)))

        for encoded_packet in encoded_packets:
            decoded_pcm = opus_decoder.decode(encoded_packet)

            # Save the decoded PCM as a new wav file
            wave_write.writeframes(decoded_pcm)

        wave_write.close()

        return

    # pcm16
    if codec == "pcm16":
        wave_write = wave.open(file_path, "wb")
        # Save the wav's specification
        wave_write.setnchannels(channels)
        wave_write.setframerate(frame_rate)
        wave_write.setsampwidth(sample_width)

        for frame in frames:
            decoded_pcm = frame
            wave_write.writeframes(decoded_pcm)

        wave_write.close()
        return

    # pcm8
    if codec == "pcm8":
        wave_write = wave.open(file_path, "wb")
        # Save the wav's specification
        wave_write.setnchannels(channels)
        wave_write.setframerate(frame_rate)
        wave_write.setsampwidth(sample_width)

        for frame in frames:
            decoded_pcm = frame
            wave_write.writeframes(decoded_pcm)

        wave_write.close()
        return

    raise Exception(f"codec {codec} is not supported")
