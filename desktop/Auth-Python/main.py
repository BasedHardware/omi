"""
Local auth backend for OMI Computer macOS app.
This fixes the hardcoded redirect_uri issue in the production backend.
"""
import os
import uuid
import json
import time
import requests
import jwt
from typing import Optional
from urllib.parse import quote
from cryptography.hazmat.primitives import serialization
from fastapi import FastAPI, Request, HTTPException, Form
from fastapi.responses import RedirectResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, auth as firebase_auth
import pathlib

# Load environment variables
load_dotenv()

app = FastAPI(title="OMI Computer Auth Backend")

# Set up Jinja2 templates
templates_path = pathlib.Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(templates_path))

# Simple in-memory session storage (for local dev only)
auth_sessions = {}
auth_codes = {}

# Initialize Firebase Admin SDK
# Support both file path (local dev) and JSON string (Cloud Run)
firebase_creds_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
firebase_creds_json = os.getenv('FIREBASE_CREDENTIALS_JSON')

if firebase_creds_json:
    # Cloud Run: credentials as JSON string
    import json as json_module
    cred_dict = json_module.loads(firebase_creds_json)
    cred = credentials.Certificate(cred_dict)
    firebase_admin.initialize_app(cred)
    print("Firebase Admin SDK initialized from FIREBASE_CREDENTIALS_JSON")
elif firebase_creds_path and os.path.exists(firebase_creds_path):
    # Local dev: credentials as file path
    cred = credentials.Certificate(firebase_creds_path)
    firebase_admin.initialize_app(cred)
    print(f"Firebase Admin SDK initialized with {firebase_creds_path}")
else:
    print("Warning: Firebase credentials not configured")


def set_auth_session(session_id: str, data: dict, ttl: int = 300):
    """Store auth session (in-memory for local dev)"""
    auth_sessions[session_id] = {
        'data': data,
        'expires': time.time() + ttl
    }


def get_auth_session(session_id: str) -> Optional[dict]:
    """Get auth session"""
    session = auth_sessions.get(session_id)
    if session and session['expires'] > time.time():
        return session['data']
    return None


def set_auth_code(code: str, data: str, ttl: int = 300):
    """Store auth code"""
    auth_codes[code] = {
        'data': data,
        'expires': time.time() + ttl
    }


def get_auth_code(code: str) -> Optional[str]:
    """Get auth code data"""
    code_data = auth_codes.get(code)
    if code_data and code_data['expires'] > time.time():
        return code_data['data']
    return None


def delete_auth_code(code: str):
    """Delete auth code"""
    auth_codes.pop(code, None)


@app.get("/.well-known/apple-developer-domain-association.txt")
async def apple_domain_association():
    """Apple domain verification file - get the content from Apple Developer Portal"""
    # This can be updated with the actual association content from Apple
    return PlainTextResponse("")


@app.get("/v1/auth/authorize")
async def auth_authorize(
    request: Request,
    provider: str,
    redirect_uri: str,
    state: Optional[str] = None,
):
    """Start OAuth flow"""
    if provider not in ['google', 'apple']:
        raise HTTPException(status_code=400, detail="Unsupported provider")

    session_id = str(uuid.uuid4())
    session_data = {
        'provider': provider,
        'redirect_uri': redirect_uri,
        'state': state,
    }
    set_auth_session(session_id, session_data, 300)

    if provider == 'apple':
        return await _apple_auth_redirect(session_id)
    elif provider == 'google':
        return await _google_auth_redirect(session_id)
    else:
        raise HTTPException(status_code=400, detail="Unsupported provider")


@app.post("/v1/auth/callback/apple")
async def auth_callback_apple_post(
    request: Request,
    code: str = Form(...),
    state: str = Form(...),
    error: Optional[str] = Form(None),
):
    """Apple OAuth callback (POST - form_post mode)"""
    if error:
        raise HTTPException(status_code=400, detail=f"Auth error: {error}")

    session_data = get_auth_session(state)
    if not session_data:
        raise HTTPException(status_code=400, detail="Invalid auth session")

    # Exchange Apple code for tokens
    oauth_credentials = await _exchange_apple_code(code, session_data)

    # Create temporary auth code
    auth_code = str(uuid.uuid4())
    set_auth_code(auth_code, oauth_credentials, 300)

    # Return HTML page that redirects to the app's custom URL scheme
    # FIXED: Pass redirect_uri to template instead of hardcoding
    return templates.TemplateResponse(
        "auth_callback.html",
        {
            "request": request,
            "code": auth_code,
            "state": session_data.get('state') or '',
            "redirect_uri": session_data.get('redirect_uri', 'omi-computer://auth/callback'),
        },
    )


