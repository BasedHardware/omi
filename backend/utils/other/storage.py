import datetime
import hashlib
import io
import json
import os
import struct
import threading
import time
import wave
from contextlib import contextmanager
from typing import Any, Callable, Dict, List, Optional, Tuple
from concurrent.futures import as_completed, wait, FIRST_COMPLETED

from utils.executors import postprocess_executor, storage_executor

try:
    import opuslib
except Exception as e:
    opuslib = None
    _opus_import_error: Optional[Exception] = e
else:
    _opus_import_error = None
from database.redis_db import cache_signed_url, get_cached_signed_url, delete_cached_signed_url
from database.legal_holds import external_write_fence
from utils.object_store.errors import ObjectNotFound
from utils import encryption
from utils.cloud_tasks import enqueue_audio_merge_job, is_audio_merge_dispatch_enabled
from utils.observability.fallback import record_fallback
from utils.other.deferred_delete import DeferredDeleter
from database import users as users_db
import logging

logger = logging.getLogger(__name__)

# Per-request fan-out limits for storage_executor (#7387)
_STORAGE_CHUNK_SEM = threading.BoundedSemaphore(32)
# 4 → 2 in #7526 was load-shedding while the pool was full of sleeping
# per-file deletion timers; restored to 4 now that the janitor thread
# (deferred_delete.py) holds those instead of pool threads.
_PRECACHE_FILE_SEM = threading.BoundedSemaphore(4)
_CHUNK_WINDOW_SIZE = 8

_merge_tracker_lock = threading.Lock()
_active_merges: dict[str, float] = {}
_recent_merges: dict[str, tuple[float, str]] = {}
_RECENT_MERGE_WINDOW = 300
_MERGE_TRACKER_MAX = 2000

# Opus encoding constants
OPUS_SAMPLE_RATE = 16000
OPUS_CHANNELS = 1
OPUS_FRAME_DURATION_MS = 20  # 20ms frames (standard for voice)
OPUS_FRAME_SIZE = OPUS_SAMPLE_RATE * OPUS_FRAME_DURATION_MS // 1000  # 320 samples per frame

# Valid private cloud sync extensions (longest first for correct matching)
PRIVATE_CLOUD_EXTENSIONS = ['.batch.enc', '.batch.bin', '.opus.enc', '.opus', '.enc', '.bin']


def _object_store():
    """Return the configured object-store adapter (ADR-0032). The migration seam: callers use this
    neutral port instead of GCS ``blob`` ops, so ``OBJECT_STORE_BACKEND`` (gcs|s3) swaps the backend.
    Kept as a thin function so tests can point it at the in-memory ``FakeObjectStore``."""
    from utils.object_store import get_object_store

    return get_object_store()


speech_profiles_bucket = (os.getenv('BUCKET_SPEECH_PROFILES') or '').strip() or None
postprocessing_audio_bucket = os.getenv('BUCKET_POSTPROCESSING')
memories_recordings_bucket = (os.getenv('BUCKET_MEMORIES_RECORDINGS') or '').strip() or None
private_cloud_sync_bucket = os.getenv('BUCKET_PRIVATE_CLOUD_SYNC', 'omi-private-cloud-sync')
syncing_local_bucket = os.getenv('BUCKET_TEMPORAL_SYNC_LOCAL')
omi_apps_bucket = os.getenv('BUCKET_PLUGINS_LOGOS')
app_thumbnails_bucket = os.getenv('BUCKET_APP_THUMBNAILS')
chat_files_bucket = os.getenv('BUCKET_CHAT_FILES')
desktop_updates_bucket = os.getenv('BUCKET_DESKTOP_UPDATES')
screen_frames_bucket = os.getenv('BUCKET_SCREEN_FRAMES')

_did_warn_missing_speech_profiles_bucket = False


def _uses_real_object_store(store: Any = None) -> bool:
    """Whether the active object store is a real adapter, not a test double.

    This is upstream's ``_uses_real_gcs_bucket`` expressed on the port. Upstream can ask "is this a
    concrete google.cloud.storage bucket?" because its writes carry a bucket OBJECT; ours carry a
    bucket NAME, so that question has no answer here — ``type('omi-speech').__module__`` is
    ``builtins`` and the fence would never engage, on any backend, GCS included.

    The question that does carry over is the one upstream is really asking: am I about to mutate a
    real provider, or a fake a test injected? Adapters we ship live under ``utils.object_store.adapters``;
    fakes injected by the factory's setter do not. So hermetic tests stay hermetic, and the fence
    covers S3/RustFS as well as GCS — those are just as external, and an on-prem install is the case
    this initiative exists for.
    """

    return type(store if store is not None else _object_store()).__module__.startswith('utils.object_store.adapters')


@contextmanager
def owner_storage_write_gate(uid: str, store: Any = None):
    """Fence one owner-scoped object-store mutation against account deletion.

    The fence is checked after authorization/encoding but before the upload/copy call: a write is
    refused while the account is being deleted or a destructive operation owns the account gate. It
    takes no lock, so concurrent uploads for one account never contend with each other; the deletion
    side verifies its purges left nothing behind. Local/offline providers and injected test doubles
    remain hermetic and do not need Firestore authority.

    ``store`` is the object the caller is about to write through, when it has one in hand. Upstream
    passes the bucket for the same reason: a caller that resolved its own store (``merge_conversations``
    holds one) must be judged on THAT store, not on whatever the global accessor would return — else a
    hermetic test injecting a fake at the caller's seam still trips the fence.
    """

    if not uid:
        raise ValueError('owner storage writes require a uid')
    stage = os.getenv('OMI_ENV_STAGE', '').strip().lower()
    provider_mode = os.getenv('PROVIDER_MODE', '').strip().lower()
    if stage in {'local', 'offline'} or provider_mode == 'offline' or not _uses_real_object_store(store):
        yield None
        return
    with external_write_fence(uid):
        yield None


@contextmanager
def _sync_path_owner_gate(file_path: str):
    """Fence a sync-bucket write when the path names its owner, pass through when it does not.

    Same shape as upstream's inline ``if owner_uid: with ... else: ...`` around each of the four
    syncing writes, said once instead of four times.
    """

    owner_uid = _owner_uid_from_sync_path(file_path)
    if not owner_uid:
        yield None
        return
    with owner_storage_write_gate(owner_uid):
        yield None


def _owner_uid_from_sync_path(file_path: str) -> Optional[str]:
    """Extract the owner from the only UID-scoped temporary-sync layout."""

    parts = str(file_path).replace('\\', '/').split('/')
    if len(parts) >= 2 and parts[0] == 'syncing' and parts[1] and parts[1] not in {'.', '..'}:
        return parts[1]
    return None


def _delete_owner_bucket_prefix(bucket: str, prefix: str) -> int:
    """Delete and verify one owner prefix, failing closed on a torn purge.

    ``bucket`` is a NAME here, not a GCS bucket object: list/delete go through the port (ADR-0032),
    so the purge works on whichever backend is configured. The verifying re-list is upstream's and
    is the point of the function — a purge that silently left objects behind is the failure this
    guards.
    """

    store = _object_store()
    deleted = 0
    for info in store.list(bucket, prefix):
        store.delete(bucket, info.key)
        deleted += 1
    remaining = store.list(bucket, prefix)
    if remaining:
        raise RuntimeError(f'owner storage purge left {len(remaining)} objects under {prefix}')
    return deleted


def delete_all_user_storage_objects(uid: str) -> int:
    """Purge every non-recordings configured GCS prefix owned by ``uid``.

    The account deletion worker calls this while it owns the account-wide
    destructive-operation gate. Prefix enumeration is intentionally broader
    than Firestore's current ID inventories so playback, merge caches, stale
    markers, and uploads from an in-flight request cannot survive the wipe.
    ``delete_all_conversation_recordings`` handles its dedicated bucket in the
    same account-deletion phase, preserving its existing operational metric.
    """

    if not uid:
        return 0
    stage = os.getenv('OMI_ENV_STAGE', '').strip().lower()
    if stage in {'local', 'offline'} or os.getenv('PROVIDER_MODE', '').strip().lower() == 'offline':
        return 0

    configured: list[tuple[Optional[str], tuple[str, ...]]] = [
        (speech_profiles_bucket, (f'{uid}/',)),
        (
            private_cloud_sync_bucket,
            tuple(f'{prefix}/{uid}/' for prefix in ('chunks', 'audio', 'merged', PLAYBACK_ARTIFACT_PREFIX)),
        ),
        (syncing_local_bucket, (f'syncing/{uid}/',)),
        (chat_files_bucket, (f'{uid}/',)),
    ]
    deleted = 0
    seen_buckets: set[tuple[str, str]] = set()
    for bucket_name, prefixes in configured:
        if not bucket_name:
            continue
        for prefix in prefixes:
            key = (bucket_name, prefix)
            if key in seen_buckets:
                continue
            seen_buckets.add(key)
            deleted += _delete_owner_bucket_prefix(bucket_name, prefix)
    return deleted


def _get_opuslib() -> Any:
    if opuslib is None:
        raise RuntimeError(
            'Opus support requires opuslib and the native libopus library. '
            'Install the OS-level Opus package before encoding or decoding .opus audio.'
        ) from _opus_import_error
    return opuslib


