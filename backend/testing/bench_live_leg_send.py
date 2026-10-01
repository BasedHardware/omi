"""Compare real LiveLegSocket.send implementations; synthetic PCM, no providers.

Run from backend: .venv/bin/python testing/bench_live_leg_send.py --baseline-ref <sha>
Vendor I/O and ONNX inference are deliberately excluded to isolate wrapper cost.
The same raw socket, deterministic gate and loop are used for both revisions.
Thread CPU time is the default: this shared host can preempt wall-clock trials.
"""

from __future__ import annotations

import argparse
import ast
import gc
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.stt import live_session
from utils.stt.resilient_stream import ResilientAudio


class Raw:
    is_connection_dead = False

    def send(self, data):
        return True


class Gate:
    mode = 'shadow'

    def __init__(self, pcm):
        self.output = SimpleNamespace(audio_to_send=pcm, is_speech=True, should_finalize=False)

    def process_audio(self, *args, **kwargs):
        return self.output

    def consume_speech_ms_delta(self):
        return 0


def baseline_class(ref):
    source = subprocess.check_output(['git', 'show', f'{ref}:backend/utils/stt/live_session.py'], text=True)
    tree = ast.parse(source)
    node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'LiveLegSocket')
    # Use identical dependencies; only the class implementation differs.
    namespace = dict(vars(live_session))
    exec(compile(ast.Module(body=[node], type_ignores=[]), '<baseline LiveLegSocket>', 'exec'), namespace)
    return namespace['LiveLegSocket']


def measure(cls, pcm, gate, count, clock):
    session = SimpleNamespace(audio_seconds=0.0, speech_ms=0, total_speech_ms=0)
    socket = cls(Raw(), Gate(pcm) if gate else None, session, live_session.st.STTService.modulate, 16000, False, False)
    send = socket.send
    for n in range(1000):
        assert send(pcm, start_sample=n * 640)
    began = clock()
    for n in range(count):
        send(pcm, start_sample=n * 640)
    return (clock() - began) / count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-ref', required=True)
    parser.add_argument('--iterations', type=int, default=10000)
    parser.add_argument('--rounds', type=int, default=101)
    parser.add_argument('--clock', choices=('thread-cpu', 'wall'), default='thread-cpu')
    parser.add_argument('--ring-memory', action='store_true', help='Measure owned ring objects at the 30ms flush floor')
    args = parser.parse_args()
    if args.ring_memory:
        for rate in (8000, 16000, 48000):
            ring = ResilientAudio(rate, ring_seconds=90, strict_replay=True)
            for _ in range(3):
                ring.reserve_replacement_headroom()
            samples = rate * 3 // 100
            for start in range(0, 135 * rate, samples):
                ring.append(b'\x01\x00' * samples, start)
            chunks = ring.snapshot()
            owned = sys.getsizeof(ring) + sys.getsizeof(ring.__dict__) + sys.getsizeof(ring._chunks)
            owned += sum(
                sys.getsizeof(chunk) + sys.getsizeof(start) + sys.getsizeof(data)
                for chunk in chunks
                for start, data in [chunk]
            )
            print(
                json.dumps(
                    {
                        'sample_rate': rate,
                        'seconds': ring.ring_seconds,
                        'pcm_bytes': ring.buffered_bytes,
                        'chunks': len(chunks),
                        'owned_object_bytes': owned,
                        'three_sessions_owned_mib': round(owned * 3 / 2**20, 3),
                    }
                )
            )
        return
    before = baseline_class(args.baseline_ref)
    clock = time.thread_time_ns if args.clock == 'thread-cpu' else time.perf_counter_ns
    pcm = b'\x01\x00' * 640  # 40ms mono PCM16 at 16kHz
    gc.disable()
    try:
        for gate in (False, True):
            samples = {'before': [], 'after': []}
            for n in range(args.rounds):
                order = [('before', before), ('after', live_session.LiveLegSocket)]
                if n % 2:
                    order.reverse()
                for label, cls in order:
                    samples[label].append(measure(cls, pcm, gate, args.iterations, clock))
            old, new = (statistics.median(samples[label]) for label in ('before', 'after'))
            print(
                json.dumps(
                    {
                        'gate': 'deterministic_speech' if gate else 'off',
                        'baseline_ref': args.baseline_ref,
                        'iterations': args.iterations,
                        'rounds': args.rounds,
                        'clock': args.clock,
                        'before_ns_per_send': round(old, 1),
                        'after_ns_per_send': round(new, 1),
                        'change_percent': round(100 * (new / old - 1), 2),
                        'paired_change_percent_median': round(
                            statistics.median(100 * (b / a - 1) for a, b in zip(samples['before'], samples['after'])), 2
                        ),
                    }
                ),
                flush=True,
            )
    finally:
        gc.enable()


if __name__ == '__main__':
    main()
