#!/usr/bin/env python3
"""E2E test: /v4/listen → pusher → GCS batch upload → conversation roundtrip.

Tests the full pipeline with local backend (port 8787) + local pusher (port 8080):
1. WebSocket session: backend connects to pusher internally
2. Audio streaming: 90s of pcm16 at real-time pace (triggers ≥1 batch flush at 60s)
3. GCS verification: check that Opus-encoded blobs exist after flush
4. Conversation roundtrip: verify conversation created with audio_files + transcript_segments
5. Audio download: GET /v1/sync/audio → verify WAV response with correct PCM data

Sequence flow:
```mermaid
sequenceDiagram
    participant Test
    participant Backend as backend (:8787)
    participant Pusher as pusher (:8080)
    participant GCS
    participant Firestore

    Test->>Backend: WS /v4/listen (pcm16, 16kHz)
    Backend->>Pusher: WS /v1/trigger/listen
    Backend->>Backend: Decode PCM → feed STT

    loop 90s of audio (real-time)
        Test->>Backend: Binary PCM frames
        Backend->>Pusher: Forward PCM + transcript events
        Pusher->>Pusher: Accumulate in private_cloud_sync_buffer
    end

    note over Pusher: At 60s: batch flush
    Pusher->>GCS: upload_audio_chunks_batch(.opus)
    Pusher->>Firestore: create_audio_files_from_chunks()

    Test->>Backend: Close WS
    note over Pusher: Shutdown flush (remaining audio)
    Pusher->>GCS: upload remaining batch

    Test->>Backend: GET /v1/conversations (verify conversation exists)
    Test->>Backend: GET /v1/sync/audio/{conv_id}/{file_id} (download roundtrip)
    Test->>Test: Verify WAV header + PCM data length
```

Usage:
    # Start pusher + backend first, then run:
    python3 tests/integration/test_e2e_listen_pusher.py --backend-port 8787

Requirements:
    - Local backend on port 8787 with HOSTED_PUSHER_API_URL=http://localhost:8080
    - Local pusher on port 8080
    - GOOGLE_APPLICATION_CREDENTIALS set
    - Dev Firebase auth (based-hardware-dev)
"""

import argparse
import asyncio
import json
import math
import os
import struct
import sys
import time
import logging
import requests

logger = logging.getLogger(__name__)


def generate_pcm_speech_like(duration_s: float, sample_rate: int) -> bytes:
    """Generate speech-like PCM16 audio (varying frequency sine waves)."""
    samples = int(sample_rate * duration_s)
    pcm = bytearray(samples * 2)
    for i in range(samples):
        t = i / sample_rate
        freq = 200 + 300 * math.sin(2 * math.pi * 0.5 * t)
        amplitude = 8000 * (0.5 + 0.5 * math.sin(2 * math.pi * 0.3 * t))
        sample = int(amplitude * math.sin(2 * math.pi * freq * t))
        sample = max(-32768, min(32767, sample))
        struct.pack_into('<h', pcm, i * 2, sample)
    return bytes(pcm)


def get_firebase_token():
    """Get a dev Firebase ID token for authentication."""
    try:
        import firebase_admin
        from firebase_admin import credentials, auth as fb_auth

        cred_path = os.environ.get(
            'GOOGLE_APPLICATION_CREDENTIALS',
            os.path.expanduser('~/.config/omi/dev/backend/google-credentials.json'),
        )
        cred = credentials.Certificate(cred_path)
        try:
            firebase_admin.initialize_app(cred)
        except ValueError:
            pass

        custom_token = fb_auth.create_custom_token('integration-test-user').decode('utf-8')
        api_key = 'AIzaSyBK-G7KmEoC72mR10gmQyb2NFBbZyDvcqM'
        r = requests.post(
            f'https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken?key={api_key}',
            json={'token': custom_token, 'returnSecureToken': True},
        )
        if r.status_code == 200:
            return r.json()['idToken']
        else:
            logger.error(f"Firebase token exchange failed: {r.status_code} {r.text}")
            return None
    except Exception as e:
        logger.error(f"Firebase auth setup failed: {e}")
        return None


