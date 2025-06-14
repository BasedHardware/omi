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
omi_apps_bucket = os.getenv('BUCKET_PLUGINS_LOGOS', '')
app_thumbnails_bucket = os.getenv('BUCKET_APP_THUMBNAILS', '')
chat_files_bucket = os.getenv('BUCKET_CHAT_FILES', '')
omiglass_bucket = os.getenv('BUCKET_OMIGLASS', '')

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
    bucket = _get_bucket_safely(speech_profiles_bucket, "speech profile download")
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
    bucket = _get_bucket_safely(speech_profiles_bucket, "additional profile upload")
    if not bucket:
        return
    path = f'{uid}/additional_profile_recordings/{file_path.split("/")[-1]}'
    blob = bucket.blob(path)
    blob.upload_from_filename(file_path)


def delete_additional_profile_audio(uid: str, file_name: str) -> None:
    bucket = _get_bucket_safely(speech_profiles_bucket, "additional profile delete")
    if not bucket:
        return
    blob = bucket.blob(f'{uid}/additional_profile_recordings/{file_name}')
    if blob.exists():
        print('delete_additional_profile_audio deleting', file_name)
        blob.delete()


def get_additional_profile_recordings(uid: str, download: bool = False) -> List[str]:
    bucket = _get_bucket_safely(speech_profiles_bucket, "additional profile list")
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
    bucket = _get_bucket_safely(speech_profiles_bucket, "person speech upload")
    if not bucket:
        return
    path = f'{uid}/people_profiles/{person_id}/{file_path.split("/")[-1]}'
    blob = bucket.blob(path)
    blob.upload_from_filename(file_path)


def delete_user_person_speech_sample(uid: str, person_id: str, file_name: str) -> None:
    bucket = _get_bucket_safely(speech_profiles_bucket, "person speech delete")
    if not bucket:
        return
    blob = bucket.blob(f'{uid}/people_profiles/{person_id}/{file_name}')
    if blob.exists():
        blob.delete()


def delete_speech_sample_for_people(uid: str, file_name: str) -> None:
    bucket = _get_bucket_safely(speech_profiles_bucket, "people speech cleanup")
    if not bucket:
        return
    blobs = bucket.list_blobs(prefix=f'{uid}/people_profiles/')
    for blob in blobs:
        if file_name in blob.name:
            print('delete_speech_sample_for_people deleting', blob.name)
            blob.delete()


def delete_user_person_speech_samples(uid: str, person_id: str) -> None:
    bucket = _get_bucket_safely(speech_profiles_bucket, "person speech samples delete")
    if not bucket:
        return
    blobs = bucket.list_blobs(prefix=f'{uid}/people_profiles/{person_id}/')
    for blob in blobs:
        blob.delete()


def get_user_people_ids(uid: str) -> List[str]:
    bucket = _get_bucket_safely(speech_profiles_bucket, "people ids list")
    if not bucket:
        return []
    blobs = bucket.list_blobs(prefix=f'{uid}/people_profiles/')
    return [blob.name.split("/")[-2] for blob in blobs]


def get_user_person_speech_samples(uid: str, person_id: str, download: bool = False) -> List[str]:
    bucket = _get_bucket_safely(speech_profiles_bucket, "person speech samples list")
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
    bucket = _get_bucket_safely(postprocessing_audio_bucket, "postprocessing upload")
    if not bucket:
        return None
    blob = bucket.blob(file_path)
    blob.upload_from_filename(file_path)
    return f'https://storage.googleapis.com/{postprocessing_audio_bucket}/{file_path}'


def delete_postprocessing_audio(file_path: str):
    bucket = _get_bucket_safely(postprocessing_audio_bucket, "postprocessing delete")
    if not bucket:
        return
    blob = bucket.blob(file_path)
    blob.delete()


# ***********************************
# ************* SDCARD **************
# ***********************************