def _required_bucket(name: Optional[str], env_var: str) -> str:
    """The configured bucket, or a failure that names the variable nobody set.

    Bucket names come from the environment and are therefore ``str | None``. Passing the None through
    to the object-store port fails anyway — deeper, as a client error about a bucket called ``None`` —
    so this turns it into the sentence an operator can act on. Buckets whose absence is a supported
    state (speech profiles: storage simply disabled) keep their own resolver and are NOT routed here.
    """
    if not name:
        raise RuntimeError(f'{env_var} is not configured, and this operation needs its bucket')
    return name


def _speech_profiles_bucket_name(required: bool = False) -> Optional[str]:
    """The configured speech-profiles bucket name, or None when unset (storage disabled)."""
    global _did_warn_missing_speech_profiles_bucket

    if speech_profiles_bucket:
        return speech_profiles_bucket

    if not _did_warn_missing_speech_profiles_bucket:
        logger.warning('BUCKET_SPEECH_PROFILES is not configured; speech profile storage is disabled')
        _did_warn_missing_speech_profiles_bucket = True

    if required:
        raise RuntimeError('BUCKET_SPEECH_PROFILES is not configured')

    return None


# *******************************************
# ************* SPEECH PROFILE **************
# *******************************************
def upload_profile_audio(file_path: str, uid: str) -> str:
    bucket = _speech_profiles_bucket_name(required=True)
    assert bucket is not None  # required=True raises if missing
    path = f'{uid}/speech_profile.wav'
    with owner_storage_write_gate(uid):
        _object_store().put_from_file(bucket, path, file_path)
    # A signed URL, not a public one: this is the user's VOICE. `public_url` returned an unauthenticated
    # link that works forever wherever the bucket is readable — on GCS it is, by project policy
    # (ADR-0087).
    return _signed_url(bucket, path, USER_AUDIO_URL_MINUTES)


def get_user_has_speech_profile(uid: str) -> bool:
    # No age cutoff: the listen pipeline (routers/transcribe.py) uses the profile
    # regardless of age, so reporting an old profile as absent only causes the app
    # to re-prompt users whose profile is still in active use (#5128).
    bucket = _speech_profiles_bucket_name()
    if bucket is None:
        return False

    return _object_store().exists(bucket, f'{uid}/speech_profile.wav')


def get_profile_audio_if_exists(uid: str, download: bool = True) -> Optional[str]:
    bucket = _speech_profiles_bucket_name()
    if bucket is None:
        return None

    path = f'{uid}/speech_profile.wav'
    if _object_store().exists(bucket, path):
        if download:
            file_path = f'_temp/{uid}_speech_profile.wav'
            _object_store().download_to(bucket, path, file_path)
            return file_path
        return _signed_url(bucket, path, 60)

    return None


def delete_additional_profile_audio(uid: str, file_name: str) -> None:
    bucket = _speech_profiles_bucket_name()
    if bucket is None:
        return

    path = f'{uid}/additional_profile_recordings/{file_name}'
    if _object_store().exists(bucket, path):
        logger.info(f'delete_additional_profile_audio deleting {file_name}')
        _object_store().delete(bucket, path)


def get_additional_profile_recordings(uid: str, download: bool = False) -> List[str]:
    bucket = _speech_profiles_bucket_name()
    if bucket is None:
        return []

    objects = _object_store().list(bucket, f'{uid}/additional_profile_recordings/')
    if download:
        paths: List[str] = []
        for obj in objects:
            file_path = f'_temp/{uid}_{obj.key.split("/")[-1]}'
            _object_store().download_to(bucket, obj.key, file_path)
            paths.append(file_path)
        return paths

    return [_signed_url(bucket, obj.key, 60) for obj in objects]


# ********************************************
# ************* PEOPLE PROFILES **************
# ********************************************


def delete_user_person_speech_sample(uid: str, person_id: str, file_name: str) -> None:
    bucket = _speech_profiles_bucket_name()
    if bucket is None:
        return

    _object_store().delete(bucket, f'{uid}/people_profiles/{person_id}/{file_name}')


def delete_user_person_speech_samples(uid: str, person_id: str) -> None:
    bucket = _speech_profiles_bucket_name()
    if bucket is None:
        return

    for obj in _object_store().list(bucket, f'{uid}/people_profiles/{person_id}/'):
        _object_store().delete(bucket, obj.key)


def upload_person_speech_sample_from_bytes(
    audio_bytes: bytes,
    uid: str,
    person_id: str,
    sample_rate: int = 16000,
) -> str:
    """Upload PCM audio bytes as WAV speech sample. Returns GCS path."""
    import uuid as uuid_module

    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, 'wb') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)  # 16-bit audio
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(audio_bytes)

    bucket = _speech_profiles_bucket_name(required=True)
    assert bucket is not None  # required=True raises if missing
    filename = f"{uuid_module.uuid4()}.wav"
    path = f'{uid}/people_profiles/{person_id}/{filename}'
    with owner_storage_write_gate(uid):
        _object_store().put(bucket, path, wav_buffer.getvalue(), content_type='audio/wav')

    return path


def get_user_people_ids(uid: str) -> List[str]:
    bucket = _speech_profiles_bucket_name()
    if bucket is None:
        return []

    return [obj.key.split("/")[-2] for obj in _object_store().list(bucket, f'{uid}/people_profiles/')]


def get_user_person_speech_samples(uid: str, person_id: str, download: bool = False) -> List[str]:
    bucket = _speech_profiles_bucket_name()
    if bucket is None:
        return []

    objects = _object_store().list(bucket, f'{uid}/people_profiles/{person_id}/')
    if download:
        paths: List[str] = []
        for obj in objects:
            file_path = f'_temp/{uid}_person_{obj.key.split("/")[-1]}'
            _object_store().download_to(bucket, obj.key, file_path)
            paths.append(file_path)
        return paths

    return [_signed_url(bucket, obj.key, 60) for obj in objects]


def get_speech_sample_signed_urls(paths: List[str]) -> List[str]:
    """
    Generate signed URLs for speech samples given their GCS paths.
    Uses the paths stored in Firestore instead of listing GCS blobs.

    Args:
        paths: List of GCS paths (e.g., '{uid}/people_profiles/{person_id}/{filename}')

    Returns:
        List of signed URLs
    """
    if not paths:
        return []
    bucket = _speech_profiles_bucket_name()
    if bucket is None:
        return []

    return [_signed_url(bucket, path, 60) for path in paths]


# ********************************************
# ************* POST PROCESSING **************
# ********************************************
def upload_postprocessing_audio(file_path: str) -> str:
    """Upload the conversation audio and return a URL the STT provider can fetch.

    Signed, not public (ADR-0087). The caller already named the result ``signed_url``, which is what it
    should always have been: this is the user's recording, and the provider only needs it for one call.
    """
    _object_store().put_from_file(
        _required_bucket(postprocessing_audio_bucket, 'BUCKET_POSTPROCESSING'), file_path, file_path
    )
    return _signed_url(
        _required_bucket(postprocessing_audio_bucket, 'BUCKET_POSTPROCESSING'), file_path, USER_AUDIO_URL_MINUTES
    )


def delete_postprocessing_audio(file_path: str) -> None:
    _object_store().delete(_required_bucket(postprocessing_audio_bucket, 'BUCKET_POSTPROCESSING'), file_path)


# ***********************************
# ************* SDCARD **************
# ***********************************


def upload_sdcard_audio(file_path: str) -> str:
    # The asymmetry this used to carry — written at `file_path`, URL minted for `sdcard/{file_path}` —
    # was upstream's, and upstream fixed it in #11992: the object goes where the URL says it is.
    path = f'sdcard/{file_path}'
    _object_store().put_from_file(
        _required_bucket(postprocessing_audio_bucket, 'BUCKET_POSTPROCESSING'), path, file_path
    )
    # Signed for the same reason as the sibling above (ADR-0087).
    return _signed_url(
        _required_bucket(postprocessing_audio_bucket, 'BUCKET_POSTPROCESSING'), path, USER_AUDIO_URL_MINUTES
    )


def download_postprocessing_audio(file_path: str, destination_file_path: str) -> None:
    _object_store().download_to(
        _required_bucket(postprocessing_audio_bucket, 'BUCKET_POSTPROCESSING'), file_path, destination_file_path
    )


# ************************************************
# *********** CONVERSATIONS RECORDINGS ***********
# ************************************************


def upload_conversation_recording(file_path: str, uid: str, conversation_id: str) -> str:
    path = f'{uid}/{conversation_id}.wav'
    with owner_storage_write_gate(uid):
        _object_store().put_from_file(
            _required_bucket(memories_recordings_bucket, 'BUCKET_MEMORIES_RECORDINGS'), path, file_path
        )
    # Signed (ADR-0087): a conversation recording behind a link that never expires is the thing this
    # initiative exists to avoid.
    return _signed_url(
        _required_bucket(memories_recordings_bucket, 'BUCKET_MEMORIES_RECORDINGS'), path, USER_AUDIO_URL_MINUTES
    )


