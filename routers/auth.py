import os
import uuid
import json
import hashlib
import time
import requests
import jwt
from typing import Optional
from urllib.parse import quote
from cryptography.hazmat.primitives import serialization
from jwt.algorithms import RSAAlgorithm
from fastapi import APIRouter, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import firebase_admin.auth
from database.redis_db import set_auth_session, get_auth_session, set_auth_code, get_auth_code, delete_auth_code

router = APIRouter(
    prefix="/v1/auth",
    tags=["authentication"],
)


@router.get("/authorize")
async def auth_authorize(
    request: Request,
    provider: str,  # 'google', 'apple'
    redirect_uri: str,
    state: Optional[str] = None,
):
    """
    User authentication authorization endpoint for the main Omi app
    Supports both initial sign-in and account linking flows
    """
    if provider not in ['google', 'apple']:
        raise HTTPException(status_code=400, detail="Unsupported provider")

    # Store session for auth flow
    session_id = str(uuid.uuid4())
    session_data = {
        'provider': provider,
        'redirect_uri': redirect_uri,
        'state': state,
        'flow_type': 'user_auth',  # Distinguish from app oauth
    }

    # Store in Redis with 5-minute expiration
    set_auth_session(session_id, session_data, 300)

    # Redirect to provider OAuth
    if provider == 'google':
        return await _google_auth_redirect(session_id)
    elif provider == 'apple':
        return await _apple_auth_redirect(session_id)


@router.get("/callback/google")
async def auth_callback_google(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
):
    """
    Google authentication callback handler (GET method)
    """
    if error:
        raise HTTPException(status_code=400, detail=f"Auth error: {error}")

    # Retrieve session
    session_data = get_auth_session(state)
    if not session_data:
        raise HTTPException(status_code=400, detail="Invalid auth session")

    # Exchange code for OAuth credentials
    oauth_credentials = await _exchange_provider_code_for_oauth_credentials('google', code, session_data)

    # Create temporary auth code
    auth_code = str(uuid.uuid4())
    set_auth_code(auth_code, oauth_credentials, 300)

    # Redirect back to app
    redirect_url = f"{session_data['redirect_uri']}?code={auth_code}&state={session_data['state'] or ''}"
    return RedirectResponse(url=redirect_url)


@router.post("/callback/apple")
async def auth_callback_apple_post(
    request: Request,
    code: str = Form(...),
    state: str = Form(...),
    error: Optional[str] = Form(None),
):
    """
    Apple authentication callback handler (POST method)
    Apple uses form_post response_mode, so we need a separate POST endpoint
    """
    if error:
        raise HTTPException(status_code=400, detail=f"Auth error: {error}")

    # Retrieve session
    session_data = get_auth_session(state)
    if not session_data:
        raise HTTPException(status_code=400, detail="Invalid auth session")

    # Exchange code for OAuth credentials
    oauth_credentials = await _exchange_provider_code_for_oauth_credentials('apple', code, session_data)

    # Create temporary auth code
    auth_code = str(uuid.uuid4())
    set_auth_code(auth_code, oauth_credentials, 300)

    # Redirect back to app
    redirect_url = f"{session_data['redirect_uri']}?code={auth_code}&state={session_data['state'] or ''}"
    return RedirectResponse(url=redirect_url)


@router.post("/token")
async def auth_token(
    request: Request,
    grant_type: str = Form(...),
    code: str = Form(...),
    redirect_uri: str = Form(...),
):
    """
    Exchange auth code for OAuth credentials
    Used for both initial sign-in and account linking flows
    """
    if grant_type != 'authorization_code':
        raise HTTPException(status_code=400, detail="Unsupported grant type")

    # Get OAuth credentials from Redis
    oauth_credentials_json = get_auth_code(code)
    if not oauth_credentials_json:
        raise HTTPException(status_code=400, detail="Invalid or expired code")

    # Clean up used code
    delete_auth_code(code)

    try:
        oauth_credentials = json.loads(oauth_credentials_json)
        provider = oauth_credentials.get('provider')

        return {
            "provider": provider,
            "id_token": oauth_credentials.get('id_token'),
            "access_token": oauth_credentials.get('access_token'),
            "provider_id": oauth_credentials.get('provider_id'),
            "token_type": "Bearer",
            "expires_in": 3600,
        }

    except Exception as e:
        print(f"Error parsing OAuth credentials: {e}")
        raise HTTPException(status_code=400, detail="Invalid OAuth credentials")


