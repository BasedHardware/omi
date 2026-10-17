"""CPU benchmark of the shipped model + original Opus decoder, single thread.

Run with the backend Python environment; no service or microphone access.
This measures the native core, separately from Dart/platform channel overhead.
"""

import argparse
import hashlib
import json
import platform
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort
from opuslib import Decoder


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--seconds', type=int, default=300)
    args = parser.parse_args()
    if args.seconds <= 0:
        parser.error('--seconds must be positive')
    model = Path(__file__).resolve().parents[1] / 'assets/models/silero_vad.onnx'
    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    session = ort.InferenceSession(str(model), options, providers=['CPUExecutionProvider'])
    decoder = Decoder(16000, 1)
    state = np.zeros((2, 1, 128), dtype=np.float32)
    context = np.zeros((1, 64), dtype=np.float32)
    samples = np.empty(0, dtype=np.float32)
    rate = np.array(16000, dtype=np.int64)
    windows = 0
    started_cpu, started_wall = time.process_time(), time.perf_counter()
    for _ in range(args.seconds * 100):
        pcm = decoder.decode(bytes([176, 255, 254]), frame_size=160)
        samples = np.concatenate([samples, np.frombuffer(pcm, dtype='<i2').astype(np.float32) / 32768])
        while len(samples) >= 512:
            window = np.concatenate([context, samples[:512].reshape(1, 512)], axis=1)
            samples = samples[512:]
            probability, state = session.run(None, {'input': window, 'state': state, 'sr': rate})
            assert np.isfinite(probability).all() and 0 <= probability[0][0] <= 1
            context = window[:, -64:]
            windows += 1
    cpu, wall = time.process_time() - started_cpu, time.perf_counter() - started_wall
    print(
        json.dumps(
            {
                'host': platform.machine(),
                'os': platform.system(),
                'onnxruntime': ort.__version__,
                'model_sha256': hashlib.sha256(model.read_bytes()).hexdigest(),
                'audio_seconds': args.seconds,
                'inference_windows': windows,
                'cpu_ms_per_audio_second': cpu * 1000 / args.seconds,
                'elapsed_ms_per_audio_second': wall * 1000 / args.seconds,
                'fixture': '10ms Opus silence',
            },
            indent=2,
        )
    )


if __name__ == '__main__':
    main()