def get_conversation_recording_if_exists(uid: str, memory_id: str) -> Optional[str]:
    logger.info(f'get_conversation_recording_if_exists {uid} {memory_id}')
    path = f'{uid}/{memory_id}.wav'
    if _object_store().exists(_required_bucket(memories_recordings_bucket, 'BUCKET_MEMORIES_RECORDINGS'), path):
        file_path = f'_temp/{memory_id}.wav'
        _object_store().download_to(
            _required_bucket(memories_recordings_bucket, 'BUCKET_MEMORIES_RECORDINGS'), path, file_path
        )
        return file_path
    return None


def delete_all_conversation_recordings(uid: str) -> int:
    if not uid:
        return 0
    stage = os.getenv('OMI_ENV_STAGE', '').strip().lower()
    if stage in {'local', 'offline'} or os.getenv('PROVIDER_MODE', '').strip().lower() == 'offline':
        return 0
    if not memories_recordings_bucket:
        # A required purge failure blocks the irreversible Firestore wipe (see
        # services/users/account_deletion.py), so an unconfigured bucket must not raise here:
        # uploads resolve the same name, so a deployment without it cannot have stored recordings.
        logger.warning('BUCKET_MEMORIES_RECORDINGS is not configured; skipping conversation recordings purge')
        return 0
    # Trailing slash so a uid is not a prefix of another uid's folder (e.g. "abc" matching "abcd/").
    deleted = 0
    for obj in _object_store().list(memories_recordings_bucket, f"{uid}/"):
        _object_store().delete(memories_recordings_bucket, obj.key)
        deleted += 1
    # Upstream's verifying re-list, on the port. Their version exempted a legacy MagicMock fixture
    # that returns the same static blob on every listing; through the port there is no such fixture —
    # the in-memory fake lists consistently, like GCS and S3 — so the proof runs unconditionally.
    if _object_store().list(memories_recordings_bucket, f"{uid}/"):
        raise RuntimeError(f'owner storage purge left objects under {uid}/')
    return deleted


# ********************************************
# ************* SYNCING FILES **************
# ********************************************
def get_syncing_file_temporal_url(file_path: str):
    """Upload a file being synced and return a URL for it.

    Signed like its twin below (ADR-0087) — it carries the same audio. The two differ only in expiry;
    this one has no live caller, and is kept because upstream's surface has it.
    """
    bucket = _required_bucket(syncing_local_bucket, 'BUCKET_TEMPORAL_SYNC_LOCAL')
    with _sync_path_owner_gate(file_path):
        _object_store().put_from_file(bucket, file_path, file_path)
    return _signed_url(bucket, file_path, USER_AUDIO_URL_MINUTES)


def get_syncing_file_temporal_signed_url(file_path: str):
    bucket = _required_bucket(syncing_local_bucket, 'BUCKET_TEMPORAL_SYNC_LOCAL')
    with _sync_path_owner_gate(file_path):
        _object_store().put_from_file(bucket, file_path, file_path)
    return _signed_url(bucket, file_path, 15)


def delete_syncing_temporal_file(file_path: str):
    # The port's delete is idempotent (no raise on a missing object), so no NotFound guard is needed.
    with _sync_path_owner_gate(file_path):
        _object_store().delete(_required_bucket(syncing_local_bucket, 'BUCKET_TEMPORAL_SYNC_LOCAL'), file_path)


# Long enough for every signed-URL consumer (Deepgram fetch, speaker-ID
# download) to finish; the URLs themselves expire at 15 minutes.
SYNCING_TEMPORAL_DELETE_DELAY_SECONDS = 480

_syncing_temporal_deleter = DeferredDeleter(delete_syncing_temporal_file, name='syncing-blob-janitor')


def schedule_syncing_temporal_file_deletion(
    file_path: str, delay_seconds: float = SYNCING_TEMPORAL_DELETE_DELAY_SECONDS
):
    """Delete a temporal syncing blob once its signed-URL consumers are done.

    One janitor thread + a due-time heap, instead of the previous per-file
    time.sleep(480) that parked a storage_executor thread per blob (#7531).
    """
    _syncing_temporal_deleter.schedule(file_path, delay_seconds)


def upload_syncing_temporal_file(file_path: str):
    """Stage a local file in the syncing bucket (blob name = local relative path)."""
    with _sync_path_owner_gate(file_path):
        _object_store().put_from_file(
            _required_bucket(syncing_local_bucket, 'BUCKET_TEMPORAL_SYNC_LOCAL'), file_path, file_path
        )


