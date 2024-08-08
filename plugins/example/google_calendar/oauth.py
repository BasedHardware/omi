import requests

from fastapi import Request, Form, APIRouter

router = APIRouter()

@router.post('/oauth' , tags = ['google_oauth'])
def get_token(request: Request, CLIENT_ID: str = Form(...), CLIENT_SECRET: str = Form(...), REDIRECT_URI: str = Form(...), code: str = Form(...)):
    params = {
        "client_id" : CLIENT_ID,
        "client_secret" : CLIENT_SECRET,
        "redirect_uri" : REDIRECT_URI,
        "code" : code,
        "grant_type" : "authorization_code"
    }
    response = requests.post("https://oauth2.googleapis.com/token", params=params)
    Acess_Token = response.json().get("access_token")
    Refresh_Token = response.json().get("refresh_token")
    return Acess_Token, Refresh_Token

