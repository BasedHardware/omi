from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from fastapi import Request
import asyncio
import os
import time


class TimeoutMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, methods_timeout: dict = None):
        super().__init__(app)

        self.default_timeout = self._get_timeout_from_env("HTTP_DEFAULT_TIMEOUT", default=2 * 60)
        self.maximum_age_seconds = self._get_timeout_from_env("HTTP_MAXIMUM_AGE_SECONDS", default=5 * 60)

        self.methods_timeout = self._parse_methods_timeout(methods_timeout or {})

    @staticmethod
    def _get_timeout_from_env(env_var: str, default: float) -> float:
        timeout = os.environ.get(env_var, default)
        try:
            return float(timeout)
        except ValueError:
            raise ValueError(f"Invalid timeout value in env {env_var}: {timeout}")

    @staticmethod
    def _parse_methods_timeout(methods_timeout: dict) -> dict:
        result = {}
        for method, timeout in methods_timeout.items():
            if timeout is None:
                continue
            try:
                result[method.upper()] = float(timeout)
            except ValueError:
                raise ValueError(f"Invalid timeout value for method {method}: {timeout}")
        return result

    async def dispatch(self, request: Request, call_next):
        # Check for stale request header first
        request_start_header = request.headers.get("x-request-start-time")
        if request_start_header:
            try:
                request_start_time = float(request_start_header)
                current_time = time.time()
                request_age = current_time - request_start_time

                if request_age > self.maximum_age_seconds:
                    # 408 Request Timeout is a fitting status code.
                    return Response(status_code=408, content="Request is too old and has been rejected.")
            except (ValueError, TypeError):
                # Header is malformed, proceed as normal or reject with 400
                pass

        timeout = self.methods_timeout.get(request.method, self.default_timeout)
        try:
            return await asyncio.wait_for(call_next(request), timeout=timeout)
        except asyncio.TimeoutError:
            return Response(status_code=504)