def download_syncing_temporal_file(file_path: str) -> bool:
    """Download a staged blob back to its local relative path.

    Returns False when the blob no longer exists (e.g. deleted by the
    bucket's 1-day lifecycle rule before a deeply delayed task ran).
    """
    directory = os.path.dirname(file_path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    try:
        _object_store().download_to(
            _required_bucket(syncing_local_bucket, 'BUCKET_TEMPORAL_SYNC_LOCAL'), file_path, file_path
        )
        return True
    except ObjectNotFound:
        return False


# ************************************************
# *********** PRIVATE CLOUD SYNC *****************
# ************************************************


def encode_pcm_to_opus(pcm_data: bytes, sample_rate: int = OPUS_SAMPLE_RATE, channels: int = OPUS_CHANNELS) -> bytes:
    """
    Encode PCM16 audio to Opus.

    Format: 4-byte little-endian packet count, then for each packet:
    2-byte little-endian length prefix followed by the Opus packet bytes.
    This allows exact reconstruction on decode.

    Args:
        pcm_data: Raw PCM16 audio bytes
        sample_rate: Sample rate in Hz (default 16000)
        channels: Number of audio channels (default 1)

    Returns:
        Length-prefixed Opus packets as bytes
    """
    opus = _get_opuslib()
    encoder = opus.Encoder(sample_rate, channels, opus.APPLICATION_VOIP)
    frame_size = sample_rate * OPUS_FRAME_DURATION_MS // 1000
    bytes_per_frame = frame_size * channels * 2  # 16-bit = 2 bytes per sample

    packets: List[bytes] = []
    offset = 0
    while offset + bytes_per_frame <= len(pcm_data):
        frame = pcm_data[offset : offset + bytes_per_frame]
        encoded = encoder.encode(frame, frame_size)
        packets.append(encoded)
        offset += bytes_per_frame

    # Encode remaining samples (pad with silence)
    if offset < len(pcm_data):
        remaining = pcm_data[offset:]
        padded = remaining + b'\x00' * (bytes_per_frame - len(remaining))
        encoded = encoder.encode(padded, frame_size)
        packets.append(encoded)

    # Pack: [packet_count (4 bytes)] + [original_pcm_len (4 bytes)] + [len (2 bytes) + data] per packet
    output: bytes = struct.pack('<I', len(packets))
    output += struct.pack('<I', len(pcm_data))
    for pkt in packets:
        output += struct.pack('<H', len(pkt)) + pkt

    return output


def decode_opus_to_pcm(opus_data: bytes, sample_rate: int = OPUS_SAMPLE_RATE, channels: int = OPUS_CHANNELS) -> bytes:
    """
    Decode length-prefixed Opus packets back to PCM16.

    Args:
        opus_data: Length-prefixed Opus packets (from encode_pcm_to_opus)
        sample_rate: Sample rate in Hz (default 16000)
        channels: Number of audio channels (default 1)

    Returns:
        Raw PCM16 audio bytes

    Raises:
        ValueError: If opus_data is too short or has invalid header/packet structure
    """
    if len(opus_data) < 8:
        raise ValueError(f"Opus data too short: {len(opus_data)} bytes (need at least 8 for header)")

    frame_size = sample_rate * OPUS_FRAME_DURATION_MS // 1000

    offset = 0
    packet_count = struct.unpack_from('<I', opus_data, offset)[0]
    offset += 4
    original_pcm_len = struct.unpack_from('<I', opus_data, offset)[0]
    offset += 4

    packets: List[bytes] = []
    for i in range(packet_count):
        if offset + 2 > len(opus_data):
            raise ValueError(f"Truncated Opus data: expected packet {i}/{packet_count} length at offset {offset}")
        pkt_len = struct.unpack_from('<H', opus_data, offset)[0]
        offset += 2
        if offset + pkt_len > len(opus_data):
            raise ValueError(
                f"Truncated Opus data: packet {i} needs {pkt_len} bytes at offset {offset}, only {len(opus_data) - offset} available"
            )
        packets.append(opus_data[offset : offset + pkt_len])
        offset += pkt_len

    opus = _get_opuslib()
    decoder = opus.Decoder(sample_rate, channels)

    pcm_parts: List[bytes] = []
    for pkt_data in packets:
        decoded = decoder.decode(pkt_data, frame_size)
        pcm_parts.append(decoded)

    result = b''.join(pcm_parts)
    # Trim to original PCM length to remove padding from partial final frame
    if original_pcm_len > 0 and original_pcm_len < len(result):
        result = result[:original_pcm_len]
    return result


def _get_extension_for_path(path: str) -> str:
    """Extract the private cloud sync extension from a GCS path."""
    if path.endswith('.batch.enc'):
        return 'batch.enc'
    elif path.endswith('.batch.bin'):
        return 'batch.bin'
    elif path.endswith('.opus.enc'):
        return 'opus.enc'
    elif path.endswith('.opus'):
        return 'opus'
    elif path.endswith('.enc'):
        return 'enc'
    elif path.endswith('.bin'):
        return 'bin'
    return 'bin'


def _strip_extension(filename: str) -> str:
    """Strip private cloud sync extension to get the timestamp string.

    Handles both single-chunk filenames (e.g. '1000.000.opus') and
    batch filenames (e.g. '1000.000-1010.000.batch.bin').
    """
    for ext in ('.batch.enc', '.batch.bin', '.opus.enc', '.opus', '.enc', '.bin'):
        if filename.endswith(ext):
            return filename[: -len(ext)]
    return filename.rsplit('.', 1)[0]


def upload_audio_chunk(
    chunk_data: bytes, uid: str, conversation_id: str, timestamp: float, data_protection_level: Optional[str] = None
) -> str:
    """
    Upload an audio chunk to Google Cloud Storage with optional encryption.

    Args:
        chunk_data: Raw audio bytes (PCM16)
        uid: User ID
        conversation_id: Conversation ID
        timestamp: Unix timestamp when chunk was recorded
        data_protection_level: Optional cached protection level. When provided,
            skips the per-chunk Firestore read. Falls back to DB read when None.

    Returns:
        GCS path of the uploaded chunk
    """
    protection_level = (
        data_protection_level if data_protection_level is not None else users_db.get_data_protection_level(uid)
    )

    # Format timestamp to 3 decimal places for cleaner filenames
    formatted_timestamp = f'{timestamp:.3f}'

    upload_data = encode_pcm_to_opus(chunk_data)

    with owner_storage_write_gate(uid):
        if protection_level == 'enhanced':
            encrypted_chunk = encryption.encrypt_audio_chunk(upload_data, uid)
            path = f'chunks/{uid}/{conversation_id}/{formatted_timestamp}.opus.enc'
            _object_store().put(
                private_cloud_sync_bucket, path, encrypted_chunk, content_type='application/octet-stream'
            )
        else:
            path = f'chunks/{uid}/{conversation_id}/{formatted_timestamp}.opus'
            _object_store().put(
                private_cloud_sync_bucket, path, upload_data, content_type='application/octet-stream'
            )

    del upload_data
    return path


def upload_audio_chunks_batch(
    chunks: List[Dict[str, Any]],
    uid: str,
    conversation_id: str,
    data_protection_level: Optional[str] = None,
) -> List[str]:
    """
    Upload multiple audio chunks to GCS in a single streaming write.

    Concatenates all chunk data into one GCS object (1 write op instead of N).

    Args:
        chunks: List of dicts with 'data' (bytes) and 'timestamp' (float).
        uid: User ID.
        conversation_id: Conversation ID.
        data_protection_level: Optional cached protection level. When provided,
            skips the Firestore read. Falls back to DB read when None.

    Returns:
        List of GCS paths for the uploaded batch.
    """
    if not chunks:
        return []

    # Sort by timestamp for consistent ordering
    sorted_chunks = sorted(chunks, key=lambda c: c['timestamp'])

    # Resolve protection level once for the entire batch
    protection_level = (
        data_protection_level if data_protection_level is not None else users_db.get_data_protection_level(uid)
    )

    # Build batch filename from first and last timestamps
    first_ts = f'{sorted_chunks[0]["timestamp"]:.3f}'
    last_ts = f'{sorted_chunks[-1]["timestamp"]:.3f}'
    batch_name = f'{first_ts}-{last_ts}' if len(sorted_chunks) > 1 else first_ts

    with owner_storage_write_gate(uid):
        if protection_level == 'enhanced':
            # Encrypt each chunk individually (length-prefixed), stream to the object store
            path = f'chunks/{uid}/{conversation_id}/{batch_name}.batch.enc'
            with _object_store().open_write(
                private_cloud_sync_bucket, path, content_type='application/octet-stream'
            ) as f:
                for chunk in sorted_chunks:
                    encrypted_chunk = encryption.encrypt_audio_chunk(chunk['data'], uid)
                    f.write(encrypted_chunk)
                    del encrypted_chunk
        else:
            # Standard — stream raw PCM data to the object store
            path = f'chunks/{uid}/{conversation_id}/{batch_name}.batch.bin'
            with _object_store().open_write(
                private_cloud_sync_bucket, path, content_type='application/octet-stream'
            ) as f:
                for chunk in sorted_chunks:
                    f.write(chunk['data'])

    return [path]


def delete_audio_chunks(uid: str, conversation_id: str, timestamps: List[float]) -> None:
    """Delete audio chunks after they've been merged.

    Handles both single-chunk blobs (per-timestamp lookup) and batch blobs
    (listed and matched by start timestamp).
    """
    store = _object_store()
    deleted_batch_paths: set[str] = set()

    for timestamp in timestamps:
        # Format timestamp to match upload format (3 decimal places)
        formatted_timestamp = f'{timestamp:.3f}'

        # Try single-chunk extensions first
        for extension in PRIVATE_CLOUD_EXTENSIONS:
            if extension in ('.batch.enc', '.batch.bin'):
                continue  # batch blobs handled separately below
            chunk_path = f'chunks/{uid}/{conversation_id}/{formatted_timestamp}{extension}'
            if store.exists(private_cloud_sync_bucket, chunk_path):
                store.delete(private_cloud_sync_bucket, chunk_path)

        # Try batch blobs: exact single-timestamp batch (e.g. "1000.000.batch.bin")
        for batch_ext in ('.batch.enc', '.batch.bin'):
            batch_path = f'chunks/{uid}/{conversation_id}/{formatted_timestamp}{batch_ext}'
            if batch_path not in deleted_batch_paths:
                if store.exists(private_cloud_sync_bucket, batch_path):
                    store.delete(private_cloud_sync_bucket, batch_path)
                    deleted_batch_paths.add(batch_path)

    # Scan for range-named batch blobs whose start timestamp matches any requested timestamp
    ts_set = {f'{ts:.3f}' for ts in timestamps}
    prefix = f'chunks/{uid}/{conversation_id}/'
    for obj in store.list(private_cloud_sync_bucket, prefix):
        if obj.key in deleted_batch_paths:
            continue
        filename = obj.key.split('/')[-1]
        if '.batch.' not in filename:
            continue
        timestamp_str = _strip_extension(filename)
        if '-' in timestamp_str:
            start_ts = timestamp_str.split('-', 1)[0]
            if start_ts in ts_set:
                store.delete(private_cloud_sync_bucket, obj.key)
                deleted_batch_paths.add(obj.key)


def list_audio_chunks(uid: str, conversation_id: str) -> List[Dict[str, Any]]:
    """
    List all audio chunks for a conversation.

    Returns:
        List of dicts with chunk info: {'timestamp': float, 'path': str, 'size': int}
    """
    prefix = f'chunks/{uid}/{conversation_id}/'
    objects = _object_store().list(private_cloud_sync_bucket, prefix)

    chunks: List[Dict[str, Any]] = []
    for obj in objects:
        # Extract timestamp from filename
        # Supports single-chunk: '1234567890.123.opus', '1234567890.123.opus.enc', etc.
        # Supports batch: '1234567890.123-1234567900.123.batch.bin', '1234567890.123.batch.enc'
        filename = obj.key.split('/')[-1]
        has_valid_ext = any(filename.endswith(ext) for ext in PRIVATE_CLOUD_EXTENSIONS)
        if has_valid_ext:
            try:
                timestamp_str = _strip_extension(filename)
                is_batch = '.batch.' in filename

                if is_batch and '-' in timestamp_str:
                    # Batch blob with timestamp range: "first_ts-last_ts"
                    first_ts_str, _ = timestamp_str.split('-', 1)
                    timestamp = float(first_ts_str)
                else:
                    timestamp = float(timestamp_str)

                chunks.append(
                    {
                        'timestamp': timestamp,
                        'path': obj.key,
                        'size': obj.size,
                        'is_batch': is_batch,
                    }
                )
            except ValueError:
                continue

    return sorted(chunks, key=lambda x: x['timestamp'])


def delete_conversation_audio_files(uid: str, conversation_id: str) -> None:
    """Delete all audio files (chunks and merged) for a conversation."""
    store = _object_store()

    # Delete chunks
    chunks_prefix = f'chunks/{uid}/{conversation_id}/'
    for obj in store.list(private_cloud_sync_bucket, chunks_prefix):
        store.delete(private_cloud_sync_bucket, obj.key)

    # Delete merged files
    audio_prefix = f'audio/{uid}/{conversation_id}/'
    for obj in store.list(private_cloud_sync_bucket, audio_prefix):
        store.delete(private_cloud_sync_bucket, obj.key)


# PCM16 mono: one sample is 2 bytes. A chunk whose byte count is not a multiple
# of this is truncated mid-sample.
_PCM16_FRAME_BYTES = 2


def _align_pcm16_frames(pcm_data: bytes, source: str) -> bytes:
    """Drop a trailing partial PCM16 sample so decoded chunks stay frame-aligned.

    A chunk stored truncated mid-sample (interrupted upload) makes every later
    chunk in the merge byte-misaligned and leaves the merged buffer an odd byte
    count, which pydub rejects with a deterministic ValueError. The audio-merge
    Cloud Task retried that unretryable error to exhaustion and then marked
    playback permanently unavailable, losing the artifact for the conversation.
    Trimming the partial sample costs 1/32000s and keeps the merge buildable.
    """
    remainder = len(pcm_data) % _PCM16_FRAME_BYTES
    if not remainder:
        return pcm_data
    record_fallback(
        component='audio_merge',
        from_mode='pcm16_frames',
        to_mode='pcm16_frames_truncated',
        reason='malformed_doc',
        outcome='recovered',
        log=logger,
    )
    logger.warning(f'audio chunk not PCM16 frame-aligned, trimming {remainder} trailing byte(s): {source}')
    return pcm_data[:-remainder]


def download_audio_chunks_and_merge(
    uid: str,
    conversation_id: str,
    timestamps: List[float],
    fill_gaps: bool = True,
    sample_rate: int = 16000,
) -> bytes:
    """
    Download and merge audio chunks on-demand, handling mixed encryption states.
    Downloads chunks in parallel.
    Normalizes all chunks to unencrypted PCM format for consistent merging.
    Supports both single-chunk blobs and batch blobs (from upload_audio_chunks_batch).

    Args:
        uid: User ID
        conversation_id: Conversation ID
        timestamps: List of chunk timestamps to merge
        fill_gaps: If True, insert silence (zero bytes) between chunks to maintain
                   continuous time-aligned audio. Default True.
        sample_rate: Audio sample rate in Hz (default 16000)

    Returns:
        Merged audio bytes (PCM16)
    """

    store = _object_store()

    # Resolve actual GCS paths — needed to find batch blobs whose filenames
    # contain timestamp ranges instead of single timestamps
    actual_chunks = list_audio_chunks(uid, conversation_id)
    ts_set = {round(ts, 3) for ts in timestamps}

    # Build batch blob map: for batch blobs, track which timestamps they cover
    batch_paths: Dict[str, Dict[str, Any]] = {}  # path -> chunk_info (deduplicate downloads)
    ts_to_batch_path: Dict[float, str] = {}  # timestamp -> batch_path (for timestamps inside batch range)
    single_chunk_timestamps: List[float] = []  # timestamps that have individual blobs

    for chunk in actual_chunks:
        if chunk.get('is_batch'):
            path = chunk['path']
            batch_paths[path] = chunk

            # Parse batch range to determine covered timestamps
            filename = path.split('/')[-1]
            ts_str = _strip_extension(filename)
            if '-' in ts_str:
                start_str, end_str = ts_str.split('-', 1)
                batch_start = float(start_str)
                batch_end = float(end_str)
            else:
                batch_start = batch_end = float(ts_str)

            # Map requested timestamps that fall within this batch's range
            for ts in timestamps:
                if batch_start <= round(ts, 3) <= batch_end:
                    ts_to_batch_path[round(ts, 3)] = path
        elif round(chunk['timestamp'], 3) in ts_set:
            single_chunk_timestamps.append(chunk['timestamp'])

    def _download_and_decode_blob(path: str) -> bytes | None:
        """Download a blob and decode/decrypt based on extension."""
        ext = _get_extension_for_path(path)
        encrypted = ext in ('opus.enc', 'enc', 'batch.enc')
        is_opus = ext in ('opus.enc', 'opus')

        try:
            chunk_data = store.get_bytes(private_cloud_sync_bucket, path)
        except ObjectNotFound:
            return None

        try:
            if encrypted:
                raw_data = encryption.decrypt_audio_file(chunk_data, uid)
            else:
                raw_data = chunk_data

            if is_opus:
                pcm_data = decode_opus_to_pcm(raw_data, sample_rate=sample_rate)
                del raw_data
            else:
                pcm_data = raw_data

            return _align_pcm16_frames(pcm_data, path)
        except Exception as e:
            logger.warning(f"Failed to decode/decrypt {path}: {e}")
            return None

    def download_single_chunk(timestamp: float) -> tuple[float, bytes | None]:
        """Download a single-chunk blob by trying extensions in priority order."""
        formatted_timestamp = f'{timestamp:.3f}'

        extensions_to_try = [
            ('opus.enc', True, True),  # (ext, encrypted, opus)
            ('enc', True, False),
            ('opus', False, True),
            ('bin', False, False),
        ]

        for ext, encrypted, opus in extensions_to_try:
            chunk_path = f'chunks/{uid}/{conversation_id}/{formatted_timestamp}.{ext}'
            try:
                chunk_data = store.get_bytes(private_cloud_sync_bucket, chunk_path)
            except ObjectNotFound:
                continue

            try:
                if encrypted:
                    raw_data = encryption.decrypt_audio_file(chunk_data, uid)
                else:
                    raw_data = chunk_data

                if opus:
                    pcm_data = decode_opus_to_pcm(raw_data, sample_rate=sample_rate)
                    del raw_data
                else:
                    pcm_data = raw_data

                return (timestamp, _align_pcm16_frames(pcm_data, chunk_path))
            except Exception as e:
                logger.warning(
                    f"Failed to decode/decrypt {ext} chunk at {formatted_timestamp}: {e}, trying next format"
                )
                continue

        logger.warning(f"Warning: Chunk not found for timestamp {formatted_timestamp}")
        return (timestamp, None)

    # Download data with bounded concurrency (sliding window + global semaphore, #7387)
    chunk_results: Dict[float, bytes] = {}

    individual_timestamps = [ts for ts in timestamps if round(ts, 3) not in ts_to_batch_path]
    unique_batch_paths = list(set(ts_to_batch_path.values()))

    # Build unified job list: ('individual', ts) or ('batch', path)
    jobs = [('individual', ts) for ts in individual_timestamps] + [('batch', p) for p in unique_batch_paths]

    def _submit_job(job: Tuple[str, Any]) -> Tuple[Any, str, Any]:
        kind, key = job
        _STORAGE_CHUNK_SEM.acquire()
        try:
            if kind == 'individual':
                f = storage_executor.submit(download_single_chunk, key)
            else:
                f = storage_executor.submit(_download_and_decode_blob, key)
            f.add_done_callback(lambda _: _STORAGE_CHUNK_SEM.release())
            return (f, kind, key)
        except Exception:
            _STORAGE_CHUNK_SEM.release()
            raise

    # Sliding window: at most _CHUNK_WINDOW_SIZE in-flight per call
    pending: Dict[Any, Tuple[Any, str, Any]] = {}
    job_iter = iter(jobs)
    for job in job_iter:
        finfo = _submit_job(job)
        pending[finfo[0]] = finfo
        if len(pending) >= _CHUNK_WINDOW_SIZE:
            break

    while pending:
        done, _ = wait(pending.keys(), return_when=FIRST_COMPLETED)
        for future in done:
            _, kind, key = pending.pop(future)
            try:
                if kind == 'individual':
                    timestamp, pcm_data = future.result()
                    if pcm_data is not None:
                        chunk_results[timestamp] = pcm_data
                else:
                    pcm_data = future.result()
                    if pcm_data is not None:
                        batch_info = batch_paths[key]
                        chunk_results[batch_info['timestamp']] = pcm_data
            except Exception as e:
                logger.warning(f"Chunk download failed ({kind}={key}): {e}")

        for job in job_iter:
            finfo = _submit_job(job)
            pending[finfo[0]] = finfo
            if len(pending) >= _CHUNK_WINDOW_SIZE:
                break

    # Merge chunks
    merged_data = bytearray()

    if fill_gaps and timestamps and chunk_results:
        # Sort timestamps to ensure proper ordering
        sorted_timestamps = sorted(timestamps)
        first_timestamp = sorted_timestamps[0]
        current_time = first_timestamp  # Track current audio end time in seconds

        for timestamp in sorted_timestamps:
            if timestamp not in chunk_results:
                continue

            pcm_data = chunk_results[timestamp]

            # Calculate gap from current position to this chunk's start
            gap_seconds = timestamp - current_time
            if gap_seconds > 0:
                # Insert silence: 16-bit mono = 2 bytes per sample
                gap_samples = int(gap_seconds * sample_rate)
                silence_bytes = bytes(gap_samples * 2)  # Zero bytes for silence
                merged_data.extend(silence_bytes)
                logger.debug(f"Filled {gap_seconds:.3f}s gap ({len(silence_bytes)} bytes) before chunk at {timestamp}")

            merged_data.extend(pcm_data)

            # Update current time based on chunk duration
            # PCM16 mono: 2 bytes per sample
            chunk_duration = len(pcm_data) / (sample_rate * 2)
            current_time = timestamp + chunk_duration
    else:
        # Original behavior - just concatenate without gap filling
        for timestamp in timestamps:
            if timestamp in chunk_results:
                merged_data.extend(chunk_results[timestamp])

    # Free memory from chunk results immediately after merging
    chunk_results.clear()

    if not merged_data:
        raise FileNotFoundError(f"No chunks found for conversation {conversation_id}")

    return bytes(merged_data)


def get_cached_merged_audio_path(uid: str, conversation_id: str, audio_file_id: str) -> str:
    """Get the GCS path for a cached merged audio file."""
    return f'merged/{uid}/{conversation_id}/{audio_file_id}.wav'


def get_or_create_merged_audio(
    uid: str,
    conversation_id: str,
    audio_file_id: str,
    timestamps: List[float],
    pcm_to_wav_func: Callable[[bytes], bytes],
    fill_gaps: bool = True,
    sample_rate: int = 16000,
    caller: str = 'unknown',
) -> tuple[bytes, bool]:
    """
    Get merged audio from cache or create it.
    Cached files are stored in GCS with 1-day TTL (via lifecycle policy).

    Returns:
        Tuple of (audio_data_bytes, was_cached)
    """
    cache_path = get_cached_merged_audio_path(uid, conversation_id, audio_file_id)

    n_chunks = len(timestamps)
    log_ctx = f'uid={uid} convo={conversation_id} file={audio_file_id} caller={caller} chunks={n_chunks}'

    cache_meta = _object_store().get_metadata(private_cloud_sync_bucket, cache_path)
    if cache_meta is not None:
        expires_at_str = cache_meta.get('expires_at')

        if expires_at_str:
            try:
                expires_at = datetime.datetime.fromisoformat(expires_at_str)
                if datetime.datetime.now(datetime.timezone.utc) < expires_at:
                    logger.debug(f'audio_merge cache_hit {log_ctx}')
                    return _object_store().get_bytes(private_cloud_sync_bucket, cache_path), True
                else:
                    logger.debug(f'audio_merge cache_expired {log_ctx}')
            except (ValueError, TypeError):
                pass

    now = time.monotonic()
    with _merge_tracker_lock:
        if cache_path in _active_merges:
            elapsed = now - _active_merges[cache_path]
            logger.warning(f'audio_merge duplicate_concurrent {log_ctx} running_for={elapsed:.1f}s')
        if cache_path in _recent_merges:
            prev_time, prev_caller = _recent_merges[cache_path]
            age = now - prev_time
            if age < _RECENT_MERGE_WINDOW:
                logger.warning(f'audio_merge duplicate_recent {log_ctx} prev_caller={prev_caller} age={age:.0f}s')
        _active_merges[cache_path] = now
        if len(_active_merges) > _MERGE_TRACKER_MAX:
            _active_merges.clear()

    logger.info(f'audio_merge cache_miss {log_ctx}')

    merge_start = time.monotonic()
    try:
        pcm_data = download_audio_chunks_and_merge(
            uid, conversation_id, timestamps, fill_gaps=fill_gaps, sample_rate=sample_rate
        )
    finally:
        merge_duration = time.monotonic() - merge_start
        with _merge_tracker_lock:
            _active_merges.pop(cache_path, None)
            _recent_merges[cache_path] = (time.monotonic(), caller)
            if len(_recent_merges) > _MERGE_TRACKER_MAX:
                cutoff = time.monotonic() - _RECENT_MERGE_WINDOW
                stale = [k for k, (t, _) in _recent_merges.items() if t < cutoff]
                for k in stale:
                    del _recent_merges[k]

    wav_data = pcm_to_wav_func(pcm_data)
    del pcm_data

    wav_kb = len(wav_data) // 1024
    logger.info(f'audio_merge complete {log_ctx} duration={merge_duration:.1f}s size={wav_kb}KB')

    def _upload_to_cache():
        try:
            expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=3)
            with owner_storage_write_gate(uid):
                _object_store().put(
                    private_cloud_sync_bucket,
                    cache_path,
                    wav_data,
                    content_type='audio/wav',
                    metadata={'expires_at': expires_at.isoformat(), 'audio_file_id': audio_file_id},
                )
            logger.info(f'audio_merge cached {log_ctx}')
        except Exception as e:
            logger.error(f'audio_merge cache_upload_failed {log_ctx}: {e}')

    storage_executor.submit(_upload_to_cache)

    return wav_data, False


