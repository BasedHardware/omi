"""
Listen API Walkthrough — L2 Integration Test for /v4/listen WebSocket.

Streams 5+ minutes of real LibriSpeech audio through the local backend's
/v4/listen WebSocket endpoint, testing both Deepgram and Modulate STT providers.
Captures transcription results, service logs, timing, and identifies flaws.

Prerequisites:
    1. LibriSpeech test-clean extracted:
       curl -L -o /tmp/test-clean.tar.gz https://www.openslr.org/resources/12/test-clean.tar.gz
       cd /tmp && mkdir -p librispeech && tar xzf test-clean.tar.gz -C librispeech
    2. Backend running via beast omi dev:
       beast omi dev start backend
    3. Environment: LOCAL_DEVELOPMENT=true (beast omi dev default)

Usage:
    cd backend && python3 scripts/stt/p_listen_api_walkthrough.py
    cd backend && python3 scripts/stt/p_listen_api_walkthrough.py --provider deepgram
    cd backend && python3 scripts/stt/p_listen_api_walkthrough.py --provider modulate
"""

import argparse
import asyncio
import json
import re
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List

import websockets

BACKEND_HOST = "localhost"
BACKEND_PORT = 8700
LISTEN_URL = f"ws://{BACKEND_HOST}:{BACKEND_PORT}/v4/listen"
DEV_AUTH_HEADER = {"authorization": "Bearer dev-token"}

LIBRISPEECH_DIR = Path('/tmp/librispeech/LibriSpeech/test-clean')
RESULTS_DIR = Path('/tmp/stt_listen_walkthrough')

CHUNK_SIZE = 3200
CHUNK_INTERVAL_S = 0.1
TARGET_DURATION_S = 300

PUNCT_RE = re.compile(r'[^\w\s]', re.UNICODE)


def normalize_for_wer(text: str) -> str:
    return PUNCT_RE.sub('', text).lower().strip()