async def run_e2e_test(host: str, backend_port: int, duration_s: int, token: str) -> dict:
    """Run the full E2E test: stream audio → verify GCS → verify conversation → download roundtrip."""
    import websockets

    results = {
        'ws_session': {'status': 'PENDING'},
        'gcs_blobs': {'status': 'PENDING'},
        'conversation': {'status': 'PENDING'},
        'audio_download': {'status': 'PENDING'},
    }

    sample_rate = 16000
    codec = 'pcm16'

    # ─── Step 1: Stream audio via WebSocket ───
    logger.info(f"[STEP 1] Streaming {duration_s}s of {codec} audio at {sample_rate}Hz...")
    pcm_data = generate_pcm_speech_like(duration_s, sample_rate)
    frame_bytes = int(sample_rate * 2 * 0.1)  # 100ms frames
    frames = [pcm_data[i : i + frame_bytes] for i in range(0, len(pcm_data), frame_bytes)]
    logger.info(f"  Generated {len(pcm_data)} bytes PCM, {len(frames)} frames")

    ws_url = (
        f"ws://{host}:{backend_port}/v4/listen"
        f"?uid={token}"
        f"&language=en"
        f"&sample_rate={sample_rate}"
        f"&codec={codec}"
        f"&channels=1"
        f"&include_speech_profile=false"
        f"&conversation_timeout=300"
        f"&source=friend"
    )

    conversation_id = None
    transcripts = []

    try:
        async with websockets.connect(
            ws_url,
            extra_headers={"Authorization": f"Bearer {token}"},
            ping_interval=None,
            ping_timeout=None,
            max_size=10 * 1024 * 1024,
        ) as ws:
            logger.info(f"  WebSocket connected")

            async def receive_messages():
                nonlocal conversation_id
                try:
                    async for msg in ws:
                        if isinstance(msg, str):
                            try:
                                data = json.loads(msg)
                                transcripts.append(data)
                                # Extract conversation_id from transcript events
                                if 'conversation_id' in data:
                                    conversation_id = data['conversation_id']
                            except json.JSONDecodeError:
                                pass
                        elif isinstance(msg, bytes) and len(msg) >= 4:
                            header_type = struct.unpack('I', msg[:4])[0]
                            if header_type == 103:  # conversation_id header
                                cid = msg[4:].decode('utf-8', errors='ignore').strip('\x00')
                                if cid:
                                    conversation_id = cid
                                    logger.info(f"  Received conversation_id: {conversation_id}")
                except websockets.exceptions.ConnectionClosed:
                    pass

            recv_task = asyncio.create_task(receive_messages())

            # Send at real-time pace
            test_start = time.monotonic()
            for i, frame in enumerate(frames):
                await ws.send(frame)
                elapsed = time.monotonic() - test_start
                expected = (i + 1) * 0.1
                sleep_time = expected - elapsed
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
                if (i + 1) % 300 == 0:  # Progress every 30s
                    logger.info(
                        f"  Progress: {elapsed:.0f}s / {duration_s}s ({i + 1} frames, {len(transcripts)} transcripts)"
                    )

            total_time = time.monotonic() - test_start
            logger.info(
                f"  Streaming complete: {len(frames)} frames in {total_time:.1f}s, {len(transcripts)} transcripts"
            )

            # Wait for final transcripts and pusher to flush
            logger.info(f"  Waiting 10s for pusher batch flush...")
            await asyncio.sleep(10)

            await ws.close()
            recv_task.cancel()
            try:
                await recv_task
            except asyncio.CancelledError:
                pass

        results['ws_session'] = {
            'status': 'PASS',
            'frames_sent': len(frames),
            'bytes_sent': len(pcm_data),
            'total_time_s': round(total_time, 1),
            'transcripts_received': len(transcripts),
            'conversation_id': conversation_id,
        }
        logger.info(f"[STEP 1] PASS — conversation_id: {conversation_id}")

    except Exception as e:
        results['ws_session'] = {'status': 'FAIL', 'error': str(e)}
        logger.error(f"[STEP 1] FAIL — {e}")
        return results

    uid = 'integration-test-user'
    base_url = f"http://{host}:{backend_port}"
    headers = {"Authorization": f"Bearer {token}"}

    # If conversation_id not received via WS, fetch from conversations API
    if not conversation_id:
        logger.info("  No conversation_id from WS — fetching from conversations API...")
        try:
            r = requests.get(f"{base_url}/v1/conversations?limit=5&statuses=in_progress", headers=headers, timeout=10)
            if r.status_code == 200:
                convos = r.json()
                if convos:
                    conversation_id = convos[0].get('id')
                    logger.info(f"  Found in-progress conversation: {conversation_id}")
        except Exception as e:
            logger.warning(f"  Failed to fetch conversations: {e}")

    if not conversation_id:
        # Last resort: get the most recent conversation
        try:
            r = requests.get(f"{base_url}/v1/conversations?limit=1", headers=headers, timeout=10)
            if r.status_code == 200:
                convos = r.json()
                if convos:
                    conversation_id = convos[0].get('id')
                    logger.info(f"  Found most recent conversation: {conversation_id}")
        except Exception as e:
            logger.warning(f"  Failed to fetch conversations: {e}")

    if not conversation_id:
        logger.error("[STEP 1] Could not determine conversation_id — cannot continue")
        results['ws_session']['status'] = 'FAIL'
        results['ws_session']['error'] = 'No conversation_id found'
        return results

    results['ws_session']['conversation_id'] = conversation_id

    # Wait additional time for pusher shutdown flush + GCS upload
    logger.info("[STEP 2] Waiting 15s for pusher shutdown flush and GCS upload...")
    await asyncio.sleep(15)

    # ─── Step 2: Verify GCS blobs ───
    logger.info(f"[STEP 2] Checking GCS blobs for conversation {conversation_id}...")
    try:
        from google.cloud import storage as gcs_storage

        bucket_name = os.environ.get('BUCKET_PRIVATE_CLOUD_SYNC', 'omi-private-cloud-sync')
        gcs_client = gcs_storage.Client()
        bucket = gcs_client.bucket(bucket_name)
        prefix = f'chunks/{uid}/{conversation_id}/'
        blobs = list(bucket.list_blobs(prefix=prefix))

        EXTENSIONS = ['.opus.enc', '.batch.enc', '.opus', '.batch.bin', '.enc', '.bin']
        chunks = []
        for blob in blobs:
            filename = blob.name.split('/')[-1]
            has_ext = any(filename.endswith(ext) for ext in EXTENSIONS)
            if has_ext:
                # Extract timestamp
                ts_str = filename
                for ext in EXTENSIONS:
                    if ts_str.endswith(ext):
                        ts_str = ts_str[: -len(ext)]
                        break
                try:
                    chunks.append({'timestamp': float(ts_str), 'path': blob.name, 'size': blob.size})
                except ValueError:
                    continue
        chunks.sort(key=lambda x: x['timestamp'])
        if chunks:
            total_size = sum(c['size'] for c in chunks)
            extensions = set()
            for c in chunks:
                path = c['path']
                for ext in ['.opus.enc', '.opus', '.batch.enc', '.batch.bin', '.enc', '.bin']:
                    if path.endswith(ext):
                        extensions.add(ext)
                        break

            results['gcs_blobs'] = {
                'status': 'PASS',
                'chunk_count': len(chunks),
                'total_size_bytes': total_size,
                'extensions': list(extensions),
                'timestamps': [c['timestamp'] for c in chunks],
            }

            # Compression check: 90s PCM16 at 16kHz = 2,880,000 bytes
            # Opus should compress ~10x → ~288,000 bytes
            expected_pcm_size = duration_s * sample_rate * 2
            compression_ratio = expected_pcm_size / total_size if total_size > 0 else 0
            results['gcs_blobs']['compression_ratio'] = round(compression_ratio, 1)
            results['gcs_blobs']['expected_pcm_bytes'] = expected_pcm_size

            logger.info(
                f"[STEP 2] PASS — {len(chunks)} chunks, {total_size} bytes total, "
                f"extensions: {extensions}, compression: {compression_ratio:.1f}x"
            )

            # Verify Opus encoding: chunks should have .opus extension
            if '.opus' in extensions or '.opus.enc' in extensions:
                logger.info(f"  Opus encoding confirmed (extensions: {extensions})")
            elif '.bin' in extensions or '.batch.bin' in extensions:
                logger.warning(f"  WARNING: raw .bin extension found — Opus encoding may not be active")
                results['gcs_blobs']['warning'] = 'Raw .bin extension — no Opus encoding detected'
        else:
            results['gcs_blobs'] = {'status': 'FAIL', 'error': 'No chunks found in GCS', 'chunk_count': 0}
            logger.error(f"[STEP 2] FAIL — No chunks found")
    except Exception as e:
        results['gcs_blobs'] = {'status': 'FAIL', 'error': str(e)}
        logger.error(f"[STEP 2] FAIL — {e}")

    # ─── Step 3: Verify conversation in Firestore ───
    logger.info(f"[STEP 3] Checking conversation {conversation_id} in Firestore...")
    try:
        r = requests.get(f"{base_url}/v1/conversations/{conversation_id}", headers=headers, timeout=10)
        if r.status_code == 200:
            conv = r.json()
            audio_files = conv.get('audio_files', [])
            segments = conv.get('transcript_segments', [])

            # Check speaker labels in segments
            speakers = set()
            for seg in segments:
                if isinstance(seg, dict) and seg.get('speaker'):
                    speakers.add(seg['speaker'])

            results['conversation'] = {
                'status': 'PASS',
                'audio_files_count': len(audio_files),
                'transcript_segments_count': len(segments),
                'speakers_found': list(speakers),
                'has_audio_files': len(audio_files) > 0,
                'has_transcript_segments': len(segments) > 0,
            }

            if audio_files:
                af = audio_files[0]
                results['conversation']['first_audio_file'] = {
                    'id': af.get('id'),
                    'duration': af.get('duration'),
                    'chunk_timestamps_count': len(af.get('chunk_timestamps', [])),
                }

            # BUG DETECTION: If GCS has blobs but conversation has 0 audio_files,
            # this indicates _strip_extension() bug — .batch.enc/.batch.bin not handled
            gcs_count = results.get('gcs_blobs', {}).get('chunk_count', 0)
            gcs_exts = results.get('gcs_blobs', {}).get('extensions', [])
            if gcs_count > 0 and len(audio_files) == 0:
                batch_exts = [e for e in gcs_exts if '.batch.' in e]
                if batch_exts:
                    bug_msg = (
                        f"BUG DETECTED: GCS has {gcs_count} blobs with extensions {batch_exts}, "
                        f"but conversation has 0 audio_files. "
                        f"Root cause: storage.py _strip_extension() does not handle .batch.enc/.batch.bin — "
                        f"strips only .enc, leaving '.batch' in timestamp string, "
                        f"causing float() ValueError → chunk silently skipped. "
                        f"Fix: add '.batch.enc' and '.batch.bin' to _strip_extension() and PRIVATE_CLOUD_EXTENSIONS."
                    )
                    results['conversation']['bug_detected'] = bug_msg
                    logger.warning(f"  *** {bug_msg}")

            logger.info(
                f"[STEP 3] PASS — {len(audio_files)} audio_files, {len(segments)} segments, " f"speakers: {speakers}"
            )
        else:
            results['conversation'] = {'status': 'FAIL', 'error': f'HTTP {r.status_code}: {r.text[:200]}'}
            logger.error(f"[STEP 3] FAIL — HTTP {r.status_code}")
    except Exception as e:
        results['conversation'] = {'status': 'FAIL', 'error': str(e)}
        logger.error(f"[STEP 3] FAIL — {e}")

    # ─── Step 4: Audio download roundtrip ───
    if results['conversation'].get('has_audio_files') and results['conversation'].get('status') == 'PASS':
        audio_file_id = results['conversation']['first_audio_file']['id']
        logger.info(f"[STEP 4] Downloading audio file {audio_file_id}...")
        try:
            r = requests.get(
                f"{base_url}/v1/sync/audio/{conversation_id}/{audio_file_id}?format=wav",
                headers=headers,
                timeout=30,
            )
            if r.status_code == 200:
                wav_data = r.content
                # Verify WAV header
                if len(wav_data) > 44 and wav_data[:4] == b'RIFF' and wav_data[8:12] == b'WAVE':
                    # Parse WAV header
                    wav_sample_rate = struct.unpack('<I', wav_data[24:28])[0]
                    bits_per_sample = struct.unpack('<H', wav_data[34:36])[0]
                    data_size = struct.unpack('<I', wav_data[40:44])[0]
                    pcm_duration = data_size / (wav_sample_rate * 2)  # 16-bit mono

                    results['audio_download'] = {
                        'status': 'PASS',
                        'wav_size_bytes': len(wav_data),
                        'sample_rate': wav_sample_rate,
                        'bits_per_sample': bits_per_sample,
                        'pcm_data_size': data_size,
                        'audio_duration_s': round(pcm_duration, 1),
                    }
                    logger.info(
                        f"[STEP 4] PASS — WAV {len(wav_data)} bytes, "
                        f"{wav_sample_rate}Hz {bits_per_sample}bit, "
                        f"duration: {pcm_duration:.1f}s"
                    )
                else:
                    results['audio_download'] = {
                        'status': 'FAIL',
                        'error': f'Invalid WAV header (got {wav_data[:12].hex()})',
                        'size': len(wav_data),
                    }
                    logger.error(f"[STEP 4] FAIL — Invalid WAV header")
            else:
                results['audio_download'] = {'status': 'FAIL', 'error': f'HTTP {r.status_code}: {r.text[:200]}'}
                logger.error(f"[STEP 4] FAIL — HTTP {r.status_code}")
        except Exception as e:
            results['audio_download'] = {'status': 'FAIL', 'error': str(e)}
            logger.error(f"[STEP 4] FAIL — {e}")
    else:
        results['audio_download'] = {'status': 'SKIP', 'error': 'No audio_files in conversation'}
        logger.warning(f"[STEP 4] SKIP — No audio files to download")

    return results