@app.get("/v1/auth/callback/google")
async def auth_callback_google(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
):
    """Google OAuth callback (GET - redirect mode)"""
    if error:
        raise HTTPException(status_code=400, detail=f"Auth error: {error}")

    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state")

    session_data = get_auth_session(state)
    if not session_data:
        raise HTTPException(status_code=400, detail="Invalid auth session")

    # Exchange Google code for tokens
    oauth_credentials = await _exchange_google_code(code, session_data)

    # Create temporary auth code
    auth_code = str(uuid.uuid4())
    set_auth_code(auth_code, oauth_credentials, 300)

    # Return HTML page that redirects to the app's custom URL scheme
    return templates.TemplateResponse(
        "auth_callback.html",
        {
            "request": request,
            "code": auth_code,
            "state": session_data.get('state') or '',
            "redirect_uri": session_data.get('redirect_uri', 'omi-computer://auth/callback'),
        },
    )


@app.post("/v1/auth/token")
async def auth_token(
    request: Request,
    grant_type: str = Form(...),
    code: str = Form(...),
    redirect_uri: str = Form(...),
    use_custom_token: bool = Form(False),
):
    """Exchange auth code for tokens"""
    if grant_type != 'authorization_code':
        raise HTTPException(status_code=400, detail="Unsupported grant type")

    oauth_credentials_json = get_auth_code(code)
    if not oauth_credentials_json:
        raise HTTPException(status_code=400, detail="Invalid or expired code")

    delete_auth_code(code)

    try:
        oauth_credentials = json.loads(oauth_credentials_json)
        provider = oauth_credentials.get('provider')
        id_token = oauth_credentials.get('id_token')
        access_token = oauth_credentials.get('access_token')

        response = {
            "provider": provider,
            "id_token": id_token,
            "access_token": access_token,
            "provider_id": oauth_credentials.get('provider_id'),
            "token_type": "Bearer",
            "expires_in": 3600,
        }

        if use_custom_token:
            try:
                custom_token = await _generate_custom_token(provider, id_token, access_token)
                response["custom_token"] = custom_token
            except Exception as e:
                print(f"Error generating custom token: {e}")

        return response

    except Exception as e:
        print(f"Error parsing OAuth credentials: {e}")
        raise HTTPException(status_code=400, detail="Invalid OAuth credentials")


async def _apple_auth_redirect(session_id: str):
    """Redirect to Apple OAuth"""
    client_id = os.getenv('APPLE_CLIENT_ID')
    api_base_url = os.getenv('BASE_API_URL', 'http://localhost:8080')

    if not client_id:
        raise HTTPException(status_code=500, detail="APPLE_CLIENT_ID not configured")

    callback_url = f"{api_base_url}/v1/auth/callback/apple"

    apple_auth_url = (
        f"https://appleid.apple.com/auth/authorize?"
        f"client_id={client_id}&"
        f"redirect_uri={callback_url}&"
        f"response_type=code&"
        f"scope=name email&"
        f"response_mode=form_post&"
        f"state={session_id}"
    )

    return RedirectResponse(url=apple_auth_url)


async def _google_auth_redirect(session_id: str):
    """Redirect to Google OAuth"""
    client_id = os.getenv('GOOGLE_CLIENT_ID')
    api_base_url = os.getenv('BASE_API_URL', 'http://localhost:8080')

    if not client_id:
        raise HTTPException(status_code=500, detail="GOOGLE_CLIENT_ID not configured")

    callback_url = f"{api_base_url}/v1/auth/callback/google"

    google_auth_url = (
        f"https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={quote(client_id)}&"
        f"redirect_uri={quote(callback_url)}&"
        f"response_type=code&"
        f"scope={quote('openid email profile')}&"
        f"state={quote(session_id)}"
    )

    return RedirectResponse(url=google_auth_url)


