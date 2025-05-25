import datetime
import json
import os
from typing import List

from google.cloud import storage
from google.oauth2 import service_account
from google.cloud.storage import transfer_manager

from database.redis_db import cache_signed_url, get_cached_signed_url

if os.environ.get('SERVICE_ACCOUNT_JSON'):
    service_account_info = json.loads(os.environ["SERVICE_ACCOUNT_JSON"])
    credentials = service_account.Credentials.from_service_account_info(service_account_info)
    storage_client = storage.Client(credentials=credentials)
else:
    storage_client = storage.Client()

# Get bucket names with fallbacks for missing env vars
speech_profiles_bucket = os.getenv('BUCKET_SPEECH_PROFILES', '')
postprocessing_audio_bucket = os.getenv('BUCKET_POSTPROCESSING', '')
memories_recordings_bucket = os.getenv('BUCKET_MEMORIES_RECORDINGS', '')
syncing_local_bucket = os.getenv('BUCKET_TEMPORAL_SYNC_LOCAL', '')
omi_plugins_bucket = os.getenv('BUCKET_PLUGINS_LOGOS', '')
app_thumbnails_bucket = os.getenv('BUCKET_APP_THUMBNAILS', '')
chat_files_bucket = os.getenv('BUCKET_CHAT_FILES', '')

# Helper function to safely get bucket
def _get_bucket_safely(bucket_name: str, operation_name: str = "operation"):
    if not bucket_name or bucket_name.strip() == '':
        print(f"Warning: Bucket name not configured for {operation_name}. Skipping.")
        return None
    try:
        return storage_client.bucket(bucket_name)
    except Exception as e:
        print(f"Error accessing bucket '{bucket_name}' for {operation_name}: {e}")
        return None

# *******************************************
# ************* SPEECH PROFILE **************
# *******************************************
def upload_profile_audio(file_path: str, uid: str):
    bucket = _get_bucket_safely(speech_profiles_bucket, "speech profile upload")
    if not bucket:
        return None
    path = f'{uid}/speech_profile.wav'
    blob = bucket.blob(path)
    blob.upload_from_filename(file_path)
    return f'https://storage.googleapis.com/{speech_profiles_bucket}/{path}'


def get_user_has_speech_profile(uid: str) -> bool:
    bucket = _get_bucket_safely(speech_profiles_bucket, "speech profile check")
    if not bucket:
        return False
    blob = bucket.blob(f'{uid}/speech_profile.wav')
    return blob.exists()


def get_profile_audio_if_exists(uid: str, download: bool = True) -> str:
    bucket = _get_bucket_safely(speech_profiles_bucket, "speech profile check")
    if not bucket:
        return None
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
    bucket = _get_bucket_safely(speech_profiles_bucket, "additional profile recording upload")
    if not bucket:
        return
    path = f'{uid}/additional_profile_recordings/{file_path.split("/")[-1]}'
    blob = bucket.blob(path)
    blob.upload_from_filename(file_path)


def delete_additional_profile_audio(uid: str, file_name: str) -> None:
    bucket = _get_bucket_safely(speech_profiles_bucket, "additional profile recording deletion")
    if not bucket:
        return
    blob = bucket.blob(f'{uid}/additional_profile_recordings/{file_name}')
    if blob.exists():
        print('delete_additional_profile_audio deleting', file_name)
        blob.delete()


def get_additional_profile_recordings(uid: str, download: bool = False) -> List[str]:
    bucket = _get_bucket_safely(speech_profiles_bucket, "additional profile recordings retrieval")
    if not bucket:
        return []
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
    bucket = _get_bucket_safely(speech_profiles_bucket, "people profile recording upload")
    if not bucket:
        return
    path = f'{uid}/people_profiles/{person_id}/{file_path.split("/")[-1]}'
    blob = bucket.blob(path)
    blob.upload_from_filename(file_path)


