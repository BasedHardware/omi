import datetime
import io
import json
import os
import wave
from typing import List
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

from google.cloud import storage
from google.oauth2 import service_account
from google.cloud.storage import transfer_manager
from google.cloud.exceptions import NotFound

from database.redis_db import cache_signed_url, get_cached_signed_url
from utils import encryption
from database import users as users_db

if os.environ.get('SERVICE_ACCOUNT_JSON'):
    service_account_info = json.loads(os.environ["SERVICE_ACCOUNT_JSON"])
    credentials = service_account.Credentials.from_service_account_info(service_account_info)
    storage_client = storage.Client(credentials=credentials)
else:
    storage_client = storage.Client()

speech_profiles_bucket = os.getenv('BUCKET_SPEECH_PROFILES')
postprocessing_audio_bucket = os.getenv('BUCKET_POSTPROCESSING')
memories_recordings_bucket = os.getenv('BUCKET_MEMORIES_RECORDINGS')
private_cloud_sync_bucket = os.getenv('BUCKET_PRIVATE_CLOUD_SYNC', 'omi-private-cloud-sync')
syncing_local_bucket = os.getenv('BUCKET_TEMPORAL_SYNC_LOCAL')
omi_apps_bucket = os.getenv('BUCKET_PLUGINS_LOGOS')
app_thumbnails_bucket = os.getenv('BUCKET_APP_THUMBNAILS')
chat_files_bucket = os.getenv('BUCKET_CHAT_FILES')
desktop_updates_bucket = os.getenv('BUCKET_DESKTOP_UPDATES')


# *******************************************
# ************* SPEECH PROFILE **************
# *******************************************
def upload_profile_audio(file_path: str, uid: str):
    bucket = storage_client.bucket(speech_profiles_bucket)
    path = f'{uid}/speech_profile.wav'
    blob = bucket.blob(path)
    blob.upload_from_filename(file_path)
    return f'https://storage.googleapis.com/{speech_profiles_bucket}/{path}'


def get_user_has_speech_profile(uid: str, max_age_days: int = None) -> bool:
    bucket = storage_client.bucket(speech_profiles_bucket)
    blob = bucket.blob(f'{uid}/speech_profile.wav')
    if not blob.exists():
        return False

    # Check age if max_age_days is specified
    if max_age_days is not None:
        blob.reload()
        if blob.time_created:
            age = datetime.datetime.now(datetime.timezone.utc) - blob.time_created
            if age.days > max_age_days:
                return False

    return True


def get_profile_audio_if_exists(uid: str, download: bool = True) -> str:
    bucket = storage_client.bucket(speech_profiles_bucket)
    path = f'{uid}/speech_profile.wav'
    blob = bucket.blob(path)
    if blob.exists():
        if download:
            file_path = f'_temp/{uid}_speech_profile.wav'
            blob.download_to_filename(file_path)
            return file_path
        return _get_signed_url(blob, 60)

    return None


def upload_additional_profile_audio(file_path: str, uid: str) -> None:
    bucket = storage_client.bucket(speech_profiles_bucket)
    path = f'{uid}/additional_profile_recordings/{file_path.split("/")[-1]}'
    blob = bucket.blob(path)
    blob.upload_from_filename(file_path)


def delete_additional_profile_audio(uid: str, file_name: str) -> None:
    bucket = storage_client.bucket(speech_profiles_bucket)
    blob = bucket.blob(f'{uid}/additional_profile_recordings/{file_name}')
    if blob.exists():
        print('delete_additional_profile_audio deleting', file_name)
        blob.delete()


def get_additional_profile_recordings(uid: str, download: bool = False) -> List[str]:
    bucket = storage_client.bucket(speech_profiles_bucket)
    blobs = bucket.list_blobs(prefix=f'{uid}/additional_profile_recordings/')
    if download:
        paths = []
        for blob in blobs:
            file_path = f'_temp/{uid}_{blob.name.split("/")[-1]}'
            blob.download_to_filename(file_path)
            paths.append(file_path)
        return paths

    return [_get_signed_url(blob, 60) for blob in blobs]


# ********************************************
# ************* PEOPLE PROFILES **************
# ********************************************


def upload_user_person_speech_sample(file_path: str, uid: str, person_id: str) -> None:
    bucket = storage_client.bucket(speech_profiles_bucket)
    path = f'{uid}/people_profiles/{person_id}/{file_path.split("/")[-1]}'
    blob = bucket.blob(path)
    blob.upload_from_filename(file_path)


