import wave
import logging

from pydub import AudioSegment
from pyogg import OpusDecoder

logger = logging.getLogger(__name__)

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

        corrupted_frames = 0
        total_frames = len(encoded_packets)
        
        for i, encoded_packet in enumerate(encoded_packets):
            try:
                decoded_pcm = opus_decoder.decode(encoded_packet)
                # Save the decoded PCM as a new wav file
                wave_write.writeframes(decoded_pcm)
            except Exception as e:
                corrupted_frames += 1
                logger.warning(f"Failed to decode Opus frame {i}/{total_frames}: {e}")
                
                # Try to recover by inserting silence
                try:
                    # Create silence frame (zeros) for the expected frame size
                    silence_frame = b'\x00' * (frame_rate * channels * sample_width // 50)  # 20ms of silence
                    wave_write.writeframes(silence_frame)
                except Exception as recovery_error:
                    logger.error(f"Failed to insert silence frame: {recovery_error}")
                    continue

        wave_write.close()
        
        if corrupted_frames > 0:
            logger.warning(f"Decoded {total_frames - corrupted_frames}/{total_frames} frames successfully. {corrupted_frames} corrupted frames replaced with silence.")
        
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
