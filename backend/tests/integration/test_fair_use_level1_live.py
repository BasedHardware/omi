#!/usr/bin/env python3
"""
Level 1 Live Test: Send real audio through /v4/listen and verify fair-use pipeline.

Requires local backend running:
  LOCAL_DEVELOPMENT=true FAIR_USE_ENABLED=true FAIR_USE_DAILY_SPEECH_MS=5000 \
  FAIR_USE_3DAY_SPEECH_MS=10000 FAIR_USE_WEEKLY_SPEECH_MS=15000 \
  FAIR_USE_CHECK_INTERVAL_SECONDS=5 \
  uvicorn main:app --port 10260

Then run:
  python3 tests/integration/test_fair_use_level1_live.py
"""

import asyncio
import json
import os
import sys
import time
import wave

import redis
import websockets

BACKEND_PORT = int(os.getenv('BACKEND_PORT', '10260'))
BACKEND_URL = f'ws://localhost:{BACKEND_PORT}/v4/listen'
TEST_WAV = os.path.join(
    os.path.dirname(__file__),
    '../../pretrained_models/snakers4_silero-vad_master/tests/data/test.wav',
)

# Redis connection (same as backend .env)
REDIS_HOST = os.getenv('REDIS_DB_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_DB_PORT', '6379'))
REDIS_PASS = os.getenv('REDIS_DB_PASSWORD', '')

# Test user ID (LOCAL_DEVELOPMENT=true maps any token to uid='123')
TEST_UID = '123'


def get_redis():
    return redis.Redis(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASS or None)


def check_redis_speech(r, uid):
    """Read current speech_ms from Redis for a user."""
    bucket_key = f'fair_use:bucket:{uid}'
    zset_key = f'fair_use:speech:{uid}'

    members = r.zrangebyscore(zset_key, '-inf', '+inf')
    if not members:
        return {'daily_ms': 0, 'buckets': 0}

    values = r.hmget(bucket_key, [m.decode() for m in members])
    total = sum(int(v) for v in values if v is not None)
    return {'daily_ms': total, 'buckets': len(members)}


def cleanup_redis(r, uid):
    """Remove test user's fair-use keys."""
    r.delete(
        f'fair_use:speech:{uid}',
        f'fair_use:bucket:{uid}',
        f'fair_use:stage:{uid}',
        f'fair_use:vad_delta:{uid}',
        f'fair_use:classifier_lock:{uid}',
    )


async def connect_and_wait_ready(url, timeout=30):
    """Connect to WebSocket and wait for 'ready' or 'stt_initiating' status."""
    ws = await websockets.connect(
        url,
        extra_headers={'authorization': 'Bearer dev-token'},
        close_timeout=5,
        max_size=10 * 1024 * 1024,
        ping_interval=None,  # Let server handle pings
    )

    start = time.time()
    statuses = []
    while time.time() - start < timeout:
        try:
            msg = await asyncio.wait_for(ws.recv(), timeout=3)
            if isinstance(msg, str) and msg != 'ping':
                try:
                    parsed = json.loads(msg)
                    status = parsed.get('status', '')
                    if status:
                        statuses.append(status)
                        print(f'  [status] {status}')
                    if status in ('ready', 'stt_initiating'):
                        # stt_initiating means Deepgram is connecting, good enough to start sending
                        return ws, statuses
                except json.JSONDecodeError:
                    pass
        except asyncio.TimeoutError:
            continue
        except Exception as e:
            print(f'  [error] waiting for ready: {e}')
            break

    print(f'  [warn] statuses so far: {statuses}')
    return ws, statuses


