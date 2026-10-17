"""Issue #21577 — cancelling Whisper must drain buffered + in-flight audio.

The other engines drain on cancel; Whisper's run() dropped whatever was
buffered below the 5s batch threshold, and an in-flight batch's result
was discarded. Both paths now transcribe before propagating the cancel.
"""

import asyncio

import pytest

from omi.stt.whisper import WhisperTranscriber


def _runner(pcm: bytes) -> str:
    return f"text:{len(pcm)}"


def test_cancel_drains_buffered_tail():
    transcripts = []

    async def go():
        q = asyncio.Queue()
        w = WhisperTranscriber(runner=_runner)
        task = asyncio.create_task(w.run(q, on_transcript=transcripts.append))
        await q.put(b"\x01\x02" * 100)  # 200 bytes — under the 5s batch
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(go())
    assert transcripts == ["text:200"], "the buffered tail must be transcribed on cancel"


def test_cancel_collects_inflight_batch():
    transcripts = []

    async def go():
        q = asyncio.Queue()
        w = WhisperTranscriber(runner=_runner)
        task = asyncio.create_task(w.run(q, on_transcript=transcripts.append))
        # a full 5s batch — the runner is mid-flight when we cancel
        await q.put(b"\x00" * (16000 * 2 * 5))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(go())
    assert transcripts == ["text:160000"], "an in-flight batch's result must be delivered on cancel"
