#!/usr/bin/env python3
"""D2 edge shadow goldens: listen's VAD gate vs listen-edge on the same audio.

For each speech fixture, codec and gate profile this runs listen's real
receive path offline (decoder, capture positions, 30 ms STT buffer,
``VADStreamingGate`` with its edge tap, window-lane AGC copy) and records the
exact mirror stream listen would send to ``/v1/shadow``. It then replays the
streams through the edge's ``edge-shadow-replay`` binary (the same
``ShadowCore`` the endpoint runs) and checks the D2 gate.

Usage:
    cd backend
    python scripts/edge_shadow_goldens.py --replay-bin <target>/release/edge-shadow-replay \
        --out /tmp/edge-goldens [--extra-wav path.wav ...] [--write-edge-fixtures]

Exit status is non-zero when the agreement gate fails.
"""

import argparse
import asyncio
import audioop
import json
import os
import struct
import subprocess
import sys
import urllib.request
import wave
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import opuslib  # noqa: E402

from scripts.edge_shadow_gate import AGREEMENT_GATE, OPEN_OFFSET_P95_GATE_MS, delta, evaluate, p95  # noqa: E402
from scripts.edge_shadow_gate import parse as parse_metrics  # noqa: E402
from utils.stt.edge_shadow import EdgeShadowMirror, GateTap, encode_frame, session_key  # noqa: E402
from utils.stt.live_session import (  # noqa: E402
    WINDOW_VAD_CONTINUE_THRESHOLD,
    WINDOW_VAD_HANGOVER_MS,
    WINDOW_VAD_SPEECH_THRESHOLD,
)
from utils.stt.parakeet_window import SessionPcmGain  # noqa: E402
from utils.stt.vad_gate import VADStreamingGate  # noqa: E402
from utils.transcribe_decisions import stt_buffer_flush_size  # noqa: E402

BACKEND = os.path.join(os.path.dirname(__file__), '..')
MODEL = os.path.join(BACKEND, 'utils', 'stt', 'assets', 'silero_vad.onnx')
FIXTURES = [
    os.path.join(BACKEND, 'testing', 'release_fixtures', 'transcription-release-probe.wav'),
    os.path.join(BACKEND, 'testing', 'release_fixtures', 'parakeet-canary-pt.wav'),
    os.path.join(BACKEND, 'scripts', 'fixtures', 'parakeet_route_synthetic.wav'),
]
EDGE_FIXTURES = os.path.join(BACKEND, 'edge', 'tests', 'fixtures', 'shadow')
# listen's OPUS_MAX_FRAME_MS (receiver.opus_decode_capacity).
OPUS_MAX_FRAME_MS = 120


@dataclass(frozen=True)
class Encoding:
    name: str
    codec: str
    sample_rate: int
    frame_ms: int


ENCODINGS = [
    Encoding('pcm16_16k', 'pcm16', 16000, 20),
    Encoding('pcm16_8k', 'pcm16', 8000, 20),
    Encoding('pcm16_48k', 'pcm16', 48000, 10),
    Encoding('pcm8_8k', 'pcm8', 8000, 20),
    Encoding('opus_fs320_16k', 'opus_fs320', 16000, 20),
    Encoding('opus_16k_60ms', 'opus', 16000, 60),
    Encoding('opus_48k', 'opus', 48000, 20),
]
PROFILES = ('standard', 'window')


def read_wav(path: str) -> np.ndarray:
    with wave.open(path, 'rb') as w:
        if w.getsampwidth() != 2 or w.getnchannels() != 1 or w.getframerate() != 16000:
            raise SystemExit(f'{path}: want 16 kHz mono PCM16')
        return np.frombuffer(w.readframes(w.getnframes()), dtype='<i2').copy()