async def _google_auth_redirect(session_id: str):
    """
    Redirect to Google OAuth for authentication
    """
    client_id = os.getenv('GOOGLE_CLIENT_ID')
    api_base_url = os.getenv('BASE_API_URL')

    if not client_id:
        raise HTTPException(status_code=500, detail="Google client ID not configured")
    if not api_base_url:
        raise HTTPException(status_code=500, detail="BASE_API_URL not configured")

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


async def _apple_auth_redirect(session_id: str):
    """
    Redirect to Apple OAuth for authentication
    """
    client_id = os.getenv('APPLE_CLIENT_ID')
    api_base_url = os.getenv('BASE_API_URL')

    if not client_id:
        raise HTTPException(status_code=500, detail="Apple client ID not configured")
    if not api_base_url:
        raise HTTPException(status_code=500, detail="BASE_API_URL not configured")

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


async def _exchange_provider_code_for_oauth_credentials(provider: str, code: str, session_data: dict) -> str:
    """
    Exchange provider-specific code for OAuth credentials
    """
    if provider == 'google':
        return await _exchange_google_code_for_oauth_credentials(code, session_data)
    elif provider == 'apple':
        return await _exchange_apple_code_for_oauth_credentials(code, session_data)
    else:
        raise HTTPException(status_code=400, detail="Unsupported provider")


async def _exchange_google_code_for_oauth_credentials(code: str, session_data: dict) -> str:
    """
    Exchange Google authorization code for Google OAuth tokens
    """
    client_id = os.getenv('GOOGLE_CLIENT_ID')
    client_secret = os.getenv('GOOGLE_CLIENT_SECRET')
    api_base_url = os.getenv('BASE_API_URL')

    if not all([client_id, client_secret, api_base_url]):
        raise HTTPException(status_code=500, detail="Google OAuth not properly configured")

    callback_url = f"{api_base_url}/v1/auth/callback/google"

    # Exchange code for Google tokens
    token_url = "https://oauth2.googleapis.com/token"
    token_data = {
        'code': code,
        'client_id': client_id,
        'client_secret': client_secret,
        'redirect_uri': callback_url,
        'grant_type': 'authorization_code',
    }

    token_response = requests.post(token_url, data=token_data)
    if token_response.status_code != 200:
        raise HTTPException(status_code=400, detail="Failed to exchange Google code")

    token_json = token_response.json()
    id_token = token_json.get('id_token')
    access_token = token_json.get('access_token')

    if not id_token or not access_token:
        raise HTTPException(status_code=400, detail="Invalid Google token response")

    # Return OAuth credentials for client-side Firebase authentication
    oauth_credentials = {
        'provider': 'google',
        'id_token': id_token,
        'access_token': access_token,
        'provider_id': 'google.com',
    }

    return json.dumps(oauth_credentials)


