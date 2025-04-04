import json
import os
import time
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi import Request
from firebase_admin import auth
from firebase_admin.auth import ExpiredIdTokenError, InvalidIdTokenError
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

security = HTTPBearer()

def get_user(uid: str):
    user = auth.get_user(uid)
    return user


def get_current_user_uid(authorization: Annotated[HTTPAuthorizationCredentials, Depends(security)]):
    token = authorization.credentials
    key = os.getenv("ADMIN_KEY")
    if key and key in token:
        return token.split(key)[1]

    try:
        decoded_token = auth.verify_id_token(authorization.credentials)
        return decoded_token["uid"]
    except KeyError:
        raise HTTPException(status_code=400, detail="User ID not found")
    except InvalidIdTokenError:
        raise HTTPException(status_code=401, detail="Invalid authorization token")
    except ExpiredIdTokenError:
        raise HTTPException(status_code=401, detail="Authorization token has expired")
    except Exception as e:
        print(e)
        raise HTTPException(status_code=400, detail="Authorization failed")


cached = {}


def rate_limit_custom(
    endpoint: str, request: Request, requests_per_window: int, window_seconds: int
):
    ip = request.client.host
    key = f"rate_limit:{endpoint}:{ip}"

    # Check if the IP is already rate-limited
    current = cached.get(key)
    if current:
        current = json.loads(current)
        remaining = current["remaining"]
        timestamp = current["timestamp"]
        current_time = int(time.time())

        # Check if the time window has expired
        if current_time - timestamp >= window_seconds:
            remaining = requests_per_window - 1  # Reset the counter for the new window
            timestamp = current_time
        elif remaining == 0:
            raise HTTPException(status_code=429, detail="Too Many Requests")

        remaining -= 1

    else:
        # If no previous data found, start a new time window
        remaining = requests_per_window - 1
        timestamp = int(time.time())

    # Update the rate limit info in Redis
    current = {"timestamp": timestamp, "remaining": remaining}
    cached[key] = json.dumps(current)

    return True


# Dependency to enforce custom rate limiting for specific endpoints
def rate_limit_dependency(
    endpoint: str = "", requests_per_window: int = 60, window_seconds: int = 60
):
    def rate_limit(request: Request):
        return rate_limit_custom(endpoint, request, requests_per_window, window_seconds)

    return rate_limit


def timeit(func):
    """
    Decorator for measuring function's running time.
    """

    def measure_time(*args, **kw):
        start_time = time.time()
        result = func(*args, **kw)
        print(
            "Processing time of %s(): %.2f seconds."
            % (func.__qualname__, time.time() - start_time)
        )
        return result

    return measure_time


def delete_account(uid: str):
    auth.delete_user(uid)
    return {"message": "User deleted"}
