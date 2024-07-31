import json
import time

from fastapi import Request, HTTPException

cached = {}


def rate_limit_custom(endpoint: str, request: Request, requests_per_window: int, window_seconds: int):
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
def rate_limit_dependency(endpoint: str = "", requests_per_window: int = 60, window_seconds: int = 60):
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
        print("Processing time of %s(): %.2f seconds."
              % (func.__qualname__, time.time() - start_time))
        return result

    return measure_time
