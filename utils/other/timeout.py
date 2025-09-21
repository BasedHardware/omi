from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from fastapi import Request
import asyncio
import os


class TimeoutMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, methods_timeout: dict = None):
        super().__init__(app)

        self.default_timeout = self._get_timeout_from_env("HTTP_DEFAULT_TIMEOUT", default=2 * 60)

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
        timeout = self.methods_timeout.get(request.method, self.default_timeout)
        try:
            return await asyncio.wait_for(call_next(request), timeout=timeout)
        except asyncio.TimeoutError:
            return Response(status_code=504)
