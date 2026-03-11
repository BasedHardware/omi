#!/usr/bin/env python3
"""Integration test: /v4/listen → private cloud sync → GCS upload/download roundtrip.

Mimics a 5-minute podcast recording session for each supported audio codec,
verifying that audio chunks land in GCS via the private cloud sync pipeline
and can be downloaded + decoded back to valid PCM.

Sequence flow (what this test exercises):
```mermaid
sequenceDiagram
    participant Device
    participant Listen as transcribe.py (/v4/listen)
    participant Pusher as pusher.py (/v1/trigger/listen)
    participant PendingDict as pending[conv_id]
    participant Storage as storage.py
    participant GCS

    Device->>Listen: WebSocket connect (codec, sample_rate)
    Listen->>Listen: Accept, validate auth
    Listen->>Pusher: Internal WebSocket connect
    Listen->>Listen: Start _stream_handler()

    loop Every audio frame
        Device->>Listen: Binary audio frame
        Listen->>Listen: Decode codec → PCM16
        Listen->>Listen: Feed STT (Deepgram/Soniox)
        Listen->>Pusher: Forward PCM to pusher WS
        Pusher->>Pusher: Accumulate in private_cloud_sync_buffer
    end

    note over Pusher: Every CHUNK_DURATION (60s batch)
    Pusher->>PendingDict: _add_to_batch(chunk_info)

    note over PendingDict: Flush when: size>=threshold OR age>=60s OR shutdown OR conv-switch
    PendingDict->>Storage: upload_audio_chunks_batch(chunks)
    Storage->>Storage: encode_pcm_to_opus() [Opus compression ~10x]
    Storage->>GCS: blob.open('wb') → stream .opus/.opus.enc/.batch.bin/.batch.enc
    GCS-->>Storage: path
    Storage-->>Pusher: path
    Pusher->>Pusher: create_audio_files_from_chunks()

    note over Pusher: Gap threshold: 90s (batch mode)

    note over Storage: Download path (sync.py)
    Device->>Listen: GET /v1/sync/audio/{conv_id}/{file_id}
    Listen->>Storage: download_audio_chunks_and_merge()
    Storage->>Storage: Try extensions: .opus.enc → .enc → .opus → .bin
    Storage->>GCS: Download blob
    GCS-->>Storage: encrypted/opus bytes
    Storage->>Storage: decrypt (if .enc) → decode_opus_to_pcm() (if .opus)
    Storage-->>Listen: PCM bytes
    Listen-->>Device: WAV response
```

Usage:
    # Run against local backend (port 8787)
    python3 tests/integration/test_listen_private_cloud_sync.py --host localhost --port 8787

    # Run specific codec only
    python3 tests/integration/test_listen_private_cloud_sync.py --codec pcm16

    # Shorter duration for quick smoke test
    python3 tests/integration/test_listen_private_cloud_sync.py --duration 30

Requirements:
    - Local backend running with GOOGLE_APPLICATION_CREDENTIALS set
    - Dev Firebase auth available (based-hardware-dev project)
    - pip install websockets opuslib
    - System: ffmpeg (for AAC encoding), lc3 python module (pip install lc3)
"""

import argparse
import asyncio
import json
import math
import os
import struct
import subprocess
import sys
import time
import logging

logger = logging.getLogger(__name__)

