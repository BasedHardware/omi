"""
Modulate WER stability test: same audio, same config, multiple runs.

Sends identical audio with identical silence to Modulate N times.
If WER varies significantly between runs, the issue is Modulate's
non-determinism, not our test methodology.

Usage:
    cd backend && python3 scripts/stt/r_modulate_stability.py
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

RUNS_PER_CONFIG = 5
CONFIGS = [
    {'silence_s': 5, 'label': '5s silence'},
    {'silence_s': 10, 'label': '10s silence'},
]


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


async def run_single(playlist, silence_s):
    """Single run: send audio to Modulate, collect results."""
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
    utt_order = []

    async def recv():
        nonlocal last_partial_text
        try:
            async for raw in ws:
                msg = json.loads(raw)
                mt = msg.get('type', '')
                if mt == 'utterance':
                    utt = msg.get('utterance', msg)
                    utterances.append(utt)
                    utt_order.append(utt.get('text', '')[:40])
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

    silence_pcm = b'\x00' * int(SAMPLE_RATE * 2 * silence_s) if silence_s > 0 else b''
    total_bytes = 0

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
            except Exception:
                break
            await asyncio.sleep(silence_s)

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
        'utterance_count': len(utterances),
        'full_text': full_text,
        'utt_order': utt_order,
    }


async def main():
    print('Building playlist (target: 30s of speech)...')
    playlist, total_s = build_playlist(30)
    if not playlist:
        print('ERROR: No LibriSpeech data.')
        sys.exit(1)

    ref_text = ' '.join(s['ref'] for s in playlist)
    ref_norm = normalize(ref_text)
    ref_words = ref_norm.split()
    print(f'  {len(playlist)} utterances, {total_s:.1f}s speech, {len(ref_words)} ref words')
    print(f'  Ref: {ref_text[:120]}...\n')

    for s in playlist:
        get_pcm(s['flac'])

    all_results = {}

    for config in CONFIGS:
        silence_s = config['silence_s']
        label = config['label']
        print(f'{"=" * 70}')
        print(f'{label} — {RUNS_PER_CONFIG} runs')
        print(f'{"=" * 70}')

        runs = []
        for r in range(RUNS_PER_CONFIG):
            print(f'  Run {r + 1}/{RUNS_PER_CONFIG}...', end=' ', flush=True)
            result = await run_single(playlist, silence_s)
            hyp_norm = normalize(result['full_text'])
            wer = compute_wer(ref_norm, hyp_norm)
            words = len(hyp_norm.split()) if hyp_norm else 0

            run_data = {
                'run': r + 1,
                'wer': wer,
                'words': words,
                'utts': result['utterance_count'],
                'utt_order': result['utt_order'],
                'text_sample': result['full_text'][:100],
            }
            runs.append(run_data)
            print(f'WER={wer * 100:.1f}% words={words}/{len(ref_words)} utts={result["utterance_count"]}')

            # Brief pause between runs
            await asyncio.sleep(2)

        wers = [r['wer'] for r in runs]
        words_list = [r['words'] for r in runs]
        avg_wer = sum(wers) / len(wers)
        min_wer = min(wers)
        max_wer = max(wers)
        spread = max_wer - min_wer
        avg_words = sum(words_list) / len(words_list)

        print(f'\n  --- {label} summary ---')
        print(
            f'  WER:   avg={avg_wer * 100:.1f}%  min={min_wer * 100:.1f}%  max={max_wer * 100:.1f}%  spread={spread * 100:.1f}%'
        )
        print(f'  Words: avg={avg_words:.0f}/{len(ref_words)}')

        # Show utterance order per run
        print(f'  Utterance arrival order:')
        for r in runs:
            order_str = ' → '.join(r['utt_order'][:4])
            print(f'    Run {r["run"]}: [{r["utts"]} utts] {order_str}')

        all_results[label] = {
            'runs': runs,
            'avg_wer': avg_wer,
            'min_wer': min_wer,
            'max_wer': max_wer,
            'spread': spread,
            'avg_words': avg_words,
        }
        print()

    # Final verdict
    print(f'{"=" * 70}')
    print('VERDICT: Modulate WER Stability')
    print(f'{"=" * 70}')
    for label, data in all_results.items():
        stable = data['spread'] < 0.05
        status = 'STABLE (spread < 5%)' if stable else f'UNSTABLE (spread = {data["spread"] * 100:.1f}%)'
        print(
            f'  {label}: avg WER = {data["avg_wer"] * 100:.1f}%, range = [{data["min_wer"] * 100:.1f}% - {data["max_wer"] * 100:.1f}%] → {status}'
        )

    with open('/tmp/modulate_stability.json', 'w') as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f'\nRaw results saved to /tmp/modulate_stability.json')


if __name__ == '__main__':
    asyncio.run(main())
