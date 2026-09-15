import asyncio
import contextlib
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from omi.transcribe import transcribe


@pytest.mark.parametrize(
    "options, expected_model, expected_language",
    [
        ({}, "tiny.en", "en"),
        ({"model_name": "tiny", "language": "de"}, "tiny", "de"),
        ({"model_name": "tiny", "language": None}, "tiny", None),
    ],
)
def test_whisper_language_through_audio_queue(
    monkeypatch, options, expected_model, expected_language
):
    calls = []
    loaded_models = []

    def model_transcribe(audio, **kwargs):
        calls.append((audio, kwargs))
        return {"text": "  Guten Tag  "}

    def load_model(name):
        loaded_models.append(name)
        return SimpleNamespace(transcribe=model_transcribe)

    monkeypatch.setitem(sys.modules, "whisper", SimpleNamespace(load_model=load_model))

    async def exercise():
        queue = asyncio.Queue()
        # Five seconds of mono s16le PCM, split across two queue entries.
        pcm = b"\x00\x40" * (16000 * 5)
        queue.put_nowait(pcm[:32000])
        queue.put_nowait(pcm[32000:])
        received = asyncio.get_running_loop().create_future()
        task = asyncio.create_task(
            transcribe(
                queue, "", received.set_result, engine="whisper", **options
            )
        )
        try:
            # Surface constructor errors immediately rather than waiting for a timeout.
            done, _ = await asyncio.wait(
                {task, received}, timeout=2, return_when=asyncio.FIRST_COMPLETED
            )
            if task in done:
                await task
            assert received in done, "Whisper did not deliver the queued transcript"
            assert received.result() == "Guten Tag"
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    asyncio.run(exercise())
    assert loaded_models == [expected_model]
    assert len(calls) == 1
    audio, kwargs = calls[0]
    assert audio.shape == (16000 * 5,)
    assert audio.dtype == np.float32
    np.testing.assert_array_equal(audio, 0.5)
    assert kwargs == {"fp16": False, "language": expected_language}


def test_whisper_runner_keeps_bytes_only_contract():
    from omi.stt import create_transcriber

    chunks = []

    def runner(pcm):
        chunks.append(pcm)
        return "custom transcript"

    engine = create_transcriber("whisper", language="de", runner=runner)
    pcm = b"\x00\x00" * 16
    assert engine._transcribe_pcm(pcm) == "custom transcript"
    assert chunks == [pcm]
