from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
import os
import secrets
import json
import base64
from datetime import datetime, timedelta, timezone
import httpx

import database.users as users_db
import database.redis_db as redis_db
from utils.other import endpoints as auth

router = APIRouter()

# OAuth state management
OAUTH_STATE_EXPIRY = 600  # 10 minutes

http_client: Optional[httpx.AsyncClient] = None

# Templates
templates = Jinja2Templates(directory="templates")

# OAuth provider configurations
OAUTH_CONFIGS = {
    'google_calendar': {'name': 'Google Calendar'},
    'whoop': {'name': 'Whoop'},
    'notion': {'name': 'Notion'},
    'twitter': {'name': 'Twitter'},
}


def get_http_client() -> httpx.AsyncClient:
    """Get or create the HTTP client instance."""
    global http_client
    if http_client is None:
        http_client = httpx.AsyncClient(timeout=10.0)
    return http_client


async def close_http_client():
    """Close the HTTP client and cleanup resources."""
    global http_client
    if http_client is not None:
        await http_client.aclose()
        http_client = None


def render_oauth_response(
    request: Request,
    app_key: str,
    success: bool = True,
    redirect_url: Optional[str] = None,
    error_type: Optional[str] = None,
) -> HTMLResponse:
    """
    Render OAuth callback response using template.

    Args:
        request: FastAPI request object
        app_key: Integration app key (google_calendar, whoop)
        success: Whether the OAuth flow was successful
        redirect_url: Deep link URL to redirect to (for success case)
        error_type: Type of error (missing_code, invalid_state, config_error, server_error)
    """
    config = OAUTH_CONFIGS.get(app_key, {'name': app_key.title()})

    if success:
        context = {
            'request': request,
            'title': f"{config['name']} Auth",
            'icon': '✓',
            'message': 'Authentication Successful!',
            'description': 'Redirecting back to Omi...',
            'redirect_url': redirect_url or f'omi://{app_key}/callback?error=unknown',
            'show_spinner': True,
        }
    else:
        error_messages = {
            'missing_code': 'No authorization code received from {}.'.format(config['name']),
            'invalid_state': 'Invalid or expired authentication request.',
            'config_error': '{} OAuth not properly configured.'.format(config['name']),
            'server_error': 'An error occurred during authentication.',
        }

        context = {
            'request': request,
            'title': f"{config['name']} Auth Error",
            'icon': '❌',
            'message': f"{'Security' if error_type == 'invalid_state' else 'Configuration' if error_type == 'config_error' else 'Authentication'} Error",
            'description': error_messages.get(error_type, 'An error occurred.'),
            'redirect_url': f'omi://{app_key}/callback?error={error_type or "unknown"}',
            'show_spinner': False,
        }

    return templates.TemplateResponse('oauth_callback.html', context)


def validate_and_consume_oauth_state(state_token: Optional[str]) -> Optional[Dict[str, str]]:
    """
    Validate OAuth state token and return associated data.
    Deletes the state token after validation to prevent replay attacks.

    Returns:
        Dict with 'uid' and 'app_key' if valid, None if invalid/expired
    """
    if not state_token:
        return None

    state_key = f"oauth_state:{state_token}"
    state_data_str = redis_db.r.get(state_key)

    if not state_data_str:
        return None

    # Delete immediately to prevent replay
    redis_db.r.delete(state_key)

    try:
        state_data = json.loads(state_data_str.decode() if isinstance(state_data_str, bytes) else state_data_str)
        return state_data
    except Exception as e:
        print(f"Error parsing state data: {e}")
        return None


# Request/Response models
class IntegrationData(BaseModel):
    """Data for an integration connection"""

    connected: bool = True
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None


class IntegrationResponse(BaseModel):
    """Response containing integration status"""

    connected: bool = Field(description="Whether the integration is connected")
    app_key: str = Field(description="Integration app key")


# *****************************
# ********** ROUTES ***********
# *****************************


@router.get("/v1/integrations/{app_key}", response_model=IntegrationResponse, tags=['integrations'])
def get_integration(app_key: str, uid: str = Depends(auth.get_current_user_uid)):
    """Get integration connection status for the current user."""
    integration = users_db.get_integration(uid, app_key)

    if integration and integration.get('connected'):
        return IntegrationResponse(connected=True, app_key=app_key)
    else:
        return IntegrationResponse(connected=False, app_key=app_key)


