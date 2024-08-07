import os
import json
import requests
from fastapi import APIRouter, HTTPException
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

router = APIRouter()

# OAuth 2.0 setup
CLIENT_SECRETS_FILE = "client_secret.json"
SCOPES = ['https://www.googleapis.com/auth/calendar']

# Store OAuth tokens securely
def store_credentials(uid: str, credentials: Credentials):
    with open(f'tokens/{uid}.json', 'w') as token:
        token.write(credentials.to_json())

def load_credentials(uid: str) -> Credentials:
    with open(f'tokens/{uid}.json', 'r') as token:
        return Credentials.from_authorized_user_info(json.load(token))

# OAuth authorization
@router.get("/authorize")
def authorize(uid: str):
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri='http://localhost:8000/oauth2callback'
    )
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true'
    )
    return {"authorization_url": authorization_url, "state": state}

@router.get("/oauth2callback")
def oauth2callback(uid: str, state: str, code: str):
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        state=state,
        redirect_uri='http://localhost:8000/oauth2callback'
    )
    flow.fetch_token(code=code)
    credentials = flow.credentials
    store_credentials(uid, credentials)
    return {"message": "Authorization successful"}

# Use Google Calendar API to manage events
def create_calendar_event(uid: str, event: dict):
    credentials = load_credentials(uid)
    service = build('calendar', 'v3', credentials=credentials)
    event = service.events().insert(calendarId='primary', body=event).execute()
    return event

@router.post("/create_event")
def create_event(uid: str, event: dict):
    try:
        created_event = create_calendar_event(uid, event)
        return {"message": "Event created successfully", "event": created_event}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
