"""Offline built-image batch decode probe (no model or audio codec loading)."""

import io
import sys
import subprocess
import wave
from unittest.mock import patch

import torch  # type: ignore[reportMissingImports]  # GPU image dependency
import torchaudio  # type: ignore[reportMissingImports]  # GPU image dependency

from final_pass import decode_audio


def run_smoke():
    # The deployed entrypoints are imported separately by the image registry.
    # Exercise the real tensor path without FFmpeg/TorchCodec or pretrained models.
    with (
        patch.dict(sys.modules, {'torchcodec': None, 'torchcodec.decoders': None}),
        patch.object(torchaudio, 'load', side_effect=AssertionError('file codec invoked')),
        patch.object(subprocess, 'Popen', side_effect=AssertionError('external decoder invoked')),
    ):
        pcm = b'\x00\x00\xff\x7f\x00\x80'
        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(16000)
            handle.writeframes(pcm)
        raw = decode_audio(pcm, 'audio/pcm')
        wav = decode_audio(buffer.getvalue(), 'audio/wav')
        assert tuple(raw.shape) == (1, 3)
        assert torch.equal(raw, wav)
        assert raw.tolist() == [[0.0, 32767 / 32768, -1.0]]
