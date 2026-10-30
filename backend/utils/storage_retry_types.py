"""The storage SDK's availability replay set, in one importable shape.

The pack-listing boundary (``utils/other/storage.py``) needs the same
tuple the storage SDK's own default retry replays
(``google.cloud.storage.retry._RETRYABLE_TYPES``), but storage-lane code
keeps the sync ``requests`` HTTP client out of module scope (the
no-requests guard pins it), so the tuple cannot be imported verbatim into
``utils/other/``. The set is declared here structurally — every member
lives in ``requests.exceptions`` and none is a base class of anything else
in that module, so the module-prefix match is identity-exact without the
import — and one test pins it against the SDK directly
(tests/unit/test_raw_archive_listing_blip.py).
"""

from __future__ import annotations

from google.api_core import exceptions as api_core_exceptions

# Mirrors ``google.cloud.storage.retry._RETRYABLE_TYPES`` — the availability
# set the storage SDK's own default retry replays. Quota pressure is
# included: the SDK replays it for listings, so a boundary this set feeds
# must shed it the same way.
STORAGE_RETRYABLE_TYPES: tuple[type[BaseException], ...] = (
    api_core_exceptions.TooManyRequests,
    api_core_exceptions.InternalServerError,
    api_core_exceptions.BadGateway,
    api_core_exceptions.ServiceUnavailable,
    api_core_exceptions.GatewayTimeout,
    ConnectionError,
)


def is_requests_transport_error(error: BaseException) -> bool:
    """True for the ``requests`` transport family (resets, chunked breaks,
    timeouts) — the SDK replays it, but its module cannot be imported into
    the utils tree (the no-requests guard pins it)."""
    module = type(error).__module__
    return module == 'requests.exceptions' or module.startswith('requests.exceptions.')
