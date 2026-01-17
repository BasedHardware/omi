import wave
from typing import Optional, Tuple

from pydub import AudioSegment
from pyogg import OpusDecoder


class AudioRingBuffer:
    """Circular buffer storing last N seconds of PCM16 mono audio with timestamp tracking."""

    def __init__(self, duration_seconds: float, sample_rate: int):
        self.sample_rate = sample_rate
        self.bytes_per_second = sample_rate * 2  # PCM16 mono
        self.capacity = int(duration_seconds * self.bytes_per_second)
        self.buffer = bytearray(self.capacity)
        self.write_pos = 0
        self.total_bytes_written = 0
        self.last_write_timestamp: Optional[float] = None

    def write(self, data: bytes, timestamp: float):
        """Append audio data with timestamp."""
        for byte in data:
            self.buffer[self.write_pos] = byte
            self.write_pos = (self.write_pos + 1) % self.capacity
        self.total_bytes_written += len(data)
        self.last_write_timestamp = timestamp

    def get_time_range(self) -> Optional[Tuple[float, float]]:
        """Return (start_ts, end_ts) of audio currently in buffer."""
        if self.last_write_timestamp is None:
            return None
        bytes_in_buffer = min(self.total_bytes_written, self.capacity)
        buffer_duration = bytes_in_buffer / self.bytes_per_second
        return (self.last_write_timestamp - buffer_duration, self.last_write_timestamp)

    def extract(self, start_ts: float, end_ts: float) -> Optional[bytes]:
        """Extract audio for absolute timestamp range."""
        time_range = self.get_time_range()
        if time_range is None:
            return None

        buffer_start_ts, buffer_end_ts = time_range
        actual_start = max(start_ts, buffer_start_ts)
        actual_end = min(end_ts, buffer_end_ts)

        if actual_start >= actual_end:
            return None

        bytes_in_buffer = min(self.total_bytes_written, self.capacity)
        buffer_logical_start = (self.write_pos - bytes_in_buffer) % self.capacity

        start_offset = int((actual_start - buffer_start_ts) * self.bytes_per_second)
        end_offset = int((actual_end - buffer_start_ts) * self.bytes_per_second)

        # Ensure even number of bytes (PCM16)
        length = ((end_offset - start_offset) // 2) * 2
        if length <= 0:
            return None

        result = bytearray(length)
        for i in range(length):
            pos = (buffer_logical_start + start_offset + i) % self.capacity
            result[i] = self.buffer[pos]

        return bytes(result)


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
