"""Product counters in the existing default Prometheus registry.

Events and surfaces are closed vocabularies: add source-owned events here, never
pass user/conversation/device IDs. Version labels accept released numeric versions
and numeric Flutter build suffixes, not User-Agent strings or arbitrary IDs. A process-lifetime cap also
bounds cardinality from arbitrary client-supplied versions; excess values share
``unknown``. No eviction: evicting labels would reset counters or grow series.
"""

import re
import threading

from starlette.requests import HTTPConnection

from utils.metrics import OMI_PRODUCT_EVENT_TOTAL

EVENTS = frozenset({'conversation_created'})
SURFACES = frozenset({'mobile', 'desktop'})
MAX_LABEL_LENGTH = 32
MAX_APP_VERSIONS = 128
_SAFE_LABEL = re.compile(r'[a-zA-Z0-9_.+-]+', re.ASCII)
_VERSION = re.compile(r'[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,5}(?:\+[0-9]{1,10})?', re.ASCII)
_versions: set[str] = set()
_versions_lock = threading.Lock()


def sanitize_label(value: object) -> str:
    """Reject rather than truncate unsafe/oversized input into plausible labels."""
    if not isinstance(value, str) or not value or len(value) > MAX_LABEL_LENGTH:
        return 'unknown'
    return value if _SAFE_LABEL.fullmatch(value) else 'unknown'


def sanitize_app_version(value: object) -> str:
    label = sanitize_label(value)
    if not _VERSION.fullmatch(label):
        return 'unknown'
    with _versions_lock:
        if label in _versions:
            return label
        if len(_versions) >= MAX_APP_VERSIONS:
            return 'unknown'
        _versions.add(label)
    return label


def extract_app_version(request: HTTPConnection) -> str:
    """Flutter shared.dart, macOS OmiHTTPTransport, Windows apiClient use X-App-Version.

    Flutter supplies version+build in X-App-Version; retain its numeric suffix.
    X-App-Build and User-Agent are deliberately not version sources: they can
    contain arbitrary build IDs or the networking library's version.
    """
    try:
        return sanitize_app_version(request.headers.get('x-app-version'))
    except Exception:
        return 'unknown'


def extract_surface(request: HTTPConnection) -> str:
    """First-party authenticated route context; never infer from transcript source.

    All current first-party transports send X-App-Platform. Missing/unknown
    platforms stay unknown; developer-key routes must use unknown explicitly.
    """
    try:
        platform = request.headers.get('x-app-platform', '').lower()
        if platform in {'ios', 'android'}:
            return 'mobile'
        if platform in {'macos', 'windows', 'linux'}:
            return 'desktop'
    except Exception:
        pass
    return 'unknown'


def record_product_event(event: str, app_version: str | None = None, surface: str | None = None) -> None:
    """Best-effort telemetry: even label/collector failures cannot fail a request."""
    try:
        event_label = sanitize_label(event)
        surface_label = sanitize_label(surface)
        OMI_PRODUCT_EVENT_TOTAL.labels(
            event=event_label if event_label in EVENTS else 'unknown',
            app_version=sanitize_app_version(app_version),
            surface=surface_label if surface_label in SURFACES else 'unknown',
        ).inc()
    except Exception:
        # Do not log exception text or labels: they may contain sensitive input.
        return
