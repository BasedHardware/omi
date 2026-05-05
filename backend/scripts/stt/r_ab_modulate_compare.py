"""
A/B comparison: Direct Modulate API vs Backend /v4/listen (Modulate STT).

Same audio, same pacing, same silence gaps. Compares WER to find implementation gaps.

Usage:
    # Start backend first with Modulate:
    #   cd backend && STT_SERVICE_MODELS=modulate-velma-2 python3 -m uvicorn main:app --port 8700
    # Then run:
    cd backend && python3 scripts/stt/r_ab_modulate_compare.py
    cd backend && python3 scripts/stt/r_ab_modulate_compare.py --duration 120  # shorter test
"""

import argparse
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

MODULATE_API_KEY = os.getenv('MODULATE_API_KEY', '11561b42-7e06-453e-a8a3-01f4eb3e9d2b')
BACKEND_HOST = 'localhost'
BACKEND_PORT = 8700
LIBRISPEECH_DIR = Path('/tmp/librispeech/LibriSpeech/test-clean')

CHUNK_SIZE = 3200
CHUNK_INTERVAL_S = 0.1
SILENCE_BETWEEN_UTTERANCES_S = 1.0
SAMPLE_RATE = 16000
PUNCT_RE = re.compile(r'[^\w\s]', re.UNICODE)


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


async def send_audio(ws, playlist, label, send_eos=True):
    """Send audio chunks with identical pacing. Returns (total_bytes, samples_sent)."""
    total_bytes = 0
    samples_sent = 0
    silence = b'\x00' * (SAMPLE_RATE * 2 * int(SILENCE_BETWEEN_UTTERANCES_S))
    t0 = time.monotonic()

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
                print(f'  [{label}] Send error at sample {i}: {e}')
                return total_bytes, samples_sent
            offset += CHUNK_SIZE
            total_bytes += len(chunk)
            await asyncio.sleep(CHUNK_INTERVAL_S)

        samples_sent += 1

        # 1s silence between utterances (identical for both tests)
        try:
            await ws.send(silence)
            total_bytes += len(silence)
        except Exception:
            break
        await asyncio.sleep(SILENCE_BETWEEN_UTTERANCES_S)

        if (i + 1) % 10 == 0:
            elapsed = time.monotonic() - t0
            print(f'  [{label}] [{elapsed:.0f}s] Sent {samples_sent}/{len(playlist)}, {total_bytes / 1024:.0f}KB')

    # Signal end of stream
    if send_eos:
        try:
            await ws.send(b'')
        except Exception:
            pass

    elapsed = time.monotonic() - t0
    print(f'  [{label}] All audio sent: {samples_sent} samples, {total_bytes / 1024:.0f}KB in {elapsed:.0f}s')
    return total_bytes, samples_sent


async def test_direct_modulate(playlist):
    """Test 1: Direct Modulate API — collect utterances and partials."""
    print('\n' + '=' * 70)
    print('TEST A: Direct Modulate API')
    print('=' * 70)

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
    print('  Connected to Modulate API')

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
                elapsed = time.monotonic() - t0
                if mt == 'utterance':
                    utt = msg.get('utterance', msg)
                    text = utt.get('text', '').strip()
                    utterances.append(utt)
                    last_partial_text = ''
                    print(f'  [DIRECT] [{elapsed:.1f}s] UTT #{len(utterances)}: {text[:80]}...')
                elif mt == 'partial_utterance':
                    pu = msg.get('partial_utterance', msg)
                    partials.append(pu)
                    last_partial_text = pu.get('text', '').strip()
                elif mt == 'done':
                    print(f'  [DIRECT] [{elapsed:.1f}s] DONE: duration_ms={msg.get("duration_ms")}')
                    done_event.set()
                    break
                elif mt == 'error':
                    print(f'  [DIRECT] [{elapsed:.1f}s] ERROR: {msg}')
                    done_event.set()
                    break
        except websockets.exceptions.ConnectionClosed as e:
            print(f'  [DIRECT] WS closed: {e}')
        finally:
            done_event.set()

    recv_task = asyncio.create_task(recv())
    await send_audio(ws, playlist, 'DIRECT', send_eos=False)

    print('  [DIRECT] Waiting for done event (up to 90s)...')
    try:
        await asyncio.wait_for(done_event.wait(), timeout=90)
    except asyncio.TimeoutError:
        print('  [DIRECT] Timed out waiting for done')

    recv_task.cancel()
    try:
        await ws.close()
    except Exception:
        pass

    # Build transcripts
    utt_text = ' '.join(u.get('text', '') for u in utterances).strip()
    # For partials: take the last partial text if no utterance followed it
    # (simulates our backend's _flush_partial at done)
    partial_final = utt_text
    if last_partial_text and not utt_text.endswith(last_partial_text):
        partial_final = (utt_text + ' ' + last_partial_text).strip() if utt_text else last_partial_text

    return {
        'utterances': utterances,
        'partials': partials,
        'utterance_text': utt_text,
        'utterance_plus_partial_text': partial_final,
        'utterance_count': len(utterances),
        'partial_count': len(partials),
    }


