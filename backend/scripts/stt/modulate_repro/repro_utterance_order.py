"""
Modulate Velma-2 STT: Non-deterministic utterance ordering reproduction.

Sends the SAME WAV file to Modulate's streaming API multiple times.
Demonstrates that utterance arrival order varies between identical runs,
causing inconsistent WER measurements.

The test WAV contains 4 spoken utterances separated by 5s silence:
  1. "He hoped there would be stew for dinner, turnips and carrots..."
  2. "Stuff it into you, his belly counselled him."
  3. "After early nightfall the yellow lamps would light up..."
  4. "Hello Bertie, any good in your mind?"

Expected: utterances arrive in order 1→2→3→4 every time.
Observed: order varies between runs (e.g., 2→1→3→4 or 1→2→3→4).

Requirements:
    pip install websockets

Usage:
    python repro_utterance_order.py                          # 5 runs
    python repro_utterance_order.py --runs 10                # 10 runs
    python repro_utterance_order.py --api-key YOUR_KEY       # custom key
"""

import argparse
import asyncio
import json
import os
import struct
import sys
import time
import urllib.parse
from pathlib import Path

import websockets

SCRIPT_DIR = Path(__file__).parent
DEFAULT_WAV = SCRIPT_DIR / 'test_audio.wav'

EXPECTED_UTTERANCE_ORDER = [
    'He hoped there would be stew for dinner',
    'Stuff it into you',
    'After early nightfall',
    'Hello Bertie',
]


def read_wav_pcm(wav_path):
    """Read WAV file and return (sample_rate, pcm_bytes)."""
    with open(wav_path, 'rb') as f:
        riff = f.read(4)
        if riff != b'RIFF':
            raise ValueError(f'Not a WAV file: {wav_path}')
        f.read(4)  # file size
        wave = f.read(4)
        if wave != b'WAVE':
            raise ValueError(f'Not a WAV file: {wav_path}')

        sample_rate = 16000
        while True:
            chunk_id = f.read(4)
            if len(chunk_id) < 4:
                break
            chunk_size = struct.unpack('<I', f.read(4))[0]
            if chunk_id == b'fmt ':
                fmt_data = f.read(chunk_size)
                sample_rate = struct.unpack('<I', fmt_data[4:8])[0]
            elif chunk_id == b'data':
                pcm_data = f.read(chunk_size)
                return sample_rate, pcm_data
            else:
                f.read(chunk_size)

    raise ValueError(f'No data chunk found in {wav_path}')


def match_utterance(text):
    """Match utterance text to expected order index."""
    text_lower = text.lower()
    for i, expected in enumerate(EXPECTED_UTTERANCE_ORDER):
        if expected.lower() in text_lower:
            return i + 1
    return '?'


async def run_once(pcm_data, sample_rate, api_key, run_id):
    """Send audio to Modulate and collect utterances."""
    params = {
        'api_key': api_key,
        'speaker_diarization': 'true',
        'partial_results': 'true',
        'sample_rate': str(sample_rate),
        'audio_format': 's16le',
        'num_channels': '1',
        'language': 'en',
    }
    uri = f'wss://modulate-developer-apis.com/api/velma-2-stt-streaming?{urllib.parse.urlencode(params)}'

    ws = await websockets.connect(uri, ping_timeout=30, ping_interval=10, max_size=None)

    utterances = []
    done = asyncio.Event()

    async def recv():
        try:
            async for raw in ws:
                msg = json.loads(raw)
                mt = msg.get('type', '')
                if mt == 'utterance':
                    utt = msg.get('utterance', msg)
                    utterances.append(
                        {
                            'text': utt.get('text', ''),
                            'start_ms': utt.get('start_ms', 0),
                            'duration_ms': utt.get('duration_ms', 0),
                        }
                    )
                elif mt in ('done', 'error'):
                    if mt == 'error':
                        pass  # Expected after audio ends (timeout)
                    done.set()
                    break
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            done.set()

    recv_task = asyncio.create_task(recv())

    # Stream audio in 100ms chunks (real-time pacing)
    chunk_size = sample_rate * 2 // 10  # 100ms of 16-bit mono
    offset = 0
    while offset < len(pcm_data):
        chunk = pcm_data[offset : offset + chunk_size]
        try:
            await ws.send(chunk)
        except Exception:
            break
        offset += chunk_size
        await asyncio.sleep(0.1)

    # Wait for final utterances
    try:
        await asyncio.wait_for(done.wait(), timeout=90)
    except asyncio.TimeoutError:
        pass

    recv_task.cancel()
    try:
        await ws.close()
    except Exception:
        pass

    return utterances


