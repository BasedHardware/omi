import logging
from typing import Any, List

import av
from av.audio.resampler import AudioResampler

logger = logging.getLogger(__name__)

# Suppress FFmpeg duration estimation warnings
av.logging.set_level(av.logging.ERROR)  # type: ignore[reportAttributeAccessIssue,reportUnknownMemberType]  # PyAV exposes logging dynamically


class AACDecoder:

    def __init__(self, uid: str = '', session_id: str = '', sample_rate: int = 16000, channels: int = 1):
        self.uid = uid
        self.session_id = session_id

        # Initialize codec context immediately
        self.codec_context: Any = av.CodecContext.create('aac', 'r')  # type: ignore[reportAttributeAccessIssue,reportUnknownMemberType]  # PyAV CodecContext exposed dynamically

        # Initialize resampler immediately
        target_layout = 'mono' if channels == 1 else 'stereo'
        self.resampler: Any = AudioResampler(
            format='s16',  # type: ignore[reportArgumentType]  # PyAV accepts str format aliases
            layout=target_layout,  # type: ignore[reportArgumentType]  # PyAV accepts str layout aliases
            rate=sample_rate,
        )

    def decode(self, aac_data: bytes) -> bytes:
        """Decode AAC frame using persistent codec context.

        Args:
            aac_data: Complete AAC frame with ADTS header

        Returns:
            PCM data as bytes
        """
        if not aac_data:
            return b''

        try:
            # Create packet and decode
            packet = av.Packet(aac_data)  # type: ignore[reportArgumentType]  # PyAV Packet accepts bytes at runtime
            frames: List[Any] = self.codec_context.decode(packet)

            if not frames:
                return b''

            # Resample and collect PCM data
            pcm_chunks: List[bytes] = []
            for frame in frames:
                resampled_frames: List[Any] = self.resampler.resample(frame)
                for resampled_frame in resampled_frames:
                    frame_array: Any = resampled_frame.to_ndarray()
                    if frame_array.ndim > 1:
                        frame_array = frame_array.T.flatten()
                    pcm_chunks.append(frame_array.tobytes())

            return b''.join(pcm_chunks)

        except (EOFError, av.AVError):  # type: ignore[reportAttributeAccessIssue,reportUnknownMemberType]  # PyAV exposes AVError dynamically
            # Expected for incomplete frames, return empty
            return b''
        except Exception as e:
            logger.error(f"[AAC] Decode error: {e} {self.uid} {self.session_id}")
            return b''