def get_merged_audio_signed_url(uid: str, conversation_id: str, audio_file_id: str) -> str | None:
    """
    Get a signed URL for cached merged audio if it exists and is valid.

    Returns:
        Signed URL valid for 1 hour, or None if cache doesn't exist
    """
    cache_path = get_cached_merged_audio_path(uid, conversation_id, audio_file_id)

    metadata = _object_store().get_metadata(private_cloud_sync_bucket, cache_path)
    if metadata is None:
        return None

    # Check expiry
    expires_at_str = metadata.get('expires_at')

    if expires_at_str:
        try:
            expires_at = datetime.datetime.fromisoformat(expires_at_str)
            if datetime.datetime.now(datetime.timezone.utc) >= expires_at:
                return None  # Expired
        except (ValueError, TypeError):
            pass

    # Generate signed URL valid for 1 hour
    return _signed_url(private_cloud_sync_bucket, cache_path, 60)


def delete_cached_merged_audio(uid: str, conversation_id: str) -> None:
    """Delete all cached merged audio for a conversation."""
    prefix = f'merged/{uid}/{conversation_id}/'
    for obj in _object_store().list(private_cloud_sync_bucket, prefix):
        _object_store().delete(private_cloud_sync_bucket, obj.key)


def _pcm_to_wav(pcm_data: bytes, sample_rate: int = 16000, channels: int = 1) -> bytes:
    """Convert PCM16 data to WAV format."""
    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, 'wb') as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(2)  # 16-bit audio
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_data)
    return wav_buffer.getvalue()


