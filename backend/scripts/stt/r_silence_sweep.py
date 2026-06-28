"""
Find the minimum silence duration that matches no-VAD WER with Modulate.

1. Baseline: send audio with generous 15s silence (simulates no-VAD / passthrough)
2. Sweep: test 0s, 0.5s, 1s, 2s, 3s, 5s, 7s, 10s
3. Find which silence duration matches baseline WER

Usage:
    cd backend && python3 scripts/stt/r_silence_sweep.py
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

SWEEP_DURATIONS = [0, 0.5, 1, 2, 3, 5, 7, 10, 15]


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


_pcm_cache = {}


def get_pcm(flac_path):
    if flac_path not in _pcm_cache:
        _pcm_cache[flac_path] = convert_to_pcm16(flac_path)
    return _pcm_cache[flac_path]


async def run_test(playlist, silence_s):
    """Send audio to Modulate with specified silence between utterances."""
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
    last_partial_text = ''
    done_event = asyncio.Event()

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
                    last_partial_text = pu.get('text', '').strip()
                elif mt in ('done', 'error'):
                    done_event.set()
                    break
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            done_event.set()

    recv_task = asyncio.create_task(recv())

    total_bytes = 0
    silence_bytes_total = 0
    silence_pcm = b'\x00' * int(SAMPLE_RATE * 2 * silence_s) if silence_s > 0 else b''

    for i, sample in enumerate(playlist):
        pcm = get_pcm(sample['flac'])
        if not pcm:
            continue
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

        if i < len(playlist) - 1 and silence_pcm:
            try:
                await ws.send(silence_pcm)
                total_bytes += len(silence_pcm)
                silence_bytes_total += len(silence_pcm)
            except Exception:
                break
            await asyncio.sleep(silence_s)

    # Wait for trailing results
    try:
        await asyncio.wait_for(done_event.wait(), timeout=90)
    except asyncio.TimeoutError:
        pass

    recv_task.cancel()
    try:
        await ws.close()
    except Exception:
        pass

    utt_text = ' '.join(u.get('text', '') for u in utterances).strip()
    full_text = utt_text
    if last_partial_text and not utt_text.endswith(last_partial_text):
        full_text = (utt_text + ' ' + last_partial_text).strip() if utt_text else last_partial_text

    return {
        'silence_s': silence_s,
        'utterance_count': len(utterances),
        'full_text': full_text,
        'total_bytes': total_bytes,
        'silence_bytes': silence_bytes_total,
    }


async def main():
    print('Building playlist (target: 30s of speech)...')
    playlist, total_s = build_playlist(30)
    if not playlist:
        print('ERROR: No LibriSpeech data. Run the download first.')
        sys.exit(1)

    ref_text = ' '.join(s['ref'] for s in playlist)
    ref_norm = normalize(ref_text)
    ref_words = ref_norm.split()
    print(f'  {len(playlist)} utterances, {total_s:.1f}s speech, {len(ref_words)} ref words\n')

    for s in playlist:
        get_pcm(s['flac'])

    # Run baseline first (15s = no-VAD equivalent)
    print('=' * 70)
    print('BASELINE: 15s silence (no-VAD equivalent)')
    print('=' * 70)
    baseline = await run_test(playlist, 15)
    b_norm = normalize(baseline['full_text'])
    b_wer = compute_wer(ref_norm, b_norm)
    b_words = len(b_norm.split()) if b_norm else 0
    print(f'  WER:   {b_wer * 100:.1f}%')
    print(f'  Words: {b_words}/{len(ref_words)}')
    print(f'  UTTs:  {baseline["utterance_count"]}')
    print(f'  Bytes: {baseline["total_bytes"] / 1024:.0f} KB')
    print(f'  Text:  {baseline["full_text"][:120]}...')

    # Sweep
    rows = []
    rows.append(
        {
            'silence_s': 15,
            'wer': b_wer,
            'words': b_words,
            'utts': baseline['utterance_count'],
            'total_kb': baseline['total_bytes'] / 1024,
            'silence_kb': baseline['silence_bytes'] / 1024,
            'delta_wer': 0,
            'text': baseline['full_text'][:100],
        }
    )

    for s in [d for d in SWEEP_DURATIONS if d != 15]:
        label = f'{s}s' if s > 0 else '0s'
        print(f'\n--- Testing {label} silence ---')
        result = await run_test(playlist, s)
        hyp_norm = normalize(result['full_text'])
        wer = compute_wer(ref_norm, hyp_norm)
        words = len(hyp_norm.split()) if hyp_norm else 0
        delta = wer - b_wer

        rows.append(
            {
                'silence_s': s,
                'wer': wer,
                'words': words,
                'utts': result['utterance_count'],
                'total_kb': result['total_bytes'] / 1024,
                'silence_kb': result['silence_bytes'] / 1024,
                'delta_wer': delta,
                'text': result['full_text'][:100],
            }
        )

        status = 'MATCH' if abs(delta) < 0.03 else ('CLOSE' if abs(delta) < 0.08 else 'MISS')
        print(f'  WER: {wer * 100:.1f}% (delta: {delta * 100:+.1f}%) [{status}]')
        print(f'  Words: {words}/{len(ref_words)}, UTTs: {result["utterance_count"]}')
        print(f'  Total: {result["total_bytes"] / 1024:.0f} KB, Silence: {result["silence_bytes"] / 1024:.0f} KB')

    # Sort by silence duration for table
    rows.sort(key=lambda r: r['silence_s'])

    print(f'\n{"=" * 70}')
    print(f'RESULTS (baseline = 15s silence, WER = {b_wer * 100:.1f}%)')
    print(f'{"=" * 70}')
    print(
        f'{"Silence":>8} {"WER":>7} {"Delta":>8} {"Words":>8} {"UTTs":>5} {"Total KB":>9} {"SilKB":>7} {"Savings":>8} {"Status":>7}'
    )
    print('-' * 75)

    for r in rows:
        savings = (1 - r['total_kb'] / rows[-1]['total_kb']) * 100 if rows[-1]['total_kb'] > 0 else 0
        # Compare to 15s baseline total bytes
        baseline_kb = [x for x in rows if x['silence_s'] == 15][0]['total_kb']
        savings = (1 - r['total_kb'] / baseline_kb) * 100 if baseline_kb > 0 else 0

        status = 'MATCH' if abs(r['delta_wer']) < 0.03 else ('CLOSE' if abs(r['delta_wer']) < 0.08 else 'MISS')
        arrow = '<<<' if status == 'MATCH' and r['silence_s'] != 15 else ''
        print(
            f'{r["silence_s"]:>7}s {r["wer"] * 100:>6.1f}% {r["delta_wer"] * 100:>+7.1f}%'
            f' {r["words"]:>5}/{len(ref_words):<3} {r["utts"]:>4}'
            f' {r["total_kb"]:>8.0f} {r["silence_kb"]:>6.0f} {savings:>7.1f}%'
            f' {status:>6} {arrow}'
        )

    # Find best match
    non_baseline = [r for r in rows if r['silence_s'] != 15]
    matches = [r for r in non_baseline if abs(r['delta_wer']) < 0.03]
    close = [r for r in non_baseline if 0.03 <= abs(r['delta_wer']) < 0.08]

    print(f'\nBaseline WER (no-VAD): {b_wer * 100:.1f}%')
    if matches:
        best = min(matches, key=lambda r: r['silence_s'])
        baseline_kb = [x for x in rows if x['silence_s'] == 15][0]['total_kb']
        savings = (1 - best['total_kb'] / baseline_kb) * 100
        print(f'ANSWER: {best["silence_s"]}s silence MATCHES baseline WER ({best["wer"] * 100:.1f}%)')
        print(f'  Bandwidth savings vs no-VAD: {savings:.1f}%')
    elif close:
        best = min(close, key=lambda r: abs(r['delta_wer']))
        print(
            f'CLOSEST: {best["silence_s"]}s silence ({best["wer"] * 100:.1f}%, delta {best["delta_wer"] * 100:+.1f}%)'
        )
    else:
        print('No silence duration matched baseline WER within 3%.')

    with open('/tmp/modulate_silence_sweep.json', 'w') as f:
        json.dump(rows, f, indent=2, default=str)
    print(f'\nRaw results saved to /tmp/modulate_silence_sweep.json')


if __name__ == '__main__':
    asyncio.run(main())
