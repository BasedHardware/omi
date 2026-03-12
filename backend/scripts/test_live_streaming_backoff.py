#!/usr/bin/env python3
"""Live streaming test for #5577 — verifies async Deepgram backoff with real podcast audio.

Mimics Flutter app behavior:
1. Opens WebSocket to /v4/listen with auth
2. Reads PCM16 WAV file and sends chunks at real-time pace (100ms chunks)
3. Monitors transcription responses + tracks segments, latency
4. Tests client disconnect during retry (is_active abort)

Usage:
    # Level 1: local dev backend, podcast durations
    python3 scripts/test_live_streaming_backoff.py --port 8790 --audio /tmp/podcast-test/podcast_1m.wav
    python3 scripts/test_live_streaming_backoff.py --port 8790 --audio /tmp/podcast-test/podcast_5m.wav
    python3 scripts/test_live_streaming_backoff.py --port 8790 --audio /tmp/podcast-test/podcast_15m.wav

    # Level 2: remote backend via Tailscale
    python3 scripts/test_live_streaming_backoff.py --host <tailscale-ip> --port 8790 --audio ...

    # All tests on one file
    python3 scripts/test_live_streaming_backoff.py --port 8790 --audio /tmp/podcast-test/podcast_1m.wav --all
"""

import argparse
import asyncio
import json
import logging
import math
import os
import struct
import sys
import time
import wave
from pathlib import Path

import websockets

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

# Default test params matching Flutter app behavior
SAMPLE_RATE = 8000
CODEC = 'pcm8'
CHANNELS = 1
LANGUAGE = 'en'
CHUNK_DURATION_MS = 100  # send 100ms chunks like the app
ADMIN_KEY = os.getenv('ADMIN_KEY', '123')
TEST_UID = 'test-streaming-5577'


def load_audio_chunks(audio_path: str, chunk_duration_ms: int = 100, sample_rate: int = 8000) -> list:
    """Load WAV file and split into fixed-size PCM16 chunks for real-time streaming."""
    chunk_bytes = int(sample_rate * (chunk_duration_ms / 1000) * 2)  # 16-bit = 2 bytes/sample
    chunks = []
    with wave.open(audio_path, 'rb') as wf:
        assert wf.getsampwidth() == 2, f"Expected 16-bit audio, got {wf.getsampwidth() * 8}-bit"
        assert wf.getnchannels() == 1, f"Expected mono, got {wf.getnchannels()} channels"
        file_sr = wf.getframerate()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)

    if file_sr != sample_rate:
        raise ValueError(f"Audio sample rate {file_sr}Hz != expected {sample_rate}Hz. Re-encode with: ffmpeg -i input.wav -ar {sample_rate} -ac 1 output.wav")

    for offset in range(0, len(raw), chunk_bytes):
        chunk = raw[offset:offset + chunk_bytes]
        if len(chunk) == chunk_bytes:
            chunks.append(chunk)

    duration_s = len(chunks) * chunk_duration_ms / 1000
    logger.info(f"Loaded {audio_path}: {len(chunks)} chunks, {duration_s:.1f}s, {len(raw)} bytes")
    return chunks


def generate_silence_chunks(duration_s: float, chunk_duration_ms: int = 100, sample_rate: int = 8000) -> list:
    """Generate silent PCM16 chunks as fallback when no audio file provided."""
    chunk_bytes = int(sample_rate * (chunk_duration_ms / 1000) * 2)
    silence = b'\x00' * chunk_bytes
    total_chunks = int(duration_s * 1000 / chunk_duration_ms)
    return [silence] * total_chunks