def session_audio(speech: np.ndarray, seed: int) -> np.ndarray:
    """Room-noise lead-in, speech, a gap longer than the 4 s hangover, speech, tail."""
    rng = np.random.default_rng(seed)

    def noise(seconds: float) -> np.ndarray:
        return np.clip(rng.normal(0, 25, int(seconds * 16000)), -32768, 32767).astype(np.int16)

    return np.concatenate([noise(1.0), speech, noise(4.6), speech, noise(1.2)])


def to_rate(samples16k: np.ndarray, rate: int) -> np.ndarray:
    """Deterministic client-side rate change (not listen's resampler)."""
    if rate == 16000:
        return samples16k
    n_out = int(len(samples16k) * rate / 16000)
    x = np.arange(n_out) * (16000 / rate)
    return np.interp(x, np.arange(len(samples16k)), samples16k.astype(np.float64)).round().astype(np.int16)


def client_frames(samples16k: np.ndarray, enc: Encoding) -> List[bytes]:
    pcm = to_rate(samples16k, enc.sample_rate)
    per = enc.sample_rate * enc.frame_ms // 1000
    frames = []
    if enc.codec.startswith('opus'):
        encoder = opuslib.Encoder(enc.sample_rate, 1, opuslib.APPLICATION_VOIP)
        encoder.bitrate = 32000
        for i in range(0, len(pcm) - per + 1, per):
            frames.append(encoder.encode(pcm[i : i + per].tobytes(), per))
        return frames
    for i in range(0, len(pcm), per):
        chunk = pcm[i : i + per]
        if enc.codec == 'pcm8':
            frames.append(((chunk.astype(np.int32) >> 8) + 128).astype(np.uint8).tobytes())
        else:
            frames.append(chunk.tobytes())
    return frames


class Recorder:
    """Duck-typed mirror: records what listen would offer, in order."""

    def __init__(self) -> None:
        self.messages: List[bytes] = []
        self._gates = 0

    def offer(self, message: bytes) -> None:
        self.messages.append(message)

    def tap(self) -> GateTap:
        self._gates += 1
        return GateTap(self, self._gates)  # type: ignore[arg-type]  # duck-typed mirror


def listen_decode(enc: Encoding) -> Any:
    codec = 'opus' if enc.codec == 'opus_fs320' else enc.codec
    if codec == 'opus':
        decoder = opuslib.Decoder(enc.sample_rate, 1)
        capacity = enc.sample_rate // 1000 * OPUS_MAX_FRAME_MS
        return lambda data: decoder.decode(bytes(data), frame_size=capacity)
    if codec == 'pcm8':
        return lambda data: audioop.lin2lin(audioop.bias(data, 1, -128), 1, 2)
    return lambda data: data


def run_listen(frames: List[bytes], enc: Encoding, profile: str) -> Tuple[Recorder, Dict[str, Any]]:
    """listen's receive_data -> _flush_stt_buffer -> gate path for one session."""
    rec = Recorder()
    if profile == 'window':
        gate = VADStreamingGate(
            sample_rate=enc.sample_rate,
            channels=1,
            mode='active',
            speech_threshold=WINDOW_VAD_SPEECH_THRESHOLD,
            continue_threshold=WINDOW_VAD_CONTINUE_THRESHOLD,
            hangover_ms=WINDOW_VAD_HANGOVER_MS,
        )
        gain: Optional[SessionPcmGain] = SessionPcmGain()
    else:
        gate = VADStreamingGate(sample_rate=enc.sample_rate, channels=1, mode='active')
        gain = None
    gate.edge_tap = rec.tap()
    decode = listen_decode(enc)
    flush = stt_buffer_flush_size(enc.sample_rate)
    cursor = 0
    buffer = bytearray()
    buffer_start = 0
    wall = 1.0
    for data in frames:
        if len(data) <= 2:
            continue
        decoded = decode(data)
        if not decoded:
            continue
        start, end = cursor, cursor + len(decoded) // 2
        cursor = end
        rec.offer(encode_frame(start, end - start, data))
        if not buffer:
            buffer_start = start
        buffer.extend(decoded)
        if len(buffer) >= flush:
            chunk = bytes(buffer)
            buffer.clear()
            score = gain.apply(chunk) if gain is not None else None
            wall += len(chunk) / (2 * enc.sample_rate)
            gate.process_audio(chunk, wall, score, start_sample=buffer_start)
    if buffer:
        # Teardown force-flushes the partial buffer (decide_stt_buffer_flush(force=True)).
        chunk = bytes(buffer)
        score = gain.apply(chunk) if gain is not None else None
        gate.process_audio(chunk, wall + len(chunk) / (2 * enc.sample_rate), score, start_sample=buffer_start)
    return rec, {'listen_windows': gate._vad_windows_scored}  # type: ignore[reportPrivateUsage]