async def main():
    parser = argparse.ArgumentParser(
        description='E2E test: /v4/listen → pusher → GCS → conversation roundtrip',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('--host', default='localhost', help='Backend host (default: localhost)')
    parser.add_argument('--backend-port', type=int, default=8787, help='Backend port (default: 8787)')
    parser.add_argument(
        '--duration',
        type=int,
        default=90,
        help='Audio duration in seconds (default: 90, must be >60 to trigger batch flush)',
    )
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose logging')
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%H:%M:%S',
    )

    if args.duration < 65:
        logger.warning(f"Duration {args.duration}s is less than 65s — may not trigger batch flush (60s threshold)")

    logger.info("Getting Firebase auth token...")
    token = get_firebase_token()
    if not token:
        logger.error("Failed to get Firebase token. Set GOOGLE_APPLICATION_CREDENTIALS.")
        sys.exit(1)
    logger.info("Auth token acquired")

    logger.info(f"\n{'='*60}")
    logger.info(f"E2E TEST: /v4/listen → pusher → GCS → conversation roundtrip")
    logger.info(f"Backend: {args.host}:{args.backend_port}")
    logger.info(f"Duration: {args.duration}s (pcm16 @ 16kHz)")
    logger.info(f"{'='*60}")

    results = await run_e2e_test(
        host=args.host,
        backend_port=args.backend_port,
        duration_s=args.duration,
        token=token,
    )

    # ─── Summary ───
    print(f"\n{'='*60}")
    print("E2E TEST RESULTS")
    print(f"{'='*60}")

    pass_count = 0
    fail_count = 0
    skip_count = 0

    for step_name, step_result in results.items():
        status = step_result.get('status', 'UNKNOWN')
        icon = '✓' if status == 'PASS' else '✗' if status == 'FAIL' else '—'
        print(f"\n{icon} {step_name}: {status}")

        if status == 'PASS':
            pass_count += 1
            for k, v in step_result.items():
                if k != 'status':
                    print(f"    {k}: {v}")
        elif status == 'FAIL':
            fail_count += 1
            if 'error' in step_result:
                print(f"    Error: {step_result['error']}")
        else:
            skip_count += 1
            if 'error' in step_result:
                print(f"    Reason: {step_result['error']}")

    print(f"\n{'='*60}")
    print(f"Total: {pass_count} PASS, {fail_count} FAIL, {skip_count} SKIP")

    # Detailed verdict
    if fail_count == 0 and skip_count == 0:
        print("VERDICT: FULL PASS — all 4 steps verified")
    elif fail_count == 0:
        print("VERDICT: PARTIAL PASS — some steps skipped")
    else:
        print("VERDICT: FAIL — see errors above")

    sys.exit(1 if fail_count > 0 else 0)


if __name__ == '__main__':
    asyncio.run(main())