def delete_user_person_speech_sample(uid: str, person_id: str, file_name: str) -> None:
    bucket = storage_client.bucket(speech_profiles_bucket)
    blob = bucket.blob(f'{uid}/people_profiles/{person_id}/{file_name}')
    if blob.exists():
        blob.delete()


def delete_speech_sample_for_people(uid: str, file_name: str) -> None:
    bucket = storage_client.bucket(speech_profiles_bucket)
    blobs = bucket.list_blobs(prefix=f'{uid}/people_profiles/')
    for blob in blobs:
        if file_name in blob.name:
            print('delete_speech_sample_for_people deleting', blob.name)
            blob.delete()


def delete_user_person_speech_samples(uid: str, person_id: str) -> None:
    bucket = storage_client.bucket(speech_profiles_bucket)
    blobs = bucket.list_blobs(prefix=f'{uid}/people_profiles/{person_id}/')
    for blob in blobs:
        blob.delete()


def get_user_people_ids(uid: str) -> List[str]:
    bucket = storage_client.bucket(speech_profiles_bucket)
    blobs = bucket.list_blobs(prefix=f'{uid}/people_profiles/')
    return [blob.name.split("/")[-2] for blob in blobs]


def get_user_person_speech_samples(uid: str, person_id: str, download: bool = False) -> List[str]:
    bucket = storage_client.bucket(speech_profiles_bucket)
    blobs = bucket.list_blobs(prefix=f'{uid}/people_profiles/{person_id}/')
    if download:
        paths = []
        for blob in blobs:
            file_path = f'_temp/{uid}_person_{blob.name.split("/")[-1]}'
            blob.download_to_filename(file_path)
            paths.append(file_path)
        return paths

    return [_get_signed_url(blob, 60) for blob in blobs]


# ********************************************
# ************* POST PROCESSING **************
# ********************************************
def upload_postprocessing_audio(file_path: str):
    bucket = storage_client.bucket(postprocessing_audio_bucket)
    blob = bucket.blob(file_path)
    blob.upload_from_filename(file_path)
    return f'https://storage.googleapis.com/{postprocessing_audio_bucket}/{file_path}'


def delete_postprocessing_audio(file_path: str):
    bucket = storage_client.bucket(postprocessing_audio_bucket)
    blob = bucket.blob(file_path)
    blob.delete()


# ***********************************
# ************* SDCARD **************
# ***********************************


def upload_sdcard_audio(file_path: str):
    bucket = storage_client.bucket(postprocessing_audio_bucket)
    blob = bucket.blob(file_path)
    blob.upload_from_filename(file_path)
    return f'https://storage.googleapis.com/{postprocessing_audio_bucket}/sdcard/{file_path}'


def download_postprocessing_audio(file_path: str, destination_file_path: str):
    bucket = storage_client.bucket(postprocessing_audio_bucket)
    blob = bucket.blob(file_path)
    blob.download_to_filename(destination_file_path)


# ************************************************
# *********** CONVERSATIONS RECORDINGS ***********
# ************************************************


def upload_conversation_recording(file_path: str, uid: str, conversation_id: str):
    bucket = storage_client.bucket(memories_recordings_bucket)
    path = f'{uid}/{conversation_id}.wav'
    blob = bucket.blob(path)
    blob.upload_from_filename(file_path)
    return f'https://storage.googleapis.com/{memories_recordings_bucket}/{path}'


def get_conversation_recording_if_exists(uid: str, memory_id: str) -> str:
    print('get_conversation_recording_if_exists', uid, memory_id)
    bucket = storage_client.bucket(memories_recordings_bucket)
    path = f'{uid}/{memory_id}.wav'
    blob = bucket.blob(path)
    if blob.exists():
        file_path = f'_temp/{memory_id}.wav'
        blob.download_to_filename(file_path)
        return file_path
    return None


def delete_all_conversation_recordings(uid: str):
    if not uid:
        return
    bucket = storage_client.bucket(memories_recordings_bucket)
    blobs = bucket.list_blobs(prefix=uid)
    for blob in blobs:
        blob.delete()


# ********************************************
# ************* SYNCING FILES **************
# ********************************************
def get_syncing_file_temporal_url(file_path: str):
    bucket = storage_client.bucket(syncing_local_bucket)
    blob = bucket.blob(file_path)
    blob.upload_from_filename(file_path)
    return f'https://storage.googleapis.com/{syncing_local_bucket}/{file_path}'


def get_syncing_file_temporal_signed_url(file_path: str):
    bucket = storage_client.bucket(syncing_local_bucket)
    blob = bucket.blob(file_path)
    blob.upload_from_filename(file_path)
    return _get_signed_url(blob, 15)


