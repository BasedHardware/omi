from fastapi import APIRouter

import requests

router = APIRouter()

@router.post('/oauth' , tags=['google_pauth'])
def get_token(CLIENT_ID: str, CLIENT_SECRET: str, code: str):
    url = 'https://oauth2.googleapis.com/token'
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    data = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'code': code,
        'redirect_uri': 'https://localhost:3000',
        'grant_type': 'authorization_code'
    }
    response = requests.post(url, headers=headers, data=data)
    Access_token = response.json()['access_token']
    Refresh_token = response.json()['refresh_token']
    return Access_token,Refresh_token

