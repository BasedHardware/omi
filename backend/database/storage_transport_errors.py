"""Exception identities from the requests transport used by the GCS SDK.

Keep SDK transport compatibility at the database boundary. This module performs
no HTTP requests; application HTTP clients and their errors use httpx.
"""

from requests.exceptions import ConnectionError, SSLError, Timeout

TRANSIENT_ERRORS = (ConnectionError, Timeout)
TLS_ERRORS = (SSLError,)
