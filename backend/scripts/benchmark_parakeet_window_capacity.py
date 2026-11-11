"""Local upper-bound memory and ingest CPU probe for eight live window sessions.

Run from backend/: .venv/bin/python scripts/benchmark_parakeet_window_capacity.py
No server, network request, or GPU is used. The shared Silero ONNX model is real.
"""

import asyncio
import os
import resource
import sys
import time
import tracemalloc
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from utils.stt.parakeet_window import SessionPcmGain, WindowedParakeetSocket
from utils.stt.vad_gate import VADStreamingGate


async def main() -> None:
    os.environ['PARAKEET_WINDOW_PACE_SECONDS'] = '6'
    os.environ['PARAKEET_WINDOW_MAX_CONTEXT_SECONDS'] = '24'
    os.environ['PARAKEET_WINDOW_DIARIZATION'] = 'false'
    VADStreamingGate()  # Warm the shared process model before measuring per-session cost.
    tracemalloc.start()
    before = tracemalloc.get_traced_memory()[0]
    rss_before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    sockets = []
    gates = []
    for _ in range(8):
        socket = WindowedParakeetSocket(lambda _segments: None, 'http://unused.invalid', 16000, lambda: None)
        socket.start()  # Pump waits without audio; it never sends a POST.
        sockets.append(socket)
        gates.append(VADStreamingGate())
    after_objects = tracemalloc.get_traced_memory()[0]
    cap = sockets[0]._buffer_cap()
    for socket in sockets:
        socket._buf.extend(b'\x01\x00' * (cap // 2))
    after_buffers, peak_buffers = tracemalloc.get_traced_memory()
    rss_after_buffers = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    window = bytes(sockets[0]._buf[: 24 * 16000 * 2])
    sockets[0]._normalize_posted_pcm(window)
    _, peak_post = tracemalloc.get_traced_memory()

    rng = np.random.default_rng(7)
    chunk = rng.integers(-3000, 3000, size=512, dtype=np.int16).tobytes()
    gains = [SessionPcmGain() for _ in gates]
    start = time.process_time()
    for gain, gate in zip(gains, gates):
        for _ in range(10 * 16000 // 512):
            gate._run_vad(gain.apply(chunk))
    cpu = time.process_time() - start
    for socket in sockets:
        socket.finish()
    await asyncio.gather(*(socket._pump_task for socket in sockets), return_exceptions=True)
    print(f'objects_and_pump_bytes_per_session={(after_objects - before) / 8:.0f}')
    print(f'full_buffer_bytes_per_session={(after_buffers - after_objects) / 8:.0f}')
    print(f'buffer_cap_bytes={cap}')
    print(f'eight_session_peak_buffer_bytes={peak_buffers - before}')
    print(f'eight_session_rss_growth_bytes={rss_after_buffers - rss_before}')
    print(f'peak_with_one_24s_agc_post_bytes={peak_post - before}')
    print(f'agc_and_real_vad_cpu_ms_per_session_per_10s={cpu * 1000 / 8:.1f}')


if __name__ == '__main__':
    asyncio.run(main())
