import datetime
import json
import os

from google.cloud import storage
from google.oauth2 import service_account

if os.environ.get('SERVICE_ACCOUNT_JSON'):
    service_account_info = json.loads(os.environ["SERVICE_ACCOUNT_JSON"])
    credentials = service_account.Credentials.from_service_account_info(service_account_info)
    storage_client = storage.Client(credentials=credentials)
else:
    storage_client = storage.Client()

speech_profiles_bucket = os.getenv('BUCKET_SPEECH_PROFILES')
postprocessing_audio_bucket = os.getenv('BUCKET_POSTPROCESSING')
memories_recordings_bucket = os.getenv('BUCKET_MEMORIES_RECORDINGS')


# *******************************************
# ************* SPEECH PROFILE **************
# *******************************************
def upload_profile_audio(file_path: str, uid: str):
    bucket = storage_client.bucket(speech_profiles_bucket)
    path = f'{uid}/speech_profile.wav'
    blob = bucket.blob(path)
    blob.upload_from_filename(file_path)
    return f'https://storage.googleapis.com/{speech_profiles_bucket}/{path}'


def get_profile_audio_if_exists(uid: str) -> str:
    bucket = storage_client.bucket(speech_profiles_bucket)
    path = f'{uid}/speech_profile.wav'
    blob = bucket.blob(path)
    if blob.exists():
        # download and return file path
        file_path = f'_temp/{uid}_speech_profile.wav'
        blob.download_to_filename(file_path)
        return file_path

    return None


def upload_additional_profile_audio(file_path: str, uid: str):
    bucket = storage_client.bucket(speech_profiles_bucket)
    path = f'{uid}/additional_profile_recordings/{file_path.split("/")[-1]}'
    blob = bucket.blob(path)
    blob.upload_from_filename(file_path)
    return f'https://storage.googleapis.com/{speech_profiles_bucket}/{path}'


def delete_additional_profile_audio(uid: str, file_name: str):
    bucket = storage_client.bucket(speech_profiles_bucket)
    blob = bucket.blob(f'{uid}/additional_profile_recordings/{file_name}')
    blob.delete()


def get_additional_profile_recordings(uid: str) -> list:
    bucket = storage_client.bucket(speech_profiles_bucket)
    blobs = bucket.list_blobs(prefix=f'{uid}/additional_profile_recordings/')
    recordings = []
    for blob in blobs:
        recordings.append(blob.name)
    return recordings


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


def create_signed_postprocessing_audio_url(file_path: str):
    bucket = storage_client.bucket(postprocessing_audio_bucket)
    blob = bucket.blob(file_path)
    url = blob.generate_signed_url(
        version="v4",
        expiration=datetime.timedelta(minutes=15),
        method="GET",
    )

    return url


# ************************************************
# ************* MEMORIES RECORDINGS **************
# ************************************************

def upload_memory_recording(file_path: str, uid: str, memory_id: str):
    bucket = storage_client.bucket(memories_recordings_bucket)
    path = f'{uid}/{memory_id}.wav'
    blob = bucket.blob(path)
    blob.upload_from_filename(file_path)
    return f'https://storage.googleapis.com/{memories_recordings_bucket}/{path}'


def get_memory_recording_if_exists(uid: str, memory_id: str) -> str:
    bucket = storage_client.bucket(memories_recordings_bucket)
    path = f'{uid}/{memory_id}.wav'
    blob = bucket.blob(path)
    if blob.exists():
        file_path = f'_temp/{memory_id}.wav'
        blob.download_to_filename(file_path)
        return file_path
    return None


def delete_all_memory_recordings(uid: str):
    if not uid:
        return
    bucket = storage_client.bucket(memories_recordings_bucket)
    blobs = bucket.list_blobs(prefix=uid)
    for blob in blobs:
        blob.delete()
