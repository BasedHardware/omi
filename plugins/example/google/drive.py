from fastapi import APIRouter
from googleapiclient.discovery import build
import google.auth
from googleapiclient.http import MediaFileUpload

from models import Memory, EndpointResponse ,Event , TranscriptSegment , MemoryPhoto
import oauth
import requests

router = APIRouter()
creds, _ = google.auth.default()
SCOPES = ['https://www.googleapis.com/auth/drive']  

service = build("drive", "v3", credentials=creds , SCOPES=SCOPES)

@router.post('/create_folder', tags=['google_drive'])
def create_folder(CLIENT_ID:str , CLIENT_SECRET:str , folder_name = Event.title):
    file_metadata = {
        'name': folder_name,
        'mimeType': 'application/vnd.google-apps.folder'
    }
    file = service.files().create(body=file_metadata).execute()
    print(f'Folder ID: "{file.get("id")}".')
    return file.get("id")

@router.post('/upload_files' , tags=['google_drive_upload'])
def upload_files(CLIENT_ID:str , CLIENT_SECRET:str , folder_id:str , photo: MemoryPhoto , transcript:TranscriptSegment):
    def transcript_upload(transcript, folder_id):
        filename = 'transcript.txt'
        with open(filename, 'w') as f:
            f.write(transcript)
        file_metadata = {
            'name': filename,
            'parents': [folder_id],
            'mimeType': 'application/vnd.google-apps.file'
        }
        media = MediaFileUpload(filename, mimetype='text/plain') 
        file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        print(f'Transcript file uploaded. File ID: {file.get("id")}.')
    
    def photo_upload(photo, folder_id):
        photo = Memory.photos
        filename = photo.get('description')
        with open(filename, 'wb') as f:
            f.write(photo.get('base64'))
        file_metadata = {
            'name': filename,
            'parents': [folder_id],
            'mimeType': 'image/jpeg'
        }
        media = MediaFileUpload(filename, mimetype='image/jpeg')
        file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        print(f'Photo uploaded. File ID: {file.get("id")}.')
        
        pref_url = 'https://localhost:3000/user_preferences'
        response = requests.get(pref_url)
        for i in response:
            if response[i] == 'Photo':
                photo_upload(photo, folder_id)
            if response[i] == 'Transcription':
                transcript_upload(transcript, folder_id)
            else:
                return None
        EndpointResponse.message = 'Files uploaded successfully'
        return EndpointResponse
    
    
        
    
