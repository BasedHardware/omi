"""Backfill yields at <=120s while retaining every frame and absolute times."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from testing.import_isolation import load_module_fresh


@pytest.fixture
def bounded():
    return load_module_fresh('bounded_audio', str(Path(__file__).resolve().parents[2] / 'parakeet/bounded_audio.py'))


@pytest.mark.asyncio
async def test_backfill_quanta_preserve_tail_and_timestamps_and_yield(bounded, tmp_path):
    source = tmp_path / 'original.wav'
    rate = 8000
    samples = np.linspace(-0.8, 0.8, 241 * rate + 1, dtype=np.float32)
    sf.write(source, samples, rate, subtype='FLOAT')
    seen, sizes, lanes = [], [], []

    class Engine:
        async def submit(self, path, **kwargs):
            audio, sr = sf.read(path, dtype='float32')
            seen.append(audio)
            sizes.append(len(audio) / sr)
            lanes.append(kwargs['lane'])
            Path(path).unlink()
            await asyncio.sleep(0)
            return {'text': 'word', 'timestamp': {'word': [{'word': 'word', 'start': 0.0, 'end': 1.0}]}}

    with ThreadPoolExecutor(1) as pool:
        result = await bounded.submit_audio(Engine(), str(source), pool, packing=True)
    assert sizes == [120, 120, 1 + 1 / rate]
    assert lanes == ['backfill'] * 3
    assert np.array_equal(np.concatenate(seen), samples)
    assert [x['start'] for x in result['timestamp']['word']] == [0, 120, 240]
    assert result['text'] == 'word word word'
    assert source.exists()
    assert list(tmp_path.iterdir()) == [source]


@pytest.mark.asyncio
async def test_cancelled_quantum_cleans_files_and_stops_remainder(bounded, tmp_path):
    source = tmp_path / 'original.wav'
    sf.write(source, np.zeros(241 * 8000), 8000)
    entered = asyncio.Event()
    calls = []

    class Engine:
        async def submit(self, path, **kwargs):
            calls.append(path)
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                Path(path).unlink()

    with ThreadPoolExecutor(1) as pool:
        task = asyncio.create_task(bounded.submit_audio(Engine(), str(source), pool, packing=True, owns_file=True))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert len(calls) == 1
    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_small_owned_file_is_retained_until_engine_finishes(bounded, tmp_path):
    source = tmp_path / 'original.wav'
    sf.write(source, np.zeros(8000), 8000)
    entered = asyncio.Event()
    released = asyncio.Event()

    class Engine:
        async def submit(self, path, **kwargs):
            assert kwargs['owns_file'] is True
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                # Model a cancelled caller with GPU ownership still outstanding.
                released.set()

    with ThreadPoolExecutor(1) as pool:
        task = asyncio.create_task(bounded.submit_audio(Engine(), str(source), pool, packing=True, owns_file=True))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert released.is_set() and source.exists()
    source.unlink()  # GPU-owner cleanup is exercised by BatchEngine's tests.
