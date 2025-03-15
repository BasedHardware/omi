from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from openai import OpenAI
import pinecone
import os
from datetime import datetime, timedelta

 router = APIRouter(prefix="/google_calendar", tags=["google_calendar"])

# OAuth 2.0 scopes
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), "../credentials.json")

# In-memory credentials (simple for testing)
stored_credentials = None

@router.get("/auth")
def initiate_auth():
 """Redirects to Google for authentication."""
 if not os.path.exists(CREDENTIALS_FILE):
 raise HTTPException(status_code=500, detail="Add credentials.json to backend/")
 flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
 flow.redirect_uri = "http://localhost:8000/google_calendar/callback"
 authorization_url, _ = flow.authorization_url(prompt="consent")
 return RedirectResponse(authorization_url)

@router.get("/callback")
def auth_callback(code: str):
 """Stores credentials after Google redirect."""
 global stored_credentials
 flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
 flow.redirect_uri = "http://localhost:8000/google_calendar/callback"
 flow.fetch_token(code=code)
 stored_credentials = flow.credentials
 return {"message": "Authenticated"}

@router.get("/sync")
def sync_calendar():
 """Fetches events, converts to text, and stores in Pinecone memory."""
 global stored_credentials
 if not stored_credentials:
 raise HTTPException(status_code=401, detail="Authenticate first at /google_calendar/auth")

 # Fetch events
 service = build('calendar', 'v3', credentials=stored_credentials)
 now = datetime.utcnow().isoformat() + 'Z'
 end = (datetime.utcnow() + timedelta(days=30)).isoformat() + 'Z'
 events_result = service.events().list(calendarId='primary', timeMin=now, timeMax=end,
 maxResults=10, singleEvents=True,
 orderBy='startTime').execute()
 events = events_result.get('items', [])

 # Convert to text
 text = ""
 for event in events:
 start = event['start'].get('dateTime', event['start'].get('date'))
 end = event['end'].get('dateTime', event['end'].get('date'))
 text += f"{event.get('summary', 'No Title')} - {start} to {end}\n"

 # Store in Pinecone memory
 client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
 pinecone.init(api_key=os.environ.get("PINECONE_API_KEY"), environment="us-west1-gcp")
 index = pinecone.Index(os.environ.get("PINECONE_INDEX_NAME", "omi-memory"))
 response = client.embeddings.create(model="text-embedding-ada-002", input=text or "No events")
 embedding = response.data[0].embedding
 index.upsert([(f"cal_{datetime.now().isoformat()}", embedding, {"text": text, "source": "google_calendar"})])

 return {"message": "Events synced to memory", "events_text": text}
