"""End-to-end speaker identification test with real podcast audio.

Full lifecycle test:
  Session 1: Stream audio → get transcripts → assign speaker → wait for embedding extraction
  Session 2: Stream same audio → verify auto-labeling via SpeakerLabelSuggestionEvent

This exercises the REAL pipeline:
  Client labels speaker → pusher queues extraction (120s min age) →
  extract_speaker_samples() downloads from GCS → calls embedding API →
  stores 256-d vector in Firestore → next session loads embeddings →
  ring buffer audio → embedding API → cosine match → SpeakerLabelSuggestionEvent

Prerequisites:
  - Backend running: LOCAL_DEVELOPMENT=true, port 10151
  - Pusher running: port 10152
  - Embedding API: port 18881 (port-forwarded from dev GKE diarizer)
  - Firebase/Firestore credentials configured
  - Test WAV file available (60s speech)

Usage:
  pytest tests/integration/test_speaker_id_e2e_podcast.py -v -x -s
"""

import asyncio
import io
import json
import socket
import struct
import time
import uuid
import wave
from datetime import datetime, timezone

import numpy as np
import pytest
import requests
import websockets

# ─── Configuration ────────────────────────────────────────────────────────────

BACKEND_HOST = "localhost"
BACKEND_PORT = 10151
PUSHER_PORT = 10152
EMBEDDING_PORT = 18881
LISTEN_URL = f"ws://{BACKEND_HOST}:{BACKEND_PORT}/v4/listen"
EMBEDDING_URL = f"http://{BACKEND_HOST}:{EMBEDDING_PORT}"
DEV_AUTH_HEADER = {"authorization": "Bearer dev-token"}
DEV_UID = "123"

# Timing constants
SPEAKER_SAMPLE_MIN_AGE = 120  # seconds — pusher won't process until sample is this old
SPEAKER_SAMPLE_PROCESS_INTERVAL = 15  # seconds — pusher polls queue at this interval
EXTRACTION_BUFFER = 30  # extra seconds for extraction + embedding API call
TOTAL_WAIT_FOR_EMBEDDING = SPEAKER_SAMPLE_MIN_AGE + SPEAKER_SAMPLE_PROCESS_INTERVAL + EXTRACTION_BUFFER

# Test audio — Silero VAD test file (60s speech, 16kHz mono PCM16)
import os

TEST_WAV = os.path.join(
    os.path.dirname(__file__),
    '../../pretrained_models/snakers4_silero-vad_master/tests/data/test.wav',
)


# ─── Helpers ──────────────────────────────────────────────────────────────────


def is_port_open(port):
    try:
        sock = socket.create_connection((BACKEND_HOST, port), timeout=2)
        sock.close()
        return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


def load_test_audio_pcm16(seconds=60):
    """Load test WAV file and return raw PCM16LE bytes + sample rate."""
    if not os.path.exists(TEST_WAV):
        return None
    wf = wave.open(TEST_WAV, 'r')
    frames = min(wf.getnframes(), wf.getframerate() * seconds)
    pcm_data = wf.readframes(frames)
    sample_rate = wf.getframerate()
    wf.close()
    return pcm_data, sample_rate


def _get_firestore_db():
    try:
        from database._client import db

        return db
    except Exception:
        return None


def create_person_in_firestore(uid, person_id, name):
    """Create a person document in Firestore (no embedding yet)."""
    db = _get_firestore_db()
    if db is None:
        pytest.skip("Firestore not available")
    person_data = {
        'id': person_id,
        'name': name,
        'speech_samples': [],
        'speech_sample_transcripts': [],
        'speech_samples_version': 1,
        'created_at': datetime.now(timezone.utc),
        'updated_at': datetime.now(timezone.utc),
    }
    db.collection('users').document(uid).collection('people').document(person_id).set(person_data)
    return person_data


def get_person_from_firestore(uid, person_id):
    """Read person document from Firestore."""
    db = _get_firestore_db()
    if db is None:
        return None
    doc = db.collection('users').document(uid).collection('people').document(person_id).get()
    if doc.exists:
        return doc.to_dict()
    return None


def cleanup_person(uid, person_id):
    """Delete person from Firestore."""
    try:
        db = _get_firestore_db()
        if db:
            db.collection('users').document(uid).collection('people').document(person_id).delete()
    except Exception:
        pass