def delete_user_person_speech_sample(uid: str, person_id: str, file_name: str) -> None:
    bucket = _get_bucket_safely(speech_profiles_bucket, "people profile recording deletion")
    if not bucket:
        return
    blob = bucket.blob(f'{uid}/people_profiles/{person_id}/{file_name}')
    if blob.exists():
        blob.delete()


def delete_speech_sample_for_people(uid: str, file_name: str) -> None:
    bucket = _get_bucket_safely(speech_profiles_bucket, "people profile recordings deletion")
    if not bucket:
        return
    blobs = bucket.list_blobs(prefix=f'{uid}/people_profiles/')
    for blob in blobs:
        if file_name in blob.name:
            print('delete_speech_sample_for_people deleting', blob.name)
            blob.delete()


def delete_user_person_speech_samples(uid: str, person_id: str) -> None:
    bucket = _get_bucket_safely(speech_profiles_bucket, "people profile recordings deletion")
    if not bucket:
        return
    blobs = bucket.list_blobs(prefix=f'{uid}/people_profiles/{person_id}/')
    for blob in blobs:
        blob.delete()


def get_user_people_ids(uid: str) -> List[str]:
    bucket = _get_bucket_safely(speech_profiles_bucket, "people profile retrieval")
    if not bucket:
        return []
    blobs = bucket.list_blobs(prefix=f'{uid}/people_profiles/')
    return [blob.name.split("/")[-2] for blob in blobs]


def get_user_person_speech_samples(uid: str, person_id: str, download: bool = False) -> List[str]:
    bucket = _get_bucket_safely(speech_profiles_bucket, "people profile retrieval")
    if not bucket:
        return []
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
    bucket = _get_bucket_safely(postprocessing_audio_bucket, "postprocessing recording upload")
    if not bucket:
        return None
    blob = bucket.blob(file_path)
    blob.upload_from_filename(file_path)
    return f'https://storage.googleapis.com/{postprocessing_audio_bucket}/{file_path}'


def delete_postprocessing_audio(file_path: str):
    bucket = _get_bucket_safely(postprocessing_audio_bucket, "postprocessing recording deletion")
    if not bucket:
        return
    blob = bucket.blob(file_path)
    blob.delete()


# ***********************************
# ************* SDCARD **************
# ***********************************

def upload_sdcard_audio(file_path: str):
    bucket = _get_bucket_safely(postprocessing_audio_bucket, "sdcard recording upload")
    if not bucket:
        return None
    blob = bucket.blob(file_path)
    blob.upload_from_filename(file_path)
    return f'https://storage.googleapis.com/{postprocessing_audio_bucket}/sdcard/{file_path}'


def download_postprocessing_audio(file_path: str, destination_file_path: str):
    bucket = _get_bucket_safely(postprocessing_audio_bucket, "postprocessing recording download")
    if not bucket:
        return
    blob = bucket.blob(file_path)
    blob.download_to_filename(destination_file_path)


# ************************************************
# *********** CONVERSATIONS RECORDINGS ***********
# ************************************************

def upload_conversation_recording(file_path: str, uid: str, conversation_id: str):
    bucket = _get_bucket_safely(memories_recordings_bucket, "conversation recording upload")
    if not bucket:
        return None
    path = f'{uid}/{conversation_id}.wav'
    blob = bucket.blob(path)
    blob.upload_from_filename(file_path)
    return f'https://storage.googleapis.com/{memories_recordings_bucket}/{path}'


def get_conversation_recording_if_exists(uid: str, memory_id: str) -> str:
    print('get_conversation_recording_if_exists', uid, memory_id)
    bucket = _get_bucket_safely(memories_recordings_bucket, "conversation recording retrieval")
    if not bucket:
        return None
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
    bucket = _get_bucket_safely(memories_recordings_bucket, "conversation recordings deletion")
    if not bucket:
        return
    blobs = bucket.list_blobs(prefix=uid)
    for blob in blobs:
        blob.delete()


