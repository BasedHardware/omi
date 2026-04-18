from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from firebase_admin import auth
import os
import logging

from utils.http_client import get_auth_client
from utils.other.endpoints import rate_limit_dependency

logger = logging.getLogger(__name__)

router = APIRouter()


class UserCredentials(BaseModel):
    email: str
    password: str


@router.post(
    "/v1/signin",
    dependencies=[Depends(rate_limit_dependency(endpoint="signin", requests_per_window=5, window_seconds=60))],
)
async def sign_in(credentials: UserCredentials):
    try:
        api_key = os.getenv("CUSTOM_AUTH_FIREBASE_API_KEY")
        url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={api_key}"
        payload = {
            "email": credentials.email,
            "password": credentials.password,
            "returnSecureToken": True,
        }
        client = get_auth_client()
        response = await client.post(url, json=payload)
        if response.status_code != 200:
            # print(response.json())
            raise HTTPException(status_code=401, detail="Invalid credentials")

        firebase_token = response.json().get("idToken")
        decoded_token = auth.verify_id_token(firebase_token)
        return {
            "status": "ok",
            "token": firebase_token,
            "uid": decoded_token["uid"],
            "name": decoded_token["name"],
            "auth_time": decoded_token["auth_time"],
            "exp": decoded_token["exp"],
        }
    except Exception as e:
        logger.error(f"error authenticating {e}")
        raise HTTPException(status_code=400, detail=str(e))
