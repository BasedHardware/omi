import logging
import threading
from typing import Any, List

import av
from av.audio.resampler import AudioResampler

logger = logging.getLogger(__name__)

# Suppress FFmpeg duration estimation warnings
av.logging.set_level(av.logging.ERROR)  # type: ignore[reportAttributeAccessIssue,reportUnknownMemberType]  # PyAV exposes logging dynamically


class AACDecodeError(Exception):
    """A frame the AAC decoder rejected.

    The listen receiver's decode-failure contract (``_record_decode_failure``:
    per-frame warning with the codec's own message, streak counter, and the
    one-shot ``silent_mic`` fallback at ``DECODE_FAILURE_STREAK_ALERT``) hangs
    off the decoder *raising*. ``opuslib`` raises ``OpusError``; before this
    class existed, ``AACDecoder.decode`` caught ``av.AVError`` and returned
    ``b''``, so a fully undecodable AAC stream recorded a whole session with
    no transcript, no ring buffer, no fallback metric — and the only trace was
    FFmpeg's context-free ``ERROR:libav.aac:Channel element … is not
    allocated`` native line per frame (~130/30min in prod, Loop S sensor).
    The message is the FFmpeg error verbatim (``Invalid data found when
    processing input data``, ``Input buffer exhausted…``), the same
    codec-owns-the-detail convention the opus path uses.
    """


# FFmpeg re-reports a rejected frame on the ``libav.aac`` Python logger while
# ``AACDecoder.decode`` is still on the stack. That native line is a duplicate
# of the failure this module turns into ``AACDecodeError`` — which the receiver
# reports with codec, type, payload size, streak, and the silent-mic metric —
# so it is dropped for the duration of our own decode call only. Outside this
# window the logger is untouched: other ``av`` users' native errors still flow.
# The flag is thread-local: one session's decode must not mute the native log
# of a concurrent session in the same process.
aac_decode_in_progress = threading.local()


class NativeDuplicateSuppressionFilter(logging.Filter):
    """Drops FFmpeg's re-report of a frame our decode already rejected."""

    def filter(self, record: logging.LogRecord) -> bool:
        return not getattr(aac_decode_in_progress, 'active', False)


logging.getLogger('libav.aac').addFilter(NativeDuplicateSuppressionFilter())


class AACDecoder:

    def __init__(self, uid: str = '', session_id: str = '', sample_rate: int = 16000, channels: int = 1):
        self.uid = uid
        self.session_id = session_id

        # Initialize codec context immediately
        self.codec_context: Any = av.CodecContext.create('aac', 'r')  # type: ignore[reportAttributeAccessIssue,reportUnknownMemberType]  # PyAV exposes logging dynamically

        # Initialize resampler immediately
        target_layout = 'mono' if channels == 1 else 'stereo'
        self.resampler: Any = AudioResampler(
            format='s16',  # type: ignore[reportArgumentType]  # PyAV accepts str format aliases
            layout=target_layout,  # type: ignore[reportArgumentType]  # PyAV accepts str layout aliases
            rate=sample_rate,
        )

    def decode(self, aac_data: bytes) -> bytes:
        """Decode one AAC frame with ADTS header into resampled PCM bytes.

        Raises AACDecodeError when FFmpeg rejects the frame (corrupt, truncated,
        or mid-stream desync — the shapes behind the prod ``libav.aac`` error
        signatures). Callers that keep the socket alive on a dropped frame must
        report the failure (the listen receiver does, via its decode-failure
        streak); swallowing it here is what made corrupt AAC streams silent.

        Returns b'' for benign no-output input: an empty payload, or a packet
        the decoder accepted without emitting frames yet (encoder priming).
        """
        if not aac_data:
            return b''

        try:
            aac_decode_in_progress.active = True
            try:
                packet = av.Packet(aac_data)  # type: ignore[reportArgumentType]  # PyAV Packet accepts bytes at runtime
                frames: List[Any] = self.codec_context.decode(packet)
            finally:
                aac_decode_in_progress.active = False

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

        except (EOFError, av.AVError) as error:  # type: ignore[reportAttributeAccessIssue,reportUnknownMemberType]  # PyAV exposes AVError dynamically
            raise AACDecodeError(
                str(error)
            ) from error  # pyright: ignore[reportUnknownArgumentType]  # av.AVError is partially unknown