# ********************************************
# ************* SYNCING FILES **************
# ********************************************
def get_syncing_file_temporal_url(file_path: str):
    bucket = _get_bucket_safely(syncing_local_bucket, "temporal syncing file retrieval")
    if not bucket:
        return None
    blob = bucket.blob(file_path)
    blob.upload_from_filename(file_path)
    return f'https://storage.googleapis.com/{syncing_local_bucket}/{file_path}'

def get_syncing_file_temporal_signed_url(file_path: str):
    bucket = _get_bucket_safely(syncing_local_bucket, "temporal syncing file retrieval")
    if not bucket:
        return None
    blob = bucket.blob(file_path)
    blob.upload_from_filename(file_path)
    return _get_signed_url(blob, 15)


def delete_syncing_temporal_file(file_path: str):
    bucket = _get_bucket_safely(syncing_local_bucket, "temporal syncing file deletion")
    if not bucket:
        return
    blob = bucket.blob(file_path)
    blob.delete()


# **********************************
# ************* UTILS **************
# **********************************

def _get_signed_url(blob, minutes):
    if cached := get_cached_signed_url(blob.name):
        return cached

    signed_url = blob.generate_signed_url(version="v4", expiration=datetime.timedelta(minutes=minutes), method="GET")
    cache_signed_url(blob.name, signed_url, minutes * 60)
    return signed_url


def upload_plugin_logo(file_path: str, plugin_id: str):
    bucket = _get_bucket_safely(omi_plugins_bucket, "plugin logo upload")
    if not bucket:
        return None
    path = f'{plugin_id}.png'
    blob = bucket.blob(path)
    blob.cache_control = 'public, no-cache'
    blob.upload_from_filename(file_path)
    return f'https://storage.googleapis.com/{omi_plugins_bucket}/{path}'


def delete_plugin_logo(img_url: str):
    bucket = _get_bucket_safely(omi_plugins_bucket, "plugin logo deletion")
    if not bucket:
        return
    path = img_url.split(f'https://storage.googleapis.com/{omi_plugins_bucket}/')[1]
    print('delete_plugin_logo', path)
    blob = bucket.blob(path)
    blob.delete()

def upload_app_thumbnail(file_path: str, thumbnail_id: str) -> str:
    bucket = _get_bucket_safely(app_thumbnails_bucket, "app thumbnail upload")
    if not bucket:
        return None
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
    bucket = _get_bucket_safely(chat_files_bucket, "chat files upload")
    if not bucket:
        return {}
    result = transfer_manager.upload_many_from_filenames(bucket, files_name, source_directory="./", blob_name_prefix=f'{uid}/')
    dictFiles = {}
    for name, result in zip(files_name, result):
        if isinstance(result, Exception):
            print("Failed to upload {} due to exception: {}".format(name, result))
        else:
            dictFiles[name] = f'https://storage.googleapis.com/{chat_files_bucket}/{uid}/{name}'
    return dictFiles

def upload_chat_file_thumbnail(file_path: str, uid: str) -> str:
    """
    Upload a chat file thumbnail to Google Cloud Storage.

    Args:
        file_path: The local path to the thumbnail file.
        uid: The user ID associated with the file.

    Returns:
        str: The public URL of the uploaded thumbnail.
    """
    print(f"Attempting to upload thumbnail: {file_path} for user {uid}")
    bucket = _get_bucket_safely(chat_files_bucket, "chat file thumbnail upload")
    if not bucket:
        return ""
    # Use a specific path for thumbnails
    blob_name = f'{uid}/thumbnails/{os.path.basename(file_path)}'
    blob = bucket.blob(blob_name)
    try:
        blob.upload_from_filename(file_path)
        print(f"Successfully uploaded thumbnail to GCS: {blob.public_url}")
        return blob.public_url
    except Exception as e:
        print(f"Error uploading thumbnail to GCS: {e}")
        return ""