async def test_backend_listen(playlist, port=BACKEND_PORT):
    """Test 2: Backend /v4/listen with Modulate STT — collect segments."""
    print('\n' + '=' * 70)
    print('TEST B: Backend /v4/listen (Modulate STT)')
    print('=' * 70)

    params = {
        'language': 'en',
        'sample_rate': str(SAMPLE_RATE),
        'codec': 'pcm16',
        'channels': '1',
        'include_speech_profile': 'false',
        'conversation_timeout': '600',
    }
    url = f'ws://{BACKEND_HOST}:{port}/v4/listen?{"&".join(f"{k}={v}" for k, v in params.items())}'

    try:
        ws = await asyncio.wait_for(
            websockets.connect(
                url,
                additional_headers={'authorization': 'Bearer dev-token'},
                ping_timeout=None,
                ping_interval=None,
                max_size=None,
                close_timeout=10,
            ),
            timeout=15,
        )
    except Exception as e:
        print(f'  [BACKEND] Connection failed: {e}')
        return None

    print(f'  [BACKEND] Connected')

    segments = []
    segments_by_id = {}
    ready = asyncio.Event()
    recv_done = asyncio.Event()
    t0 = time.monotonic()

    async def recv():
        try:
            async for raw in ws:
                if isinstance(raw, bytes) or raw == 'ping':
                    continue
                elapsed = time.monotonic() - t0
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                if isinstance(msg, list):
                    segs = msg
                elif isinstance(msg, dict):
                    if msg.get('status') == 'ready':
                        ready.set()
                        print(f'  [BACKEND] [{elapsed:.1f}s] Ready')
                        continue
                    if 'segments' in msg:
                        segs = msg['segments']
                    else:
                        continue
                else:
                    continue

                if not isinstance(segs, list):
                    continue
                for seg in segs:
                    if not isinstance(seg, dict):
                        continue
                    text = seg.get('text', '').strip()
                    if text:
                        entry = {
                            'id': seg.get('id', ''),
                            'text': text,
                            'speaker': seg.get('speaker', ''),
                            'start': seg.get('start', 0),
                            'end': seg.get('end', 0),
                            'recv_ts': round(elapsed, 3),
                        }
                        segments.append(entry)
                        sid = seg.get('id', '')
                        if sid:
                            segments_by_id[sid] = entry
                        print(f'  [BACKEND] [{elapsed:.1f}s] SEG: {text[:80]}')
        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception as e:
            print(f'  [BACKEND] Recv error: {e}')
        finally:
            recv_done.set()

    recv_task = asyncio.create_task(recv())

    # Wait for ready
    try:
        await asyncio.wait_for(ready.wait(), timeout=30)
    except asyncio.TimeoutError:
        print('  [BACKEND] No ready signal, proceeding...')

    await send_audio(ws, playlist, 'BACKEND', send_eos=False)

    # Wait for trailing results — match the drain timeout our implementation uses
    print('  [BACKEND] Waiting 90s for trailing results...')
    await asyncio.sleep(90)

    try:
        await ws.close()
    except Exception:
        pass
    await asyncio.sleep(2)
    recv_task.cancel()

    final = list(segments_by_id.values()) if segments_by_id else segments
    full_text = ' '.join(s['text'] for s in final).strip()

    return {
        'segments': final,
        'segment_updates': len(segments),
        'segment_final_count': len(final),
        'full_text': full_text,
    }


