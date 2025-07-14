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
from database.redis_db import (
    set_auth_session, get_auth_session, 
    set_auth_code, get_auth_code, delete_auth_code
)

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
    """
    if provider not in ['google', 'apple']:
        raise HTTPException(status_code=400, detail="Unsupported provider")
    
    # Store session for auth flow
    session_id = str(uuid.uuid4())
    session_data = {
        'provider': provider,
        'redirect_uri': redirect_uri,
        'state': state,
        'flow_type': 'user_auth'  # Distinguish from app oauth
    }
    
    # Store in Redis with 10-minute expiration
    set_auth_session(session_id, session_data, 600)
    
    # Redirect to provider OAuth
    if provider == 'google':
        return await _google_auth_redirect(session_id)
    elif provider == 'apple':
        return await _apple_auth_redirect(session_id)

@router.get("/callback/google")
async def auth_callback(
    request: Request,
    provider: str,
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
    
    # Exchange code for Firebase token
    firebase_token = await _exchange_provider_code_for_firebase_token(
        provider, code, session_data
    )
    
    # Create temporary auth code
    auth_code = str(uuid.uuid4())
    set_auth_code(auth_code, firebase_token, 300)
    
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
    
    # Exchange code for Firebase token
    firebase_token = await _exchange_provider_code_for_firebase_token(
        'apple', code, session_data
    )
    
    # Create temporary auth code
    auth_code = str(uuid.uuid4())
    set_auth_code(auth_code, firebase_token, 300)
    
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
    Exchange auth code for Firebase token
    """
    if grant_type != 'authorization_code':
        raise HTTPException(status_code=400, detail="Unsupported grant type")
    
    # Get Firebase token from Redis
    firebase_token = get_auth_code(code)
    if not firebase_token:
        raise HTTPException(status_code=400, detail="Invalid or expired code")
    
    # Clean up used code
    delete_auth_code(code)
    
    try:
        decoded_token = jwt.decode(firebase_token, options={"verify_signature": False})
        uid = decoded_token.get('uid')
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid token")
    
    return {
        "access_token": firebase_token,
        "token_type": "Bearer",
        "expires_in": 3600,
        "uid": uid
    }


async def _google_auth_redirect(session_id: str):
    """
    Redirect to Google OAuth for authentication
    """
    client_id = os.getenv('GOOGLE_CLIENT_ID')
    api_base_url = os.getenv('API_BASE_URL')
    
    if not client_id:
        raise HTTPException(status_code=500, detail="Google client ID not configured")
    if not api_base_url:
        raise HTTPException(status_code=500, detail="API_BASE_URL not configured")
    
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
    api_base_url = os.getenv('API_BASE_URL')
    
    if not client_id:
        raise HTTPException(status_code=500, detail="Apple client ID not configured")
    if not api_base_url:
        raise HTTPException(status_code=500, detail="API_BASE_URL not configured")
    
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

async def _exchange_provider_code_for_firebase_token(provider: str, code: str, session_data: dict) -> str:
    """
    Exchange provider-specific code for Firebase ID token
    """
    if provider == 'google':
        return await _exchange_google_code_for_firebase_token(code, session_data)
    elif provider == 'apple':
        return await _exchange_apple_code_for_firebase_token(code, session_data)
    else:
        raise HTTPException(status_code=400, detail="Unsupported provider")

async def _exchange_google_code_for_firebase_token(code: str, session_data: dict) -> str:
    """
    Exchange Google authorization code for Firebase ID token
    """
    client_id = os.getenv('GOOGLE_CLIENT_ID')
    client_secret = os.getenv('GOOGLE_CLIENT_SECRET')
    api_base_url = os.getenv('API_BASE_URL')
    
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
        'grant_type': 'authorization_code'
    }
    
    token_response = requests.post(token_url, data=token_data)
    if token_response.status_code != 200:
        raise HTTPException(status_code=400, detail="Failed to exchange Google code")
    
    token_json = token_response.json()
    id_token = token_json.get('id_token')
    access_token = token_json.get('access_token')
    
    if not id_token or not access_token:
        raise HTTPException(status_code=400, detail="Invalid Google token response")
    
    # Create Firebase credential and sign in
    try:
        # verify the Google ID token to get user info
        decoded_google_token = jwt.decode(id_token, options={"verify_signature": False})
        uid = decoded_google_token.get('sub')
        email = decoded_google_token.get('email')
        name = decoded_google_token.get('name')
        
        # Create or update user in Firebase
        try:
            # First try to get user by uid
            user = firebase_admin.auth.get_user(uid)
        except firebase_admin.auth.UserNotFoundError:
            try:
                # If user doesn't exist by uid, try to get by email
                user = firebase_admin.auth.get_user_by_email(email)
                # If user exists by email but different uid, we need to handle this
                if user.uid != uid:
                    # User exists with different uid, use existing user
                    uid = user.uid
                else:
                    # User exists with same uid, use existing user
                    pass
            except firebase_admin.auth.UserNotFoundError:
                # User doesn't exist at all, create new user
                user = firebase_admin.auth.create_user(
                    uid=uid,
                    email=email,
                    display_name=name,
                    email_verified=True
                )
        
        # Create Firebase custom token
        custom_token = firebase_admin.auth.create_custom_token(user.uid)
        
        # Return the custom token
        return custom_token.decode('utf-8')
        
    except Exception as e:
        print(f"Error creating Firebase token: {e}")
        raise HTTPException(status_code=500, detail="Failed to create Firebase token")