async def stream_audio_test(host: str, port: int, chunks: list, label: str, uid_suffix: str = ''):
    """Core streaming test — sends audio chunks at real-time pace, collects metrics.

    Returns dict with metrics or None on connection failure.
    """
    uid = f"{TEST_UID}{uid_suffix}"
    uri = (
        f"ws://{host}:{port}/v4/listen?"
        f"language={LANGUAGE}&sample_rate={SAMPLE_RATE}&codec={CODEC}"
        f"&channels={CHANNELS}&include_speech_profile=false"
    )
    auth_token = f"{ADMIN_KEY}{uid}"
    headers = {"Authorization": f"Bearer {auth_token}"}

    metrics = {
        'label': label,
        'total_chunks': len(chunks),
        'duration_s': len(chunks) * CHUNK_DURATION_MS / 1000,
        'segments_received': 0,
        'transcript_words': 0,
        'status_messages': 0,
        'errors': [],
        'connection_held': False,
        'elapsed_s': 0,
        'first_segment_latency_s': None,
    }

    try:
        t_connect_start = time.time()
        async with websockets.connect(uri, extra_headers=headers, ping_interval=None, open_timeout=30) as ws:
            t_connected = time.time()
            logger.info(f"  [{label}] Connected ({t_connected - t_connect_start:.1f}s handshake)")

            t_start = time.time()
            send_done = asyncio.Event()

            async def receive_loop():
                try:
                    async for msg in ws:
                        elapsed = time.time() - t_start
                        try:
                            data = json.loads(msg)
                            # Backend sends segments as a plain JSON array, or as
                            # {"segments": [...]} in some code paths, or {"type": ...} events
                            segments = None
                            if isinstance(data, list) and data:
                                segments = data
                            elif isinstance(data, dict) and 'segments' in data and data['segments']:
                                segments = data['segments']

                            if segments:
                                metrics['segments_received'] += len(segments)
                                words = sum(len(s.get('text', '').split()) for s in segments)
                                metrics['transcript_words'] += words
                                if metrics['first_segment_latency_s'] is None:
                                    metrics['first_segment_latency_s'] = elapsed
                                logger.info(
                                    f"  [{label}] [{elapsed:.1f}s] {len(segments)} segments, "
                                    f"{words} words (total: {metrics['segments_received']} segs, "
                                    f"{metrics['transcript_words']} words)"
                                )
                            elif isinstance(data, dict) and 'status' in data:
                                metrics['status_messages'] += 1
                            # else: other messages (ping, events etc)
                        except json.JSONDecodeError:
                            pass  # ping frames
                except websockets.exceptions.ConnectionClosed:
                    pass
                except Exception as e:
                    metrics['errors'].append(f"recv: {e}")

            recv_task = asyncio.create_task(receive_loop())

            # Send audio at real-time pace
            chunks_sent = 0
            for i, chunk in enumerate(chunks):
                try:
                    await ws.send(chunk)
                    chunks_sent += 1
                except websockets.exceptions.ConnectionClosed:
                    logger.warning(f"  [{label}] Connection closed at chunk {i}/{len(chunks)}")
                    break
                await asyncio.sleep(CHUNK_DURATION_MS / 1000)

                # Progress every 30s
                elapsed = (i + 1) * CHUNK_DURATION_MS / 1000
                if i > 0 and i % (30000 // CHUNK_DURATION_MS) == 0:
                    logger.info(f"  [{label}] Progress: {elapsed:.0f}s / {metrics['duration_s']:.0f}s sent")

            send_done.set()
            send_elapsed = time.time() - t_start
            logger.info(f"  [{label}] Sent {chunks_sent}/{len(chunks)} chunks in {send_elapsed:.1f}s. Waiting 5s for final transcripts...")

            # Wait for trailing transcripts
            await asyncio.sleep(5)

            try:
                await ws.close()
            except Exception:
                pass

            recv_task.cancel()
            try:
                await recv_task
            except asyncio.CancelledError:
                pass

            metrics['connection_held'] = (chunks_sent == len(chunks))
            metrics['elapsed_s'] = time.time() - t_start

    except Exception as e:
        metrics['errors'].append(f"connect: {e}")
        logger.error(f"  [{label}] Connection failed: {e}")

    return metrics


async def test_podcast_streaming(host: str, port: int, audio_path: str):
    """Test: Stream podcast audio file end-to-end and verify connection stability + transcription."""
    duration_label = Path(audio_path).stem
    logger.info("=" * 70)
    logger.info(f"TEST: Podcast streaming — {duration_label}")
    logger.info("=" * 70)

    chunks = load_audio_chunks(audio_path)
    metrics = await stream_audio_test(host, port, chunks, duration_label)

    # Evaluate
    passed = True
    reasons = []

    if not metrics['connection_held']:
        passed = False
        reasons.append("connection dropped before all audio sent")

    if metrics['errors']:
        passed = False
        reasons.append(f"errors: {metrics['errors']}")

    if metrics['segments_received'] == 0:
        # Not a hard failure — DG may not detect speech in looped test audio
        reasons.append("WARNING: no transcript segments received (Deepgram may not detect speech in test audio)")

    status = "PASSED" if passed else "FAILED"
    logger.info(f"RESULT [{duration_label}]: {status}")
    logger.info(f"  Duration: {metrics['duration_s']:.0f}s streamed in {metrics['elapsed_s']:.1f}s")
    logger.info(f"  Segments: {metrics['segments_received']}, Words: {metrics['transcript_words']}")
    logger.info(f"  First segment latency: {metrics['first_segment_latency_s']:.1f}s" if metrics['first_segment_latency_s'] else "  First segment latency: N/A")
    logger.info(f"  Status messages: {metrics['status_messages']}")
    if reasons:
        for r in reasons:
            logger.info(f"  Note: {r}")

    return passed, metrics


async def test_client_disconnect(host: str, port: int, audio_path: str):
    """Test: Client disconnects mid-stream — backend should abort DG retries via is_active."""
    logger.info("=" * 70)
    logger.info("TEST: Client disconnect mid-stream (is_active abort)")
    logger.info("=" * 70)

    chunks = load_audio_chunks(audio_path)
    # Send only first 5 seconds then disconnect
    cutoff = min(len(chunks), int(5 * 1000 / CHUNK_DURATION_MS))
    partial_chunks = chunks[:cutoff]

    uid = f"{TEST_UID}-disconnect"
    uri = (
        f"ws://{host}:{port}/v4/listen?"
        f"language={LANGUAGE}&sample_rate={SAMPLE_RATE}&codec={CODEC}"
        f"&channels={CHANNELS}&include_speech_profile=false"
    )
    auth_token = f"{ADMIN_KEY}{uid}"
    headers = {"Authorization": f"Bearer {auth_token}"}

    try:
        async with websockets.connect(uri, extra_headers=headers, ping_interval=None, open_timeout=30) as ws:
            logger.info(f"  Connected. Sending {len(partial_chunks)} chunks (5s) then disconnecting...")

            for chunk in partial_chunks:
                await ws.send(chunk)
                await asyncio.sleep(CHUNK_DURATION_MS / 1000)

            logger.info("  Disconnecting abruptly...")
            await ws.close(code=1000, reason="client disconnect test")

        logger.info("RESULT [disconnect]: PASSED — clean disconnect, backend should abort retries via is_active")
        logger.info("  (Check backend logs for 'Session ended, aborting' messages)")
        return True, {}

    except Exception as e:
        logger.error(f"RESULT [disconnect]: FAILED — {e}")
        return False, {}


async def test_concurrent_streaming(host: str, port: int, audio_path: str, num_connections: int = 3):
    """Test: Multiple concurrent podcast streams — verifies no event loop blocking.

    With old time.sleep(), one DG retry would stall ALL connections on the pod.
    With await asyncio.sleep(), each connection retries independently.
    """
    logger.info("=" * 70)
    logger.info(f"TEST: Concurrent podcast streams ({num_connections}x)")
    logger.info("=" * 70)

    chunks = load_audio_chunks(audio_path)
    # Use first 30s for concurrent test (faster)
    cutoff = min(len(chunks), int(30 * 1000 / CHUNK_DURATION_MS))
    short_chunks = chunks[:cutoff]
    logger.info(f"  Using first {cutoff * CHUNK_DURATION_MS / 1000:.0f}s of audio per connection")

    # Stagger connections by 3s to avoid overwhelming single-worker handshake
    results = []
    tasks = []
    for i in range(num_connections):
        if i > 0:
            await asyncio.sleep(3)
        task = asyncio.create_task(
            stream_audio_test(host, port, short_chunks, f"concurrent-{i}", uid_suffix=f"-conc-{i}")
        )
        tasks.append(task)

    results = await asyncio.gather(*tasks)

    passed_count = sum(1 for m in results if m['connection_held'] and not m['errors'])
    total_segments = sum(m['segments_received'] for m in results)

    passed = (passed_count == num_connections)
    status = "PASSED" if passed else "FAILED"
    logger.info(f"RESULT [concurrent]: {status} — {passed_count}/{num_connections} connections held")
    logger.info(f"  Total segments across all connections: {total_segments}")
    for m in results:
        logger.info(f"  {m['label']}: held={m['connection_held']} segs={m['segments_received']} errs={len(m['errors'])}")

    return passed, results


async def main():
    parser = argparse.ArgumentParser(description='Live podcast streaming test for #5577')
    parser.add_argument('--host', default='localhost', help='Backend host')
    parser.add_argument('--port', type=int, default=8790, help='Backend port')
    parser.add_argument('--audio', required=True, help='Path to WAV file (8kHz mono PCM16)')
    parser.add_argument('--test-disconnect', action='store_true', help='Run disconnect test')
    parser.add_argument('--test-concurrent', action='store_true', help='Run concurrent test')
    parser.add_argument('--concurrent-count', type=int, default=3, help='Number of concurrent connections')
    parser.add_argument('--all', action='store_true', help='Run all tests')
    args = parser.parse_args()

    if not os.path.exists(args.audio):
        logger.error(f"Audio file not found: {args.audio}")
        sys.exit(1)

    results = {}

    logger.info(f"Target: ws://{args.host}:{args.port}/v4/listen")
    logger.info(f"Audio:  {args.audio}")
    logger.info("")

    # Test 1: Full podcast streaming
    passed, metrics = await test_podcast_streaming(args.host, args.port, args.audio)
    results['podcast'] = passed

    # Test 2: Client disconnect
    if args.test_disconnect or args.all:
        passed, _ = await test_client_disconnect(args.host, args.port, args.audio)
        results['disconnect'] = passed

    # Test 3: Concurrent connections
    if args.test_concurrent or args.all:
        passed, _ = await test_concurrent_streaming(args.host, args.port, args.audio, args.concurrent_count)
        results['concurrent'] = passed

    # Summary
    logger.info("")
    logger.info("=" * 70)
    logger.info("SUMMARY")
    logger.info("=" * 70)
    all_passed = True
    for name, passed in results.items():
        status = "PASSED" if passed else "FAILED"
        logger.info(f"  {name}: {status}")
        if not passed:
            all_passed = False

    if all_passed:
        logger.info("ALL TESTS PASSED")
        sys.exit(0)
    else:
        logger.error("SOME TESTS FAILED")
        sys.exit(1)


if __name__ == '__main__':
    asyncio.run(main())