def build_audio_playlist(target_seconds: float = TARGET_DURATION_S) -> List[dict]:
    if not LIBRISPEECH_DIR.exists():
        print(f'ERROR: LibriSpeech not found at {LIBRISPEECH_DIR}')
        print('  curl -L -o /tmp/test-clean.tar.gz https://www.openslr.org/resources/12/test-clean.tar.gz')
        print('  cd /tmp && mkdir -p librispeech && tar xzf test-clean.tar.gz -C librispeech')
        sys.exit(1)

    playlist = []
    total = 0.0
    speakers = sorted(LIBRISPEECH_DIR.iterdir())

    for speaker_dir in speakers:
        if total >= target_seconds:
            break
        if not speaker_dir.is_dir():
            continue
        for chapter_dir in sorted(speaker_dir.iterdir()):
            if total >= target_seconds:
                break
            if not chapter_dir.is_dir():
                continue

            trans_files = list(chapter_dir.glob('*.trans.txt'))
            transcripts = {}
            for tf in trans_files:
                for line in tf.read_text().strip().split('\n'):
                    parts = line.split(' ', 1)
                    if len(parts) == 2:
                        transcripts[parts[0]] = parts[1]

            for flac in sorted(chapter_dir.glob('*.flac')):
                if total >= target_seconds:
                    break
                uid = flac.stem
                text = transcripts.get(uid, '')
                r = subprocess.run(
                    ['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(flac)],
                    capture_output=True,
                    text=True,
                )
                dur = float(r.stdout.strip()) if r.stdout.strip() else 0
                if dur < 1:
                    continue
                playlist.append(
                    {
                        'uid': uid,
                        'flac': str(flac),
                        'speaker': speaker_dir.name,
                        'text': text,
                        'duration_s': round(dur, 2),
                        'word_count': len(text.split()) if text else 0,
                    }
                )
                total += dur

    return playlist


def convert_to_pcm16(flac_path: str) -> bytes:
    r = subprocess.run(
        ['ffmpeg', '-y', '-i', flac_path, '-f', 's16le', '-ar', '16000', '-ac', '1', 'pipe:1'],
        capture_output=True,
    )
    return r.stdout


def capture_service_logs(service: str, output_path: Path, duration: int = 5):
    try:
        r = subprocess.run(
            ['timeout', str(duration), 'beast', 'omi', 'dev', 'logs', service],
            capture_output=True,
            text=True,
            timeout=duration + 5,
        )
        output_path.write_text(r.stdout + r.stderr)
    except Exception:
        pass


async def run_listen_test(
    provider: str,
    playlist: List[dict],
    stt_service_models: str,
) -> dict:
    results = {
        'provider': provider,
        'stt_service_models': stt_service_models,
        'start_time': datetime.now(tz=None).isoformat(),
        'samples': [],
        'events': [],
        'flaws': [],
        'stats': {},
    }

    total_audio_s = sum(s['duration_s'] for s in playlist)
    total_words = sum(s['word_count'] for s in playlist)
    print(f'\n{"=" * 80}')
    print(f'LISTEN API WALKTHROUGH — {provider.upper()}')
    print(f'{"=" * 80}')
    print(
        f'Audio: {total_audio_s:.1f}s ({total_audio_s / 60:.1f} min), {len(playlist)} utterances, {total_words} words'
    )
    print(f'STT_SERVICE_MODELS={stt_service_models}')
    print(f'Endpoint: {LISTEN_URL}')
    print()

    params = {
        'language': 'en',
        'sample_rate': '16000',
        'codec': 'pcm8',
        'channels': '1',
        'include_speech_profile': 'false',
        'conversation_timeout': '600',
    }
    url = f'{LISTEN_URL}?{"&".join(f"{k}={v}" for k, v in params.items())}'

    segments_received = []
    segments_by_id = {}
    events_received = []
    first_segment_time = [None]
    ready_time = [None]
    connect_start = time.monotonic()

    try:
        ws = await asyncio.wait_for(
            websockets.connect(
                url,
                additional_headers=DEV_AUTH_HEADER,
                ping_timeout=None,
                ping_interval=None,
                max_size=None,
                close_timeout=10,
            ),
            timeout=15,
        )
    except Exception as e:
        err = f'Connection failed: {e}'
        print(f'  ERROR: {err}')
        results['flaws'].append({'type': 'connection_failure', 'detail': err})
        results['end_time'] = datetime.now(tz=None).isoformat()
        return results

    connect_time = time.monotonic() - connect_start
    print(f'  Connected in {connect_time:.2f}s')

    msg_count = [0]

    async def recv_messages():
        nonlocal segments_received, events_received
        try:
            async for raw in ws:
                msg_count[0] += 1
                if isinstance(raw, bytes):
                    ts = time.monotonic() - connect_start
                    if msg_count[0] <= 5:
                        print(f'  [{ts:.1f}s] binary msg #{msg_count[0]}: {len(raw)} bytes')
                    continue
                if raw == 'ping':
                    continue

                ts = time.monotonic() - connect_start

                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    print(f'  [{ts:.1f}s] non-JSON msg: {raw[:200]}')
                    continue

                try:
                    # Server sends segments as bare JSON array [...] or as {"segments": [...]}
                    if isinstance(msg, list):
                        segs = msg
                    elif isinstance(msg, dict):
                        msg['_recv_ts'] = round(ts, 3)

                        if msg.get('status') == 'ready':
                            ready_time[0] = ts
                            events_received.append({'type': 'ready', 'ts': round(ts, 3)})
                            print(f'  [{ts:.1f}s] Server ready')
                            continue

                        if 'segments' in msg:
                            segs = msg['segments']
                        else:
                            msg_type = str(msg.get('type', msg.get('status', 'unknown')))
                            if msg_count[0] <= 30 or msg_type not in ('ping', 'pong'):
                                print(f'  [{ts:.1f}s] event: {msg_type} — {json.dumps(msg)[:300]}')
                            events_received.append(msg)
                            continue
                    else:
                        continue

                    if not isinstance(segs, list):
                        continue
                    seg_texts = []
                    for seg in segs:
                        if not isinstance(seg, dict):
                            continue
                        text = seg.get('text', '').strip()
                        if text:
                            if first_segment_time[0] is None:
                                first_segment_time[0] = ts
                            entry = {
                                'id': seg.get('id', ''),
                                'text': text,
                                'speaker': seg.get('speaker', ''),
                                'start': seg.get('start', 0),
                                'end': seg.get('end', 0),
                                'recv_ts': round(ts, 3),
                                'is_user': seg.get('is_user', False),
                            }
                            segments_received.append(entry)
                            seg_id = seg.get('id', '')
                            if seg_id:
                                segments_by_id[seg_id] = entry
                            seg_texts.append(text[:60])
                    if seg_texts:
                        print(f'  [{ts:.1f}s] SEGMENT: {" | ".join(seg_texts)}')

                except Exception as e:
                    print(f'  [{ts:.1f}s] MSG PARSE ERROR: {e} — raw: {raw[:300]}')
                    continue

        except websockets.exceptions.ConnectionClosed as e:
            events_received.append({'type': 'ws_closed', 'code': e.code, 'reason': str(e.reason)})
            print(f'  WS CLOSED: code={e.code} reason={e.reason}')
        except Exception as e:
            events_received.append({'type': 'recv_error', 'detail': str(e)})
            print(f'  RECV ERROR: {e}')

    recv_task = asyncio.create_task(recv_messages())

    # Wait for ready
    deadline = time.monotonic() + 30
    while ready_time[0] is None and time.monotonic() < deadline:
        if recv_task.done():
            break
        await asyncio.sleep(0.1)

    if ready_time[0] is None:
        results['flaws'].append({'type': 'no_ready_signal', 'detail': 'Server did not send ready status within 30s'})
        print('  WARNING: No ready signal received, proceeding anyway...')

    # Stream audio
    stream_start = time.monotonic()
    total_bytes_sent = 0
    samples_sent = 0

    send_failed = False
    for i, sample in enumerate(playlist):
        if send_failed:
            break
        pcm = convert_to_pcm16(sample['flac'])
        if not pcm:
            continue

        offset = 0
        while offset < len(pcm):
            chunk = pcm[offset : offset + CHUNK_SIZE]
            try:
                await ws.send(chunk)
            except Exception as e:
                err = f'Send failed at sample {i} offset {offset}: {e}'
                results['flaws'].append({'type': 'send_failure', 'detail': err})
                print(f'  ERROR: {err}')
                send_failed = True
                break
            offset += CHUNK_SIZE
            total_bytes_sent += len(chunk)
            await asyncio.sleep(CHUNK_INTERVAL_S)

        if send_failed:
            break

        samples_sent += 1
        elapsed = time.monotonic() - connect_start
        words_so_far = sum(len(s['text'].split()) for s in segments_received)

        if (i + 1) % 10 == 0 or i == len(playlist) - 1:
            print(
                f'  [{elapsed:.0f}s] Sent {samples_sent}/{len(playlist)} samples, '
                f'{total_bytes_sent / 1024:.0f}KB, received {len(segments_received)} segments ({words_so_far} words)'
            )

        # Insert 1s silence between utterances
        silence = b'\x00' * (16000 * 2)
        try:
            await ws.send(silence)
        except Exception:
            send_failed = True
            break
        total_bytes_sent += len(silence)
        await asyncio.sleep(1.0)

    stream_duration = time.monotonic() - stream_start

    # Wait for trailing transcription
    print(f'  Waiting for trailing transcription results...')
    await asyncio.sleep(8)

    # Close
    try:
        await ws.close()
    except Exception:
        pass

    await asyncio.sleep(2)
    recv_task.cancel()
    try:
        await recv_task
    except (asyncio.CancelledError, Exception):
        pass

    total_time = time.monotonic() - connect_start

    # Compute stats — use deduplicated segments (final version of each ID)
    final_segments = list(segments_by_id.values()) if segments_by_id else segments_received
    all_received_text = ' '.join(s['text'] for s in final_segments)
    all_ref_text = ' '.join(s['text'] for s in playlist[:samples_sent])
    received_words = len(all_received_text.split()) if all_received_text else 0

    wer = None
    try:
        from jiwer import wer as compute_wer

        ref_norm = normalize_for_wer(all_ref_text)
        hyp_norm = normalize_for_wer(all_received_text)
        if ref_norm and hyp_norm:
            wer = compute_wer(ref_norm, hyp_norm)
    except ImportError:
        pass

    punct_marks = re.findall(r'[^\w\s]', all_received_text)

    stats = {
        'connect_time_s': round(connect_time, 3),
        'ready_time_s': round(ready_time[0], 3) if ready_time[0] else None,
        'first_segment_time_s': round(first_segment_time[0], 3) if first_segment_time[0] else None,
        'stream_duration_s': round(stream_duration, 1),
        'total_time_s': round(total_time, 1),
        'samples_sent': samples_sent,
        'total_audio_s': round(total_audio_s, 1),
        'total_bytes_sent': total_bytes_sent,
        'segment_updates': len(segments_received),
        'segments_final': len(final_segments),
        'words_received': received_words,
        'ref_words': total_words,
        'wer': round(wer, 4) if wer is not None else None,
        'punctuation_marks': len(punct_marks),
        'unique_speakers': len(set(s['speaker'] for s in final_segments)),
        'events_count': len(events_received),
    }
    results['stats'] = stats
    results['events'] = events_received[:100]
    results['end_time'] = datetime.now(tz=None).isoformat()
    results['final_segments'] = final_segments
    results['full_transcript'] = all_received_text
    results['full_reference'] = all_ref_text

    # Flaw detection
    if not final_segments:
        results['flaws'].append({'type': 'no_transcription', 'detail': 'No segments received from server'})

    if ready_time[0] and first_segment_time[0]:
        latency = first_segment_time[0] - ready_time[0]
        if latency > 15:
            results['flaws'].append(
                {'type': 'high_first_segment_latency', 'detail': f'First segment took {latency:.1f}s after ready'}
            )

    if received_words > 0 and total_words > 0:
        word_ratio = received_words / total_words
        if word_ratio < 0.3:
            results['flaws'].append(
                {
                    'type': 'low_word_capture',
                    'detail': f'Only captured {word_ratio:.0%} of expected words ({received_words}/{total_words})',
                }
            )

    if wer is not None and wer > 0.5:
        results['flaws'].append({'type': 'high_wer', 'detail': f'WER={wer:.1%} — more than 50% of words incorrect'})

    if segments_received:
        last_seg_ts = segments_received[-1]['recv_ts']
        if total_time - last_seg_ts > 30:
            results['flaws'].append(
                {
                    'type': 'stale_transcription',
                    'detail': f'Last segment at {last_seg_ts:.0f}s but test ran {total_time:.0f}s — {total_time - last_seg_ts:.0f}s gap',
                }
            )

    # Print summary
    print(f'\n  RESULTS — {provider.upper()}')
    print(f'  {"─" * 60}')
    print(f'  Connect time:      {stats["connect_time_s"]:.2f}s')
    print(f'  Ready time:        {stats["ready_time_s"]:.2f}s' if stats['ready_time_s'] else '  Ready time:        N/A')
    print(
        f'  First segment:     {stats["first_segment_time_s"]:.2f}s'
        if stats['first_segment_time_s']
        else '  First segment:     N/A'
    )
    print(f'  Stream duration:   {stats["stream_duration_s"]:.1f}s')
    print(f'  Total time:        {stats["total_time_s"]:.1f}s')
    print(f'  Samples sent:      {stats["samples_sent"]}')
    print(f'  Audio duration:    {stats["total_audio_s"]:.1f}s ({stats["total_audio_s"] / 60:.1f} min)')
    print(f'  Bytes sent:        {stats["total_bytes_sent"] / 1024:.0f} KB')
    print(f'  Segment updates:   {stats["segment_updates"]}')
    print(f'  Final segments:    {stats["segments_final"]}')
    print(f'  Words received:    {stats["words_received"]} (ref: {stats["ref_words"]})')
    if stats['wer'] is not None:
        print(f'  WER:               {stats["wer"]:.1%}')
    print(f'  Punctuation:       {stats["punctuation_marks"]}')
    print(f'  Unique speakers:   {stats["unique_speakers"]}')

    if results['flaws']:
        print(f'\n  FLAWS DETECTED:')
        for flaw in results['flaws']:
            print(f'    [{flaw["type"]}] {flaw["detail"]}')
    else:
        print(f'\n  No flaws detected.')

    # Save per-sample transcript comparison
    results['transcript_sample'] = []
    seg_idx = 0
    for sample in playlist[: min(samples_sent, 20)]:
        matching = []
        while seg_idx < len(segments_received):
            s = segments_received[seg_idx]
            matching.append(s['text'])
            seg_idx += 1
            if len(' '.join(matching).split()) >= sample['word_count']:
                break
        results['transcript_sample'].append(
            {
                'uid': sample['uid'],
                'ref': sample['text'],
                'hyp': ' '.join(matching),
                'ref_words': sample['word_count'],
            }
        )

    return results


async def main():
    global BACKEND_PORT, LISTEN_URL

    parser = argparse.ArgumentParser(description='Listen API Walkthrough — L2 Integration Test')
    parser.add_argument('--provider', choices=['deepgram', 'modulate', 'both'], default='both')
    parser.add_argument('--duration', type=int, default=TARGET_DURATION_S, help='Target audio duration in seconds')
    parser.add_argument('--port', type=int, default=BACKEND_PORT, help='Backend port')
    parser.add_argument(
        '--skip-restart', action='store_true', help='Skip backend restart, use currently running backend'
    )
    args = parser.parse_args()

    BACKEND_PORT = args.port
    LISTEN_URL = f'ws://{BACKEND_HOST}:{BACKEND_PORT}/v4/listen'

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    try:
        sock = socket.create_connection((BACKEND_HOST, BACKEND_PORT), timeout=3)
        sock.close()
    except (socket.timeout, ConnectionRefusedError, OSError):
        print(f'ERROR: Backend not running on {BACKEND_HOST}:{BACKEND_PORT}')
        print('  Run: beast omi dev start backend')
        sys.exit(1)

    print(f'Building audio playlist (target: {args.duration}s / {args.duration / 60:.1f} min)...')
    playlist = build_audio_playlist(args.duration)
    total_s = sum(s['duration_s'] for s in playlist)
    print(f'  {len(playlist)} utterances, {total_s:.1f}s ({total_s / 60:.1f} min)')

    providers = []
    if args.provider in ('deepgram', 'both'):
        providers.append(('deepgram', 'dg-nova-3'))
    if args.provider in ('modulate', 'both'):
        providers.append(('modulate', 'modulate-velma-2'))

    all_results = []

    for provider_name, stt_models in providers:
        print(f'\n--- Configuring backend for {provider_name} (STT_SERVICE_MODELS={stt_models}) ---')

        if args.skip_restart:
            print(f'  --skip-restart: using currently running backend on port {BACKEND_PORT}')
        else:
            subprocess.run(['beast', 'omi', 'dev', 'stop', 'backend'], capture_output=True)
            await asyncio.sleep(2)

            env_override = f'STT_SERVICE_MODELS={stt_models}'
            print(f'  Starting backend with {env_override}...')

            subprocess.Popen(
                ['bash', '-c', f'{env_override} beast omi dev start backend'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            ).wait(timeout=30)

            for attempt in range(30):
                try:
                    sock = socket.create_connection((BACKEND_HOST, BACKEND_PORT), timeout=2)
                    sock.close()
                    break
                except (socket.timeout, ConnectionRefusedError, OSError):
                    await asyncio.sleep(1)
            else:
                print(f'  ERROR: Backend did not start within 30s')
                continue

            await asyncio.sleep(3)

        print(f'  Backend ready on port {BACKEND_PORT}')

        pre_log_path = RESULTS_DIR / f'{provider_name}_pre_logs.txt'
        capture_service_logs('backend', pre_log_path, duration=3)

        result = await run_listen_test(provider_name, playlist, stt_models)
        all_results.append(result)

        post_log_path = RESULTS_DIR / f'{provider_name}_post_logs.txt'
        capture_service_logs('backend', post_log_path, duration=5)

        result_path = RESULTS_DIR / f'{provider_name}_result.json'
        with open(result_path, 'w') as f:
            json.dump(result, f, indent=2, default=str)
        print(f'  Results saved to: {result_path}')

    if len(all_results) == 2:
        print(f'\n{"=" * 80}')
        print('COMPARISON SUMMARY')
        print(f'{"=" * 80}')
        print(f'{"Metric":<30} {"Deepgram":<25} {"Modulate":<25}')
        print(f'{"─" * 80}')

        dg, mod = all_results[0], all_results[1]
        dg_s, mod_s = dg['stats'], mod['stats']

        metrics = [
            ('Connect time', f'{dg_s["connect_time_s"]:.2f}s', f'{mod_s["connect_time_s"]:.2f}s'),
            (
                'Ready time',
                f'{dg_s["ready_time_s"]:.2f}s' if dg_s['ready_time_s'] else 'N/A',
                f'{mod_s["ready_time_s"]:.2f}s' if mod_s['ready_time_s'] else 'N/A',
            ),
            (
                'First segment',
                f'{dg_s["first_segment_time_s"]:.2f}s' if dg_s['first_segment_time_s'] else 'N/A',
                f'{mod_s["first_segment_time_s"]:.2f}s' if mod_s['first_segment_time_s'] else 'N/A',
            ),
            ('Segment updates', str(dg_s['segment_updates']), str(mod_s['segment_updates'])),
            ('Final segments', str(dg_s['segments_final']), str(mod_s['segments_final'])),
            (
                'Words received',
                f'{dg_s["words_received"]} / {dg_s["ref_words"]}',
                f'{mod_s["words_received"]} / {mod_s["ref_words"]}',
            ),
            (
                'WER',
                f'{dg_s["wer"]:.1%}' if dg_s['wer'] is not None else 'N/A',
                f'{mod_s["wer"]:.1%}' if mod_s['wer'] is not None else 'N/A',
            ),
            ('Punctuation marks', str(dg_s['punctuation_marks']), str(mod_s['punctuation_marks'])),
            ('Unique speakers', str(dg_s['unique_speakers']), str(mod_s['unique_speakers'])),
            ('Flaws', str(len(dg['flaws'])), str(len(mod['flaws']))),
        ]

        for label, dg_val, mod_val in metrics:
            print(f'{label:<30} {dg_val:<25} {mod_val:<25}')

        print(f'\nTRANSCRIPT COMPARISON (first 5 samples):')
        for i in range(min(5, len(dg.get('transcript_sample', [])))):
            dg_t = dg['transcript_sample'][i] if i < len(dg.get('transcript_sample', [])) else {}
            mod_t = mod['transcript_sample'][i] if i < len(mod.get('transcript_sample', [])) else {}
            print(f'\n  [{dg_t.get("uid", "?")}]')
            print(f'    REF:      {dg_t.get("ref", "N/A")}')
            print(f'    DEEPGRAM: {dg_t.get("hyp", "N/A")}')
            print(f'    MODULATE: {mod_t.get("hyp", "N/A")}')

    print(f'\nALL FLAWS FOUND:')
    all_flaws = []
    for r in all_results:
        for f in r['flaws']:
            f['provider'] = r['provider']
            all_flaws.append(f)
    if all_flaws:
        for f in all_flaws:
            print(f'  [{f["provider"]}] [{f["type"]}] {f["detail"]}')
    else:
        print('  None detected.')

    combined_path = RESULTS_DIR / 'listen_walkthrough_combined.json'
    with open(combined_path, 'w') as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f'\nCombined results saved to: {combined_path}')
    print(f'Log files in: {RESULTS_DIR}/')


if __name__ == '__main__':
    asyncio.run(main())