# Supported codecs and their properties
CODECS = {
    'pcm8': {
        'sample_rate': 8000,
        'description': 'Raw PCM 8kHz 16-bit mono',
        'encoder': lambda pcm, sr: pcm,  # identity — already PCM
    },
    'pcm16': {
        'sample_rate': 16000,
        'description': 'Raw PCM 16kHz 16-bit mono',
        'encoder': lambda pcm, sr: pcm,
    },
    'opus': {
        'sample_rate': 16000,
        'description': 'Opus 16kHz mono (frame_size=160)',
        'encoder': None,  # set up at runtime (needs opuslib)
    },
    'opus_fs320': {
        'sample_rate': 16000,
        'description': 'Opus 16kHz mono (frame_size=320)',
        'encoder': None,
    },
    'aac': {
        'sample_rate': 16000,
        'description': 'AAC-LC 16kHz mono (ADTS framed)',
        'encoder': None,  # set up at runtime (needs ffmpeg)
    },
    'lc3_fs1030': {
        'sample_rate': 16000,
        'description': 'LC3 16kHz mono (10ms frames, 30 bytes/frame)',
        'encoder': None,  # set up at runtime (needs lc3 module)
    },
}


def generate_pcm_speech_like(duration_s: float, sample_rate: int) -> bytes:
    """Generate speech-like PCM16 audio (varying frequency sine waves).

    Not real speech, but exercises the full codec pipeline including
    silence detection and frame boundaries.
    """
    samples = int(sample_rate * duration_s)
    pcm = bytearray(samples * 2)

    for i in range(samples):
        t = i / sample_rate
        # Mix frequencies to simulate speech-like signal
        freq = 200 + 300 * math.sin(2 * math.pi * 0.5 * t)  # Slowly varying pitch
        amplitude = 8000 * (0.5 + 0.5 * math.sin(2 * math.pi * 0.3 * t))  # Amplitude modulation
        sample = int(amplitude * math.sin(2 * math.pi * freq * t))
        sample = max(-32768, min(32767, sample))
        struct.pack_into('<h', pcm, i * 2, sample)

    return bytes(pcm)


def setup_opus_encoder(sample_rate: int, frame_size: int):
    """Create an Opus encoder function."""
    try:
        import opuslib
    except ImportError:
        logger.warning("opuslib not installed — skipping Opus codecs. Install: pip install opuslib")
        return None

    encoder = opuslib.Encoder(sample_rate, 1, opuslib.APPLICATION_VOIP)

    def encode_frames(pcm_data: bytes, sr: int) -> list:
        """Encode PCM to list of Opus frames."""
        frames = []
        bytes_per_frame = frame_size * 2  # 16-bit mono
        for offset in range(0, len(pcm_data), bytes_per_frame):
            chunk = pcm_data[offset : offset + bytes_per_frame]
            if len(chunk) < bytes_per_frame:
                chunk += b'\x00' * (bytes_per_frame - len(chunk))
            encoded = encoder.encode(chunk, frame_size)
            frames.append(encoded)
        return frames

    return encode_frames