@router.put("/v1/integrations/{app_key}", tags=['integrations'])
def save_integration(app_key: str, data: IntegrationData, uid: str = Depends(auth.get_current_user_uid)):
    """Save or update an integration connection."""
    # Convert Pydantic model to dict, excluding None values
    integration_data = data.model_dump(exclude_none=True)

    users_db.set_integration(uid, app_key, integration_data)

    return {"status": "ok", "app_key": app_key}


@router.delete("/v1/integrations/{app_key}", status_code=204, tags=['integrations'])
def delete_integration(app_key: str, uid: str = Depends(auth.get_current_user_uid)):
    """Delete an integration connection."""
    success = users_db.delete_integration(uid, app_key)

    if not success:
        raise HTTPException(status_code=404, detail="Integration not found")

    return {"status": "ok"}


# *****************************
# ****** OAuth Initiation *****
# *****************************


class OAuthUrlResponse(BaseModel):
    """Response containing OAuth authorization URL"""

    auth_url: str = Field(description="OAuth authorization URL to open in browser")


@router.get("/v1/integrations/{app_key}/oauth-url", response_model=OAuthUrlResponse, tags=['integrations'])
def get_oauth_url(app_key: str, uid: str = Depends(auth.get_current_user_uid)):
    """
    Get OAuth authorization URL for an integration.
    Frontend opens this URL in browser to start OAuth flow.
    Uses secure random state tokens to prevent CSRF attacks.
    """
    base_url = os.getenv('BASE_API_URL')
    if not base_url:
        print(f'ERROR: BASE_API_URL not configured for integration OAuth')
        raise HTTPException(status_code=500, detail="BASE_API_URL not configured")

    # Generate cryptographically secure random state token
    state_token = secrets.token_urlsafe(32)

    # Store state mapping in Redis with expiry
    try:
        state_key = f"oauth_state:{state_token}"
        state_data = {'uid': uid, 'app_key': app_key, 'created_at': datetime.now(timezone.utc).isoformat()}
        redis_db.r.setex(state_key, OAUTH_STATE_EXPIRY, json.dumps(state_data))
    except Exception as e:
        print(f'ERROR: Failed to store OAuth state in Redis: {e}')
        raise HTTPException(status_code=500, detail=f"Failed to initialize OAuth flow: {str(e)}")

    if app_key == 'google_calendar':
        client_id = os.getenv('GOOGLE_CLIENT_ID')
        if not client_id:
            print(f'ERROR: GOOGLE_CLIENT_ID not configured for integration OAuth')
            raise HTTPException(status_code=500, detail="Google Calendar not configured - GOOGLE_CLIENT_ID missing")

        # Remove trailing slash from base_url if present
        base_url_clean = base_url.rstrip('/')
        redirect_uri = f'{base_url_clean}/v2/integrations/google-calendar/callback'
        # Use calendar scope (includes read and write access), contacts scopes for People API, and Gmail scope
        # This allows creating events, looking up contacts by name, and accessing Gmail
        scope = 'https://www.googleapis.com/auth/calendar https://www.googleapis.com/auth/contacts.readonly https://www.googleapis.com/auth/contacts.other.readonly https://www.googleapis.com/auth/gmail.readonly'
        from urllib.parse import quote

        auth_url = f'https://accounts.google.com/o/oauth2/v2/auth?client_id={client_id}&redirect_uri={quote(redirect_uri)}&response_type=code&scope={quote(scope)}&access_type=offline&prompt=consent&state={state_token}'
        print(f'Generated Google Calendar OAuth URL for user {uid}')

    elif app_key == 'whoop':
        client_id = os.getenv('WHOOP_CLIENT_ID')
        if not client_id:
            print(f'ERROR: WHOOP_CLIENT_ID not configured for Whoop integration OAuth')
            raise HTTPException(status_code=500, detail="Whoop not configured - WHOOP_CLIENT_ID missing")

        # Remove trailing slash from base_url if present
        base_url_clean = base_url.rstrip('/')
        redirect_uri = f'{base_url_clean}/v2/integrations/whoop/callback'

        # Whoop scopes: read:recovery, read:cycles, read:workout, read:sleep, read:profile, read:body_measurement
        # IMPORTANT: Include 'offline' scope to receive refresh_token
        scopes = 'read:recovery read:cycles read:workout read:sleep read:profile read:body_measurement offline'
        from urllib.parse import quote

        auth_url = f'https://api.prod.whoop.com/oauth/oauth2/auth?client_id={client_id}&redirect_uri={quote(redirect_uri)}&response_type=code&scope={quote(scopes)}&state={state_token}'
        print(f'Generated Whoop OAuth URL for user {uid}')

    elif app_key == 'notion':
        client_id = os.getenv('NOTION_CLIENT_ID')
        if not client_id:
            print(f'ERROR: NOTION_CLIENT_ID not configured for Notion integration OAuth')
            raise HTTPException(status_code=500, detail="Notion not configured - NOTION_CLIENT_ID missing")

        # Remove trailing slash from base_url if present
        base_url_clean = base_url.rstrip('/')
        redirect_uri = f'{base_url_clean}/v2/integrations/notion/callback'
        from urllib.parse import quote

        auth_url = f'https://api.notion.com/v1/oauth/authorize?client_id={client_id}&response_type=code&owner=user&redirect_uri={quote(redirect_uri)}&state={state_token}'
        print(f'Generated Notion OAuth URL for user {uid}')

    elif app_key == 'twitter':
        client_id = os.getenv('TWITTER_CLIENT_ID')
        if not client_id:
            print(f'ERROR: TWITTER_CLIENT_ID not configured for Twitter integration OAuth')
            raise HTTPException(status_code=500, detail="Twitter not configured - TWITTER_CLIENT_ID missing")

        # Remove trailing slash from base_url if present
        base_url_clean = base_url.rstrip('/')
        redirect_uri = f'{base_url_clean}/v2/integrations/twitter/callback'
        from urllib.parse import quote
        import hashlib
        import base64

        # Twitter OAuth 2.0 requires PKCE
        # Generate code_verifier (random string) and code_challenge (SHA256 hash)
        # Using state_token as seed for code_verifier for simplicity
        code_verifier = state_token[:43]  # Twitter requires 43-128 chars
        code_challenge = base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest()).decode().rstrip('=')

        # Store code_verifier in Redis for later use in callback
        verifier_key = f"oauth_code_verifier:{state_token}"
        redis_db.r.setex(verifier_key, OAUTH_STATE_EXPIRY, code_verifier)

        # Twitter OAuth 2.0 authorization URL
        # Scopes: tweet.read (read tweets), users.read (read user profile), offline.access (for refresh token)
        scopes = 'tweet.read users.read offline.access'
        auth_url = f'https://twitter.com/i/oauth2/authorize?response_type=code&client_id={client_id}&redirect_uri={quote(redirect_uri)}&scope={quote(scopes)}&state={state_token}&code_challenge={code_challenge}&code_challenge_method=S256'
        print(f'Generated Twitter OAuth URL for user {uid}')

    else:
        raise HTTPException(status_code=400, detail=f"Unsupported integration: {app_key}")

    return OAuthUrlResponse(auth_url=auth_url)


