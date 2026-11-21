"""Pure HTTP retry classification shared by diarization and speaker custody."""

import ssl

import httpx


def has_tls_cause(error, extra_types=()):
    pending, seen = [error], set()
    while pending:
        current = pending.pop()
        if current is None or id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, (ssl.SSLError, *extra_types)):
            return True
        pending.extend((current.__cause__, current.__context__))
    return False


def retryable_http_error(error):
    if has_tls_cause(error):
        return False
    if isinstance(error, httpx.HTTPStatusError):
        status = error.response.status_code
        return status in {408, 429} or 500 <= status <= 599
    return isinstance(error, httpx.TransportError)
