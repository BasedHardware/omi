import asyncio
import contextlib
import pytest
from omi.stt.whisper import WhisperTranscriber
from omi.transcribe import transcribe


def test_whisper_batch_seconds_validation():
    def dummy_runner(pcm):
        return "ok"

    # Default
    t = WhisperTranscriber(runner=dummy_runner)
    assert t.batch_seconds == 5.0
    assert t._target_bytes == 16000 * 2 * 5

    # Valid values
    t1 = WhisperTranscriber(runner=dummy_runner, batch_seconds=1.0)
    assert t1.batch_seconds == 1.0
    assert t1._target_bytes == 16000 * 2 * 1

    t2 = WhisperTranscriber(runner=dummy_runner, batch_seconds=0.1)
    assert t2._target_bytes == int(16000 * 0.1) * 2

    t3 = WhisperTranscriber(runner=dummy_runner, batch_seconds=30.0)
    assert t3._target_bytes == 16000 * 30 * 2

    # Invalid values
    for invalid in [0.0, 0.05, 30.1, -1.0, 100, "5", None, True, False]:
        with pytest.raises(ValueError, match="batch_seconds must be between 0.1 and 30 seconds"):
            WhisperTranscriber(runner=dummy_runner, batch_seconds=invalid)


def test_whisper_transcribe_custom_batch_seconds():
    async def _test():
        queue = asyncio.Queue()
        # Put 1 second of audio (16000 samples * 2 bytes)
        one_second_pcm = b"\x01\x00" * 16000
        queue.put_nowait(one_second_pcm)

        loop = asyncio.get_running_loop()
        transcript_fut = loop.create_future()
        batches = []

        def runner(pcm):
            batches.append(pcm)
            return "synthetic transcript"

        task = asyncio.create_task(
            transcribe(
                queue,
                "",
                transcript_fut.set_result,
                engine="whisper",
                runner=runner,
                batch_seconds=1.0,
            )
        )

        try:
            done, _ = await asyncio.wait(
                (task, transcript_fut),
                timeout=3,
                return_when=asyncio.FIRST_COMPLETED,
            )
            assert transcript_fut in done, "Transcript callback was not called"
            assert transcript_fut.result() == "synthetic transcript"
            assert batches == [one_second_pcm]
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    asyncio.run(_test())
