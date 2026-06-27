"""
Test: Can we compress silence sent to Modulate to save costs?

Sends identical speech audio with varying silence durations between utterances:
  - 0s (no silence — back-to-back speech)
  - 0.5s
  - 1s
  - 5s
  - 10s (baseline — generous padding)

If WER stays consistent across all silence durations, we can compress silence
and save bandwidth/costs while keeping Modulate's continuous stream intact.

Usage:
    cd backend && python3 scripts/stt/r_silence_compression_test.py
"""

import asyncio
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

import websockets

MODULATE_API_KEY = os.getenv('MODULATE_API_KEY', '')
LIBRISPEECH_DIR = Path('/tmp/librispeech/LibriSpeech/test-clean')

CHUNK_SIZE = 3200
CHUNK_INTERVAL_S = 0.1
SAMPLE_RATE = 16000
PUNCT_RE = re.compile(r'[^\w\s]', re.UNICODE)

SILENCE_DURATIONS = [0, 0.5, 1, 5, 10]


def normalize(text):
    text = PUNCT_RE.sub(' ', text).upper()
    return ' '.join(text.split())


def compute_wer(ref, hyp):
    ref_words = ref.split()
    hyp_words = hyp.split()
    if not ref_words:
        return 0.0 if not hyp_words else 1.0
    d = [[0] * (len(hyp_words) + 1) for _ in range(len(ref_words) + 1)]
    for i in range(len(ref_words) + 1):
        d[i][0] = i
    for j in range(len(hyp_words) + 1):
        d[0][j] = j
    for i in range(1, len(ref_words) + 1):
        for j in range(1, len(hyp_words) + 1):
            if ref_words[i - 1] == hyp_words[j - 1]:
                d[i][j] = d[i - 1][j - 1]
            else:
                d[i][j] = 1 + min(d[i - 1][j], d[i][j - 1], d[i - 1][j - 1])
    return d[len(ref_words)][len(hyp_words)] / len(ref_words)


def build_playlist(target_s):
    playlist = []
    total_s = 0
    for reader_dir in sorted(LIBRISPEECH_DIR.iterdir()):
        if not reader_dir.is_dir():
            continue
        for chapter_dir in sorted(reader_dir.iterdir()):
            if not chapter_dir.is_dir():
                continue
            trans_file = list(chapter_dir.glob('*.trans.txt'))
            if not trans_file:
                continue
            transcripts = {}
            for line in trans_file[0].read_text().strip().split('\n'):
                parts = line.strip().split(' ', 1)
                if len(parts) == 2:
                    transcripts[parts[0]] = parts[1]
            for flac in sorted(chapter_dir.glob('*.flac')):
                uid = flac.stem
                ref = transcripts.get(uid, '')
                result = subprocess.run(
                    [
                        'ffprobe',
                        '-v',
                        'error',
                        '-show_entries',
                        'format=duration',
                        '-of',
                        'default=noprint_wrappers=1:nokey=1',
                        str(flac),
                    ],
                    capture_output=True,
                    text=True,
                )
                dur = float(result.stdout.strip()) if result.returncode == 0 else 5.0
                playlist.append({'flac': str(flac), 'ref': ref, 'uid': uid, 'duration_s': dur})
                total_s += dur
                if total_s >= target_s:
                    return playlist, total_s
    return playlist, total_s


def convert_to_pcm16(flac_path):
    result = subprocess.run(
        ['ffmpeg', '-y', '-i', flac_path, '-f', 's16le', '-ar', str(SAMPLE_RATE), '-ac', '1', 'pipe:1'],
        capture_output=True,
    )
    return result.stdout if result.returncode == 0 else None


# Pre-convert all audio once
_pcm_cache = {}


def get_pcm(flac_path):
    if flac_path not in _pcm_cache:
        _pcm_cache[flac_path] = convert_to_pcm16(flac_path)
    return _pcm_cache[flac_path]