# ----------------------------------------------------------------------------
# Playback artifacts: merged MP3 under playback/, expiry via the bucket's
# 30-day lifecycle rule on the prefix (existence == validity, no metadata).
# Built off-request by the audio-merge Cloud Tasks handler (routers/sync.py).
# ----------------------------------------------------------------------------

PLAYBACK_ARTIFACT_PREFIX = 'playback'


def _playback_artifact_path(uid: str, conversation_id: str, audio_file_id: str) -> str:
    return f'{PLAYBACK_ARTIFACT_PREFIX}/{uid}/{conversation_id}/{audio_file_id}.mp3'


def get_playback_artifact_signed_url(uid: str, conversation_id: str, audio_file_id: str):
    path = _playback_artifact_path(uid, conversation_id, audio_file_id)
    if not _object_store().exists(private_cloud_sync_bucket, path):
        return None
    return _signed_url(private_cloud_sync_bucket, path, 60)


def download_playback_artifact(uid: str, conversation_id: str, audio_file_id: str):
    path = _playback_artifact_path(uid, conversation_id, audio_file_id)
    try:
        return _object_store().get_bytes(private_cloud_sync_bucket, path)
    except ObjectNotFound:
        return None


def upload_playback_artifact(uid: str, conversation_id: str, audio_file_id: str, mp3_data: bytes) -> None:
    path = _playback_artifact_path(uid, conversation_id, audio_file_id)
    with owner_storage_write_gate(uid):
        _object_store().put(private_cloud_sync_bucket, path, mp3_data, content_type='audio/mpeg')


def _playback_unavailable_path(uid: str, conversation_id: str, audio_file_id: str) -> str:
    return f'{PLAYBACK_ARTIFACT_PREFIX}/{uid}/{conversation_id}/{audio_file_id}.unavailable'


def mark_playback_unavailable(uid: str, conversation_id: str, audio_file_id: str, reason: str) -> None:
    """Mark an audio file as unbuildable (e.g. source chunks gone).

    Without this, /urls would report the file as pending forever and clients
    would poll to exhaustion. The marker lives under playback/ so the 30-day
    lifecycle rule grants even these a retry eventually.
    """
    path = _playback_unavailable_path(uid, conversation_id, audio_file_id)
    with owner_storage_write_gate(uid):
        _object_store().put(private_cloud_sync_bucket, path, reason.encode('utf-8'), content_type='text/plain')


def is_playback_unavailable(uid: str, conversation_id: str, audio_file_id: str) -> bool:
    return _object_store().exists(
        private_cloud_sync_bucket, _playback_unavailable_path(uid, conversation_id, audio_file_id)
    )


def enqueue_conversation_audio_merge(
    uid: str, conversation_id: str, audio_files: List[Dict[str, Any]], caller: str
) -> None:
    """Enqueue one audio-merge Cloud Task per audio file (named-task deduped).

    Enqueue failures are swallowed: the file stays pending and the next /urls
    poll re-enqueues it.
    """
    for af in audio_files:
        audio_file_id = af.get('id')
        timestamps = af.get('chunk_timestamps')
        if not audio_file_id or not timestamps:
            continue
        try:
            enqueue_audio_merge_job(
                {
                    'schema_version': 1,
                    'uid': uid,
                    'conversation_id': conversation_id,
                    'audio_file_id': audio_file_id,
                    'timestamps': timestamps,
                    'caller': caller,
                }
            )
        except Exception as e:
            logger.error(f'audio_merge: enqueue failed conv={conversation_id} file={audio_file_id}: {e}')


# ----------------------------------------------------------------------------
# Conversation-level playback artifact: ONE dense MP3 per conversation
# (playback/{uid}/{conversation_id}/conversation.mp3) with only captured audio;
# inter-part gaps collapsed. The spans manifest + audio_files fingerprint are
# stamped on the conversation doc (conversation_audio). Same 30-day lifecycle.
# 'conversation' cannot collide with per-part names: audio_file ids are UUIDv4.
# ----------------------------------------------------------------------------