def ensure_private_cloud_sync(uid, enabled=True):
    """Set private_cloud_sync_enabled flag in Firestore."""
    db = _get_firestore_db()
    if db is None:
        pytest.skip("Firestore not available")
    db.collection('users').document(uid).set({'private_cloud_sync_enabled': enabled}, merge=True)


async def connect_listen(extra_params="", timeout=30):
    """Connect to /v4/listen and wait for 'ready' status."""
    url = (
        f"{LISTEN_URL}?uid={DEV_UID}&language=en&sample_rate=16000&codec=pcm8"
        f"&speaker_auto_assign=enabled{extra_params}"
    )
    ws = await websockets.connect(url, extra_headers=DEV_AUTH_HEADER, max_size=10 * 1024 * 1024)
    start = time.time()
    while time.time() - start < timeout:
        try:
            msg = await asyncio.wait_for(ws.recv(), timeout=3)
            if isinstance(msg, str) and msg != 'ping':
                try:
                    parsed = json.loads(msg)
                    if (
                        isinstance(parsed, dict)
                        and parsed.get('type') == 'service_status'
                        and parsed.get('status') == 'ready'
                    ):
                        return ws
                except json.JSONDecodeError:
                    pass
        except asyncio.TimeoutError:
            continue
    raise TimeoutError("WS never reached 'ready' status")


async def stream_audio_and_collect(ws, pcm_data, stream_duration_s, chunk_size=3200, delay=0.02):
    """Stream PCM audio and collect all WS messages (transcripts + events).

    Streams audio in real-time-ish pace, collecting all messages.
    Returns (transcripts, events) where:
      - transcripts: list of segment dicts (from JSON arrays)
      - events: list of event dicts (from JSON objects with 'type' field)
    """
    transcripts = []
    events = []
    start_time = time.time()

    # Calculate how much audio data to send
    bytes_per_second = 16000 * 2  # 16kHz, 16-bit
    total_bytes_to_send = int(stream_duration_s * bytes_per_second)
    audio_to_send = pcm_data[:total_bytes_to_send]

    # Send audio in background
    async def send_audio():
        offset = 0
        while offset < len(audio_to_send):
            end = min(offset + chunk_size, len(audio_to_send))
            chunk = audio_to_send[offset:end]
            try:
                await ws.send(chunk)
            except Exception:
                break
            offset = end
            await asyncio.sleep(delay)

    send_task = asyncio.create_task(send_audio())

    # Collect messages until stream_duration_s elapsed
    while time.time() - start_time < stream_duration_s + 5:
        try:
            msg = await asyncio.wait_for(ws.recv(), timeout=2)
            if isinstance(msg, str) and msg != 'ping':
                try:
                    parsed = json.loads(msg)
                    if isinstance(parsed, list):
                        # Transcript segments
                        transcripts.extend(parsed)
                    elif isinstance(parsed, dict) and parsed.get('type'):
                        events.append(parsed)
                except json.JSONDecodeError:
                    pass
        except asyncio.TimeoutError:
            if send_task.done():
                break
            continue
        except websockets.exceptions.ConnectionClosed:
            break

    if not send_task.done():
        send_task.cancel()
        try:
            await send_task
        except asyncio.CancelledError:
            pass

    return transcripts, events


async def wait_and_collect_events(ws, wait_seconds, event_types=None):
    """Keep WS open and collect events for wait_seconds.

    Sends periodic pings to keep connection alive.
    Returns list of matching events.
    """
    events = []
    start_time = time.time()
    last_keepalive = time.time()

    while time.time() - start_time < wait_seconds:
        # Send keepalive ping every 30 seconds
        if time.time() - last_keepalive > 30:
            try:
                await ws.send(b'\x00' * 320)  # tiny audio to prevent inactivity disconnect
            except Exception:
                break
            last_keepalive = time.time()

        try:
            msg = await asyncio.wait_for(ws.recv(), timeout=5)
            if isinstance(msg, str) and msg != 'ping':
                try:
                    parsed = json.loads(msg)
                    if isinstance(parsed, dict) and parsed.get('type'):
                        if event_types is None or parsed['type'] in event_types:
                            events.append(parsed)
                except json.JSONDecodeError:
                    pass
        except asyncio.TimeoutError:
            continue
        except websockets.exceptions.ConnectionClosed:
            break

    return events


# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def check_all_services():
    """Check that all 3 services are running."""
    if not is_port_open(BACKEND_PORT):
        pytest.skip(f"Backend not running on port {BACKEND_PORT}")
    if not is_port_open(PUSHER_PORT):
        pytest.skip(f"Pusher not running on port {PUSHER_PORT}")
    if not is_port_open(EMBEDDING_PORT):
        pytest.skip(f"Embedding API not running on port {EMBEDDING_PORT}")


@pytest.fixture(scope="module")
def test_audio():
    """Load test audio file."""
    result = load_test_audio_pcm16(seconds=60)
    if not result:
        pytest.skip("Test WAV not available")
    return result


# ─── E2E Test ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestSpeakerIdE2EPodcast:
    """Full end-to-end speaker identification lifecycle test.

    Sequence (matches issue #5623 flow chart):
    ┌─────────────────────────────────────────────────────────────────┐
    │ SESSION 1: Label + Extract                                      │
    │  Client ──WS──► Backend ──audio──► Deepgram ──transcripts──►    │
    │  Client ◄──────────────────────────────────────── transcripts    │
    │  Client ──speaker_assigned──► Backend ──opcode105──► Pusher     │
    │  ... 120s min age ...                                           │
    │  Pusher ──extract_speaker_samples()──► GCS audio download       │
    │  Pusher ──► Embedding API ──256d vector──► Firestore            │
    ├─────────────────────────────────────────────────────────────────┤
    │ SESSION 2: Auto-label                                           │
    │  Client ──WS──► Backend (loads embeddings from Firestore)       │
    │  Client ──audio──► Backend ──ring buffer──► Embedding API       │
    │  Backend: cosine_distance(query, stored) < 0.45                 │
    │  Client ◄──── SpeakerLabelSuggestionEvent(person_name=X)       │
    └─────────────────────────────────────────────────────────────────┘
    """

    async def test_full_speaker_id_lifecycle(self, check_all_services, test_audio):
        """Stream podcast → assign speaker → wait for extraction → verify auto-labeling."""
        pcm_data, sample_rate = test_audio
        person_id = str(uuid.uuid4())
        person_name = "PodcastHost"

        print(f"\n{'='*70}")
        print(f"E2E Speaker ID Test — person_id={person_id[:8]}...")
        print(f"{'='*70}")

        try:
            # ── SETUP: Create person + enable private cloud sync ──────────
            print("\n[SETUP] Creating person in Firestore...")
            ensure_private_cloud_sync(DEV_UID, True)
            create_person_in_firestore(DEV_UID, person_id, person_name)

            # Verify person exists with no embedding
            person = get_person_from_firestore(DEV_UID, person_id)
            assert person is not None, "Person not created in Firestore"
            assert person.get('speaker_embedding') is None, "Person should not have embedding yet"
            print(f"  Person '{person_name}' created (no embedding)")

            # ── SESSION 1: Stream audio, get transcripts, assign speaker ──
            print("\n[SESSION 1] Connecting to /v4/listen...")
            ws1 = await connect_listen()
            assert ws1.open, "WS1 failed to connect"
            print("  Connected. Streaming 55s of audio...")

            # Stream 55 seconds of audio (need enough for transcripts)
            transcripts1, events1 = await stream_audio_and_collect(
                ws1, pcm_data, stream_duration_s=55, chunk_size=3200, delay=0.02
            )
            print(f"  Got {len(transcripts1)} transcript segments")

            # Find segments with speaker_id to assign
            segments_with_speaker = []
            seen_ids = set()
            for seg in transcripts1:
                sid = seg.get('id')
                if sid and sid not in seen_ids:
                    seen_ids.add(sid)
                    segments_with_speaker.append(seg)

            assert len(segments_with_speaker) > 0, "No transcript segments received — STT may not be working"
            print(f"  Found {len(segments_with_speaker)} unique segments")

            # Pick the first few segments (ideally with same speaker_id)
            target_speaker_id = segments_with_speaker[0].get('speaker_id', 0)
            assign_segment_ids = [
                seg['id'] for seg in segments_with_speaker if seg.get('speaker_id') == target_speaker_id
            ][:5]

            print(f"  Assigning speaker_id={target_speaker_id} to person '{person_name}'")
            print(f"  Segment IDs: {[sid[:8]+'...' for sid in assign_segment_ids]}")

            # Send speaker_assigned event
            assign_msg = json.dumps(
                {
                    'type': 'speaker_assigned',
                    'speaker_id': target_speaker_id,
                    'person_id': person_id,
                    'person_name': person_name,
                    'segment_ids': assign_segment_ids,
                }
            )
            await ws1.send(assign_msg)
            print("  speaker_assigned event sent!")

            # Keep streaming a bit more audio to ensure audio chunks are uploaded to GCS
            print("  Streaming 5s more audio (for GCS upload)...")
            _, extra_events = await stream_audio_and_collect(
                ws1, pcm_data, stream_duration_s=5, chunk_size=3200, delay=0.02
            )

            # ── WAIT: Keep session open while pusher processes ────────────
            # Pusher won't extract until sample is 120s old + 15s poll interval
            print(f"\n[WAIT] Keeping WS open for {TOTAL_WAIT_FOR_EMBEDDING}s while pusher extracts embedding...")
            print(f"  (120s min age + 15s poll interval + {EXTRACTION_BUFFER}s extraction buffer)")

            wait_start = time.time()
            check_interval = 30
            last_check = 0
            embedding_found = False

            while time.time() - wait_start < TOTAL_WAIT_FOR_EMBEDDING:
                elapsed = time.time() - wait_start

                # Periodic Firestore check
                if elapsed - last_check >= check_interval:
                    person = get_person_from_firestore(DEV_UID, person_id)
                    has_embedding = person and person.get('speaker_embedding') is not None
                    samples = person.get('speech_samples', []) if person else []
                    version = person.get('speech_samples_version', 1) if person else 1
                    print(
                        f"  T+{elapsed:.0f}s — embedding: {'YES' if has_embedding else 'no'}, "
                        f"samples: {len(samples)}, version: {version}"
                    )
                    if has_embedding:
                        embedding_found = True
                        break
                    last_check = elapsed

                # Keep WS alive with small audio bursts
                try:
                    await ws1.send(b'\x00' * 3200)
                except Exception:
                    print("  WS1 disconnected during wait — reconnecting...")
                    try:
                        ws1 = await connect_listen()
                    except Exception:
                        pass
                await asyncio.sleep(5)

            # Close session 1
            try:
                await ws1.close()
            except Exception:
                pass
            print("  Session 1 closed.")

            # Final Firestore check
            if not embedding_found:
                person = get_person_from_firestore(DEV_UID, person_id)
                embedding_found = person and person.get('speaker_embedding') is not None
                if embedding_found:
                    print(f"  Embedding found on final check!")

            # ── VERIFY: Embedding stored ──────────────────────────────────
            print(f"\n[VERIFY] Checking Firestore for speaker embedding...")
            person = get_person_from_firestore(DEV_UID, person_id)
            assert person is not None, "Person disappeared from Firestore"

            embedding = person.get('speaker_embedding')
            samples = person.get('speech_samples', [])
            version = person.get('speech_samples_version', 1)

            print(f"  Embedding: {'present (' + str(len(embedding)) + '-d)' if embedding else 'MISSING'}")
            print(f"  Samples: {len(samples)}")
            print(f"  Version: {version}")

            if not embedding:
                # Check backend/pusher logs for clues
                print("\n  WARNING: Embedding not extracted. Possible causes:")
                print("  - Audio not uploaded to GCS (private_cloud_sync issue)")
                print("  - Segment IDs not in current_session_segments (can_assign=False)")
                print("  - extract_speaker_samples() failed (check pusher logs)")
                print("  Skipping session 2 — investigate pusher logs at /tmp/pusher.log")
                pytest.fail(
                    f"Embedding not extracted after {TOTAL_WAIT_FOR_EMBEDDING}s. "
                    f"Samples: {len(samples)}, version: {version}. Check /tmp/pusher.log"
                )

            # ── SESSION 2: Verify auto-labeling ──────────────────────────
            print(f"\n[SESSION 2] Connecting to /v4/listen (should load stored embedding)...")

            # Small delay to ensure Firestore is consistent
            await asyncio.sleep(2)

            ws2 = await connect_listen()
            assert ws2.open, "WS2 failed to connect"
            print("  Connected. Streaming 30s of audio...")

            # Stream audio and collect ALL messages (transcripts + events)
            transcripts2 = []
            suggestion_events = []
            all_events = []

            start_time = time.time()
            stream_duration = 30  # seconds

            # Send audio in background
            async def send_audio_session2():
                offset = 0
                bytes_per_sec = sample_rate * 2
                total = int(stream_duration * bytes_per_sec)
                audio = pcm_data[:total]
                while offset < len(audio):
                    end = min(offset + 3200, len(audio))
                    try:
                        await ws2.send(audio[offset:end])
                    except Exception:
                        break
                    offset = end
                    await asyncio.sleep(0.02)

            send_task = asyncio.create_task(send_audio_session2())

            # Collect for stream_duration + extra wait for speaker ID processing
            collect_until = stream_duration + 30  # extra 30s for speaker ID task
            while time.time() - start_time < collect_until:
                try:
                    msg = await asyncio.wait_for(ws2.recv(), timeout=3)
                    if isinstance(msg, str) and msg != 'ping':
                        try:
                            parsed = json.loads(msg)
                            if isinstance(parsed, list):
                                transcripts2.extend(parsed)
                            elif isinstance(parsed, dict):
                                event_type = parsed.get('type')
                                if event_type:
                                    all_events.append(parsed)
                                    if event_type == 'speaker_label_suggestion':
                                        suggestion_events.append(parsed)
                                        print(
                                            f"  >>> SpeakerLabelSuggestionEvent: "
                                            f"speaker={parsed.get('speaker_id')}, "
                                            f"person={parsed.get('person_name')}, "
                                            f"distance info in backend logs"
                                        )
                        except json.JSONDecodeError:
                            pass
                except asyncio.TimeoutError:
                    if send_task.done() and time.time() - start_time > stream_duration + 15:
                        break
                    continue
                except websockets.exceptions.ConnectionClosed:
                    break

            if not send_task.done():
                send_task.cancel()
                try:
                    await send_task
                except asyncio.CancelledError:
                    pass

            try:
                await ws2.close()
            except Exception:
                pass

            # ── RESULTS ───────────────────────────────────────────────────
            print(f"\n{'='*70}")
            print(f"RESULTS")
            print(f"{'='*70}")
            print(f"  Session 2 transcripts: {len(transcripts2)} segments")
            print(f"  All events: {[e.get('type') for e in all_events]}")
            print(f"  Speaker label suggestions: {len(suggestion_events)}")

            if suggestion_events:
                for sug in suggestion_events:
                    print(
                        f"    - speaker_id={sug.get('speaker_id')}, "
                        f"person_name='{sug.get('person_name')}', "
                        f"person_id={sug.get('person_id', '')[:8]}..., "
                        f"segment_id={sug.get('segment_id', '')[:8]}..."
                    )

                # Verify the suggestion matches our person
                matched = [s for s in suggestion_events if s.get('person_name') == person_name]
                assert len(matched) > 0, (
                    f"Got {len(suggestion_events)} suggestions but none for '{person_name}': "
                    f"{[s.get('person_name') for s in suggestion_events]}"
                )
                print(f"\n  SUCCESS: Speaker '{person_name}' auto-labeled in session 2!")
            else:
                # No suggestions — might be a timing issue or no segments matched
                print(f"\n  No SpeakerLabelSuggestionEvent received.")
                print(f"  Possible causes:")
                print(f"  - No segments with duration >= 2s (SPEAKER_ID_MIN_AUDIO)")
                print(f"  - Ring buffer empty or too short")
                print(f"  - Embedding API call failed")
                print(f"  - Cosine distance > 0.45 threshold")
                print(f"  Check backend logs at /tmp/backend.log for 'Speaker ID:' lines")

                # Don't hard-fail — log evidence for investigation
                # The embedding was stored, so the pipeline partially works
                pytest.fail(
                    f"No SpeakerLabelSuggestionEvent in session 2. "
                    f"Got {len(transcripts2)} transcripts, {len(all_events)} events. "
                    f"Check /tmp/backend.log"
                )

        finally:
            # ── CLEANUP ───────────────────────────────────────────────────
            print(f"\n[CLEANUP] Removing person '{person_name}'...")
            cleanup_person(DEV_UID, person_id)
            print("  Done.")