async def send_audio(ws, wav_path, seconds=15, chunk_ms=60):
    """Stream real audio from WAV file to WebSocket."""
    wf = wave.open(wav_path, 'r')
    sample_rate = wf.getframerate()
    n_channels = wf.getnchannels()
    sample_width = wf.getsampwidth()

    print(f'  [audio] {wav_path}')
    print(f'  [audio] rate={sample_rate} channels={n_channels} width={sample_width}')

    max_frames = int(sample_rate * seconds)
    frames_read = 0
    chunk_frames = int(sample_rate * chunk_ms / 1000)
    bytes_sent = 0
    chunks_sent = 0

    while frames_read < max_frames:
        to_read = min(chunk_frames, max_frames - frames_read)
        pcm_data = wf.readframes(to_read)
        if not pcm_data:
            break

        await ws.send(pcm_data)
        bytes_sent += len(pcm_data)
        chunks_sent += 1
        frames_read += to_read

        # Real-time pacing
        await asyncio.sleep(chunk_ms / 1000 * 0.8)

    wf.close()
    duration = frames_read / sample_rate
    print(f'  [audio] sent {duration:.1f}s ({bytes_sent} bytes, {chunks_sent} chunks)')
    return duration


async def drain_messages(ws, duration=5):
    """Drain WebSocket messages for a period, collecting transcripts."""
    transcripts = []
    start = time.time()
    while time.time() - start < duration:
        try:
            msg = await asyncio.wait_for(ws.recv(), timeout=1)
            if isinstance(msg, str) and msg != 'ping':
                try:
                    parsed = json.loads(msg)
                    if isinstance(parsed, list):
                        transcripts.extend(parsed)
                        for seg in parsed:
                            text = seg.get('text', '')[:60]
                            print(f'  [transcript] {text}')
                except json.JSONDecodeError:
                    pass
        except asyncio.TimeoutError:
            continue
        except websockets.exceptions.ConnectionClosed:
            break
    return transcripts


