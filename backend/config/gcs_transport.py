"""Pure SDK transport error policy; no HTTP clients or I/O.

Requests is the GCS SDK's transport. Utility coordinators consume this error
policy without importing a Requests client into the async HTTP layer.
"""

import requests.exceptions
import urllib3.exceptions
from google.api_core.exceptions import RetryError
from google.auth.exceptions import TransportError

UploadWaitTimeout = requests.exceptions.ReadTimeout


def transport_cause(error: BaseException | None) -> str | None:
    """Unwrap transport faults only; API/throttle/Firestore faults do not opt in."""
    if error is None:
        return None
    pending = [error]
    seen = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(
            current,
            (requests.exceptions.Timeout, urllib3.exceptions.ReadTimeoutError, urllib3.exceptions.ConnectTimeoutError),
        ) and not isinstance(current, urllib3.exceptions.NewConnectionError):
            return 'timeout'
        if isinstance(
            current,
            (
                requests.exceptions.ConnectionError,
                requests.exceptions.ChunkedEncodingError,
                urllib3.exceptions.ProtocolError,
                urllib3.exceptions.NewConnectionError,
            ),
        ):
            return 'connection'
        if isinstance(current.__cause__, BaseException):
            pending.append(current.__cause__)
        if isinstance(current, (RetryError, TransportError, urllib3.exceptions.MaxRetryError)):
            for inner in (getattr(current, 'cause', None), getattr(current, 'reason', None), *current.args):
                if isinstance(inner, BaseException):
                    pending.append(inner)
    return None