def write_stream(path: str, query: str, messages: List[bytes]) -> None:
    with open(path, 'wb') as f:
        for record in [query.encode()] + messages:
            f.write(struct.pack('>I', len(record)))
            f.write(record)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--replay-bin', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--extra-wav', action='append', default=[])
    parser.add_argument(
        '--write-edge-fixtures',
        action='store_true',
        help='also refresh backend/edge/tests/fixtures/shadow (a small subset for the Rust test)',
    )
    parser.add_argument(
        '--edge-url',
        help='also mirror every stream live through EdgeShadowMirror to this running edge '
        '(ws://host:port/v1/shadow) and gate on its /metrics',
    )
    args = parser.parse_args()
    os.makedirs(args.out, exist_ok=True)

    streams: List[str] = []
    listen_counts: Dict[str, Dict[str, Any]] = {}
    for f_index, wav in enumerate(FIXTURES + args.extra_wav):
        audio = session_audio(read_wav(wav), seed=f_index)
        base = os.path.splitext(os.path.basename(wav))[0]
        for enc in ENCODINGS:
            frames = client_frames(audio, enc)
            for profile in PROFILES:
                name = f'{base}.{enc.name}.{profile}'
                rec, counts = run_listen(frames, enc, profile)
                query = f'v=1&codec={enc.codec}&sample_rate={enc.sample_rate}&session={session_key(name)}'
                path = os.path.join(args.out, f'{name}.shadow')
                write_stream(path, query, rec.messages)
                streams.append(path)
                listen_counts[os.path.basename(path)] = counts

    out = subprocess.run([args.replay_bin, MODEL, *streams], capture_output=True, text=True, check=False)
    if out.returncode != 0:
        sys.stderr.write(out.stderr)
        return 2
    rows = [json.loads(line) for line in out.stdout.splitlines() if line.strip()]
    for row in rows:
        row.update(listen_counts.get(row['stream'], {}))

    with open(os.path.join(args.out, 'summary.jsonl'), 'w') as f:
        for row in rows:
            f.write(json.dumps(row) + '\n')

    compared = sum(
        r['agree_speech'] + r['agree_silence'] + r['edge_speech_only'] + r['listen_speech_only'] for r in rows
    )
    agreed = sum(r['agree_speech'] + r['agree_silence'] for r in rows)
    unmatched = sum(r['unmatched'] + r['not_comparable'] for r in rows)
    offsets = [o for r in rows for o in r['open_offsets_ms']]
    opens_unmatched = sum(r['opens_listen_only'] + r['opens_edge_only'] for r in rows)
    agreement = agreed / compared if compared else 0.0
    open_p95 = p95(offsets)

    print(
        f'{"stream":58} {"windows":>7} {"agree":>8} {"e_only":>6} {"l_only":>6} {"maxdiff":>9} {"opens":>5} {"vad ms/s":>8}'
    )
    for r in rows:
        n = r['agree_speech'] + r['agree_silence'] + r['edge_speech_only'] + r['listen_speech_only']
        print(
            f'{r["stream"]:58} {n:7d} {r["agreement"] if r["agreement"] is not None else 0:8.4%} '
            f'{r["edge_speech_only"]:6d} {r["listen_speech_only"]:6d} {r["max_prob_diff"]:9.2e} '
            f'{r["opens_matched"]:5d} {r["vad_ms_per_audio_s"]:8.3f}'
        )
    print(
        f'\nTOTAL windows compared {compared}, agreement {agreement:.4%} (gate >= {AGREEMENT_GATE:.1%}), '
        f'unmatched+not_comparable {unmatched}, gate-open offset p95 {open_p95:.1f} ms '
        f'(gate <= {OPEN_OFFSET_P95_GATE_MS} ms) over {len(offsets)} opens, unmatched opens {opens_unmatched}'
    )

    if args.write_edge_fixtures:
        os.makedirs(EDGE_FIXTURES, exist_ok=True)
        keep = {
            'transcription-release-probe.opus_fs320_16k.standard.shadow',
            'transcription-release-probe.opus_fs320_16k.window.shadow',
            'transcription-release-probe.pcm8_8k.window.shadow',
        }
        for path in streams:
            if os.path.basename(path) in keep:
                with open(path, 'rb') as src, open(os.path.join(EDGE_FIXTURES, os.path.basename(path)), 'wb') as dst:
                    dst.write(src.read())

    ok = compared > 0 and agreement >= AGREEMENT_GATE and unmatched == 0 and open_p95 <= OPEN_OFFSET_P95_GATE_MS
    print('GATE', 'PASS' if ok else 'FAIL')

    if args.edge_url:
        live_ok = asyncio.run(mirror_live(args.edge_url, streams))
        ok = ok and live_ok
    return 0 if ok else 1


