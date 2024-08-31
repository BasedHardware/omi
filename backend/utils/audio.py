import io
import opuslib
from pydub import AudioSegment


# frames is 2darray
def create_wav_from_bytes(file_path: str, frames: [], codec: str, frame_rate: int = 16000, channels: int = 1, sample_width: int = 2):
    # decode
    dec = opuslib.api.decoder.create_state(frame_rate, channels)
    pcm_buffer = _decode(frames, codec, frame_rate, channels, sample_width)

    cn = AudioSegment.from_raw(
        io.BytesIO(pcm_buffer),
        sample_width=sample_width,
        channels=channels,
        frame_rate=frame_rate,
    )

    cn.export(file_path, format="wav")

def _decode(frames: [], codec: str, frame_rate: int = 16000, channels: int = 1, sample_width: int = 2):
    if codec == "opus":
        # decode
        dec = opuslib.api.decoder.create_state(frame_rate, channels)
        pcm_buffer = bytearray()
        for frame in frames:
            audio_buffer = bytes(frame)
            try:
                i_pcm_buffer = opuslib.api.decoder.decode(dec, audio_buffer, len(audio_buffer), 1920, 0)
                pcm_buffer.extend(i_pcm_buffer)
            except opuslib.OpusError as e:
                print(f'Decode failed {e}')
        opuslib.api.decoder.destroy(dec)

        return pcm_buffer

    # else
    pcm_buffer = bytearray()
    for frame in frames:
        pcm_buffer.extend(frame)