def delete_syncing_temporal_file(file_path: str):
    bucket = storage_client.bucket(syncing_local_bucket)
    blob = bucket.blob(file_path)
    blob.delete()


# ************************************************
# *********** PRIVATE CLOUD SYNC *****************
# ************************************************


def upload_audio_chunk(chunk_data: bytes, uid: str, conversation_id: str, timestamp: float) -> str:
    """
    Upload an audio chunk to Google Cloud Storage with optional encryption.

    Args:
        chunk_data: Raw audio bytes (PCM16)
        uid: User ID
        conversation_id: Conversation ID
        timestamp: Unix timestamp when chunk was recorded

    Returns:
        GCS path of the uploaded chunk
    """
    bucket = storage_client.bucket(private_cloud_sync_bucket)
    protection_level = users_db.get_data_protection_level(uid)

    # Format timestamp to 3 decimal places for cleaner filenames
    formatted_timestamp = f'{timestamp:.3f}'

    if protection_level == 'enhanced':
        # Encrypt as length-prefixed binary
        encrypted_chunk = encryption.encrypt_audio_chunk(chunk_data, uid)
        path = f'chunks/{uid}/{conversation_id}/{formatted_timestamp}.enc'
        blob = bucket.blob(path)
        blob.upload_from_string(encrypted_chunk, content_type='application/octet-stream')
    else:
        # Standard - no encryption
        path = f'chunks/{uid}/{conversation_id}/{formatted_timestamp}.bin'
        blob = bucket.blob(path)
        blob.upload_from_string(chunk_data, content_type='application/octet-stream')

    return path


def delete_audio_chunks(uid: str, conversation_id: str, timestamps: List[float]) -> None:
    """Delete audio chunks after they've been merged."""
    bucket = storage_client.bucket(private_cloud_sync_bucket)
    for timestamp in timestamps:
        # Format timestamp to match upload format (3 decimal places)
        formatted_timestamp = f'{timestamp:.3f}'
        # Try both encrypted and unencrypted paths
        for extension in ['.enc', '.bin']:
            chunk_path = f'chunks/{uid}/{conversation_id}/{formatted_timestamp}{extension}'
            blob = bucket.blob(chunk_path)
            if blob.exists():
                blob.delete()


def list_audio_chunks(uid: str, conversation_id: str) -> List[dict]:
    """
    List all audio chunks for a conversation.

    Returns:
        List of dicts with chunk info: {'timestamp': float, 'path': str, 'size': int}
    """
    bucket = storage_client.bucket(private_cloud_sync_bucket)
    prefix = f'chunks/{uid}/{conversation_id}/'
    blobs = bucket.list_blobs(prefix=prefix)

    chunks = []
    for blob in blobs:
        # Extract timestamp from filename (e.g., '1234567890.123.bin' or '1234567890.123.enc')
        filename = blob.name.split('/')[-1]
        if filename.endswith('.bin') or filename.endswith('.enc'):
            try:
                # Remove extension (.bin or .enc)
                timestamp_str = filename.rsplit('.', 1)[0]
                timestamp = float(timestamp_str)
                chunks.append(
                    {
                        'timestamp': timestamp,
                        'path': blob.name,
                        'size': blob.size,
                    }
                )
            except ValueError:
                continue

    return sorted(chunks, key=lambda x: x['timestamp'])


def delete_conversation_audio_files(uid: str, conversation_id: str) -> None:
    """Delete all audio files (chunks and merged) for a conversation."""
    bucket = storage_client.bucket(private_cloud_sync_bucket)

    # Delete chunks
    chunks_prefix = f'chunks/{uid}/{conversation_id}/'
    for blob in bucket.list_blobs(prefix=chunks_prefix):
        blob.delete()

    # Delete merged files
    audio_prefix = f'audio/{uid}/{conversation_id}/'
    for blob in bucket.list_blobs(prefix=audio_prefix):
        blob.delete()


