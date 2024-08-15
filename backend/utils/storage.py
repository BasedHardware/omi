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
backups_bucket = os.getenv('BUCKET_BACKUPS')


def upload_profile_audio(file_path: str, uid: str):
    bucket = storage_client.bucket(speech_profiles_bucket)
    path = f'{uid}/speech_profile.wav'
    blob = bucket.blob(path)
    blob.upload_from_filename(file_path)
    return f'https://storage.googleapis.com/{speech_profiles_bucket}/{path}'


# def get_speech_profile(uid: str):
#     bucket = storage_client.bucket(speech_profiles_bucket)
#     path = f'{uid}/speech_profile.wav'
#     blob = bucket.blob(path)
#     if not blob.exists():
#         return None
#
#     os.makedirs('_speech_profiles/', exist_ok=True)
#     profile_path = f'_speech_profiles/{uid}.wav'
#     blob.download_to_filename(profile_path)
#     return profile_path


# ***********
# *** OLD ***
# ***********
# soon to be deprecated

def upload_sample_storage(file_path: str, uid: str):
    print('upload_sample_storage', file_path)
    bucket = storage_client.bucket(speech_profiles_bucket)
    blobs = bucket.list_blobs(prefix=f'{uid}/samples/')
    sample_i = len(list(blobs))
    path = f'{uid}/samples/{file_path.split("/")[-1]}'
    blob = bucket.blob(path)
    blob.upload_from_filename(file_path)
    return f'https://storage.googleapis.com/{speech_profiles_bucket}/{path}', sample_i + 1


def upload_speaker_profile(profile_path: str, uid: str):
    print('upload_speaker_profile', profile_path)
    bucket = storage_client.bucket(speech_profiles_bucket)
    path = f'{uid}/profile.pt'
    blob = bucket.blob(path)
    blob.upload_from_filename(profile_path)
    print('upload_speaker_profile ~ uploaded')
    return f'https://storage.googleapis.com/{speech_profiles_bucket}/{path}'


def retrieve_all_samples(uid: str):
    print('retrieve_all_samples')
    # retrieve each of the _samples in the user folder, and store them in _samples/{uid}
    bucket = storage_client.bucket(speech_profiles_bucket)
    blobs = bucket.list_blobs(prefix=f'{uid}/samples/')
    base_path = f'_samples/{uid}/'
    os.makedirs(base_path, exist_ok=True)

    for i, blob in enumerate(blobs):
        path = f'{base_path}{blob.name.split("/")[-1]}'
        if os.path.exists(path):  # when opus uploaded? should refresh the download
            continue
        try:
            blob.download_to_filename(path)
        except Exception as e:
            print(f'Error downloading {blob.name}', e)
    return base_path
