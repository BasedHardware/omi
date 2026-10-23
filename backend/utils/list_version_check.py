"""Conditional GET against atomic writer versions; the source path stays authoritative."""

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from typing import Any

from fastapi import Request, Response
from prometheus_client import Counter

from database._client import get_firestore_client
from database.action_items_cache import if_none_match_matches
from database.list_projection_head import initialize_head
from config.list_projection import STATE_COLLECTION, writer_enabled
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)
CHECKS = Counter(
    'omi_list_version_checks_total',
    'Conditional list version checks (source queries remain authoritative).',
    ['origin', 'outcome'],
)
ORIGINS = {
    '/v1/conversations': 'http:/v1/conversations',
    '/v1/action-items': 'http:/v1/action-items',
    '/v1/dev/user/action-items': 'http:/v1/dev/user/action-items',
}


def _version(uid: str, family: str) -> str | None:
    try:
        client = get_firestore_client()
        reference = client.collection('users').document(uid).collection(STATE_COLLECTION).document(family)
        snapshot = reference.get(timeout=1.0, retry=None)
        if not snapshot.exists:
            return initialize_head(uid, family, firestore_client=client)
        value = (snapshot.to_dict() or {}).get('version') if snapshot.exists else None
        return value if isinstance(value, str) and len(value) == 32 else None
    except Exception:
        record_fallback(
            component='firestore_read',
            from_mode='list_version',
            to_mode='source_query',
            reason='unavailable',
            outcome='degraded',
            log=logger,
        )
        return None


@dataclass
class ListVersionCheck:
    uid: str
    family: str
    origin: str
    before: str | None = None
    etag: str | None = None
    not_modified: Response | None = None

    @classmethod
    def start(cls, request: Request | None, uid: str, family: str) -> 'ListVersionCheck':
        check = cls(uid, family, ORIGINS.get(request.url.path, '') if isinstance(request, Request) else '')
        # An epoch is an operator attestation that ALL writer runtimes are
        # upgraded. Rotate it after any writer rollback/gap; never auto-enable
        # a mixed fleet simply because the serving process has new code.
        epoch = os.getenv('OMI_LIST_VERSION_EPOCH', '').strip()
        release = os.getenv('OMI_BACKEND_RELEASE_SHA', '').strip()
        if not check.origin or not epoch or not release or not writer_enabled():
            return check
        # Preserve existing action-item cache economics for clients that never
        # send validators. Clients already sending body ETags graduate on the
        # next source read; no cache TTL or existing lever is retuned here.
        if family == 'action_items' and not request.headers.get('if-none-match'):
            return check
        check.before = _version(uid, family)
        if check.before is None:
            CHECKS.labels(check.origin, 'untracked').inc()
            return check
        # Scope to identity, exact request shape, representation code and the
        # rollout epoch. Tokens and owner IDs never become metric labels.
        scope: Any = [
            uid,
            family,
            check.before,
            epoch,
            release,
            request.url.path,
            list(request.query_params.multi_items()),
            request.headers.get('authorization', ''),
        ]
        # Only authentication affects these representations. Trace/request IDs
        # added by the proxy change on every poll and must not enter the token.
        digest = hashlib.sha256(json.dumps(scope, separators=(',', ':')).encode()).hexdigest()
        check.etag = f'W/"lp1-{digest}"'
        if if_none_match_matches(request.headers.get('if-none-match'), check.etag):
            # This read is the GET's linearization point. Authentication and
            # route-specific scope dependencies have already executed.
            check.not_modified = Response(status_code=304, headers=check.headers())
            CHECKS.labels(check.origin, 'not_modified').inc()
        else:
            CHECKS.labels(check.origin, 'changed').inc()
        return check

    @property
    def active(self) -> bool:
        return self.before is not None

    def headers(self) -> dict[str, str]:
        return {'ETag': self.etag or '', 'Cache-Control': 'private, no-cache', 'Vary': 'Authorization'}

    def finish(self, response: Response | None, *, truncated: bool, cacheable: bool = True) -> None:
        # Never attach a validator to a partial page or a page spanning a
        # concurrent mutation. Existing clients receive the original response.
        if (
            response is not None
            and self.active
            and not truncated
            and cacheable
            and _version(self.uid, self.family) == self.before
        ):
            response.headers.update(self.headers())
