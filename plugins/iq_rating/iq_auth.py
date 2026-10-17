import os
import hmac
from functools import wraps
from flask import request, jsonify, current_app

IQ_RATING_SECRET = os.environ.get("IQ_RATING_SECRET")

def require_iq_auth(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not IQ_RATING_SECRET:
            current_app.logger.error("IQ_RATING_SECRET not configured, returning 503")
            return jsonify({"error": "Service temporarily unavailable"}), 503

        token = None
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1]
        else:
            token = request.args.get("iq_rating_token")

        if not token:
            return jsonify({"error": "Missing authentication token"}), 401

        expected_token = hmac.new(
            IQ_RATING_SECRET.encode(),
            request.full_path.encode(),
            "sha256"
        ).hexdigest()

        if not hmac.compare_digest(token, expected_token):
            return jsonify({"error": "Invalid authentication token"}), 401

        return f(*args, **kwargs)
    return decorated_function