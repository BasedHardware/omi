"""Adapt already-decoded worker audio to the shared strict silence disposition."""

import io
import wave

import numpy as np

from utils.batch_pipeline.recovery_disposition import inspect_audio, silence_payload


def inspect_worker_silence(item, samples):
    # Worker decoding is lossless PCM16 / 32768. Reject other representations
    # rather than quantizing a different signal into false silence evidence.
    samples = np.asarray(samples)
    scaled = samples * 32768
    if (
        samples.ndim != 1
        or not np.isfinite(scaled).all()
        or np.any(scaled < -32768)
        or np.any(scaled > 32767)
        or np.any(scaled != np.rint(scaled))
    ):
        raise ValueError('worker silence requires canonical PCM16 samples')
    output = io.BytesIO()
    with wave.open(output, 'wb') as wav:
        wav.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        wav.writeframes(scaled.astype('<i2').tobytes())
    # Exactly integration's audio validation, local VAD and span validation.
    # No provider, hosted VAD, cache, or account lookup belongs at this seam.
    _, duration, spans = inspect_audio(item, output.getvalue())
    return None if spans else silence_payload(duration)