# *****************************
# ******* OAuth Callbacks *****
# *****************************


class OAuthProviderConfig(BaseModel):
    """Configuration for OAuth provider-specific logic"""

    token_endpoint: str
    token_request_type: str = "form"
    token_request_data: Dict[str, Any]
    additional_headers: Dict[str, str] = {}

    async def fetch_additional_data(self, client: httpx.AsyncClient, access_token: str) -> Dict[str, Any]:
        """Hook for fetching provider-specific data after token exchange"""
        return {}


async def handle_oauth_callback(
    request: Request,
    app_key: str,
    code: Optional[str],
    state: Optional[str],
    provider_config: OAuthProviderConfig,
) -> HTMLResponse:
    """
    Generic OAuth callback handler that works for all providers.

    Args:
        request: FastAPI request object
        app_key: Integration app key (google_calendar, whoop)
        code: Authorization code from OAuth provider
        state: State token for CSRF protection
        provider_config: Provider-specific configuration

    Returns:
        HTMLResponse with OAuth callback page
    """
    if not code or not state:
        return render_oauth_response(request, app_key, success=False, error_type='missing_code')

    # Validate state token
    state_data = validate_and_consume_oauth_state(state)
    if not state_data or state_data.get('app_key') != app_key:
        return render_oauth_response(request, app_key, success=False, error_type='invalid_state')

    uid = state_data['uid']

    try:
        client = get_http_client()

        if provider_config.token_request_type == "form":
            token_response = await client.post(
                provider_config.token_endpoint,
                headers={
                    'Content-Type': 'application/x-www-form-urlencoded',
                    **provider_config.additional_headers,
                },
                data=provider_config.token_request_data,
            )
        elif provider_config.token_request_type == "json":
            token_response = await client.post(
                provider_config.token_endpoint,
                headers={
                    'Content-Type': 'application/json',
                    **provider_config.additional_headers,
                },
                json=provider_config.token_request_data,
            )
        else:  # params
            token_response = await client.post(
                provider_config.token_endpoint,
                params=provider_config.token_request_data,
                headers=provider_config.additional_headers,
            )

        if token_response.status_code == 200:
            token_data = token_response.json()
            access_token = token_data.get('access_token', '')
            refresh_token = token_data.get('refresh_token')

            if not access_token:
                print(f'{app_key}: No access token received in response')
                deep_link = f'omi://{app_key}/callback?error=no_access_token'
                return render_oauth_response(request, app_key, success=True, redirect_url=deep_link)

            # Debug: Log token response keys for Whoop
            if app_key == 'whoop':
                token_keys = list(token_data.keys())
                print(f'{app_key}: Token response keys: {token_keys}')
                print(f'{app_key}: Has refresh_token: {bool(refresh_token)}')

            integration_data = {
                'connected': True,
                'access_token': access_token,
            }

            if refresh_token:
                integration_data['refresh_token'] = refresh_token
                if app_key == 'whoop':
                    print(f'{app_key}: Storing refresh_token (length: {len(refresh_token)})')
            else:
                if app_key == 'whoop':
                    print(f'{app_key}: WARNING - No refresh_token in token response!')

            try:
                additional_data = await provider_config.fetch_additional_data(client, access_token)
                integration_data.update(additional_data)
            except Exception as e:
                print(f'{app_key}: Error fetching additional data: {e}')

            # Store in Firebase
            try:
                users_db.set_integration(uid, app_key, integration_data)
                print(f'{app_key}: Successfully stored tokens for user {uid}')
            except Exception as e:
                print(f'{app_key}: Error storing tokens in Firebase: {e}')
                deep_link = f'omi://{app_key}/callback?error=storage_failed'
                return render_oauth_response(request, app_key, success=True, redirect_url=deep_link)

            deep_link = f'omi://{app_key}/callback?success=true'

            return render_oauth_response(request, app_key, success=True, redirect_url=deep_link)
        else:
            error_body = token_response.text[:500] if token_response.text else "No error body"
            print(f'{app_key}: Token exchange failed with HTTP {token_response.status_code}')
            print(f'{app_key}: Error response: {error_body}')
            deep_link = f'omi://{app_key}/callback?error=token_exchange_failed'
            return render_oauth_response(request, app_key, success=True, redirect_url=deep_link)

    except Exception as e:
        print(f'{app_key}: Unexpected error during OAuth callback: {e}')
        deep_link = f'omi://{app_key}/callback?error=server_error'
        return render_oauth_response(request, app_key, success=True, redirect_url=deep_link)