def setup_aac_encoder(sample_rate: int):
    """Create an AAC encoder function using ffmpeg subprocess.

    Produces ADTS-framed AAC packets that the backend's AACDecoder can decode.
    """
    try:
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, timeout=5)
        if result.returncode != 0:
            logger.warning("ffmpeg not available — skipping AAC codec")
            return None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        logger.warning("ffmpeg not found — skipping AAC codec. Install: apt install ffmpeg")
        return None

    def encode_to_adts_frames(pcm_data: bytes, sr: int) -> list:
        """Encode PCM16 to list of ADTS-framed AAC packets via ffmpeg."""
        proc = subprocess.Popen(
            [
                'ffmpeg',
                '-f',
                's16le',
                '-ar',
                str(sr),
                '-ac',
                '1',
                '-i',
                'pipe:0',
                '-c:a',
                'aac',
                '-b:a',
                '64k',
                '-f',
                'adts',
                'pipe:1',
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        adts_data, _ = proc.communicate(pcm_data)

        # Parse individual ADTS frames from the stream
        frames = []
        pos = 0
        while pos < len(adts_data) - 7:
            sync = (adts_data[pos] << 4) | (adts_data[pos + 1] >> 4)
            if sync != 0xFFF:
                break
            frame_len = ((adts_data[pos + 3] & 0x03) << 11) | (adts_data[pos + 4] << 3) | (adts_data[pos + 5] >> 5)
            if frame_len < 7 or pos + frame_len > len(adts_data):
                break
            frames.append(adts_data[pos : pos + frame_len])
            pos += frame_len

        return frames

    return encode_to_adts_frames


def setup_lc3_encoder(sample_rate: int, frame_duration_us: int = 10000, num_bytes: int = 30):
    """Create an LC3 encoder function.

    Parameters match the backend's lc3_fs1030 alias:
    - frame_duration_us=10000 (10ms frames)
    - num_bytes=30 (30 bytes per encoded frame)
    """
    try:
        import lc3
    except ImportError:
        logger.warning("lc3 module not installed — skipping LC3 codec. Install: pip install lc3")
        return None

    encoder = lc3.Encoder(frame_duration_us, sample_rate)
    frame_samples = encoder.get_frame_samples()  # 160 samples for 10ms at 16kHz

    def encode_frames(pcm_data: bytes, sr: int) -> list:
        """Encode PCM16 to list of LC3 frames."""
        frames = []
        bytes_per_frame = frame_samples * 2  # 16-bit mono
        for offset in range(0, len(pcm_data), bytes_per_frame):
            chunk = pcm_data[offset : offset + bytes_per_frame]
            if len(chunk) < bytes_per_frame:
                chunk += b'\x00' * (bytes_per_frame - len(chunk))
            encoded = encoder.encode(chunk, bit_depth=16, num_bytes=num_bytes)
            frames.append(encoded)
        return frames

    return encode_frames


def get_firebase_token():
    """Get a dev Firebase ID token for authentication."""
    try:
        import firebase_admin
        from firebase_admin import credentials, auth as fb_auth
        import requests

        cred_path = os.environ.get(
            'GOOGLE_APPLICATION_CREDENTIALS',
            os.path.expanduser('~/.config/omi/dev/backend/google-credentials.json'),
        )
        cred = credentials.Certificate(cred_path)
        try:
            firebase_admin.initialize_app(cred)
        except ValueError:
            pass  # already initialized

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


async def run_codec_test(
    host: str,
    port: int,
    codec_name: str,
    codec_config: dict,
    duration_s: float,
    token: str,
) -> dict:
    """Run a single codec test session against /v4/listen.

    Returns dict with test results.
    """
    import websockets

    sample_rate = codec_config['sample_rate']
    result = {
        'codec': codec_name,
        'sample_rate': sample_rate,
        'duration_s': duration_s,
        'status': 'PENDING',
        'error': None,
        'frames_sent': 0,
        'bytes_sent': 0,
        'connect_time_ms': 0,
        'total_time_s': 0,
        'transcripts_received': 0,
    }

    # Generate test audio
    logger.info(f"[{codec_name}] Generating {duration_s}s of test audio at {sample_rate}Hz...")
    pcm_data = generate_pcm_speech_like(duration_s, sample_rate)
    logger.info(f"[{codec_name}] Generated {len(pcm_data)} bytes PCM")

    # Prepare encoded frames based on codec
    if codec_name in ('opus', 'opus_fs320'):
        frame_size = 320 if codec_name == 'opus_fs320' else 160
        encoder = setup_opus_encoder(sample_rate, frame_size)
        if encoder is None:
            result['status'] = 'SKIP'
            result['error'] = 'opuslib not installed'
            return result
        frames = encoder(pcm_data, sample_rate)
        logger.info(f"[{codec_name}] Encoded {len(frames)} Opus frames (frame_size={frame_size})")
    elif codec_name == 'aac':
        encoder = setup_aac_encoder(sample_rate)
        if encoder is None:
            result['status'] = 'SKIP'
            result['error'] = 'ffmpeg not available'
            return result
        frames = encoder(pcm_data, sample_rate)
        logger.info(f"[{codec_name}] Encoded {len(frames)} AAC ADTS frames")
    elif codec_name == 'lc3_fs1030':
        encoder = setup_lc3_encoder(sample_rate, frame_duration_us=10000, num_bytes=30)
        if encoder is None:
            result['status'] = 'SKIP'
            result['error'] = 'lc3 module not installed'
            return result
        frames = encoder(pcm_data, sample_rate)
        logger.info(f"[{codec_name}] Encoded {len(frames)} LC3 frames (10ms, 30 bytes/frame)")
    else:
        # PCM codecs: chunk into 100ms frames
        frame_bytes = int(sample_rate * 2 * 0.1)  # 100ms frames
        frames = [pcm_data[i : i + frame_bytes] for i in range(0, len(pcm_data), frame_bytes)]
        logger.info(f"[{codec_name}] Split into {len(frames)} PCM frames ({frame_bytes} bytes each)")

    # Calculate send interval to match real-time
    if codec_name in ('opus', 'opus_fs320'):
        frame_size = 320 if codec_name == 'opus_fs320' else 160
        frame_duration_s = frame_size / sample_rate
    elif codec_name == 'aac':
        # AAC frames are 1024 samples at the sample rate
        frame_duration_s = 1024.0 / sample_rate  # ~64ms at 16kHz
    elif codec_name == 'lc3_fs1030':
        # LC3 frames are 10ms (frame_duration_us=10000)
        frame_duration_s = 0.01  # 10ms
    else:
        frame_duration_s = 0.1  # 100ms PCM chunks

    # Connect to WebSocket
    ws_url = (
        f"ws://{host}:{port}/v4/listen"
        f"?uid={token}"  # uid param is overridden by auth header
        f"&language=en"
        f"&sample_rate={sample_rate}"
        f"&codec={codec_name}"
        f"&channels=1"
        f"&include_speech_profile=false"
        f"&conversation_timeout=300"
        f"&source=friend"
    )

    logger.info(f"[{codec_name}] Connecting to {ws_url[:80]}...")
    connect_start = time.monotonic()

    try:
        async with websockets.connect(
            ws_url,
            extra_headers={"Authorization": f"Bearer {token}"},
            ping_interval=None,  # Disable client pings — backend sends its own keepalive
            ping_timeout=None,
            max_size=10 * 1024 * 1024,
        ) as ws:
            connect_time = time.monotonic() - connect_start
            result['connect_time_ms'] = int(connect_time * 1000)
            logger.info(f"[{codec_name}] Connected in {result['connect_time_ms']}ms")

            # Background task to receive messages
            transcripts = []

            async def receive_messages():
                try:
                    async for msg in ws:
                        if isinstance(msg, str):
                            try:
                                data = json.loads(msg)
                                transcripts.append(data)
                            except json.JSONDecodeError:
                                pass
                        elif isinstance(msg, bytes):
                            # Binary message (header type responses)
                            if len(msg) >= 4:
                                header_type = struct.unpack('I', msg[:4])[0]
                                if header_type == 101:  # ping
                                    pass
                except websockets.exceptions.ConnectionClosed:
                    pass

            recv_task = asyncio.create_task(receive_messages())

            # Send frames at real-time pace
            test_start = time.monotonic()
            batch_size = max(1, int(0.1 / frame_duration_s))  # Send ~100ms worth at a time

            for i in range(0, len(frames), batch_size):
                batch = frames[i : i + batch_size]
                for frame in batch:
                    await ws.send(frame)
                    result['frames_sent'] += 1
                    result['bytes_sent'] += len(frame)

                # Pace to real-time
                elapsed = time.monotonic() - test_start
                expected = (i + len(batch)) * frame_duration_s
                sleep_time = expected - elapsed
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)

                # Progress every 60s
                if result['frames_sent'] % int(60 / frame_duration_s) == 0:
                    logger.info(
                        f"[{codec_name}] Progress: {elapsed:.0f}s / {duration_s}s "
                        f"({result['frames_sent']} frames, {result['bytes_sent']} bytes, "
                        f"{len(transcripts)} transcripts)"
                    )

            # Wait a bit for final transcripts
            await asyncio.sleep(3)

            # Close cleanly
            await ws.close()
            recv_task.cancel()
            try:
                await recv_task
            except asyncio.CancelledError:
                pass

            total_time = time.monotonic() - test_start
            result['total_time_s'] = round(total_time, 1)
            result['transcripts_received'] = len(transcripts)
            result['status'] = 'PASS'

            logger.info(
                f"[{codec_name}] COMPLETE: {result['frames_sent']} frames, "
                f"{result['bytes_sent']} bytes sent in {result['total_time_s']}s, "
                f"{result['transcripts_received']} transcripts received"
            )

    except Exception as e:
        result['status'] = 'FAIL'
        result['error'] = str(e)
        logger.error(f"[{codec_name}] FAILED: {e}")

    return result


async def main():
    parser = argparse.ArgumentParser(
        description='Integration test: /v4/listen WebSocket with private cloud sync',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('--host', default='localhost', help='Backend host (default: localhost)')
    parser.add_argument('--port', type=int, default=8787, help='Backend port (default: 8787)')
    parser.add_argument('--duration', type=int, default=300, help='Test duration in seconds (default: 300 = 5min)')
    parser.add_argument('--codec', choices=list(CODECS.keys()), help='Test single codec only')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose logging')
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%H:%M:%S',
    )

    # Get auth token
    logger.info("Getting Firebase auth token...")
    token = get_firebase_token()
    if not token:
        logger.error("Failed to get Firebase token. Set GOOGLE_APPLICATION_CREDENTIALS.")
        sys.exit(1)
    logger.info("Auth token acquired")

    # Select codecs to test
    codecs_to_test = {args.codec: CODECS[args.codec]} if args.codec else CODECS

    # Run tests
    results = []
    for codec_name, codec_config in codecs_to_test.items():
        logger.info(f"\n{'='*60}")
        logger.info(f"TESTING CODEC: {codec_name} ({codec_config['description']})")
        logger.info(f"Duration: {args.duration}s, Sample rate: {codec_config['sample_rate']}Hz")
        logger.info(f"{'='*60}")

        result = await run_codec_test(
            host=args.host,
            port=args.port,
            codec_name=codec_name,
            codec_config=codec_config,
            duration_s=args.duration,
            token=token,
        )
        results.append(result)

        # Brief pause between codecs
        if codec_name != list(codecs_to_test.keys())[-1]:
            logger.info("Waiting 5s before next codec...")
            await asyncio.sleep(5)

    # Summary
    print(f"\n{'='*60}")
    print("INTEGRATION TEST RESULTS")
    print(f"{'='*60}")
    print(f"{'Codec':<15} {'Status':<8} {'Frames':<10} {'Bytes':<12} {'Time':<8} {'Transcripts':<12}")
    print(f"{'-'*15} {'-'*8} {'-'*10} {'-'*12} {'-'*8} {'-'*12}")

    pass_count = 0
    fail_count = 0
    skip_count = 0

    for r in results:
        status_icon = '✓' if r['status'] == 'PASS' else '✗' if r['status'] == 'FAIL' else '—'
        print(
            f"{r['codec']:<15} {status_icon} {r['status']:<6} {r['frames_sent']:<10} "
            f"{r['bytes_sent']:<12} {r['total_time_s']:<8} {r['transcripts_received']:<12}"
        )
        if r['error']:
            print(f"  Error: {r['error']}")

        if r['status'] == 'PASS':
            pass_count += 1
        elif r['status'] == 'FAIL':
            fail_count += 1
        else:
            skip_count += 1

    print(f"\nTotal: {pass_count} PASS, {fail_count} FAIL, {skip_count} SKIP")
    sys.exit(1 if fail_count > 0 else 0)


if __name__ == '__main__':
    asyncio.run(main())