async def _exchange_apple_code_for_oauth_credentials(code: str, session_data: dict) -> str:
    """
    Exchange Apple authorization code for Apple OAuth tokens
    """
    try:
        # Get Apple configuration
        client_id = os.getenv('APPLE_CLIENT_ID')
        team_id = os.getenv('APPLE_TEAM_ID')
        key_id = os.getenv('APPLE_KEY_ID')
        private_key_content = os.getenv('APPLE_PRIVATE_KEY')

        if not all([client_id, team_id, key_id, private_key_content]):
            raise HTTPException(
                status_code=500, detail="Apple authentication not properly configured. Missing environment variables."
            )

        # Generate client secret JWT
        client_secret = _generate_apple_client_secret(client_id, team_id, key_id, private_key_content)

        # Exchange authorization code for Apple tokens
        api_base_url = os.getenv('BASE_API_URL')
        if not api_base_url:
            raise HTTPException(status_code=500, detail="BASE_API_URL not configured")

        callback_url = f"{api_base_url}/v1/auth/callback/apple"

        token_url = "https://appleid.apple.com/auth/token"
        token_data = {
            'client_id': client_id,
            'client_secret': client_secret,
            'code': code,
            'grant_type': 'authorization_code',
            'redirect_uri': callback_url,
        }

        token_response = requests.post(
            token_url, data=token_data, headers={'Content-Type': 'application/x-www-form-urlencoded'}
        )

        if token_response.status_code != 200:
            print(f"Apple token exchange failed: {token_response.text}")
            raise HTTPException(status_code=400, detail="Failed to exchange Apple authorization code")

        token_json = token_response.json()
        id_token = token_json.get('id_token')
        access_token = token_json.get('access_token')  # Apple typically returns access_token

        if not id_token:
            raise HTTPException(status_code=400, detail="No ID token received from Apple")

        # Return OAuth credentials for client-side Firebase authentication
        oauth_credentials = {
            'provider': 'apple',
            'id_token': id_token,
            'access_token': access_token,
            'provider_id': 'apple.com',
        }

        return json.dumps(oauth_credentials)

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error exchanging Apple code for tokens: {e}")
        raise HTTPException(status_code=500, detail="Failed to exchange Apple code for tokens")


def _generate_apple_client_secret(client_id: str, team_id: str, key_id: str, private_key_content: str) -> str:
    """
    Generate Apple client secret JWT as per Apple's requirements
    https://developer.apple.com/documentation/signinwithapplerestapi/generate_and_validate_tokens
    """
    try:
        # Load the private key from direct PEM content
        private_key = serialization.load_pem_private_key(
            private_key_content.encode('utf-8'),
            password=None,
        )

        # Create the JWT payload
        now = int(time.time())
        payload = {
            'iss': team_id,
            'iat': now,
            'exp': now + 3600,  # Token expires in 1 hour
            'aud': 'https://appleid.apple.com',
            'sub': client_id,
        }

        # Create the JWT headers
        headers = {
            'alg': 'ES256',
            'kid': key_id,
        }

        # Generate the client secret
        client_secret = jwt.encode(payload, private_key, algorithm='ES256', headers=headers)

        return client_secret

    except Exception as e:
        print(f"Error generating Apple client secret: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate Apple client secret")


def _verify_apple_id_token(id_token: str, client_id: str) -> dict:
    """
    Verify Apple ID token and extract user information
    """
    try:
        # Get Apple's public keys
        apple_keys_response = requests.get('https://appleid.apple.com/auth/keys')
        if apple_keys_response.status_code != 200:
            raise Exception("Failed to fetch Apple's public keys")

        apple_keys = apple_keys_response.json()

        # Decode the token header to get the key ID
        unverified_header = jwt.get_unverified_header(id_token)
        key_id = unverified_header.get('kid')

        if not key_id:
            raise Exception("No key ID found in token header")

        # Find the matching public key
        public_key = None
        for key in apple_keys['keys']:
            if key['kid'] == key_id:
                public_key = RSAAlgorithm.from_jwk(key)
                break

        if not public_key:
            raise Exception("No matching public key found")

        # Verify and decode the token
        decoded_token = jwt.decode(
            id_token, public_key, algorithms=['RS256'], audience=client_id, issuer='https://appleid.apple.com'
        )

        return decoded_token

    except Exception as e:
        print(f"Error verifying Apple ID token: {e}")
        raise HTTPException(status_code=400, detail="Invalid Apple ID token")