@router.get(
    '/v2/integrations/google-calendar/callback',
    response_class=HTMLResponse,
    tags=['integrations', 'oauth'],
)
async def google_calendar_oauth_callback(
    request: Request,
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
):
    """OAuth callback endpoint for Google Calendar integration."""
    client_id = os.getenv('GOOGLE_CLIENT_ID')
    client_secret = os.getenv('GOOGLE_CLIENT_SECRET')
    base_url = os.getenv('BASE_API_URL')

    if not all([client_id, client_secret, base_url]):
        return render_oauth_response(request, 'google_calendar', success=False, error_type='config_error')

    # Remove trailing slash from base_url if present
    base_url_clean = base_url.rstrip('/')
    redirect_uri = f'{base_url_clean}/v2/integrations/google-calendar/callback'

    config = OAuthProviderConfig(
        token_endpoint='https://oauth2.googleapis.com/token',
        token_request_type='form',
        token_request_data={
            'code': code,
            'client_id': client_id,
            'client_secret': client_secret,
            'redirect_uri': redirect_uri,
            'grant_type': 'authorization_code',
        },
    )

    return await handle_oauth_callback(request, 'google_calendar', code, state, config)


@router.get(
    '/v2/integrations/whoop/callback',
    response_class=HTMLResponse,
    tags=['integrations', 'oauth'],
)
async def whoop_oauth_callback(
    request: Request,
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
):
    """OAuth callback endpoint for Whoop integration."""
    client_id = os.getenv('WHOOP_CLIENT_ID')
    client_secret = os.getenv('WHOOP_CLIENT_SECRET')
    base_url = os.getenv('BASE_API_URL')

    if not all([client_id, client_secret, base_url]):
        return render_oauth_response(request, 'whoop', success=False, error_type='config_error')

    # Remove trailing slash from base_url if present
    base_url_clean = base_url.rstrip('/')
    redirect_uri = f'{base_url_clean}/v2/integrations/whoop/callback'

    config = OAuthProviderConfig(
        token_endpoint='https://api.prod.whoop.com/oauth/oauth2/token',
        token_request_type='form',
        token_request_data={
            'code': code,
            'client_id': client_id,
            'client_secret': client_secret,
            'redirect_uri': redirect_uri,
            'grant_type': 'authorization_code',
        },
    )

    return await handle_oauth_callback(request, 'whoop', code, state, config)