async def test_with_silence(playlist, silence_s, ref_text):
    """Send audio to Modulate with specific silence duration between utterances."""
    params = {
        'api_key': MODULATE_API_KEY,
        'speaker_diarization': 'true',
        'partial_results': 'true',
        'sample_rate': str(SAMPLE_RATE),
        'audio_format': 's16le',
        'num_channels': '1',
        'language': 'en',
    }
    uri = f'wss://modulate-developer-apis.com/api/velma-2-stt-streaming?{urllib.parse.urlencode(params)}'

    ws = await websockets.connect(uri, ping_timeout=30, ping_interval=10, max_size=None)

    utterances = []
    partials = []
    last_partial_text = ''
    done_event = asyncio.Event()
    t0 = time.monotonic()

    async def recv():
        nonlocal last_partial_text
        try:
            async for raw in ws:
                msg = json.loads(raw)
                mt = msg.get('type', '')
                if mt == 'utterance':
                    utt = msg.get('utterance', msg)
                    utterances.append(utt)
                    last_partial_text = ''
                elif mt == 'partial_utterance':
                    pu = msg.get('partial_utterance', msg)
                    partials.append(pu)
                    last_partial_text = pu.get('text', '').strip()
                elif mt == 'done':
                    done_event.set()
                    break
                elif mt == 'error':
                    done_event.set()
                    break
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            done_event.set()

    recv_task = asyncio.create_task(recv())

    # Send audio with specified silence duration
    total_bytes = 0
    silence_bytes = b'\x00' * int(SAMPLE_RATE * 2 * silence_s) if silence_s > 0 else b''
    total_silence_bytes = 0

    for i, sample in enumerate(playlist):
        pcm = get_pcm(sample['flac'])
        if not pcm:
            continue

        # Send speech audio in chunks
        offset = 0
        while offset < len(pcm):
            chunk = pcm[offset : offset + CHUNK_SIZE]
            try:
                await ws.send(chunk)
            except Exception:
                break
            offset += CHUNK_SIZE
            total_bytes += len(chunk)
            await asyncio.sleep(CHUNK_INTERVAL_S)

        # Send silence between utterances (except after last)
        if i < len(playlist) - 1 and silence_bytes:
            try:
                await ws.send(silence_bytes)
                total_bytes += len(silence_bytes)
                total_silence_bytes += len(silence_bytes)
            except Exception:
                break
            # Pace silence to real-time
            await asyncio.sleep(silence_s)

    elapsed_send = time.monotonic() - t0

    # Wait for results
    try:
        await asyncio.wait_for(done_event.wait(), timeout=90)
    except asyncio.TimeoutError:
        pass

    recv_task.cancel()
    try:
        await ws.close()
    except Exception:
        pass

    elapsed_total = time.monotonic() - t0

    # Build transcript
    utt_text = ' '.join(u.get('text', '') for u in utterances).strip()
    # Include last partial if not already in an utterance
    full_text = utt_text
    if last_partial_text and not utt_text.endswith(last_partial_text):
        full_text = (utt_text + ' ' + last_partial_text).strip() if utt_text else last_partial_text

    ref_norm = normalize(ref_text)
    hyp_norm = normalize(full_text)
    wer = compute_wer(ref_norm, hyp_norm)
    word_count = len(hyp_norm.split()) if hyp_norm else 0
    ref_count = len(ref_norm.split())

    speech_bytes = total_bytes - total_silence_bytes
    savings_pct = (total_silence_bytes / total_bytes * 100) if total_bytes > 0 else 0

    return {
        'silence_s': silence_s,
        'wer': wer,
        'word_count': word_count,
        'ref_count': ref_count,
        'utterances': len(utterances),
        'partials': len(partials),
        'total_bytes': total_bytes,
        'speech_bytes': speech_bytes,
        'silence_bytes': total_silence_bytes,
        'savings_pct': savings_pct,
        'send_time': elapsed_send,
        'total_time': elapsed_total,
        'text_sample': full_text[:150],
    }


async def main():
    print('Building playlist (target: 30s)...')
    playlist, total_s = build_playlist(30)
    if not playlist:
        print('ERROR: No LibriSpeech data found. Download first.')
        sys.exit(1)

    ref_text = ' '.join(s['ref'] for s in playlist)
    ref_norm = normalize(ref_text)
    ref_words = len(ref_norm.split())
    print(f'  {len(playlist)} utterances, {total_s:.1f}s speech, {ref_words} ref words')

    # Pre-cache PCM
    for s in playlist:
        get_pcm(s['flac'])

    results = []

    for silence_s in SILENCE_DURATIONS:
        label = f'{silence_s}s' if silence_s > 0 else '0s (back-to-back)'
        print(f'\n{"=" * 60}')
        print(f'Testing silence = {label}')
        print(f'{"=" * 60}')

        result = await test_with_silence(playlist, silence_s, ref_text)
        results.append(result)

        print(f'  WER:          {result["wer"] * 100:.1f}%')
        print(f'  Words:        {result["word_count"]} / {result["ref_count"]}')
        print(f'  Utterances:   {result["utterances"]}')
        print(f'  Total bytes:  {result["total_bytes"] / 1024:.0f} KB')
        print(f'  Silence bytes:{result["silence_bytes"] / 1024:.0f} KB ({result["savings_pct"]:.1f}% of total)')
        print(f'  Send time:    {result["send_time"]:.1f}s')
        print(f'  Text sample:  {result["text_sample"]}')

    # Summary table
    print(f'\n{"=" * 60}')
    print('SUMMARY: Silence Compression Results')
    print(f'{"=" * 60}')
    print(f'{"Silence":>10} {"WER":>8} {"Words":>8} {"UTTs":>6} {"Total KB":>10} {"Silence KB":>12} {"Savings":>10}')
    print('-' * 70)
    for r in results:
        label = f'{r["silence_s"]}s'
        print(
            f'{label:>10} {r["wer"] * 100:>7.1f}% {r["word_count"]:>5}/{r["ref_count"]:<3}'
            f' {r["utterances"]:>5} {r["total_bytes"] / 1024:>9.0f} {r["silence_bytes"] / 1024:>11.0f}'
            f' {r["savings_pct"]:>9.1f}%'
        )

    # Verdict
    baseline = results[-1]  # 10s silence = baseline
    print(f'\nBaseline (10s silence): WER = {baseline["wer"] * 100:.1f}%')
    for r in results[:-1]:
        delta = (r['wer'] - baseline['wer']) * 100
        direction = 'worse' if delta > 0 else 'better' if delta < 0 else 'same'
        print(f'  {r["silence_s"]}s silence: WER = {r["wer"] * 100:.1f}% ({delta:+.1f}% {direction})')

    # Save raw results
    with open('/tmp/modulate_silence_test.json', 'w') as f:
        json.dump(results, f, indent=2)
    print(f'\nRaw results saved to /tmp/modulate_silence_test.json')


if __name__ == '__main__':
    asyncio.run(main())
