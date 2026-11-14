"""Request bindings and the directory process cache supply IO-free plane routing.

Without a binding or cached directory route an owner uses Firestore. The environment override is
loaded once, like other process configuration, and is harness-only.
"""

import os
import sys
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator, Literal

from config import directory_routing

from config.chat_first_e2e_fixture import is_chat_first_e2e_harness_runtime

Plane = Literal['firestore', 'cell']
_request_plane: ContextVar[tuple[str, Plane] | None] = ContextVar('request_plane', default=None)


def _load_test_cell_uids() -> frozenset[str]:
    uids = frozenset(uid.strip() for uid in os.getenv('PLANE_LEAK_TEST_CELL_UIDS', '').split(',') if uid.strip())
    if uids and not (is_chat_first_e2e_harness_runtime() or os.getenv('OMI_ENV_STAGE', '').strip().lower() == 'test'):
        raise RuntimeError('PLANE_LEAK_TEST_CELL_UIDS requires a local, offline, or test stage')
    return uids


_TEST_CELL_UIDS = _load_test_cell_uids()


def plane_for(uid: str) -> Plane:
    binding = _request_plane.get()
    if binding is not None and binding[0] == uid:
        return binding[1]
    if uid in _TEST_CELL_UIDS:
        return 'cell'
    # Never initialize serving imports from an SDK probe. In particular, the
    # jobstore/user/probe import graph can still be partially initialized here.
    router = sys.modules.get('database.directory.router')
    cached_plane = getattr(router, 'cached_plane', None)
    return cached_plane(uid) if cached_plane is not None else 'firestore'


def has_cell_plane() -> bool:
    """Cheap probe gate; no path parsing, hashing, labels, or directory IO."""
    return (
        directory_routing.routing_active()
        or bool(_TEST_CELL_UIDS)
        or (_request_plane.get() or (None, None))[1] == 'cell'
    )


@contextmanager
def plane_context(uid: str, plane: Plane) -> Iterator[None]:
    """Bind an already-resolved route for this request and restore it on exit."""
    token = _request_plane.set((uid, plane))
    try:
        yield
    finally:
        _request_plane.reset(token)