@router.get(
    '/v2/integrations/notion/callback',
    response_class=HTMLResponse,
    tags=['integrations', 'oauth'],
)
async def notion_oauth_callback(
    request: Request,
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
):
    """OAuth callback endpoint for Notion integration."""
    client_id = os.getenv('NOTION_CLIENT_ID')
    client_secret = os.getenv('NOTION_CLIENT_SECRET')
    base_url = os.getenv('BASE_API_URL')

    if not all([client_id, client_secret, base_url]):
        return render_oauth_response(request, 'notion', success=False, error_type='config_error')

    # Remove trailing slash from base_url if present
    base_url_clean = base_url.rstrip('/')
    redirect_uri = f'{base_url_clean}/v2/integrations/notion/callback'

    # Notion requires Basic Auth with base64(client_id:client_secret) in Authorization header
    # and only grant_type, code, redirect_uri in the JSON body
    credentials = f'{client_id}:{client_secret}'
    encoded_credentials = base64.b64encode(credentials.encode()).decode()

    config = OAuthProviderConfig(
        token_endpoint='https://api.notion.com/v1/oauth/token',
        token_request_type='json',  # Use JSON instead of form
        token_request_data={
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': redirect_uri,
        },
        additional_headers={
            'Content-Type': 'application/json',
            'Authorization': f'Basic {encoded_credentials}',
        },
    )

    return await handle_oauth_callback(request, 'notion', code, state, config)


@router.get(
    '/v2/integrations/twitter/callback',
    response_class=HTMLResponse,
    tags=['integrations', 'oauth'],
)
async def twitter_oauth_callback(
    request: Request,
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
):
    """OAuth callback endpoint for Twitter integration."""
    client_id = os.getenv('TWITTER_CLIENT_ID')
    client_secret = os.getenv('TWITTER_CLIENT_SECRET')
    base_url = os.getenv('BASE_API_URL')

    if not all([client_id, client_secret, base_url]):
        return render_oauth_response(request, 'twitter', success=False, error_type='config_error')

    # Remove trailing slash from base_url if present
    base_url_clean = base_url.rstrip('/')
    redirect_uri = f'{base_url_clean}/v2/integrations/twitter/callback'

    # Retrieve code_verifier from Redis (stored during OAuth initiation)
    verifier_key = f"oauth_code_verifier:{state}"
    code_verifier = redis_db.r.get(verifier_key)
    if code_verifier:
        code_verifier = code_verifier.decode() if isinstance(code_verifier, bytes) else code_verifier
        # Delete after use
        redis_db.r.delete(verifier_key)
    else:
        print(f'ERROR: Code verifier not found for state {state}')
        return render_oauth_response(request, 'twitter', success=False, error_type='invalid_state')

    # Twitter OAuth 2.0 uses Basic Auth with client_id:client_secret
    credentials = f'{client_id}:{client_secret}'
    encoded_credentials = base64.b64encode(credentials.encode()).decode()

    config = OAuthProviderConfig(
        token_endpoint='https://api.twitter.com/2/oauth2/token',
        token_request_type='form',
        token_request_data={
            'code': code,
            'grant_type': 'authorization_code',
            'redirect_uri': redirect_uri,
            'code_verifier': code_verifier,
        },
        additional_headers={
            'Authorization': f'Basic {encoded_credentials}',
        },
    )

    return await handle_oauth_callback(request, 'twitter', code, state, config)


@router.on_event("shutdown")
async def shutdown_http_client():
    """Cleanup HTTP client on app shutdown."""
    await close_http_client()