def upload_sdcard_audio(file_path: str):
    bucket = _get_bucket_safely(postprocessing_audio_bucket, "sdcard upload")
    if not bucket:
        return None
    blob = bucket.blob(file_path)
    blob.upload_from_filename(file_path)
    return f'https://storage.googleapis.com/{postprocessing_audio_bucket}/sdcard/{file_path}'


def download_postprocessing_audio(file_path: str, destination_file_path: str):
    bucket = _get_bucket_safely(postprocessing_audio_bucket, "postprocessing download")
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
    bucket = _get_bucket_safely(memories_recordings_bucket, "conversation recording download")
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
    bucket = _get_bucket_safely(memories_recordings_bucket, "conversation recordings cleanup")
    if not bucket:
        return
    blobs = bucket.list_blobs(prefix=uid)
    for blob in blobs:
        blob.delete()


# ********************************************
# ************* SYNCING FILES **************
# ********************************************
def get_syncing_file_temporal_url(file_path: str):
    bucket = _get_bucket_safely(syncing_local_bucket, "syncing file upload")
    if not bucket:
        return None
    blob = bucket.blob(file_path)
    blob.upload_from_filename(file_path)
    return f'https://storage.googleapis.com/{syncing_local_bucket}/{file_path}'

def get_syncing_file_temporal_signed_url(file_path: str):
    bucket = _get_bucket_safely(syncing_local_bucket, "syncing file signed upload")
    if not bucket:
        return None
    blob = bucket.blob(file_path)
    blob.upload_from_filename(file_path)
    return _get_signed_url(blob, 15)


def delete_syncing_temporal_file(file_path: str):
    bucket = _get_bucket_safely(syncing_local_bucket, "syncing file cleanup")
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


def upload_app_logo(file_path: str, app_id: str):
    bucket = _get_bucket_safely(omi_apps_bucket, "app logo upload")
    if not bucket:
        return None
    path = f'{app_id}.png'
    blob = bucket.blob(path)
    blob.cache_control = 'public, no-cache'
    blob.upload_from_filename(file_path)
    return f'https://storage.googleapis.com/{omi_apps_bucket}/{path}'


def delete_app_logo(img_url: str):
    bucket = _get_bucket_safely(omi_apps_bucket, "app logo delete")
    if not bucket:
        return
    path = img_url.split(f'https://storage.googleapis.com/{omi_apps_bucket}/')[1]
    print('delete_app_logo', path)
    blob = bucket.blob(path)
    blob.delete()

def upload_app_thumbnail(file_path: str, thumbnail_id: str) -> str:
    bucket = _get_bucket_safely(app_thumbnails_bucket, "app thumbnail upload")
    if not bucket:
        return ""
    path = f'{thumbnail_id}.jpg'
    blob = bucket.blob(path)
    blob.cache_control = 'public, no-cache'
    blob.upload_from_filename(file_path)
    public_url = f'https://storage.googleapis.com/{app_thumbnails_bucket}/{path}'
    return public_url

def get_app_thumbnail_url(thumbnail_id: str) -> str:
    if not app_thumbnails_bucket:
        return ""
    path = f'{thumbnail_id}.jpg'
    return f'https://storage.googleapis.com/{app_thumbnails_bucket}/{path}'

# **********************************
# ************* OMIGLASS IMAGES **************
# **********************************

def upload_omiglass_image(image_data: bytes, uid: str, filename: str) -> str:
    """Upload OmiGlass image to dedicated bucket and return signed URL"""
    import tempfile
    
    bucket = _get_bucket_safely(omiglass_bucket, "omiglass image upload")
    if not bucket:
        return ""
    
    try:
        # Save to temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as temp_file:
            temp_file.write(image_data)
            temp_file_path = temp_file.name
        
        try:
            # Upload to OmiGlass-specific bucket with organized path structure
            blob_name = f'{uid}/images/{filename}'
            blob = bucket.blob(blob_name)
            blob.upload_from_filename(temp_file_path)
            
            # Clean up temp file
            os.unlink(temp_file_path)
            
            # Return signed URL for private bucket access (24 hour expiry)
            return _get_signed_url(blob, 1440)
            
        except Exception as e:
            print(f"Error uploading OmiGlass image to bucket: {e}")
            # Clean up temp file even on error
            try:
                os.unlink(temp_file_path)
            except:
                pass
            return ""
            
    except Exception as e:
        print(f"Error in upload_omiglass_image: {e}")
        return ""


