"""
Debug: stream the same 5-min LibriSpeech audio directly to Modulate API
and log every raw message. Compare raw Modulate output vs what our
SafeModulateSocket produces to find where words get lost.

Usage:
  python3 scripts/stt/q_modulate_debug.py
"""

import asyncio
import json
import os
import struct
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
TARGET_DURATION = 300


def build_playlist(target_s):
    playlist = []
    total_s = 0
    ref_path = LIBRISPEECH_DIR
    for reader_dir in sorted(ref_path.iterdir()):
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
                playlist.append({'flac': str(flac), 'ref': ref, 'uid': uid})
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
                total_s += dur
                if total_s >= target_s:
                    return playlist, total_s
    return playlist, total_s


def convert_to_pcm16(flac_path):
    result = subprocess.run(
        ['ffmpeg', '-y', '-i', flac_path, '-f', 's16le', '-ar', '16000', '-ac', '1', 'pipe:1'],
        capture_output=True,
    )
    return result.stdout if result.returncode == 0 else None


def compute_wer(ref, hyp):
    ref_words = ref.upper().split()
    hyp_words = hyp.upper().split()
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


async def main():
    playlist, total_s = build_playlist(TARGET_DURATION)
    ref_text = ' '.join(s['ref'] for s in playlist)
    ref_words = ref_text.split()
    print(f'Audio: {total_s:.1f}s, {len(playlist)} utterances, {len(ref_words)} ref words\n')

    # --- Test 1: Direct to Modulate API (like benchmark, but one long connection) ---
    print('=' * 70)
    print('TEST 1: Direct to Modulate API — single long connection, all audio')
    print('=' * 70)

    params = {
        'api_key': MODULATE_API_KEY,
        'speaker_diarization': 'true',
        'partial_results': 'true',
        'sample_rate': '16000',
        'audio_format': 's16le',
        'num_channels': '1',
        'language': 'en',
    }
    uri = f'wss://modulate-developer-apis.com/api/velma-2-stt-streaming?{urllib.parse.urlencode(params)}'

    ws = await websockets.connect(uri, ping_timeout=30, ping_interval=10, max_size=None)
    print(f'Connected to Modulate API')

    raw_messages = []
    all_utterances = []
    all_partials = []
    recv_done = asyncio.Event()

    async def recv_loop():
        try:
            async for raw_msg in ws:
                msg = json.loads(raw_msg)
                msg['_recv_ts'] = time.monotonic() - send_start
                raw_messages.append(msg)
                msg_type = msg.get('type', '')
                if msg_type == 'partial_utterance':
                    pu = msg.get('partial_utterance', msg)
                    all_partials.append(pu)
                elif msg_type == 'utterance':
                    utt = msg.get('utterance', msg)
                    all_utterances.append(utt)
                    print(f'  [{msg["_recv_ts"]:.1f}s] UTTERANCE: {utt.get("text", "")[:80]}')
                elif msg_type == 'done':
                    print(f'  [{msg["_recv_ts"]:.1f}s] DONE: duration_ms={msg.get("duration_ms")}')
                elif msg_type == 'error':
                    print(f'  [{msg["_recv_ts"]:.1f}s] ERROR: {msg}')
        except websockets.exceptions.ConnectionClosed as e:
            print(f'  WS closed: {e}')
        finally:
            recv_done.set()

    send_start = time.monotonic()
    recv_task = asyncio.create_task(recv_loop())

    total_bytes = 0
    for i, sample in enumerate(playlist):
        pcm = convert_to_pcm16(sample['flac'])
        if not pcm:
            continue
        offset = 0
        while offset < len(pcm):
            chunk = pcm[offset : offset + CHUNK_SIZE]
            try:
                await ws.send(chunk)
            except Exception as e:
                print(f'  Send error at sample {i}: {e}')
                break
            offset += CHUNK_SIZE
            total_bytes += len(chunk)
            await asyncio.sleep(CHUNK_INTERVAL_S)

        if (i + 1) % 10 == 0:
            elapsed = time.monotonic() - send_start
            print(f'  [{elapsed:.0f}s] Sent {i + 1}/{len(playlist)} samples, {total_bytes / 1024:.0f}KB')

    # Signal end of audio
    try:
        await ws.send('')
    except Exception:
        pass

    print(f'\nAll audio sent ({total_bytes / 1024:.0f}KB). Waiting for final results...')
    try:
        await asyncio.wait_for(recv_done.wait(), timeout=60)
    except asyncio.TimeoutError:
        print('  Timed out waiting for recv loop')
    recv_task.cancel()
    try:
        await ws.close()
    except Exception:
        pass

    # Analyze raw results
    print(f'\n--- RAW MODULATE RESULTS ---')
    print(f'Total messages: {len(raw_messages)}')
    print(f'Utterances (final): {len(all_utterances)}')
    print(f'Partial utterances: {len(all_partials)}')

    # Build transcript from final utterances only
    utterance_text = ' '.join(u.get('text', '') for u in all_utterances).strip()
    utterance_words = utterance_text.split()
    print(f'Words from utterances: {len(utterance_words)}')

    # Build transcript from partials (simulating confirmed-word delta)
    partial_words_emitted = 0
    delta_words = []
    for pu in all_partials:
        text = pu.get('text', '').strip()
        if not text:
            continue
        words = text.split()
        confirmed_end = len(words) - 1
        if confirmed_end <= partial_words_emitted:
            continue
        delta = words[partial_words_emitted:confirmed_end]
        delta_words.extend(delta)
        partial_words_emitted = confirmed_end

    # Also handle final utterances with the delta approach
    for utt in all_utterances:
        text = utt.get('text', '').strip()
        if not text:
            continue
        words = text.split()
        if partial_words_emitted > 0:
            remaining = words[partial_words_emitted:]
            partial_words_emitted = 0
            delta_words.extend(remaining)
        else:
            delta_words.extend(words)

    delta_text = ' '.join(delta_words)
    print(f'Words from delta approach: {len(delta_words)}')

    # WER
    import re

    def strip_punct(t):
        return re.sub(r'[^\w\s]', '', t)

    ref_clean = strip_punct(ref_text)
    utt_wer = compute_wer(ref_clean, strip_punct(utterance_text))
    delta_wer = compute_wer(ref_clean, strip_punct(delta_text))
    print(f'\nWER (utterances only): {utt_wer * 100:.1f}%')
    print(f'WER (delta approach):  {delta_wer * 100:.1f}%')

    # Show first few utterances
    print(f'\n--- FIRST 5 UTTERANCES ---')
    for i, u in enumerate(all_utterances[:5]):
        t = u.get('text', '')
        print(f'  [{i}] start={u.get("start_ms", 0)}ms dur={u.get("duration_ms", 0)}ms words={len(t.split())}')
        print(f'      {t[:120]}')

    # Show last few utterances
    print(f'\n--- LAST 5 UTTERANCES ---')
    for i, u in enumerate(all_utterances[-5:]):
        t = u.get('text', '')
        print(
            f'  [{len(all_utterances) - 5 + i}] start={u.get("start_ms", 0)}ms dur={u.get("duration_ms", 0)}ms words={len(t.split())}'
        )
        print(f'      {t[:120]}')

    # Check partial_words_emitted drift
    print(f'\n--- PARTIAL WORD COUNTER ANALYSIS ---')
    max_counter = 0
    resets = 0
    prev_counter = 0
    for pu in all_partials:
        words = pu.get('text', '').split()
        if len(words) - 1 < prev_counter and prev_counter > 5:
            resets += 1
        if len(words) > max_counter:
            max_counter = len(words)
        prev_counter = len(words) - 1

    print(f'Max partial word count in a single partial: {max_counter}')
    print(f'Times counter appeared to reset (new partial shorter than prev): {resets}')

    # Transcript samples
    print(f'\n--- UTTERANCE TRANSCRIPT (first 300 chars) ---')
    print(utterance_text[:300])
    print(f'\n--- DELTA TRANSCRIPT (first 300 chars) ---')
    print(delta_text[:300])
    print(f'\n--- REFERENCE (first 300 chars) ---')
    print(ref_text[:300])

    # Save full results
    # Detailed delta trace — show where words get lost/garbled
    print(f'\n--- DELTA APPROACH DETAILED TRACE (first 30 events) ---')
    pwe = 0
    trace_events = []
    for idx, pu in enumerate(all_partials):
        text = pu.get('text', '').strip()
        if not text:
            continue
        words = text.split()
        confirmed_end = len(words) - 1
        old_pwe = pwe
        if confirmed_end <= pwe:
            if len(words) < pwe and pwe > 5:
                trace_events.append(
                    {
                        'idx': idx,
                        'action': 'RESET_SKIPPED',
                        'words_in_partial': len(words),
                        'counter': pwe,
                        'text_start': ' '.join(words[:5]),
                    }
                )
            continue
        delta = words[pwe:confirmed_end]
        pwe = confirmed_end
        if old_pwe > 5 and len(words) < old_pwe:
            trace_events.append(
                {
                    'idx': idx,
                    'action': 'CROSS_BOUNDARY_EMIT',
                    'words_in_partial': len(words),
                    'old_counter': old_pwe,
                    'new_counter': pwe,
                    'delta': ' '.join(delta[:10]),
                    'text_start': ' '.join(words[:5]),
                }
            )
        elif len(trace_events) < 30:
            trace_events.append(
                {
                    'idx': idx,
                    'action': 'EMIT',
                    'words_in_partial': len(words),
                    'counter': pwe,
                    'delta': ' '.join(delta[:8]),
                }
            )

    for utt_idx, utt in enumerate(all_utterances):
        text = utt.get('text', '').strip()
        if not text:
            continue
        words = text.split()
        if pwe > 0:
            remaining = words[pwe:]
            trace_events.append(
                {
                    'idx': f'UTT{utt_idx}',
                    'action': 'UTT_RESET',
                    'words_in_utterance': len(words),
                    'old_counter': pwe,
                    'remaining_words': len(remaining),
                    'remaining_start': ' '.join(remaining[:5]) if remaining else '(none)',
                }
            )
            pwe = 0
        else:
            trace_events.append(
                {
                    'idx': f'UTT{utt_idx}',
                    'action': 'UTT_FULL',
                    'words_in_utterance': len(words),
                }
            )

    for ev in trace_events[:50]:
        print(f'  {ev}')

    # Count how many partials were skipped due to counter
    pwe2 = 0
    skipped = 0
    emitted = 0
    cross_boundary = 0
    for pu in all_partials:
        text = pu.get('text', '').strip()
        if not text:
            continue
        words = text.split()
        confirmed_end = len(words) - 1
        if confirmed_end <= pwe2:
            skipped += 1
            continue
        if pwe2 > 10 and len(words) < pwe2:
            cross_boundary += 1
        pwe2 = confirmed_end
        emitted += 1

    print(f'\n--- DELTA COUNTER SUMMARY ---')
    print(f'Partials processed: {len(all_partials)}')
    print(f'Emitted: {emitted}')
    print(f'Skipped (counter too high): {skipped}')
    print(f'Cross-boundary emits (wrong offset): {cross_boundary}')

    out = {
        'raw_message_count': len(raw_messages),
        'utterance_count': len(all_utterances),
        'partial_count': len(all_partials),
        'utterance_wer': utt_wer,
        'delta_wer': delta_wer,
        'utterance_word_count': len(utterance_words),
        'delta_word_count': len(delta_words),
        'ref_word_count': len(ref_words),
        'utterance_text': utterance_text,
        'delta_text': delta_text,
        'ref_text': ref_text,
        'utterances': all_utterances,
        'partial_count_by_utterance': max_counter,
        'counter_resets': resets,
        'partials': [
            {'text': p.get('text', ''), 'start_ms': p.get('start_ms', 0), 'type': 'partial'} for p in all_partials
        ],
    }
    out_path = '/tmp/modulate_debug_direct.json'
    with open(out_path, 'w') as f:
        json.dump(out, f, indent=2)
    print(f'\nFull results saved to {out_path}')


if __name__ == '__main__':
    asyncio.run(main())