async def _exchange_apple_code(code: str, session_data: dict) -> str:
    """Exchange Apple authorization code for tokens"""
    client_id = os.getenv('APPLE_CLIENT_ID')
    team_id = os.getenv('APPLE_TEAM_ID')
    key_id = os.getenv('APPLE_KEY_ID')
    private_key_content = os.getenv('APPLE_PRIVATE_KEY')
    api_base_url = os.getenv('BASE_API_URL', 'http://localhost:8080')

    if not all([client_id, team_id, key_id, private_key_content]):
        raise HTTPException(status_code=500, detail="Apple auth not configured")

    # Generate client secret JWT
    client_secret = _generate_apple_client_secret(client_id, team_id, key_id, private_key_content)

    callback_url = f"{api_base_url}/v1/auth/callback/apple"

    token_response = requests.post(
        "https://appleid.apple.com/auth/token",
        data={
            'client_id': client_id,
            'client_secret': client_secret,
            'code': code,
            'grant_type': 'authorization_code',
            'redirect_uri': callback_url,
        },
        headers={'Content-Type': 'application/x-www-form-urlencoded'}
    )

    if token_response.status_code != 200:
        print(f"Apple token exchange failed: {token_response.text}")
        raise HTTPException(status_code=400, detail="Failed to exchange Apple code")

    token_json = token_response.json()
    id_token = token_json.get('id_token')
    access_token = token_json.get('access_token')

    if not id_token:
        raise HTTPException(status_code=400, detail="No ID token from Apple")

    return json.dumps({
        'provider': 'apple',
        'id_token': id_token,
        'access_token': access_token,
        'provider_id': 'apple.com',
    })


async def _exchange_google_code(code: str, session_data: dict) -> str:
    """Exchange Google authorization code for tokens"""
    client_id = os.getenv('GOOGLE_CLIENT_ID')
    client_secret = os.getenv('GOOGLE_CLIENT_SECRET')
    api_base_url = os.getenv('BASE_API_URL', 'http://localhost:8080')

    if not all([client_id, client_secret]):
        raise HTTPException(status_code=500, detail="Google auth not configured")

    callback_url = f"{api_base_url}/v1/auth/callback/google"

    token_response = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            'code': code,
            'client_id': client_id,
            'client_secret': client_secret,
            'redirect_uri': callback_url,
            'grant_type': 'authorization_code',
        },
    )

    if token_response.status_code != 200:
        print(f"Google token exchange failed: {token_response.text}")
        raise HTTPException(status_code=400, detail="Failed to exchange Google code")

    token_json = token_response.json()
    id_token = token_json.get('id_token')
    access_token = token_json.get('access_token')

    if not id_token:
        raise HTTPException(status_code=400, detail="No ID token from Google")

    return json.dumps({
        'provider': 'google',
        'id_token': id_token,
        'access_token': access_token,
        'provider_id': 'google.com',
    })


def _generate_apple_client_secret(client_id: str, team_id: str, key_id: str, private_key_content: str) -> str:
    """Generate Apple client secret JWT"""
    private_key = serialization.load_pem_private_key(
        private_key_content.encode('utf-8'),
        password=None,
    )

    now = int(time.time())
    payload = {
        'iss': team_id,
        'iat': now,
        'exp': now + 3600,
        'aud': 'https://appleid.apple.com',
        'sub': client_id,
    }

    return jwt.encode(payload, private_key, algorithm='ES256', headers={'kid': key_id})


async def _generate_custom_token(provider: str, id_token: str, access_token: str = None) -> str:
    """Generate Firebase custom token"""
    firebase_api_key = os.getenv('FIREBASE_API_KEY')
    if not firebase_api_key:
        raise Exception("FIREBASE_API_KEY not configured")

    # Sign in with OAuth credential using Firebase Auth REST API
    sign_in_url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithIdp?key={firebase_api_key}"

    # Set provider ID based on provider
    if provider == 'google':
        provider_id = 'google.com'
    elif provider == 'apple':
        provider_id = 'apple.com'
    else:
        raise Exception(f"Unsupported provider: {provider}")

    post_body = f'id_token={id_token}&providerId={provider_id}'
    if access_token:
        post_body += f'&access_token={access_token}'

    response = requests.post(sign_in_url, json={
        'postBody': post_body,
        'requestUri': 'http://localhost',
        'returnIdpCredential': True,
        'returnSecureToken': True,
    })

    if response.status_code != 200:
        print(f"Firebase sign-in failed: {response.text}")
        raise Exception(f"Firebase sign-in failed")

    result = response.json()
    firebase_uid = result.get('localId')

    if not firebase_uid:
        raise Exception("No Firebase UID returned")

    print(f"Firebase sign-in successful, UID: {firebase_uid}")

    # Create custom token
    custom_token = firebase_auth.create_custom_token(firebase_uid)
    return custom_token.decode('utf-8') if isinstance(custom_token, bytes) else custom_token


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