async def main():
    print('=' * 60)
    print('Level 1 Live Test: Fair-Use Pipeline via /v4/listen')
    print('=' * 60)

    # Check prerequisites
    if not os.path.exists(TEST_WAV):
        print(f'FAIL: test WAV not found at {TEST_WAV}')
        sys.exit(1)

    r = get_redis()
    try:
        r.ping()
        print('[OK] Redis connected')
    except Exception as e:
        print(f'FAIL: Redis not available: {e}')
        sys.exit(1)

    # Clean up any prior test data
    cleanup_redis(r, TEST_UID)
    before = check_redis_speech(r, TEST_UID)
    print(f'[pre] speech_ms before test: {before}')

    # Phase 1: Connect and verify ready
    print('\n--- Phase 1: Connect to /v4/listen ---')
    url = f'{BACKEND_URL}?language=en&sample_rate=16000&codec=pcm8&channels=1&vad_gate=enabled'
    print(f'  [url] {url}')

    try:
        ws, statuses = await connect_and_wait_ready(url)
    except Exception as e:
        print(f'FAIL: Could not connect: {e}')
        sys.exit(1)

    # Phase 2: Stream real audio for 55s to keep WS alive through the 60s recording cycle
    # The _record_usage_periodically loop fires after 60s sleep, so we need the
    # connection alive for at least 60-65 seconds
    print('\n--- Phase 2: Stream real audio (55s, enough for 60s recording cycle) ---')

    # Send audio and collect transcripts concurrently
    transcripts = []
    ws_alive = True

    async def recv_loop():
        nonlocal ws_alive
        while ws_alive:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=2)
                if isinstance(msg, str) and msg != 'ping':
                    try:
                        parsed = json.loads(msg)
                        if isinstance(parsed, list):
                            transcripts.extend(parsed)
                            for seg in parsed:
                                text = seg.get('text', '')[:60]
                                print(f'  [transcript] {text}')
                    except json.JSONDecodeError:
                        pass
            except asyncio.TimeoutError:
                continue
            except websockets.exceptions.ConnectionClosed:
                ws_alive = False
                print('  [warn] WebSocket closed by server during recv')
                break

    recv_task = asyncio.create_task(recv_loop())

    # Send 55 seconds of audio (the test.wav is 60s)
    duration = await send_audio(ws, TEST_WAV, seconds=55, chunk_ms=60)

    # Phase 3: Keep connection alive after audio ends, waiting for the 60s recording cycle
    print('\n--- Phase 3: Wait for usage recording cycle ---')
    print('  Need ~65s from WS open for first recording. Sending silence keepalive...')

    speech_detected = False
    start_wait = time.time()
    last_check = 0

    # Send silence bytes to keep the connection alive
    silence_chunk = b'\x00' * 1920  # 60ms of silence at 16kHz PCM16

    while time.time() - start_wait < 30 and ws_alive:
        # Send silence to keep connection alive
        try:
            await ws.send(silence_chunk)
        except Exception:
            print('  [warn] Could not send keepalive')
            break
        await asyncio.sleep(0.5)

        # Check Redis every 5 seconds
        elapsed = int(time.time() - start_wait)
        if elapsed - last_check >= 5:
            last_check = elapsed
            current = check_redis_speech(r, TEST_UID)
            total_elapsed = int(duration) + elapsed
            print(f'  [{total_elapsed}s total] speech_ms={current["daily_ms"]} buckets={current["buckets"]}')
            if current['daily_ms'] > 0 and not speech_detected:
                speech_detected = True
                print(f'  [OK] Speech detected in Redis!')

    # Stop receiver
    ws_alive = False
    recv_task.cancel()
    try:
        await recv_task
    except asyncio.CancelledError:
        pass

    # If still no speech, wait a bit more (the connection may have triggered recording on close)
    if not speech_detected:
        print('  Waiting 15s more for post-close recording...')
        for i in range(3):
            await asyncio.sleep(5)
            current = check_redis_speech(r, TEST_UID)
            print(f'  [+{(i+1)*5}s] speech_ms={current["daily_ms"]} buckets={current["buckets"]}')
            if current['daily_ms'] > 0:
                speech_detected = True
                print(f'  [OK] Speech detected in Redis (post-close)!')
                break

    print(f'  [transcripts] received {len(transcripts)} segments total')

    # Phase 5: Check fair-use state
    print('\n--- Phase 5: Verify fair-use state ---')
    final = check_redis_speech(r, TEST_UID)
    print(f'  speech_ms total: {final["daily_ms"]}')
    print(f'  buckets: {final["buckets"]}')

    stage_key = f'fair_use:stage:{TEST_UID}'
    cached_stage = r.get(stage_key)
    if cached_stage:
        print(f'  cached stage: {cached_stage.decode()}')
    else:
        print(f'  cached stage: (not set)')

    lock_key = f'fair_use:classifier_lock:{TEST_UID}'
    lock_val = r.get(lock_key)
    print(f'  classifier lock: {"active" if lock_val else "not set"}')

    # Close WebSocket
    try:
        await ws.close()
    except Exception:
        pass

    # Phase 6: Results
    print('\n' + '=' * 60)
    print('RESULTS')
    print('=' * 60)

    results = {
        'connection': 'ready' in statuses or 'stt_initiating' in statuses,
        'audio_sent': duration > 0,
        'transcripts': len(transcripts) > 0,
        'speech_in_redis': speech_detected,
        'speech_ms': final['daily_ms'],
    }

    for key, val in results.items():
        status = 'PASS' if val else 'FAIL'
        print(f'  [{status}] {key}: {val}')

    # Cap trigger check (threshold is 5000ms = 5s)
    if final['daily_ms'] > 5000:
        print(f'  [PASS] speech_ms ({final["daily_ms"]}) > daily cap (5000ms) — cap would trigger')
    elif speech_detected:
        print(f'  [INFO] speech_ms ({final["daily_ms"]}) <= daily cap (5000ms) — may need more audio time')
    else:
        print(f'  [FAIL] no speech recorded in Redis')

    # Cleanup
    cleanup_redis(r, TEST_UID)

    all_pass = all(results.values())
    print(f'\nOverall: {"ALL PASS" if all_pass else "SOME FAILURES"}')
    sys.exit(0 if all_pass else 1)


if __name__ == '__main__':
    asyncio.run(main())