def upload_omiglass_thumbnail(image_bytes: bytes, uid: str, thumbnail_filename: str) -> str:
    """Generate and upload OmiGlass thumbnail to dedicated bucket"""
    try:
        from PIL import Image
        import tempfile
        import io
        
        bucket = _get_bucket_safely(omiglass_bucket, "omiglass thumbnail upload")
        if not bucket:
            return ""
        
        # Create thumbnail from bytes directly
        with Image.open(io.BytesIO(image_bytes)) as img:
            img.thumbnail((128, 128))
            
            # Save thumbnail to temporary file
            thumbnail_path = f"/tmp/{thumbnail_filename}"
            img.save(thumbnail_path, format='JPEG')
            
            try:
                # Upload to OmiGlass bucket with organized path structure
                blob_name = f'{uid}/thumbnails/{thumbnail_filename}'
                blob = bucket.blob(blob_name)
                blob.upload_from_filename(thumbnail_path)
                
                # Clean up local thumbnail file
                os.unlink(thumbnail_path)
                
                # Return signed URL for private bucket access (24 hour expiry)
                return _get_signed_url(blob, 1440)
                
            except Exception as upload_error:
                print(f"Error uploading OmiGlass thumbnail: {upload_error}")
                # Clean up local thumbnail file
                try:
                    os.unlink(thumbnail_path)
                except:
                    pass
                return ""
            
    except Exception as e:
        print(f"Error generating OmiGlass thumbnail: {e}")
        return ""


def delete_omiglass_images(uid: str, image_ids: List[str]) -> None:
    """Delete OmiGlass images and their thumbnails"""
    bucket = _get_bucket_safely(omiglass_bucket, "omiglass image deletion")
    if not bucket:
        return
    
    for image_id in image_ids:
        try:
            # Delete main image
            image_blob = bucket.blob(f'{uid}/images/{image_id}.jpg')
            if image_blob.exists():
                image_blob.delete()
            
            # Delete thumbnail
            thumb_blob = bucket.blob(f'{uid}/thumbnails/{image_id}_thumb.jpg')
            if thumb_blob.exists():
                thumb_blob.delete()
                
        except Exception as e:
            print(f"Error deleting OmiGlass image {image_id}: {e}")


def get_omiglass_image_signed_url(uid: str, filename: str, minutes: int = 60) -> str:
    """Get signed URL for OmiGlass image"""
    bucket = _get_bucket_safely(omiglass_bucket, "omiglass image access")
    if not bucket:
        return ""
    
    blob = bucket.blob(f'{uid}/images/{filename}')
    if blob.exists():
        return _get_signed_url(blob, minutes)
    return ""


# **********************************
# ************* CHAT FILES **************
# **********************************
def upload_multi_chat_files(files_name: List[str], uid: str) -> dict:
    """
    Upload multiple files to Google Cloud Storage using transfer manager.

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
    """Upload a chat file thumbnail to Google Cloud Storage."""
    try:
        bucket = _get_bucket_safely(chat_files_bucket, "chat thumbnail upload")
        if not bucket:
            return ""
        blob_name = f'{uid}/thumbnails/{os.path.basename(file_path)}'
        blob = bucket.blob(blob_name)
        blob.upload_from_filename(file_path)
        return f'https://storage.googleapis.com/{chat_files_bucket}/{blob_name}'
    except Exception as e:
        print(f"Error uploading thumbnail: {e}")
        return ""