def analyze_and_compare(ref_text, direct_result, backend_result):
    """Compare WER and identify word-level differences."""
    ref_norm = normalize(ref_text)
    ref_words = ref_norm.split()

    print('\n' + '=' * 70)
    print('COMPARISON RESULTS')
    print('=' * 70)

    # Direct Modulate
    d_utt_text = normalize(direct_result['utterance_text'])
    d_utt_plus = normalize(direct_result['utterance_plus_partial_text'])
    d_utt_words = d_utt_text.split()
    d_utt_plus_words = d_utt_plus.split()
    d_utt_wer = compute_wer(ref_norm, d_utt_text) if d_utt_text else 1.0
    d_plus_wer = compute_wer(ref_norm, d_utt_plus) if d_utt_plus else 1.0

    print(f'\n--- TEST A: Direct Modulate API ---')
    print(f'  Utterances received:      {direct_result["utterance_count"]}')
    print(f'  Partials received:        {direct_result["partial_count"]}')
    print(f'  Words (utterances only):  {len(d_utt_words)} / {len(ref_words)}')
    print(f'  Words (utt + partial):    {len(d_utt_plus_words)} / {len(ref_words)}')
    print(f'  WER (utterances only):    {d_utt_wer * 100:.1f}%')
    print(f'  WER (utt + last partial): {d_plus_wer * 100:.1f}%')

    # Backend
    if backend_result is None:
        print(f'\n--- TEST B: Backend --- FAILED (no connection)')
        return

    b_text = normalize(backend_result['full_text'])
    b_words = b_text.split()
    b_wer = compute_wer(ref_norm, b_text) if b_text else 1.0

    print(f'\n--- TEST B: Backend /v4/listen (Modulate) ---')
    print(f'  Segment updates:          {backend_result["segment_updates"]}')
    print(f'  Final segments:           {backend_result["segment_final_count"]}')
    print(f'  Words received:           {len(b_words)} / {len(ref_words)}')
    print(f'  WER:                      {b_wer * 100:.1f}%')

    # Delta
    print(f'\n--- DELTA (B minus A) ---')
    wer_delta = (b_wer - d_plus_wer) * 100
    word_delta = len(b_words) - len(d_utt_plus_words)
    print(
        f'  WER difference:           {wer_delta:+.1f}% ({"WORSE" if wer_delta > 0 else "BETTER" if wer_delta < 0 else "SAME"})'
    )
    print(f'  Word count difference:    {word_delta:+d} words')

    if abs(wer_delta) < 2.0:
        print(f'\n  VERDICT: WER difference is minimal (<2%). No significant implementation flaw.')
    elif wer_delta > 0:
        print(f'\n  VERDICT: Backend is {wer_delta:.1f}% worse than direct. Investigating...')
        # Show word-level diff
        _show_transcript_diff(d_utt_plus, b_text, ref_norm)
    else:
        print(f'\n  VERDICT: Backend is {-wer_delta:.1f}% better than direct (combine_segments dedup may help).')

    # Show first few segments from each
    print(f'\n--- TRANSCRIPT SAMPLES ---')
    print(f'  REF (first 200 chars):     {ref_text[:200]}')
    print(f'  DIRECT (first 200 chars):  {direct_result["utterance_plus_partial_text"][:200]}')
    print(f'  BACKEND (first 200 chars): {backend_result["full_text"][:200]}')

    # Save full results
    out = {
        'ref_words': len(ref_words),
        'direct': {
            'utterance_count': direct_result['utterance_count'],
            'partial_count': direct_result['partial_count'],
            'utt_word_count': len(d_utt_words),
            'utt_plus_word_count': len(d_utt_plus_words),
            'wer_utt': round(d_utt_wer, 4),
            'wer_utt_plus': round(d_plus_wer, 4),
            'text': direct_result['utterance_plus_partial_text'],
        },
        'backend': {
            'segment_updates': backend_result['segment_updates'],
            'final_segments': backend_result['segment_final_count'],
            'word_count': len(b_words),
            'wer': round(b_wer, 4),
            'text': backend_result['full_text'],
        },
        'delta_wer_pct': round(wer_delta, 2),
        'delta_words': word_delta,
        'ref_text': ref_text,
    }
    out_path = '/tmp/modulate_ab_compare.json'
    with open(out_path, 'w') as f:
        json.dump(out, f, indent=2)
    print(f'\nFull results saved to {out_path}')


