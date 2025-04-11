import datetime
import json
import os
import tempfile
from typing import List, Optional

from google.cloud import storage
from google.oauth2 import service_account
from google.cloud.storage import transfer_manager

from database.redis_db import cache_signed_url, get_cached_signed_url

# Get project ID from google-credentials.json
project_id = None
try:
    with open('google-credentials.json', 'r') as f:
        credentials = json.load(f)
        # Try to get project_id, if not available use quota_project_id
        project_id = credentials.get('project_id') or credentials.get('quota_project_id')
        print(f"Using Google Cloud project ID for storage: {project_id}")
except Exception as e:
    print(f"Error reading google-credentials.json: {e}")

try:
    if os.environ.get('SERVICE_ACCOUNT_JSON'):
        service_account_info = json.loads(os.environ["SERVICE_ACCOUNT_JSON"])
        credentials = service_account.Credentials.from_service_account_info(service_account_info)
        storage_client = storage.Client(credentials=credentials, project=project_id)
    else:
        storage_client = storage.Client(project=project_id)
except Exception as e:
    print(f"WARNING: Could not initialize storage client: {e}")
    storage_client = None

# Get bucket names from environment variables with empty string fallbacks
speech_profiles_bucket = os.getenv('BUCKET_SPEECH_PROFILES', '')
postprocessing_audio_bucket = os.getenv('BUCKET_POSTPROCESSING', '')
memories_recordings_bucket = os.getenv('BUCKET_MEMORIES_RECORDINGS', '')
syncing_local_bucket = os.getenv('BUCKET_TEMPORAL_SYNC_LOCAL', '')
omi_plugins_bucket = os.getenv('BUCKET_PLUGINS_LOGOS', '')
app_thumbnails_bucket = os.getenv('BUCKET_APP_THUMBNAILS', '')
chat_files_bucket = os.getenv('BUCKET_CHAT_FILES', '')

# Helper function to create a mock blob for cases when storage is not available
class MockBlob:
    def __init__(self, name):
        self.name = name
        self._exists = False
        self._local_path = None

    def exists(self):
        return self._exists

    def upload_from_filename(self, filename):
        # Store the local file path for potential retrieval
        self._local_path = filename
        self._exists = True
        print(f"MOCK: Uploaded {filename} to {self.name}")
        return True

    def download_to_filename(self, filename):
        # If we have a local path, copy the file to the destination
        if self._local_path and os.path.exists(self._local_path):
            import shutil
            shutil.copy(self._local_path, filename)
            print(f"MOCK: Downloaded {self.name} to {filename}")
            return True
        print(f"MOCK: Could not download {self.name} to {filename}")
        return False

    def delete(self):
        self._exists = False
        print(f"MOCK: Deleted {self.name}")
        return True

# Helper function to get a bucket, with fallback to mock implementation
def get_bucket(bucket_name):
    if not storage_client or not bucket_name:
        return None
    try:
        return storage_client.bucket(bucket_name)
    except Exception as e:
        print(f"Error getting bucket {bucket_name}: {e}")
        return None

# Helper function to generate a mock signed URL for local development
def generate_mock_signed_url(blob_name):
    return f"mock-signed-url://{blob_name}?mock=true"

# *******************************************
# ************* SPEECH PROFILE **************
# *******************************************
def upload_profile_audio(file_path: str, uid: str):
    try:
        bucket = get_bucket(speech_profiles_bucket)
        if not bucket:
            print(f"WARNING: Speech profiles bucket not configured. Using local file.")
            return f"file://{file_path}"

        path = f'{uid}/speech_profile.wav'
        blob = bucket.blob(path)
        blob.upload_from_filename(file_path)
        return f'https://storage.googleapis.com/{speech_profiles_bucket}/{path}'
    except Exception as e:
        print(f"Error uploading profile audio: {e}")
        return f"file://{file_path}"


def get_user_has_speech_profile(uid: str) -> bool:
    try:
        bucket = get_bucket(speech_profiles_bucket)
        if not bucket:
            # Check if there's a local file indicating a speech profile
            local_path = f'_speech_profiles/{uid}/speech_profile.wav'
            return os.path.exists(local_path)

        blob = bucket.blob(f'{uid}/speech_profile.wav')
        return blob.exists()
    except Exception as e:
        print(f"Error checking speech profile: {e}")
        return False


def get_profile_audio_if_exists(uid: str, download: bool = True) -> Optional[str]:
    try:
        bucket = get_bucket(speech_profiles_bucket)
        if not bucket:
            # Check for local file
            local_path = f'_speech_profiles/{uid}/speech_profile.wav'
            if os.path.exists(local_path):
                return local_path
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
    except Exception as e:
        print(f"Error getting profile audio: {e}")
        return None


