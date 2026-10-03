<content>
from datetime import timedelta
from uuid import uuid4

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.core.cache import cache

from omi.core.models import User
from omi.apps.models import App, AppData
from omi.apps.mcp.services import (
    get_mcp_app_by_client_id,
    exchange_code_for_token,
    get_or_create_mcp_app_installation,
)

OAUTH_STATE_EXPIRY = 600  # 10 minutes, in seconds

@csrf_exempt
@require_http_methods(["GET"])
def mcp_oauth_callback(request: HttpRequest) -> HttpResponse:
    """
    Handles the OAuth2 callback from an MCP server.
    Verifies the state token to prevent CSRF and enables the app for the user.
    """
    code = request.GET.get("code")
    state = request.GET.get("state")

    if not code or not state:
        return JsonResponse({"error": "Missing code or state parameter"}, status=400)

    # Retrieve the state payload from Redis and delete it to prevent replay
    state_payload = cache.get(f"mcp_oauth_state:{state}")

    if not state_payload:
        return JsonResponse({"error": "Invalid or expired state token"}, status=400)

    # Extract app_id and uid from the payload
    app_id = state_payload.get("app_id")
    uid = state_payload.get("uid")

    if not app_id or not uid:
        return JsonResponse({"error": "Invalid state payload"}, status=400)

    # Verify the user making the request is the same user who initiated the OAuth flow
    try:
        user = User.objects.get(id=uid)
    except User.DoesNotExist:
        return JsonResponse({"error": "User not found"}, status=404)

    if request.user.id != user.id:
        return JsonResponse({"error": "Unauthorized access to state token"}, status=403)

    # Get the app using the client_id
    app = get_mcp_app_by_client_id(app_id)
    if not app:
        return JsonResponse({"error": "App not found"}, status=404)

    # Exchange the authorization code for an access token
    token_data = exchange_code_for_token(app, code)
    if not token_data:
        return JsonResponse({"error": "Failed to exchange code for token"}, status=400)

    # Create or get the app installation
    app_installation, _ = get_or_create_mcp_app_installation(
        user=user,
        app=app,
        access_token=token_data["access_token"],
        refresh_token=token_data.get("refresh_token"),
        token_expires_at=token_data.get("expires_at"),
    )

    return JsonResponse({"status": "success", "app_id": app_id})

def generate_oauth_state(app_id: str, uid: str) -> str:
    """
    Generates a unique, opaque state token for the OAuth flow.
    Stores the app_id and uid in Redis for later validation.
    """
    state_token = str(uuid4())
    payload = {"app_id": app_id, "uid": uid}
    cache.set(f"mcp_oauth_state:{state_token}", payload, timeout=OAUTH_STATE_EXPIRY)
    return state_token
</content>