async def main():
    parser = argparse.ArgumentParser(description='Modulate utterance order repro')
    parser.add_argument('--wav', type=str, default=str(DEFAULT_WAV), help='Path to test WAV')
    parser.add_argument('--api-key', type=str, default=os.getenv('MODULATE_API_KEY', ''))
    parser.add_argument('--runs', type=int, default=5, help='Number of identical runs')
    args = parser.parse_args()

    if not args.api_key:
        print('ERROR: Modulate API key required.')
        print('  Set MODULATE_API_KEY env var or pass --api-key YOUR_KEY')
        sys.exit(1)

    wav_path = Path(args.wav)
    if not wav_path.exists():
        print(f'ERROR: WAV file not found: {wav_path}')
        print(f'Download from: https://storage.googleapis.com/omi-pr-assets/modulate-repro/test_audio.wav')
        sys.exit(1)

    sample_rate, pcm_data = read_wav_pcm(wav_path)
    duration_s = len(pcm_data) / (sample_rate * 2)

    print(f'Modulate Velma-2 Utterance Order Reproducibility Test')
    print(f'====================================================')
    print(f'WAV:       {wav_path.name} ({duration_s:.1f}s, {sample_rate}Hz, mono PCM16)')
    print(f'Runs:      {args.runs}')
    print(f'Expected:  4 utterances always arriving in order 1→2→3→4')
    print(f'')
    print(f'Utterance key:')
    for i, text in enumerate(EXPECTED_UTTERANCE_ORDER):
        print(f'  {i + 1}. "{text}..."')
    print()

    all_orders = []

    for r in range(args.runs):
        print(f'Run {r + 1}/{args.runs}...', end=' ', flush=True)
        utterances = await run_once(pcm_data, sample_rate, args.api_key, r + 1)

        order = []
        for u in utterances:
            idx = match_utterance(u['text'])
            order.append(idx)

        order_str = '→'.join(str(x) for x in order)
        print(f'{len(utterances)} utterances, order: [{order_str}]')

        for u in utterances:
            idx = match_utterance(u['text'])
            print(f'    #{idx}: "{u["text"][:60]}..." (start={u["start_ms"]}ms)')

        all_orders.append(order)
        await asyncio.sleep(2)

    # Analysis
    print(f'\n====================================================')
    print(f'Results')
    print(f'====================================================')
    print(f'Expected order: [1→2→3→4]')
    print()

    correct_count = 0
    for i, order in enumerate(all_orders):
        order_str = '→'.join(str(x) for x in order)
        is_correct = order == [1, 2, 3, 4]
        status = 'CORRECT' if is_correct else 'WRONG ORDER'
        print(f'  Run {i + 1}: [{order_str}] {status}')
        if is_correct:
            correct_count += 1

    print(f'\nOrder consistency: {correct_count}/{args.runs} runs correct ({correct_count / args.runs * 100:.0f}%)')

    if correct_count < args.runs:
        print(f'\nBUG: Utterances arrive in non-deterministic order.')
        print(f'Same audio file sent with identical parameters produces')
        print(f'different utterance ordering across runs.')
    else:
        print(f'\nAll runs produced consistent ordering.')


if __name__ == '__main__':
    asyncio.run(main())
