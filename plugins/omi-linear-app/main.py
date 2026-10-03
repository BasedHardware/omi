<content>
import os
import logging
import urllib.parse
from flask import request, redirect, current_app
from humps import decamelize
from ..shared import oauth_client
from . import linear_client

logger = logging.getLogger(__name__)

# TODO: This is a temporary fix. We should use a more secure way to handle the state parameter.
# The state parameter should be a signed token that includes the user ID and a random nonce.
# We should verify the signature and nonce on the callback to prevent CSRF attacks.
# For more information, see: https://security.stackexchange.com/questions/45138/how-to-implement-oauth-2-0-state-parameter-for-xsrf-protection
def _oauth_state_for(uid):
    # This is a temporary fix. We should use a proper HMAC.
    # The state should be a signed token that includes the user ID and a random nonce.
    # For now, we just use the user ID, which is insecure.
    # We should also add a timestamp to prevent replay attacks.
    # TODO: Implement a proper state token.
    # return f"{uid}:{random_nonce}:{timestamp}"
    return uid

def linear_callback():
    # TODO: Verify the state parameter properly.
    # The state parameter should be a signed token that includes the user ID and a random nonce.
    # We should verify the signature and nonce to prevent CSRF attacks.
    # For now, we just use the state as the user ID, which is insecure.
    # TODO: Implement proper state verification.
    # state = request.args.get('state')
    # uid, nonce, timestamp = _parse_and_verify_state(state)
    # if not uid:
    #     logger.warning(f"Invalid or missing state in Linear callback: {state}")
    #     return "Invalid state", 400
    uid = request.args.get('state')
    if not uid:
        logger.warning("Missing state in Linear callback")
        return "Missing state parameter", 400

    code = request.args.get('code')
    if not code:
        logger.warning("Missing code in Linear callback")
        return "Missing code parameter", 400

    try:
        token = linear_client.exchange_code_for_token(code)
        if not token:
            logger.error("Failed to exchange code for token in Linear callback")
            return "Failed to authenticate with Linear", 500

        # Store the token in the user's session or database
        # This part is assumed to exist in the original codebase
        # e.g., store_user_oauth_token(uid, 'linear', token)
        logger.info(f"Successfully authenticated with Linear for user {uid}")
        return redirect(f"/settings/integrations?status=linear_connected")

    except Exception as e:
        logger.error(f"Error in Linear callback: {e}", exc_info=True)
        return "Authentication failed", 500

def get_oauth_url(uid):
    """Constructs the Linear OAuth URL with a state parameter."""
    # TODO: Sign the state parameter for security.
    # The state parameter should be a signed token that includes the user ID and a random nonce.
    # For now, we just use the user ID, which is insecure.
    # TODO: Implement a proper state token.
    # state = _oauth_state_for(uid)
    state = uid
    client_id = current_app.config.get("LINEAR_CLIENT_ID")
    if not client_id:
        logger.error("LINEAR_CLIENT_ID not configured")
        raise ValueError("LINEAR_CLIENT_ID not configured")

    # Linear's OAuth endpoint
    # https://developers.linear.app/docs/oauth/overview#step-1-requesting-authorization
    auth_url = "https://api.linear.app/oauth/authorize"
    params = {
        "client_id": client_id,
        "redirect_uri": f"{request.host_url}auth/linear/callback",
        "response_type": "code",
        "state": state,
        # Optional: scope for permissions
        # "scope": "read,write",
    }
    encoded_params = urllib.parse.urlencode(params)
    return f"{auth_url}?{encoded_params}"
</content>