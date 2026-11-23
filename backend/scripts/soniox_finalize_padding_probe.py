#!/usr/bin/env python3
# LIFECYCLE: permanent
"""Probe Soniox real-time finalize padding for the wire ledger's provider clocks.

OrderedSonioxProviderClock (utils/stt/soniox_wire_ledger.py) predicts that a
finalize moves the provider cursor P to (floor(P / 1920) + 1) * 1920 samples
(120 ms at 16 kHz) and that the <fin> ack reports that position. That law was
measured on stt-rt-v5 on 2026-10-06. On 2026-11-23 this probe found that
neither stt-rt-v5 nor stt-rt-v6 pads any more: every ack reported the exact
sent cursor. Run it again before changing SONIOX_MODEL or enabling
SONIOX_ORDERED_FINALIZE.

Each case sends synthetic speech with the production socket config, then
replays the cursor under two models: "padded" (the 120 ms law) and "exact"
(no hole). Every <fin> ack and every post-finalize speech start is classified
by the model it matches.

Usage, with a NON-customer Soniox key in SONIOX_API_KEY (never print it) and
a mono s16le 16 kHz WAV of speech, for example made with macOS `say`:

    say -o clip.wav --data-format=LEI16@16000 "The quick brown fox jumps over the lazy dog."
    uv run --with websockets python3 scripts/soniox_finalize_padding_probe.py \\
        --clip clip.wav --model stt-rt-v5 --model stt-rt-v6 --out result.json

It prints one summary line per model. The exit status is 0 when every
observation matches one model consistently for each model id.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import wave

import websockets

URL = 'wss://stt-rt.soniox.com/transcribe-websocket'
RATE = 16000
QUANTUM = 1920
FRAME = 320  # 20 ms, paced in real time like the live path
ACK_TOLERANCE_MS = 1  # acks are whole milliseconds
SPEECH_EARLY_MS = 120  # how far before its audio a first token may be timestamped


def load_clip(path: str) -> bytes:
    with wave.open(path, 'rb') as w:
        if (w.getnchannels(), w.getsampwidth(), w.getframerate()) != (1, 2, RATE):
            raise SystemExit('clip must be mono s16le 16 kHz')
        return w.readframes(w.getnframes())


def silence(samples: int) -> bytes:
    return b'\x00\x00' * samples


def fit(pcm: bytes, samples: int) -> bytes:
    want = samples * 2
    return pcm[:want] if len(pcm) >= want else pcm + silence((want - len(pcm)) // 2)


class Cursor:
    """Replays the provider cursor under both models."""

    def __init__(self) -> None:
        self.padded = 0
        self.exact = 0

    def audio(self, samples: int) -> None:
        self.padded += samples
        self.exact += samples

    def finalize(self) -> tuple[int, int]:
        self.padded = (self.padded // QUANTUM + 1) * QUANTUM
        return self.padded, self.exact


def classify(observed_ms: float | None, padded_ms: float, exact_ms: float, tolerance: float) -> str:
    if observed_ms is None:
        return 'missing'
    hits = [name for name, ms in (('padded', padded_ms), ('exact', exact_ms)) if abs(observed_ms - ms) <= tolerance]
    if len(hits) == 2:
        return 'either'
    return hits[0] if hits else 'other'


class Session:
    def __init__(self, ws) -> None:
        self.ws = ws
        self.acks: list[dict] = []
        self.tokens: list[int] = []
        self.errors: list[dict] = []
        self.changed = asyncio.Event()

    async def recv_loop(self) -> None:
        try:
            async for raw in self.ws:
                msg = json.loads(raw)
                if msg.get('error_code') or msg.get('error_message'):
                    self.errors.append({k: msg.get(k) for k in ('error_code', 'error_message')})
                fins = 0
                for token in msg.get('tokens') or []:
                    if token.get('text') == '<fin>' and token.get('is_final') is True:
                        fins += 1
                    elif token.get('is_final') and str(token.get('text', '')).strip() and 'start_ms' in token:
                        self.tokens.append(token['start_ms'])
                for _ in range(fins):
                    self.acks.append(
                        {
                            'fins_in_message': fins,
                            'total_ms': msg.get('total_audio_proc_ms'),
                            'final_ms': msg.get('final_audio_proc_ms'),
                        }
                    )
                self.changed.set()
                if msg.get('finished'):
                    return
        except websockets.ConnectionClosed:
            return

    async def send_pcm(self, pcm: bytes) -> None:
        step = FRAME * 2
        start = time.monotonic()
        for i in range(0, len(pcm), step):
            await self.ws.send(pcm[i : i + step])
            delay = start + (i + step) / 2 / RATE - time.monotonic()
            if delay > 0:
                await asyncio.sleep(delay)

    async def finalize(self) -> None:
        await self.ws.send(json.dumps({'type': 'finalize'}))

    async def wait_acks(self, count: int, timeout: float = 20.0) -> None:
        deadline = time.monotonic() + timeout
        while len(self.acks) < count and time.monotonic() < deadline:
            self.changed.clear()
            try:
                await asyncio.wait_for(self.changed.wait(), deadline - time.monotonic())
            except asyncio.TimeoutError:
                return


async def open_session(model: str, key: str) -> tuple[Session, asyncio.Task]:
    ws = await websockets.connect(URL, max_size=None)
    await ws.send(
        json.dumps(
            {
                'api_key': key,
                'model': model,
                'audio_format': 'pcm_s16le',
                'sample_rate': RATE,
                'num_channels': 1,
                'enable_speaker_diarization': True,
                'enable_language_identification': True,
                'language_hints': ['en'],
            }
        )
    )
    session = Session(ws)
    return session, asyncio.create_task(session.recv_loop())


async def close_session(session: Session, task: asyncio.Task) -> None:
    try:
        await session.ws.send('')
        await asyncio.wait_for(task, 10)
    except Exception:
        task.cancel()
    await session.ws.close()


def ack_rows(session: Session, predictions: list[tuple[int, int]]) -> list[dict]:
    rows = []
    for i, (padded, exact) in enumerate(predictions):
        ack = session.acks[i] if i < len(session.acks) else {}
        total = ack.get('total_ms')
        consistent = type(total) is int and total == ack.get('final_ms') and ack.get('fins_in_message') == 1
        rows.append(
            {
                'reported_ms': total,
                'padded_ms': padded * 1000 / RATE,
                'exact_ms': exact * 1000 / RATE,
                'verdict': (
                    classify(total, padded * 1000 / RATE, exact * 1000 / RATE, ACK_TOLERANCE_MS)
                    if consistent
                    else 'other'
                ),
            }
        )
    return rows


async def case_split(model: str, key: str, first: bytes, second: bytes, name: str) -> dict:
    """Finalize after `first`, then send `second` and finalize again."""
    session, task = await open_session(model, key)
    cursor = Cursor()
    try:
        await session.send_pcm(first)
        cursor.audio(len(first) // 2)
        await session.finalize()
        preds = [cursor.finalize()]
        await session.wait_acks(1)
        seen = len(session.tokens)
        hole = preds[0]
        await session.send_pcm(second)
        cursor.audio(len(second) // 2)
        await session.finalize()
        preds.append(cursor.finalize())
        await session.wait_acks(2)
        row = {
            'case': name,
            'first_samples': len(first) // 2,
            'acks': ack_rows(session, preds),
            'errors': session.errors,
        }
        later = session.tokens[seen:]
        if later and name == 'repeat':
            # Mid-word cuts are skipped: the cut word's token starts before the cut.
            # Under the padded law the second half starts at the padded hole end, so no
            # token after the finalize can be timestamped before it. A token earlier than
            # that end rules padding out; one at or after it is consistent with both.
            observed = min(later)
            padded_ms, exact_ms = hole[0] * 1000 / RATE, hole[1] * 1000 / RATE
            if observed < exact_ms - SPEECH_EARLY_MS:
                verdict = 'other'
            elif observed < padded_ms - SPEECH_EARLY_MS / 3:
                verdict = 'exact'
            else:
                verdict = 'either'
            row['speech_start'] = {
                'observed_ms': observed,
                'padded_ms': padded_ms,
                'exact_ms': exact_ms,
                'verdict': verdict,
            }
        return row
    finally:
        await close_session(session, task)


async def case_burst(model: str, key: str, clip: bytes, finalizes: int, gap: int, name: str) -> dict:
    """Several finalizes before any ack; `gap` samples of silence between them."""
    session, task = await open_session(model, key)
    cursor = Cursor()
    try:
        lead = fit(clip, len(clip) // 2 + 211)
        await session.send_pcm(lead)
        cursor.audio(len(lead) // 2)
        preds = []
        for _ in range(finalizes):
            await session.finalize()
            preds.append(cursor.finalize())
            if gap:
                await session.ws.send(silence(gap))
                cursor.audio(gap)
        await session.wait_acks(finalizes, timeout=30)
        return {'case': name, 'acks': ack_rows(session, preds), 'errors': session.errors}
    finally:
        await close_session(session, task)


async def guarded(name: str, run) -> dict:
    # A server close mid-case is an observation, not a crash; it counts as 'missing'.
    try:
        return await run
    except websockets.ConnectionClosed as exc:
        return {'case': name, 'acks': [{'verdict': 'missing'}], 'closed': f'{exc.rcvd.code if exc.rcvd else None}'}


async def probe(model: str, key: str, clip: bytes) -> list[dict]:
    clip_samples = len(clip) // 2
    rows = []
    # Silence-ended halves at assorted residues modulo the quantum.
    for lead, residue in ((3200, 0), (3200, 1), (3200, 320), (4000, 959), (4800, 1919), (1600, 1280)):
        length = ((lead + clip_samples) // QUANTUM + 1) * QUANTUM + residue
        half = silence(lead) + clip
        rows.append(await guarded('repeat', case_split(model, key, fit(half, length), half, 'repeat')))
    # Finalize mid-word; the rest of the clip follows.
    for cut in (24000, 24001, 30577, 41039):
        if cut < clip_samples:
            rows.append(await guarded('mid_word', case_split(model, key, clip[: cut * 2], clip[cut * 2 :], 'mid_word')))
    rows.append(await guarded('back_to_back', case_burst(model, key, clip, 2, 0, 'back_to_back')))
    rows.append(await guarded('five_in_flight', case_burst(model, key, clip, 5, 593, 'five_in_flight')))
    return rows


def summarize(model: str, rows: list[dict]) -> dict:
    counts: dict[str, dict[str, int]] = {'acks': {}, 'speech_starts': {}}
    for row in rows:
        for ack in row['acks']:
            counts['acks'][ack['verdict']] = counts['acks'].get(ack['verdict'], 0) + 1
        if 'speech_start' in row:
            verdict = row['speech_start']['verdict']
            counts['speech_starts'][verdict] = counts['speech_starts'].get(verdict, 0) + 1
    decisive = {v for c in counts.values() for v in c if v in ('padded', 'exact')}
    clean = not any(v in ('other', 'missing') for c in counts.values() for v in c)
    law = decisive.pop() if clean and len(decisive) == 1 else 'inconsistent'
    return {'model': model, 'law': law, **counts}


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--clip', required=True)
    parser.add_argument('--model', action='append', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    key = os.environ.get('SONIOX_API_KEY')
    if not key:
        raise SystemExit('SONIOX_API_KEY is not set')
    clip = load_clip(args.clip)
    report: dict = {'quantum_samples': QUANTUM, 'rate': RATE, 'models': {}}
    ok = True
    for model in args.model:
        rows = await probe(model, key, clip)
        summary = summarize(model, rows)
        report['models'][model] = {'summary': summary, 'cases': rows}
        print(json.dumps(summary))
        ok &= summary['law'] != 'inconsistent'
    with open(args.out, 'w') as f:
        json.dump(report, f, indent=2)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