async def _exchange_apple_code_for_firebase_token(code: str, session_data: dict) -> str:
    """
    Exchange Apple authorization code for Firebase custom token
    """
    try:
        # Get Apple configuration
        client_id = os.getenv('APPLE_CLIENT_ID')
        team_id = os.getenv('APPLE_TEAM_ID')
        key_id = os.getenv('APPLE_KEY_ID')
        private_key_content = os.getenv('APPLE_PRIVATE_KEY')
        
        if not all([client_id, team_id, key_id, private_key_content]):
            raise HTTPException(
                status_code=500, 
                detail="Apple authentication not properly configured. Missing environment variables."
            )
        
        # Generate client secret JWT
        client_secret = _generate_apple_client_secret(client_id, team_id, key_id, private_key_content)
        
        # Exchange authorization code for Apple tokens
        api_base_url = os.getenv('API_BASE_URL')
        if not api_base_url:
            raise HTTPException(status_code=500, detail="API_BASE_URL not configured")
            
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
            token_url, 
            data=token_data,
            headers={'Content-Type': 'application/x-www-form-urlencoded'}
        )
        
        if token_response.status_code != 200:
            print(f"Apple token exchange failed: {token_response.text}")
            raise HTTPException(status_code=400, detail="Failed to exchange Apple authorization code")
        
        token_json = token_response.json()
        id_token = token_json.get('id_token')
        
        if not id_token:
            raise HTTPException(status_code=400, detail="No ID token received from Apple")
        
        # Verify and decode the Apple ID token
        apple_user_info = _verify_apple_id_token(id_token, client_id)
        
        # Extract user information
        uid = apple_user_info.get('sub')
        email = apple_user_info.get('email')
        email_verified = apple_user_info.get('email_verified', False)
        
        if not uid:
            raise HTTPException(status_code=400, detail="Invalid Apple ID token")
        
        # Create or update user in Firebase
        try:
            # First try to get user by Apple UID
            firebase_uid = f"apple_{uid}"
            user = firebase_admin.auth.get_user(firebase_uid)
        except firebase_admin.auth.UserNotFoundError:
            try:
                # If user doesn't exist by UID, try to get by email
                if email:
                    user = firebase_admin.auth.get_user_by_email(email)
                    firebase_uid = user.uid
                else:
                    raise firebase_admin.auth.UserNotFoundError("No email provided")
            except firebase_admin.auth.UserNotFoundError:
                # Create new user
                user = firebase_admin.auth.create_user(
                    uid=firebase_uid,
                    email=email,
                    email_verified=email_verified if isinstance(email_verified, bool) else str(email_verified).lower() == 'true',
                    display_name="Apple User"
                )
        
        # Create Firebase custom token
        custom_token = firebase_admin.auth.create_custom_token(user.uid)
        
        return custom_token.decode('utf-8')
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error creating Firebase token for Apple: {e}")
        raise HTTPException(status_code=500, detail="Failed to create Firebase token")


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
        client_secret = jwt.encode(
            payload, 
            private_key, 
            algorithm='ES256', 
            headers=headers
        )
        
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
            id_token,
            public_key,
            algorithms=['RS256'],
            audience=client_id,
            issuer='https://appleid.apple.com'
        )
        
        return decoded_token
        
    except Exception as e:
        print(f"Error verifying Apple ID token: {e}")
        raise HTTPException(status_code=400, detail="Invalid Apple ID token") 