def _show_transcript_diff(direct_text, backend_text, ref_text):
    """Show where backend transcript diverges from direct."""
    d_words = direct_text.split()
    b_words = backend_text.split()
    r_words = ref_text.split()

    # Find words in direct but not in backend (potential word loss)
    d_set = set(w.lower() for w in d_words)
    b_set = set(w.lower() for w in b_words)
    lost = d_set - b_set
    gained = b_set - d_set
    if lost:
        print(f'\n  Words in DIRECT but not in BACKEND (sample): {list(lost)[:20]}')
    if gained:
        print(f'  Words in BACKEND but not in DIRECT (sample): {list(gained)[:20]}')


async def main():
    parser = argparse.ArgumentParser(description='A/B: Direct Modulate vs Backend Listen')
    parser.add_argument('--duration', type=int, default=300, help='Target audio duration (seconds)')
    parser.add_argument('--port', type=int, default=BACKEND_PORT, help='Backend port')
    parser.add_argument('--direct-only', action='store_true', help='Run only direct test')
    parser.add_argument('--backend-only', action='store_true', help='Run only backend test')
    args = parser.parse_args()

    _port = args.port

    if not LIBRISPEECH_DIR.exists():
        print('ERROR: LibriSpeech not found. Run:')
        print('  curl -L -o /tmp/test-clean.tar.gz https://www.openslr.org/resources/12/test-clean.tar.gz')
        print('  cd /tmp && mkdir -p librispeech && tar xzf test-clean.tar.gz -C librispeech')
        sys.exit(1)

    print(f'Building playlist (target: {args.duration}s)...')
    playlist, total_s = build_playlist(args.duration)
    ref_text = ' '.join(s['ref'] for s in playlist)
    ref_words = ref_text.split()
    print(f'  {len(playlist)} utterances, {total_s:.1f}s, {len(ref_words)} ref words')

    direct_result = None
    backend_result = None

    if not args.backend_only:
        direct_result = await test_direct_modulate(playlist)

    if not args.direct_only:
        backend_result = await test_backend_listen(playlist, port=_port)

    if direct_result and backend_result:
        analyze_and_compare(ref_text, direct_result, backend_result)
    elif direct_result:
        ref_norm = normalize(ref_text)
        d_text = normalize(direct_result['utterance_plus_partial_text'])
        wer = compute_wer(ref_norm, d_text)
        print(f'\nDirect only — WER: {wer * 100:.1f}%, Words: {len(d_text.split())} / {len(ref_words)}')
    elif backend_result:
        ref_norm = normalize(ref_text)
        b_text = normalize(backend_result['full_text'])
        wer = compute_wer(ref_norm, b_text)
        print(f'\nBackend only — WER: {wer * 100:.1f}%, Words: {len(b_text.split())} / {len(ref_words)}')


if __name__ == '__main__':
    asyncio.run(main())