def upload_additional_profile_audio(file_path: str, uid: str) -> None:
    try:
        bucket = get_bucket(speech_profiles_bucket)
        if not bucket:
            # Save to local directory
            os.makedirs(f'_speech_profiles/{uid}/additional_profile_recordings', exist_ok=True)
            local_path = f'_speech_profiles/{uid}/additional_profile_recordings/{os.path.basename(file_path)}'
            import shutil
            shutil.copy(file_path, local_path)
            print(f"Saved additional profile audio to {local_path}")
            return

        path = f'{uid}/additional_profile_recordings/{file_path.split("/")[-1]}'
        blob = bucket.blob(path)
        blob.upload_from_filename(file_path)
    except Exception as e:
        print(f"Error uploading additional profile audio: {e}")


def delete_additional_profile_audio(uid: str, file_name: str) -> None:
    try:
        bucket = get_bucket(speech_profiles_bucket)
        if not bucket:
            # Delete from local directory
            local_path = f'_speech_profiles/{uid}/additional_profile_recordings/{file_name}'
            if os.path.exists(local_path):
                os.remove(local_path)
                print(f"Deleted local file: {local_path}")
            return

        blob = bucket.blob(f'{uid}/additional_profile_recordings/{file_name}')
        if blob.exists():
            print('delete_additional_profile_audio deleting', file_name)
            blob.delete()
    except Exception as e:
        print(f"Error deleting additional profile audio: {e}")


def get_additional_profile_recordings(uid: str, download: bool = False) -> List[str]:
    try:
        bucket = get_bucket(speech_profiles_bucket)
        if not bucket:
            # Check local directory
            dir_path = f'_speech_profiles/{uid}/additional_profile_recordings'
            if not os.path.exists(dir_path):
                return []
            files = os.listdir(dir_path)
            return [f'file://{dir_path}/{file}' for file in files]

        blobs = bucket.list_blobs(prefix=f'{uid}/additional_profile_recordings/')
        if download:
            paths = []
            for blob in blobs:
                file_path = f'_temp/{uid}_{blob.name.split("/")[-1]}'
                blob.download_to_filename(file_path)
                paths.append(file_path)
            return paths

        return [_get_signed_url(blob, 60) for blob in blobs]
    except Exception as e:
        print(f"Error getting additional profile recordings: {e}")
        return []


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


# **********************************
# ************* UTILS **************
# **********************************

def _get_signed_url(blob, expiration_minutes=60):
    try:
        if isinstance(blob, MockBlob):
            return generate_mock_signed_url(blob.name)

        # Check if the URL is already cached
        cached_url = get_cached_signed_url(blob.name)
        if cached_url:
            return cached_url

        # Generate a new signed URL
        expiration = datetime.timedelta(minutes=expiration_minutes)
        signed_url = blob.generate_signed_url(
            version="v4",
            expiration=expiration,
            method="GET"
        )

        # Cache the URL
        cache_signed_url(blob.name, signed_url, int(expiration.total_seconds()))

        return signed_url
    except Exception as e:
        print(f"Error generating signed URL: {e}")
        return generate_mock_signed_url(blob.name)


def upload_plugin_logo(file_path: str, plugin_id: str):
    bucket = storage_client.bucket(omi_plugins_bucket)
    path = f'{plugin_id}.png'
    blob = bucket.blob(path)
    blob.upload_from_filename(file_path)
    return f'https://storage.googleapis.com/{omi_plugins_bucket}/{path}'


def delete_plugin_logo(img_url: str):
    bucket = storage_client.bucket(omi_plugins_bucket)
    path = img_url.split(f'https://storage.googleapis.com/{omi_plugins_bucket}/')[1]
    print('delete_plugin_logo', path)
    blob = bucket.blob(path)
    blob.delete()

def upload_app_thumbnail(file_path: str, thumbnail_id: str) -> str:
    bucket = storage_client.bucket(app_thumbnails_bucket)
    path = f'{thumbnail_id}.jpg'
    blob = bucket.blob(path)
    blob.upload_from_filename(file_path)
    return f'https://storage.googleapis.com/{app_thumbnails_bucket}/{path}'

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
    result = transfer_manager.upload_many_from_filenames(bucket, files_name, source_directory="./", blob_name_prefix=f'{uid}/')
    dictFiles = {}
    for name, result in zip(files_name, result):
        if isinstance(result, Exception):
            print("Failed to upload {} due to exception: {}".format(name, result))
        else:
            dictFiles[name] = f'https://storage.googleapis.com/{chat_files_bucket}/{uid}/{name}'
    return dictFiles
