import requests
from models import Event , Memory , EndpointResponse

from fastapi import Request, Form, APIRouter

router = APIRouter()

@router.post('/oauth/create_event' , tags=['google_calendar_api'])
def get_token(request: Request, CLIENT_ID: str = Form(...), CLIENT_SECRET: str = Form(...), REDIRECT_URI: str = Form(...), summary: str = Form(...), location: str = Form(...), description =  Memory.transcript_segments, start=  Memory.started_at, end=  Memory.finished_at):
    params = {
        "Client_ID" : CLIENT_ID,
        "Client_Sectret" : CLIENT_SECRET,
        "Redirect_URI" : REDIRECT_URI,
        "grant_type" : "authorization_code"
    }
    response = requests.post("https://oauth2.googleapis.com/token", params=params)
    Refresh_Token = response.json().get("refresh_token")
    Acess_Token = response.json().get("access_token")
    headers = {
        "Authorization" : f"Bearer {Acess_Token}"
    }
    data = {
        "summary" : summary,
        "location" : location,
        "description" : description,
        "start" : {
            "dateTime" : start,
        },
        "end" : {
            "dateTime" : end
        }
    }
    response = requests.post("https://www.googleapis.com/calendar/v3/calendars/primary/events", headers=headers, data=data)
    EndpointResponse(response.status_code, response.json())
    return response.json()





