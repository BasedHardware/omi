import requests
from models import  Memory , EndpointResponse
from oauth import get_token
from fastapi import Request, Form, APIRouter

router = APIRouter()

@router.post('/oauth/create_event' , tags=['create_event'])
def createEvent(summary: str = Form(...), location: str = Form(...), description =  Memory.transcript_segments, start=  Memory.started_at, end=  Memory.finished_at):
    Acess_Token = get_token.Acess_token
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

