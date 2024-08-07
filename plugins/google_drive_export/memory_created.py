import os
import requests
from fastapi import APIRouter, HTTPException, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from models import Memory, EndpointResponse

router = APIRouter()
templates = Jinja2Templates(directory="templates")

SCOPES = ['https://www.googleapis.com/auth/drive.file']
SERVICE_ACCOUNT_FILE = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')

credentials = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES)
drive_service = build('drive', 'v3', credentials=credentials)


@router.get('/setup-google-drive', response_class=HTMLResponse, tags=['google_drive_export'])
async def setup_google_drive(request: Request, uid: str):
    if not uid:
        raise HTTPException(status_code=400, detail='UID is required')
    return templates.TemplateResponse("setup_google_drive.html", {"request": request, "uid": uid})


@router.post('/creds/google-drive', response_class=HTMLResponse, tags=['google_drive_export'])
def creds_google_drive(request: Request, uid: str = Form(...), folder_id: str = Form(...)):
    if not folder_id:
        raise HTTPException(status_code=400, detail='Folder ID is required')
    store_google_drive_folder_id(uid, folder_id)
    return templates.TemplateResponse("okpage.html", {"request": request, "uid": uid})


@router.get('/setup/google-drive', tags=['google_drive_export'])
def is_setup_completed(uid: str):
    folder_id = get_google_drive_folder_id(uid)
    return {'is_setup_completed': folder_id is not None}


@router.post('/google-drive', tags=['google_drive_export', 'memory_created'], response_model=EndpointResponse)
def google_drive_export(memory: Memory, uid: str):
    folder_id = get_google_drive_folder_id(uid)
    if not folder_id:
        return {'message': 'Your Google Drive plugin is not setup properly. Check your plugin settings.'}

    file_metadata = {
        'name': f'{memory.structured.title}.txt',
        'parents': [folder_id]
    }
    media = MediaFileUpload(memory.get_transcript(), mimetype='text/plain')
    file = drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
    return {'message': f'File ID: {file.get("id")}'}
