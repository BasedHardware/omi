from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from firebase_admin import auth
import os
import requests

router = APIRouter()


class UserCredentials(BaseModel):
    email: str
    password: str
    name: Optional[str] = None


@router.post("/v1/signup")
def sign_up(credentials: UserCredentials):
    try:
        user = auth.create_user(
            email=credentials.email,
            password=credentials.password,
            display_name=credentials.name,
        )
        return {"status": "ok", "message": "User created successfully", "uid": user.uid}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/v1/signin")
def sign_in(credentials: UserCredentials):
    try:
        api_key = os.getenv("CUSTOM_AUTH_FIREBASE_API_KEY")
        url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={api_key}"
        payload = {
            "email": credentials.email,
            "password": credentials.password,
            "returnSecureToken": True,
        }
        response = requests.post(url, json=payload)
        if response.status_code != 200:
            print(response.json())
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
        print("error authenticating", e)
        raise HTTPException(status_code=400, detail=str(e))
