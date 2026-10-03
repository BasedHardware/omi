<content>
import os
import hmac
import hashlib
from flask import request, jsonify, current_app
from functools import wraps

# --- Webhook Authentication ---

def require_zapier_webhook_auth(f):
    """
    Decorator to enforce authentication for Zapier webhook routes.
    Requires the ZAPIER_WEBHOOK_SECRET environment variable to be set.
    Authentication is provided via:
    1. Bearer token in the Authorization header.
    2. 'zapier_webhook_token' query parameter.
    Uses hmac.compare_digest for timing-safe comparison.
    Returns a 503 Service Unavailable error if the secret is not configured.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        secret = os.environ.get('ZAPIER_WEBHOOK_SECRET')
        if not secret:
            # Fail closed: if the secret is not configured, block the request.
            current_app.logger.error("ZAPIER_WEBHOOK_SECRET is not configured. Blocking webhook request to %s.", request.path)
            return jsonify({"error": "Webhook service is not configured"}), 503

        token = None
        # Check Authorization header for Bearer token
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
        # Fallback to query parameter
        elif not token:
            token = request.args.get('zapier_webhook_token')

        if not token:
            current_app.logger.warning("Zapier webhook request to %s missing token.", request.path)
            return jsonify({"error": "Authentication token required"}), 401

        # Timing-safe comparison
        if not hmac.compare_digest(token, secret):
            current_app.logger.warning("Zapier webhook to %s: Invalid token provided.", request.path)
            return jsonify({"error": "Invalid authentication token"}), 401

        return f(*args, **kwargs)
    return decorated_function

# --- Zapier Routes ---

@require_zapier_webhook_auth
def get_memory_sample(uid):
    """Returns the latest conversation for a given user."""
    current_app.logger.info("Authenticated Zapier request to GET /zapier/trigger/memory/sample for uid: %s", uid)
    # The actual logic to fetch the memory sample would go here.
    # For this fix, we only ensure the authentication decorator is in place.
    return jsonify({"status": "success", "uid": uid, "data": "latest_conversation_data"})

@require_zapier_webhook_auth
def post_memories(uid):
    """Creates a new conversation for a given user."""
    current_app.logger.info("Authenticated Zapier request to POST /zapier/action/memories for uid: %s", uid)
    # The actual logic to create a memory would go here.
    return jsonify({"status": "success", "uid": uid, "data": "memory_created"})

@require_zapier_webhook_auth
def manage_subscribe(uid):
    """Handles subscription (POST/DELETE) for a given user."""
    current_app.logger.info("Authenticated Zapier request to %s /zapier/trigger/subscribe for uid: %s", request.method, uid)
    # The actual logic to manage subscription would go here.
    return jsonify({"status": "success", "uid": uid, "data": "subscription_updated"})

@require_zapier_webhook_auth
def post_memories_webhook(uid):
    """Accepts conversation webhooks for a given user."""
    current_app.logger.info("Authenticated Zapier request to POST /zapier/memories for uid: %s", uid)
    # The actual logic to process the webhook would go here.
    return jsonify({"status": "success", "uid": uid, "data": "webhook_processed"})

@require_zapier_webhook_auth
def get_me(uid):
    """Probes integration status for a given user."""
    current_app.logger.info("Authenticated Zapier request to GET /zapier/me for uid: %s", uid)
    # The actual logic to get user status would go here.
    return jsonify({"status": "success", "uid": uid, "data": "integration_status"})
</content>