CONVERSATION_ARTIFACT_NAME = 'conversation'


def compute_audio_files_fingerprint(audio_files: List[Dict[str, Any]]) -> str:
    """Content fingerprint of a conversation's audio_files (id + chunk count +
    last chunk timestamp per part, order-insensitive). Stamped on the doc at
    build time; a mismatch with the current audio_files means the artifact is
    stale. Also embedded in the Cloud Tasks task name so rebuilds after late
    chunks aren't swallowed by named-task dedup."""
    parts = sorted(
        [
            [af['id'], len(af['chunk_timestamps']), round(sorted(af['chunk_timestamps'])[-1], 3)]
            for af in audio_files
            if af.get('id') and af.get('chunk_timestamps')
        ],
        key=lambda p: p[0],
    )
    return hashlib.sha1(json.dumps(parts).encode()).hexdigest()[:12]


def maybe_invalidate_conversation_playback(
    uid: str,
    conversation_id: str,
    conversation: Optional[Dict[str, Any]],
    audio_files: List[Dict[str, Any]],
    caller: str,
) -> None:
    """Re-enqueue the conversation artifact build if a stamped artifact went
    stale (audio_files changed). No stamp -> no-op, so live-conversation batch
    flushes never churn rebuilds; the first build happens at completion."""
    stamp = (conversation or {}).get('conversation_audio') or {}
    stamped = stamp.get('audio_files_fingerprint')
    if not stamped:
        return
    fingerprint = compute_audio_files_fingerprint(audio_files)
    if fingerprint != stamped:
        enqueue_conversation_artifact_build(uid, conversation_id, fingerprint, caller)


def _conversation_playback_path(uid: str, conversation_id: str) -> str:
    return f'{PLAYBACK_ARTIFACT_PREFIX}/{uid}/{conversation_id}/{CONVERSATION_ARTIFACT_NAME}.mp3'


def get_conversation_playback_signed_url(uid: str, conversation_id: str):
    path = _conversation_playback_path(uid, conversation_id)
    if not _object_store().exists(private_cloud_sync_bucket, path):
        return None
    return _signed_url(private_cloud_sync_bucket, path, 60)


def upload_conversation_playback_artifact(uid: str, conversation_id: str, mp3_data: bytes) -> None:
    path = _conversation_playback_path(uid, conversation_id)
    with owner_storage_write_gate(uid):
        _object_store().put(private_cloud_sync_bucket, path, mp3_data, content_type='audio/mpeg')


def _conversation_playback_unavailable_path(uid: str, conversation_id: str) -> str:
    return f'{PLAYBACK_ARTIFACT_PREFIX}/{uid}/{conversation_id}/{CONVERSATION_ARTIFACT_NAME}.unavailable'


def mark_conversation_playback_unavailable(uid: str, conversation_id: str, fingerprint: str, reason: str) -> None:
    """Marker content carries the fingerprint it was written for: a marker for a
    stale fingerprint is ignored on read (late chunks may fix a chunks_missing verdict)."""
    path = _conversation_playback_unavailable_path(uid, conversation_id)
    with owner_storage_write_gate(uid):
        _object_store().put(
            private_cloud_sync_bucket, path, f'{fingerprint}:{reason}'.encode('utf-8'), content_type='text/plain'
        )


def get_conversation_playback_unavailable_fingerprint(uid: str, conversation_id: str) -> Optional[str]:
    path = _conversation_playback_unavailable_path(uid, conversation_id)
    try:
        content = _object_store().get_bytes(private_cloud_sync_bucket, path).decode()
    except ObjectNotFound:
        return None
    return content.split(':', 1)[0] if content else None


def enqueue_conversation_artifact_build(uid: str, conversation_id: str, fingerprint: str, caller: str) -> None:
    """Enqueue the conversation-level artifact build (named-task deduped on the
    fingerprint). Failures are swallowed: the next /urls poll re-enqueues."""
    try:
        enqueue_audio_merge_job(
            {
                'schema_version': 2,
                'uid': uid,
                'conversation_id': conversation_id,
                'fingerprint': fingerprint,
                'caller': caller,
            }
        )
    except Exception as e:
        logger.error(f'audio_merge: conversation enqueue failed conv={conversation_id}: {e}')


def download_legacy_merged_wav(uid: str, conversation_id: str, audio_file_id: str):
    """Download a legacy merged WAV cache blob directly — never merges.

    Used by the artifact-backed download path so a cached blob missing
    expires_at metadata can't fall through get_or_create_merged_audio into
    the inline merge pipeline (Greptile P1 on #7872).
    """
    try:
        return _object_store().get_bytes(
            private_cloud_sync_bucket, get_cached_merged_audio_path(uid, conversation_id, audio_file_id)
        )
    except ObjectNotFound:
        return None


def precache_conversation_audio(
    uid: str, conversation_id: str, audio_files: List[Dict[str, Any]], fill_gaps: bool = True, sample_rate: int = 16000
) -> None:
    """
    Pre-cache all audio files for a conversation in a background thread.

    Args:
        uid: User ID
        conversation_id: Conversation ID
        audio_files: List of audio file dicts with 'id' and 'chunk_timestamps'
        fill_gaps: If True, insert silence between chunks to maintain time alignment. Default True.
        sample_rate: Audio sample rate in Hz (default 16000)
    """
    if not audio_files:
        return

    if is_audio_merge_dispatch_enabled():
        # Eager build at conversation completion, off-process via Cloud Tasks
        enqueue_conversation_audio_merge(uid, conversation_id, audio_files, caller='process_conversation')
        return

    def _precache_all():
        def _cache_single(af: Dict[str, Any]) -> None:
            try:
                audio_file_id = af.get('id')
                timestamps = af.get('chunk_timestamps')
                if not audio_file_id or not timestamps:
                    return
                get_or_create_merged_audio(
                    uid=uid,
                    conversation_id=conversation_id,
                    audio_file_id=audio_file_id,
                    timestamps=timestamps,
                    pcm_to_wav_func=_pcm_to_wav,
                    fill_gaps=fill_gaps,
                    sample_rate=sample_rate,
                    caller='process_conversation',
                )
            except Exception as e:
                logger.error(f"[PRECACHE] Error caching audio file {af.get('id')}: {e}")

        futures: List[Any] = []
        for af in audio_files:
            _PRECACHE_FILE_SEM.acquire()
            try:
                f = storage_executor.submit(_cache_single, af)
                f.add_done_callback(lambda _: _PRECACHE_FILE_SEM.release())
                futures.append(f)
            except Exception:
                _PRECACHE_FILE_SEM.release()
                raise
        for future in as_completed(futures):
            try:
                future.result()
            except Exception:
                pass

    postprocess_executor.submit(_precache_all)


# **********************************
# ************* UTILS **************
# **********************************


def download_blob_bytes(bucket_name: str, path: str) -> bytes:
    """
    Download object content as bytes through the object-store port.

    Args:
        bucket_name: Name of the (logical) bucket
        path: Path to the object within the bucket

    Returns:
        Object content as bytes

    Raises:
        ObjectNotFound: If the object doesn't exist
    """
    return _object_store().get_bytes(bucket_name, path)


def delete_blob(bucket_name: str, path: str) -> bool:
    """
    Delete an object through the object-store port.

    Args:
        bucket_name: Name of the (logical) bucket
        path: Path to the object within the bucket

    Returns:
        True if deleted, False if not found
    """
    return _object_store().delete(bucket_name, path)


def download_speech_profile_bytes(path: str) -> bytes:
    """
    Download speech profile/sample audio through the object-store port.

    Args:
        path: Object path to the sample (e.g., '{uid}/people_profiles/{person_id}/{filename}.wav')

    Returns:
        Audio bytes (WAV format)

    Raises:
        ObjectNotFound: If the sample doesn't exist (or storage is unconfigured)
    """
    if not speech_profiles_bucket:
        raise ObjectNotFound(speech_profiles_bucket or '', path)
    return download_blob_bytes(speech_profiles_bucket, path)


def delete_speech_profile_blob(path: str) -> bool:
    """
    Delete speech profile/sample from GCS.

    Args:
        path: GCS path to the sample

    Returns:
        True if deleted, False if not found
    """
    if not speech_profiles_bucket:
        return False
    return delete_blob(speech_profiles_bucket, path)


# How long a server-minted URL for USER AUDIO stays valid (ADR-0087). Long enough for the consumer that
# actually fetches it — the STT provider pulling the post-processing file, or the app right after an
# upload — and short enough that a leaked URL is not a permanent handle on somebody's recording. The
# syncing helper below uses 15 minutes because its file is consumed within seconds.
USER_AUDIO_URL_MINUTES = 60


def _signed_url(bucket: str, key: str, minutes: int) -> str:
    """Server-minted GET download URL, Redis-cached by object key (ADR-0032). Replaces the previous
    blob-based helper; the port's presign_get maps to GCS V4 / S3 SigV4."""
    if cached := get_cached_signed_url(key):
        return cached

    signed_url = _object_store().presign_get(bucket, key, expires_seconds=minutes * 60)
    cache_signed_url(key, signed_url, minutes * 60)
    return signed_url