def download_audio_chunks_and_merge(uid: str, conversation_id: str, timestamps: List[float]) -> bytes:
    """
    Download and merge audio chunks on-demand, handling mixed encryption states.
    Downloads chunks in parallel.
    Normalizes all chunks to unencrypted PCM format for consistent merging.

    Args:
        uid: User ID
        conversation_id: Conversation ID
        timestamps: List of chunk timestamps to merge

    Returns:
        Merged audio bytes (PCM16)
    """

    bucket = storage_client.bucket(private_cloud_sync_bucket)

    def download_single_chunk(timestamp: float) -> tuple[float, bytes | None]:
        """Download a single chunk and return (timestamp, pcm_data)."""
        formatted_timestamp = f'{timestamp:.3f}'
        chunk_path_enc = f'chunks/{uid}/{conversation_id}/{formatted_timestamp}.enc'
        chunk_path_bin = f'chunks/{uid}/{conversation_id}/{formatted_timestamp}.bin'

        chunk_data = None
        is_encrypted = False

        # Try encrypted first, then unencrypted
        try:
            chunk_data = bucket.blob(chunk_path_enc).download_as_bytes()
            is_encrypted = True
        except NotFound:
            try:
                chunk_data = bucket.blob(chunk_path_bin).download_as_bytes()
                is_encrypted = False
            except NotFound:
                print(f"Warning: Chunk not found for timestamp {formatted_timestamp}")
                return (timestamp, None)

        # Normalize to PCM (decrypt if needed
        if is_encrypted:
            pcm_data = encryption.decrypt_audio_file(chunk_data, uid)
        else:
            pcm_data = chunk_data

        return (timestamp, pcm_data)

    # Download chunks in parallel
    chunk_results = {}
    max_workers = min(10, len(timestamps))

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_timestamp = {executor.submit(download_single_chunk, ts): ts for ts in timestamps}

        for future in as_completed(future_to_timestamp):
            timestamp, pcm_data = future.result()
            if pcm_data is not None:
                chunk_results[timestamp] = pcm_data

    # Merge chunks
    merged_data = bytearray()
    for timestamp in timestamps:
        if timestamp in chunk_results:
            merged_data.extend(chunk_results[timestamp])

    if not merged_data:
        raise FileNotFoundError(f"No chunks found for conversation {conversation_id}")

    return bytes(merged_data)


def get_cached_merged_audio_path(uid: str, conversation_id: str, audio_file_id: str) -> str:
    """Get the GCS path for a cached merged audio file."""
    return f'merged/{uid}/{conversation_id}/{audio_file_id}.wav'


def get_or_create_merged_audio(
    uid: str, conversation_id: str, audio_file_id: str, timestamps: List[float], pcm_to_wav_func
) -> tuple[bytes, bool]:
    """
    Get merged audio from cache or create it.
    Cached files are stored in GCS with 1-day TTL (via lifecycle policy).

    Args:
        uid: User ID
        conversation_id: Conversation ID
        audio_file_id: Audio file ID
        timestamps: List of chunk timestamps
        pcm_to_wav_func: Function to convert PCM to WAV

    Returns:
        Tuple of (audio_data_bytes, was_cached)
    """
    bucket = storage_client.bucket(private_cloud_sync_bucket)
    cache_path = get_cached_merged_audio_path(uid, conversation_id, audio_file_id)
    cache_blob = bucket.blob(cache_path)

    # Check if cached version exists and is not expired
    if cache_blob.exists():
        # Check custom metadata for expiry
        cache_blob.reload()
        metadata = cache_blob.metadata or {}
        expires_at_str = metadata.get('expires_at')

        if expires_at_str:
            try:
                expires_at = datetime.datetime.fromisoformat(expires_at_str)
                if datetime.datetime.now(datetime.timezone.utc) < expires_at:
                    # Cache is valid, return it
                    print(f"Serving merged audio from cache: {cache_path}")
                    return cache_blob.download_as_bytes(), True
                else:
                    print(f"Cache expired for: {cache_path}")
            except (ValueError, TypeError):
                pass

    # Cache miss or expired - create new merged file
    print(f"Cache miss, merging audio for: {cache_path}")

    # Download and merge chunks
    pcm_data = download_audio_chunks_and_merge(uid, conversation_id, timestamps)

    # Convert to WAV
    wav_data = pcm_to_wav_func(pcm_data)

    # Upload to cache in background thread with 3-day TTL
    def _upload_to_cache():
        try:
            expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=3)
            cache_blob.metadata = {
                'expires_at': expires_at.isoformat(),
                'audio_file_id': audio_file_id,
            }
            cache_blob.upload_from_string(wav_data, content_type='audio/wav')
            print(f"Cached merged audio at: {cache_path}")
        except Exception as e:
            print(f"Error uploading audio cache: {e}")

    cache_thread = threading.Thread(target=_upload_to_cache, daemon=True)
    cache_thread.start()

    return wav_data, False


