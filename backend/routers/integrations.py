from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
import os
import secrets
import json
import base64
import hashlib
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
}

# Provider-specific OAuth URL configuration
AUTH_PROVIDERS = {
    'google_calendar': {
        'client_env': 'GOOGLE_CLIENT_ID',
        'auth_base': 'https://accounts.google.com/o/oauth2/v2/auth',
        'redirect_path': '/v2/integrations/google-calendar/callback',
        'query': {
            'response_type': 'code',
            'scope': 'https://www.googleapis.com/auth/calendar https://www.googleapis.com/auth/contacts.readonly https://www.googleapis.com/auth/contacts.other.readonly',
            'access_type': 'offline',
            'prompt': 'consent',
        },
        'log_name': 'Google Calendar',
        'error_detail': 'Google Calendar not configured - GOOGLE_CLIENT_ID missing',
    },
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

    try:
        state_data = json.loads(state_data_str.decode() if isinstance(state_data_str, bytes) else state_data_str)
        # Delete after successful parse to prevent replay
        redis_db.r.delete(state_key)
        return state_data
    except Exception as e:
        print(f"Error parsing state data: {e}")
        # Delete invalid state to prevent repeated parse failures
        redis_db.r.delete(state_key)
        return None


# Request/Response models
class IntegrationData(BaseModel):
    """Data for an integration connection"""

    connected: bool = True
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None


class AppleHealthSyncData(BaseModel):
    """Health data synced from Apple Health on iOS device"""

    period_days: int = Field(default=7, description="Number of days of data")

    # Steps data
    total_steps: Optional[int] = Field(default=None, description="Total steps in period")
    average_steps_per_day: Optional[float] = Field(default=None, description="Average steps per day")
    daily_steps: Optional[list] = Field(default=None, description="Daily steps breakdown [{date, steps}]")

    # Sleep data
    total_sleep_hours: Optional[float] = Field(default=None, description="Total sleep hours")
    total_in_bed_hours: Optional[float] = Field(default=None, description="Total time in bed hours")
    sleep_sessions_count: Optional[int] = Field(default=None, description="Number of sleep sessions")
    sleep_sessions: Optional[list] = Field(default=None, description="Sleep session details")
    daily_sleep: Optional[list] = Field(default=None, description="Daily sleep breakdown [{date, sleepHours}]")

    # Heart rate data
    heart_rate_average: Optional[float] = Field(default=None, description="Average heart rate")
    heart_rate_min: Optional[float] = Field(default=None, description="Minimum heart rate")
    heart_rate_max: Optional[float] = Field(default=None, description="Maximum heart rate")

    # Active energy data
    total_active_energy: Optional[float] = Field(default=None, description="Total active energy kcal")
    average_active_energy_per_day: Optional[float] = Field(default=None, description="Average daily active energy")
    daily_active_energy: Optional[list] = Field(default=None, description="Daily energy breakdown [{date, calories}]")

    # Workouts data
    workouts: Optional[list] = Field(default=None, description="List of workout records")


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

    return None


@router.put("/v1/integrations/apple-health/sync", tags=['integrations'])
def sync_apple_health_data(data: AppleHealthSyncData, uid: str = Depends(auth.get_current_user_uid)):
    """
    Sync Apple Health data from the iOS device.

    This endpoint receives health data collected from Apple HealthKit on the user's
    iPhone/Apple Watch and stores it for use in chat queries.

    Unlike other integrations that use OAuth, Apple Health data is pushed from the device.
    """
    # Build the health data structure
    health_data = {
        'period_days': data.period_days,
    }

    # Steps
    if data.total_steps is not None:
        health_data['steps'] = {
            'total': data.total_steps,
            'average_per_day': data.average_steps_per_day or (data.total_steps / max(data.period_days, 1)),
            'period_days': data.period_days,
            'daily': data.daily_steps or [],  # Daily breakdown [{date, steps}]
        }

    # Sleep
    if data.total_sleep_hours is not None or data.sleep_sessions:
        health_data['sleep'] = {
            'total_sleep_hours': data.total_sleep_hours or 0,
            'total_in_bed_hours': data.total_in_bed_hours or 0,
            'sessions_count': data.sleep_sessions_count or 0,
            'sessions': data.sleep_sessions or [],
            'daily': data.daily_sleep or [],  # Daily breakdown [{date, sleepHours}]
        }

    # Heart rate
    if data.heart_rate_average is not None:
        health_data['heart_rate'] = {
            'average': data.heart_rate_average,
            'minimum': data.heart_rate_min,
            'maximum': data.heart_rate_max,
        }

    # Active energy
    if data.total_active_energy is not None:
        health_data['active_energy'] = {
            'total': data.total_active_energy,
            'average_per_day': data.average_active_energy_per_day
            or (data.total_active_energy / max(data.period_days, 1)),
            'daily': data.daily_active_energy or [],  # Daily breakdown [{date, calories}]
        }

    # Workouts
    if data.workouts:
        health_data['workouts'] = data.workouts

    # Save the integration with health data
    integration_data = {
        'connected': True,
        'health_data': health_data,
        'last_synced': datetime.now(timezone.utc).isoformat(),
    }

    users_db.set_integration(uid, 'apple_health', integration_data)

    return {
        "status": "ok",
        "app_key": "apple_health",
        "synced_at": integration_data['last_synced'],
        "data_types_synced": list(health_data.keys()),
    }


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

    if app_key in AUTH_PROVIDERS:
        cfg = AUTH_PROVIDERS[app_key]
        client_id = os.getenv(cfg['client_env'])
        if not client_id:
            print(f"ERROR: {cfg['client_env']} not configured for {cfg['log_name']} integration OAuth")
            raise HTTPException(status_code=500, detail=cfg['error_detail'])

        base_url_clean = base_url.rstrip('/')
        redirect_uri = f"{base_url_clean}{cfg['redirect_path']}"

        from urllib.parse import urlencode

        params = {
            'client_id': client_id,
            'redirect_uri': redirect_uri,
            'state': state_token,
        }
        params.update(cfg['query'])

        if cfg.get('requires_pkce'):
            code_verifier = secrets.token_urlsafe(32)
            code_challenge = (
                base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest()).decode().rstrip('=')
            )
            verifier_key = f"oauth_code_verifier:{state_token}"
            redis_db.r.setex(verifier_key, OAUTH_STATE_EXPIRY, code_verifier)
            params['code_challenge'] = code_challenge

        auth_url = f"{cfg['auth_base']}?{urlencode(params)}"
        print(f"Generated {cfg['log_name']} OAuth URL for user {uid}")

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
                return render_oauth_response(request, app_key, success=False, error_type='server_error')

            integration_data = {
                'connected': True,
                'access_token': access_token,
            }

            if refresh_token:
                integration_data['refresh_token'] = refresh_token

            try:
                additional_data = await provider_config.fetch_additional_data(client, access_token)
                integration_data.update(additional_data)
            except Exception as e:
                print(f'{app_key}: Error fetching additional data: {e}')

            # Store in Firebase
            try:
                users_db.set_integration(uid, app_key, integration_data)
            except Exception as e:
                print(f'{app_key}: Error storing tokens in Firebase: {e}')
                return render_oauth_response(request, app_key, success=False, error_type='server_error')

            deep_link = f'omi://{app_key}/callback?success=true'

            return render_oauth_response(request, app_key, success=True, redirect_url=deep_link)
        else:
            error_body = token_response.text[:500] if token_response.text else "No error body"
            print(f'{app_key}: Token exchange failed with HTTP {token_response.status_code}')
            print(f'{app_key}: Error response: {error_body}')
            return render_oauth_response(request, app_key, success=False, error_type='server_error')

    except Exception as e:
        print(f'{app_key}: Unexpected error during OAuth callback: {e}')
        return render_oauth_response(request, app_key, success=False, error_type='server_error')