def upload_app_logo(file_path: str, app_id: str):
    path = f'{app_id}.png'
    _object_store().put_from_file(
        _required_bucket(omi_apps_bucket, 'BUCKET_PLUGINS_LOGOS'),
        path,
        file_path,
        content_type='image/png',
        cache_control='public, no-cache',
    )
    return _object_store().public_url(_required_bucket(omi_apps_bucket, 'BUCKET_PLUGINS_LOGOS'), path)


def delete_app_logo(img_url: str):
    prefix = _object_store().public_url(_required_bucket(omi_apps_bucket, 'BUCKET_PLUGINS_LOGOS'), '')
    # Require the URL to START WITH the app-logo prefix, not merely contain it: a foreign-bucket URL
    # embedding the prefix later could otherwise delete an unrelated object (this is a deletion path).
    if not img_url.startswith(prefix):
        logger.warning(f'delete_app_logo: url not in {omi_apps_bucket}, skipping')
        return
    path = img_url[len(prefix) :]
    logger.info(f'delete_app_logo {path}')
    _object_store().delete(_required_bucket(omi_apps_bucket, 'BUCKET_PLUGINS_LOGOS'), path)


def upload_app_thumbnail(file_path: str, thumbnail_id: str) -> str:
    path = f'{thumbnail_id}.jpg'
    _object_store().put_from_file(
        _required_bucket(app_thumbnails_bucket, 'BUCKET_APP_THUMBNAILS'),
        path,
        file_path,
        content_type='image/jpeg',
        cache_control='public, no-cache',
    )
    return _object_store().public_url(_required_bucket(app_thumbnails_bucket, 'BUCKET_APP_THUMBNAILS'), path)


def get_app_thumbnail_url(thumbnail_id: str) -> str:
    path = f'{thumbnail_id}.jpg'
    return _object_store().public_url(_required_bucket(app_thumbnails_bucket, 'BUCKET_APP_THUMBNAILS'), path)


# **********************************
# ************* CHAT FILES **************
# **********************************
def upload_multi_chat_files(files_name: List[str], uid: str) -> Dict[str, str]:
    """Upload chat image thumbnails and return {file name: object KEY}.

    Keys, not URLs (ADR-0087). The value goes into the chat message document and is re-served on every
    later read, so a signed URL stored here would become a deferred 403 the day it expired — which is why
    the other five audio surfaces could switch outright and this one could not. Storing the key and
    minting the URL at read time is the shape the codebase already uses for APP thumbnails
    (``models/app.py`` keeps ids, ``routers/conversations.py`` mints ``thumbnail_urls``).

    ``public=True`` is kept on the upload: it is inert on RustFS (the ACL is not honoured) and correct on
    MinIO/GCS, and removing it would change the object's ACL on the backends that DO honour it — a
    separate decision from where the URL comes from.
    """
    keys: Dict[str, str] = {}
    with owner_storage_write_gate(uid):
        for name in files_name:
            try:
                path = f'{uid}/{name}'
                _object_store().put_from_file(
                    _required_bucket(chat_files_bucket, 'BUCKET_CHAT_FILES'),
                    path,
                    f'./{name}',
                    cache_control='public, no-cache',
                    public=True,
                )
                keys[name] = path
            except Exception as e:
                logger.error("Failed to upload {} due to exception: {}".format(name, e))
    return keys


def resolve_chat_thumbnail(stored: str) -> str:
    """Turn what is stored in ``FileChat.thumbnail`` into a URL the client can fetch.

    Two shapes reach this, and both must work:

      * an object KEY (``{uid}/{name}``) — everything written since ADR-0087 — which is signed here;
      * a full URL — every message written BEFORE it. Passed through untouched. Without this branch the
        change would turn every image already in a user's chat history into a broken link, which is the
        legacy-principal rule in AGENTS.md and the whole reason the field is not simply re-typed.

    Empty stays empty: a non-image file has no thumbnail and must not acquire a URL to nothing.
    """
    if not stored or '://' in stored:
        return stored
    return _signed_url(_required_bucket(chat_files_bucket, 'BUCKET_CHAT_FILES'), stored, USER_AUDIO_URL_MINUTES)


def resolve_chat_file_thumbnails(files: List[Any]) -> List[Any]:
    """Resolve ``thumbnail`` on each stored chat-file record, in place, and return the list.

    One place, called where the records leave the database, so every consumer that builds a ``FileChat``
    downstream gets a fetchable URL without knowing any of this.

    ``List[Any]`` deliberately, not ``List[Dict[str, Any]]``: these records come straight out of a
    stored document, so their shape is whatever was written, not what the annotation wishes. The
    stricter type made the ``isinstance`` below provably dead — and dropping a guard because a type
    hint promised something the database never did is how one malformed row turns a chat read into a 500.
    """
    for record in files:
        if isinstance(record, dict) and record.get('thumbnail'):
            record['thumbnail'] = resolve_chat_thumbnail(record['thumbnail'])
    return files


# **************************************************
# ************* DESKTOP UPDATES ********************
# **************************************************


def get_desktop_update_signed_url(blob_path: str, expiration_hours: int = 1) -> str:
    """
    Generate a signed URL for a desktop update file (ZIP).

    Args:
        blob_path: Path to the blob in GCS (e.g., "1.0.78+474-macos/1.0.78+474-macos.zip")
        expiration_hours: Hours until the URL expires (default: 1 hour)

    Returns:
        Signed URL valid for the specified duration
    """
    # Uses the _signed_url helper (Redis-cached, port-backed)
    return _signed_url(
        _required_bucket(desktop_updates_bucket, 'BUCKET_DESKTOP_UPDATES'), blob_path, expiration_hours * 60
    )


# **************************************************
# ****** SCREEN FRAMES (meeting-note screenshots) ***
# **************************************************
#
# Path convention: {uid}/{conversation_id}/{frame_id}.jpg and
# {uid}/{conversation_id}/{frame_id}_thumb.jpg (contract §8).
#
# upload_screen_frame_blobs is called from exactly one place in the codebase:
# utils/screen_frames/writer.py — the writer described in contract §5 that is
# the only code path allowed to write BUCKET_SCREEN_FRAMES. Nothing else
# should call it. In production this bucket-writing call runs under a
# separate service account scoped to BUCKET_SCREEN_FRAMES only (contract §5
# deploy prerequisite; not something this change provisions).

SCREEN_FRAME_SIGNED_URL_MINUTES = 60


def _screen_frame_blob_path(uid: str, conversation_id: str, frame_id: str) -> str:
    return f'{uid}/{conversation_id}/{frame_id}.jpg'


def _screen_frame_thumbnail_blob_path(uid: str, conversation_id: str, frame_id: str) -> str:
    return f'{uid}/{conversation_id}/{frame_id}_thumb.jpg'


def upload_screen_frame_blobs(
    uid: str,
    conversation_id: str,
    frame_id: str,
    jpeg_bytes: bytes,
    thumbnail_jpeg_bytes: bytes,
) -> None:
    """Write the canonical frame and its thumbnail. Writer-only — see module note above."""
    bucket = _required_bucket(screen_frames_bucket, 'BUCKET_SCREEN_FRAMES')
    store = _object_store()
    store.put(bucket, _screen_frame_blob_path(uid, conversation_id, frame_id), jpeg_bytes, content_type='image/jpeg')
    store.put(
        bucket,
        _screen_frame_thumbnail_blob_path(uid, conversation_id, frame_id),
        thumbnail_jpeg_bytes,
        content_type='image/jpeg',
    )


def get_screen_frame_signed_url(uid: str, conversation_id: str, frame_id: str) -> str:
    return _signed_url(
        _required_bucket(screen_frames_bucket, 'BUCKET_SCREEN_FRAMES'),
        _screen_frame_blob_path(uid, conversation_id, frame_id),
        SCREEN_FRAME_SIGNED_URL_MINUTES,
    )


def get_screen_frame_thumbnail_signed_url(uid: str, conversation_id: str, frame_id: str) -> str:
    return _signed_url(
        _required_bucket(screen_frames_bucket, 'BUCKET_SCREEN_FRAMES'),
        _screen_frame_thumbnail_blob_path(uid, conversation_id, frame_id),
        SCREEN_FRAME_SIGNED_URL_MINUTES,
    )


def delete_screen_frame_blobs(uid: str, conversation_id: str, frame_id: str) -> None:
    """Delete both objects for a frame and their cached signed URLs.

    A delete that leaves bytes in the bucket, or a still-live cached signed
    URL, is a bug, not a partial success (contract §8) — so both object
    deletes and both cache evictions happen here unconditionally, even if
    one of the blobs was already missing.
    """
    content_path = _screen_frame_blob_path(uid, conversation_id, frame_id)
    thumb_path = _screen_frame_thumbnail_blob_path(uid, conversation_id, frame_id)
    bucket_name = _required_bucket(screen_frames_bucket, 'BUCKET_SCREEN_FRAMES')
    delete_blob(bucket_name, content_path)
    delete_blob(bucket_name, thumb_path)
    delete_cached_signed_url(content_path)
    delete_cached_signed_url(thumb_path)