def get_merged_audio_signed_url(uid: str, conversation_id: str, audio_file_id: str) -> str | None:
    """
    Get a signed URL for cached merged audio if it exists and is valid.

    Returns:
        Signed URL valid for 1 hour, or None if cache doesn't exist
    """
    bucket = storage_client.bucket(private_cloud_sync_bucket)
    cache_path = get_cached_merged_audio_path(uid, conversation_id, audio_file_id)
    cache_blob = bucket.blob(cache_path)

    if not cache_blob.exists():
        return None

    # Check expiry
    cache_blob.reload()
    metadata = cache_blob.metadata or {}
    expires_at_str = metadata.get('expires_at')

    if expires_at_str:
        try:
            expires_at = datetime.datetime.fromisoformat(expires_at_str)
            if datetime.datetime.now(datetime.timezone.utc) >= expires_at:
                return None  # Expired
        except (ValueError, TypeError):
            pass

    # Generate signed URL valid for 1 hour
    return _get_signed_url(cache_blob, 60)


def delete_cached_merged_audio(uid: str, conversation_id: str) -> None:
    """Delete all cached merged audio for a conversation."""
    bucket = storage_client.bucket(private_cloud_sync_bucket)
    prefix = f'merged/{uid}/{conversation_id}/'
    for blob in bucket.list_blobs(prefix=prefix):
        blob.delete()


def _pcm_to_wav(pcm_data: bytes, sample_rate: int = 16000, channels: int = 1) -> bytes:
    """Convert PCM16 data to WAV format."""
    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, 'wb') as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(2)  # 16-bit audio
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_data)
    return wav_buffer.getvalue()


def precache_conversation_audio(uid: str, conversation_id: str, audio_files: list) -> None:
    """
    Pre-cache all audio files for a conversation in a background thread.

    Args:
        uid: User ID
        conversation_id: Conversation ID
        audio_files: List of audio file dicts with 'id' and 'chunk_timestamps'
    """
    if not audio_files:
        return

    def _precache_all():

        def _cache_single(af):
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
                )
            except Exception as e:
                print(f"[PRECACHE] Error caching audio file {af.get('id')}: {e}")

        with ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(_cache_single, audio_files))

    thread = threading.Thread(target=_precache_all, daemon=True)
    thread.start()


# **********************************
# ************* UTILS **************
# **********************************


def _get_signed_url(blob, minutes):
    if cached := get_cached_signed_url(blob.name):
        return cached

    signed_url = blob.generate_signed_url(version="v4", expiration=datetime.timedelta(minutes=minutes), method="GET")
    cache_signed_url(blob.name, signed_url, minutes * 60)
    return signed_url


def upload_app_logo(file_path: str, app_id: str):
    bucket = storage_client.bucket(omi_apps_bucket)
    path = f'{app_id}.png'
    blob = bucket.blob(path)
    blob.cache_control = 'public, no-cache'
    blob.upload_from_filename(file_path)
    return f'https://storage.googleapis.com/{omi_apps_bucket}/{path}'


def delete_app_logo(img_url: str):
    bucket = storage_client.bucket(omi_apps_bucket)
    path = img_url.split(f'https://storage.googleapis.com/{omi_apps_bucket}/')[1]
    print('delete_app_logo', path)
    blob = bucket.blob(path)
    blob.delete()


def upload_app_thumbnail(file_path: str, thumbnail_id: str) -> str:
    bucket = storage_client.bucket(app_thumbnails_bucket)
    path = f'{thumbnail_id}.jpg'
    blob = bucket.blob(path)
    blob.cache_control = 'public, no-cache'
    blob.upload_from_filename(file_path)
    public_url = f'https://storage.googleapis.com/{app_thumbnails_bucket}/{path}'
    return public_url


def get_app_thumbnail_url(thumbnail_id: str) -> str:
    path = f'{thumbnail_id}.jpg'
    return f'https://storage.googleapis.com/{app_thumbnails_bucket}/{path}'


# **********************************
# ************* CHAT FILES **************
# **********************************
def upload_multi_chat_files(files_name: List[str], uid: str) -> dict:
    """
    Upload multiple files to Google Cloud Storage in the chat files bucket.

    Args:
        files_name: List of file paths to upload
        uid: User ID to use as part of the storage path

    Returns:
        dict: A dictionary mapping original filenames to their Google Cloud Storage URLs
    """
    bucket = storage_client.bucket(chat_files_bucket)
    result = transfer_manager.upload_many_from_filenames(
        bucket, files_name, source_directory="./", blob_name_prefix=f'{uid}/'
    )
    dictFiles = {}
    for name, result in zip(files_name, result):
        if isinstance(result, Exception):
            print("Failed to upload {} due to exception: {}".format(name, result))
        else:
            dictFiles[name] = f'https://storage.googleapis.com/{chat_files_bucket}/{uid}/{name}'
    return dictFiles


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
    bucket = storage_client.bucket(desktop_updates_bucket)
    blob = bucket.blob(blob_path)

    # Use existing _get_signed_url helper with caching
    return _get_signed_url(blob, expiration_hours * 60)
