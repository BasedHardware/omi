import json
import os

from google.cloud import storage
from google.oauth2 import service_account

from utils.stt.soniox_util import create_speaker_profile

if os.environ.get('SERVICE_ACCOUNT_JSON'):
    service_account_info = json.loads(os.environ["SERVICE_ACCOUNT_JSON"])
    credentials = service_account.Credentials.from_service_account_info(service_account_info)
    storage_client = storage.Client(credentials=credentials)
else:
    storage_client = storage.Client()

speech_profiles_bucket = os.getenv('BUCKET_SPEECH_PROFILES')
backups_bucket = os.getenv('BUCKET_BACKUPS')


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


def retrieve_speaker_profile(uid: str):
    try:
        bucket = storage_client.bucket(speech_profiles_bucket)
        path = f'{uid}/profile.pt'
        blob = bucket.blob(path)
        profile_path = f'_speaker_profile/{uid}.pt'
        blob.download_to_filename(profile_path)
        return profile_path
    except Exception as e:
        print(f'retrieve_speaker_profile not found {uid}')
        return None


def migrate():
    bucket = storage_client.bucket(speech_profiles_bucket)
    blobs = bucket.list_blobs()
    # get all dirs available
    # from each dir get all files in /samples
    # download each file to _samples/{uid}
    # create speaker profile
    uids = set()
    for blob in blobs:
        uid = blob.name.split("/")[0]
        uids.add(uid)
    print(len(uids))

    for uid in uids:
        base_path = retrieve_all_samples(uid)
        count = len(os.listdir(base_path))
        if count >= 5:
            try:
                result = create_speaker_profile(uid, base_path)
                print('create_speaker_profile', result)
            except:
                pass
    # base_path = retrieve_all_samples(uid)
    # print('uid', uid, print(base_path))


def retrieve_all_samples(uid: str):
    print('retrieve_all_samples')
    # retrieve each of the _samples in the user folder, and store them in _samples/{uid}
    bucket = storage_client.bucket(speech_profiles_bucket)
    blobs = bucket.list_blobs(prefix=f'{uid}/samples/')
    base_path = f'_samples/{uid}/'
    os.makedirs(base_path, exist_ok=True)

    for i, blob in enumerate(blobs):
        path = f'{base_path}{blob.name.split("/")[-1]}'
        if os.path.exists(path):
            continue
        blob.download_to_filename(path)
    return base_path


def upload_user_backup(uid: str, data: str):
    print('upload_user_backup')
    bucket = storage_client.bucket(backups_bucket)
    path = f'{uid}/backup.txt'
    blob = bucket.blob(path)
    blob.upload_from_string(data)
    return f'https://storage.googleapis.com/{backups_bucket}/{path}'


def retrieve_user_backup(uid: str):
    try:
        bucket = storage_client.bucket(backups_bucket)
        path = f'{uid}/backup.txt'
        blob = bucket.blob(path)
        # retrieve content and return it
        return blob.download_as_string().decode('utf-8')
    except Exception as e:
        print(f'retrieve_user_backup not found {uid}')
        return None


def delete_backup_storage(uid: str):
    bucket = storage_client.bucket(backups_bucket)
    path = f'{uid}/backup.txt'
    blob = bucket.blob(path)
    blob.delete()
    return True


# migrate()