async def mirror_live(edge_url: str, streams: List[str]) -> bool:
    """Send the recorded streams through listen's real mirror to a running edge.

    Exercises EdgeShadowMirror's websocket transport and the edge endpoint
    together, then evaluates the D2 gate on the edge's /metrics delta.
    """
    host = edge_url.split('://', 1)[1].split('/', 1)[0]
    metrics_url = f'http://{host}/metrics'
    before = parse_metrics(urllib.request.urlopen(metrics_url, timeout=5).read().decode())
    outcomes: Dict[str, int] = {}
    for path in streams:
        with open(path, 'rb') as f:
            data = f.read()
        records = []
        i = 0
        while i < len(data):
            (n,) = struct.unpack('>I', data[i : i + 4])
            records.append(data[i + 4 : i + 4 + n])
            i += 4 + n
        meta = dict(kv.split('=', 1) for kv in records[0].decode().split('&'))
        mirror = EdgeShadowMirror(
            edge_url,
            codec=meta['codec'],
            sample_rate=int(meta['sample_rate']),
            session_id=os.path.basename(path),
            token=os.getenv('EDGE_SHADOW_TOKEN', ''),
        )
        mirror.start(lambda coro, name: asyncio.get_running_loop().create_task(coro, name=name))
        for message in records[1:]:
            # listen offers at capture pace; here, just never outrun the queue.
            while mirror.active and mirror._queue.qsize() > 256:  # type: ignore[reportPrivateUsage]
                await asyncio.sleep(0.001)
            mirror.offer(message)
        mirror.close()
        await asyncio.wait_for(mirror._task, 30)  # type: ignore[reportPrivateUsage,arg-type]
        outcomes[mirror.outcome or 'none'] = outcomes.get(mirror.outcome or 'none', 0) + 1
    await asyncio.sleep(0.5)  # let the edge finish its last sessions
    after = parse_metrics(urllib.request.urlopen(metrics_url, timeout=5).read().decode())
    print(f'\nLIVE via EdgeShadowMirror -> {edge_url}: mirror outcomes {outcomes}')
    ok, lines = evaluate(delta(after, before))
    print('\n'.join(lines))
    print('LIVE GATE', 'PASS' if ok else 'FAIL')
    return ok and set(outcomes) == {'completed'}


if __name__ == '__main__':
    sys.exit(main())