@router.get(
    '/v2/integrations/{app_key}/callback',
    response_class=HTMLResponse,
    tags=['integrations', 'oauth'],
)
async def oauth_callback(
    request: Request,
    app_key: str,
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
):
    key_map = {
        'google-calendar': 'google_calendar',
    }
    normalized_key = key_map.get(app_key, app_key)

    client_envs = {
        'google_calendar': ('GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET'),
    }

    if normalized_key not in client_envs:
        return render_oauth_response(request, normalized_key, success=False, error_type='config_error')

    client_id_env, client_secret_env = client_envs[normalized_key]
    client_id = os.getenv(client_id_env)
    client_secret = os.getenv(client_secret_env)
    base_url = os.getenv('BASE_API_URL')

    if not all([client_id, client_secret, base_url]):
        return render_oauth_response(request, normalized_key, success=False, error_type='config_error')

    base_url_clean = base_url.rstrip('/')
    # Preserve existing redirect paths used during auth initiation
    redirect_path_map = {
        'google_calendar': '/v2/integrations/google-calendar/callback',
    }
    redirect_uri = f"{base_url_clean}{redirect_path_map[normalized_key]}"

    if normalized_key == 'google_calendar':
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
        return await handle_oauth_callback(request, normalized_key, code, state, config)


@router.on_event("shutdown")
async def shutdown_http_client():
    """Cleanup HTTP client on app shutdown."""
    await close_http_client()
