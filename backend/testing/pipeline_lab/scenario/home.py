"""The Home stage of a scenario run: what the product's own Home routes return, at each checkpoint and at the end.

The lab's copy of the visibility rule (``v3/export.home_visible``, mirrored in ``checks.conversation_row``)
says what *should* be on Home. This module asks the product instead: it calls the routes the phone's Home
calls, in process, against the scenario's emulator state, as the lab uid, under the scenario's flag profile,
and writes their bodies unmodified to ``home.json``.

Which routes (``app/lib``, read 2026-11-25):

- A v3 account's Home is the plain conversation list, not the Home feed. ``ConversationsV3Provider``
  (``app/lib/providers/conversations_v3_provider.dart:224``) suppresses the feed and episode reads for a v3
  account, and the page builds feed cards only when ``!v3On``
  (``app/lib/pages/conversations/conversations_page.dart:920``). ``GET /v1/home/feed`` is never called.
- The list is ``ConversationProvider._getConversationsFromServer``
  (``app/lib/providers/conversation_home_fetch.dart:115``): ``GET /v1/conversations`` with
  ``include_discarded=false&limit=50&offset=0&statuses=`` (``app/lib/backend/http/api/conversations.dart:619``)
  and the headers ``X-Omi-Home-Ownership: 1`` and ``X-Omi-Home-Page-Mode: auto``
  (``app/lib/backend/http/api/conversation_home_list.dart``).
- The conversation in progress leads Today from ``GET /v1/conversations/live``
  (``app/lib/backend/http/api/conversations_v3.dart:20``); it is recorded beside each list snapshot.

How the route runs: a FastAPI app holding the product router ``routers.conversations`` (imported before the
lab clock is installed, see :data:`HOME_MODULES`), driven over ASGI in this process (no socket, so the lab's
egress sinks are not involved). Auth is the hermetic tests' seam (``backend/testing/e2e/task_filter_qa_server.py``,
``owner_confirmation_fixture.py``): ``app.dependency_overrides`` replaces ``get_current_user_uid`` with the lab
uid, keeping its ``request_read_scope`` sub-dependency. Every check inside the route runs unchanged.

``on_home`` (a check field) is true when the conversation is in the list body, or is the live conversation the
live route returns. Disagreements with the lab's ``visible`` are listed in ``home.json`` (``disagreements``).
``home_titled`` / ``home_has_notes`` say whether the route's own row for it carries a title / an overview.

Paging (``page_to_end``, the ``home_paging`` check): at the end of a run, Home is paged the way
``ConversationProvider._loadMorePage`` (``app/lib/providers/conversation_provider.dart:1500``) pages it: the
first page as above, then each next page at ``offset`` + the storage rows the server reported
(``X-Omi-Conversation-Page-Size``, else the rows returned), with the server's ``X-Omi-Next-Cursor`` and the
page mode it answered (``X-Omi-Home-Page-Mode``), until ``X-Omi-Has-More`` says no (an older server's
answer: a page under 50 storage rows, or one the read budget cut, ``X-Omi-List-Truncated``). Ids are
compared by handle; the walk is written to ``home.json`` (``paging``, counts and handles only).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence
from urllib.parse import urlencode

SCHEMA = 1
ROUTE = 'GET /v1/conversations'
LIVE_ROUTE = 'GET /v1/conversations/live'
EVIDENCE = 'app/lib/providers/conversation_home_fetch.dart:115'
EVIDENCE_DETAIL = (
    'app/lib/providers/conversations_v3_provider.dart:224 (a v3 account makes no feed or episode reads)',
    'app/lib/pages/conversations/conversations_page.dart:920 (feed cards only when !v3On)',
    'app/lib/providers/conversation_home_fetch.dart:115 (Home list: ConversationApi.list, homeMode auto)',
    'app/lib/backend/http/api/conversations.dart:619 (query string)',
    'app/lib/backend/http/api/conversation_home_list.dart (X-Omi-Home-Ownership, X-Omi-Home-Page-Mode)',
    'app/lib/backend/http/api/conversations_v3.dart:20 (live conversation on top)',
)
# What the phone sends for the first Home page (no filters, no held episodes on a v3 account).
LIST_PATH = '/v1/conversations'
LIST_QUERY = {'include_discarded': 'false', 'limit': '50', 'offset': '0', 'statuses': ''}
LIST_HEADERS = {'X-Omi-Home-Ownership': '1', 'X-Omi-Home-Page-Mode': 'auto'}
LIVE_PATH = '/v1/conversations/live'
# Imported under the lab env before the clock is installed, so the routes read the virtual clock.
HOME_MODULES = ('routers.conversations',)
FINAL = 'final'
PAGE_SIZE = 50  # app/lib/providers/conversation_provider.dart _conversationPageSize
MAX_PAGES = 200
PAGING_EVIDENCE = 'app/lib/providers/conversation_provider.dart:1500 (_loadMorePage: offset, cursor, has-more)'


def handle_of(conversation_id: Any) -> str:
    """The short handle ``checks.conversation_row`` uses (the first 8 characters of the id)."""
    return str(conversation_id or '')[:8]


def list_ids(body: Any) -> list[str]:
    """Conversation ids in the list body, in the order the route returned them."""
    if not isinstance(body, list):
        return []
    return [str(row.get('id')) for row in body if isinstance(row, Mapping) and row.get('id')]


def live_id(body: Any) -> Optional[str]:
    if not isinstance(body, Mapping):
        return None
    conversation = body.get('conversation')
    if isinstance(conversation, Mapping) and conversation.get('id'):
        return str(conversation['id'])
    return None


def home_handles(snapshot: Mapping[str, Any]) -> Optional[set[str]]:
    """Handles on Home in one snapshot, or ``None`` when the list route did not answer 200."""
    if snapshot.get('status') != 200:
        return None
    handles = {handle_of(i) for i in list_ids(snapshot.get('response'))}
    live = snapshot.get('live') or {}
    if live.get('status') == 200 and live_id(live.get('response')):
        handles.add(handle_of(live_id(live.get('response'))))
    return handles


def home_rows(snapshot: Optional[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    """The route's rows in one snapshot (list body, then the live conversation), by handle."""
    out: dict[str, Mapping[str, Any]] = {}
    if not snapshot or snapshot.get('status') != 200:
        return out
    body = snapshot.get('response')
    for row in body if isinstance(body, list) else []:
        if isinstance(row, Mapping) and row.get('id'):
            out.setdefault(handle_of(row['id']), row)
    live = snapshot.get('live') or {}
    response = live.get('response') if live.get('status') == 200 else None
    conversation = response.get('conversation') if isinstance(response, Mapping) else None
    if isinstance(conversation, Mapping) and conversation.get('id'):
        out.setdefault(handle_of(conversation['id']), conversation)
    return out


def annotate(
    rows: Sequence[dict[str, Any]],
    handles: Optional[set[str]],
    route_rows: Optional[Mapping[str, Mapping[str, Any]]] = None,
) -> list[dict[str, Any]]:
    """Set ``on_home`` on each conversation row (``None`` when the route gave no answer), and
    ``home_titled`` / ``home_has_notes`` from the route's own row (``None`` when it is not on Home)."""
    from testing.pipeline_lab.scenario.checks import has_notes, has_title

    for row in rows:
        row['on_home'] = None if handles is None else row.get('handle') in handles
        route = (route_rows or {}).get(row.get('handle'))
        row['home_titled'] = None if route is None else has_title(route)
        row['home_has_notes'] = None if route is None else has_notes(route)
    return list(rows)


def disagreements(
    label: str, rows: Sequence[Mapping[str, Any]], handles: Optional[set[str]] = None
) -> list[dict[str, Any]]:
    """Rows where the lab's copy (``visible``) and the route (``on_home``) disagree, and cards the route
    returned that are not among the lab's v3 rows (``route_only``). Handles and labels only, no text."""
    out = []
    known = {row.get('handle') for row in rows}
    for handle in sorted((handles or set()) - known):
        out.append({'label': label, 'handle': handle, 'route_only': True, 'lab_visible': None, 'on_home': True})
    for row in rows:
        if row.get('deleted') or row.get('on_home') is None:
            continue
        if bool(row.get('visible')) != bool(row.get('on_home')):
            out.append(
                {
                    'label': label,
                    'handle': row.get('handle'),
                    'recordings': list(row.get('recordings') or []),
                    'lab_visible': bool(row.get('visible')),
                    'on_home': bool(row.get('on_home')),
                    'hidden_reason': row.get('hidden_reason'),
                    'status': row.get('status'),
                }
            )
    return out


# ---- calling the route ---------------------------------------------------------------------------


def build_app(uid: str) -> Any:
    """The product's conversations router with the lab uid as the authenticated owner."""
    from fastapi import Depends, FastAPI
    from routers import conversations as conversations_router
    from utils.other import endpoints as auth

    app = FastAPI()
    app.include_router(conversations_router.router)

    def lab_owner(_read_scope: Any = Depends(auth.request_read_scope)) -> str:
        return uid

    app.dependency_overrides[auth.get_current_user_uid] = lab_owner
    return app


async def asgi_get(app: Any, path: str, query: Mapping[str, str], headers: Mapping[str, str]) -> tuple[int, Any]:
    """One GET through the ASGI app, no socket. Returns ``(status, parsed JSON body)``."""
    status, body, _ = await asgi_request(app, path, query, headers)
    return status, body


async def asgi_request(
    app: Any, path: str, query: Mapping[str, str], headers: Mapping[str, str]
) -> tuple[int, Any, dict[str, str]]:
    """One GET through the ASGI app, no socket. Returns ``(status, parsed JSON body, response headers)``
    with header names lowercased."""
    sent: list[Mapping[str, Any]] = []
    raw_headers = [(b'host', b'lab.local')] + [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    scope = {
        'type': 'http',
        'asgi': {'version': '3.0'},
        'http_version': '1.1',
        'method': 'GET',
        'scheme': 'http',
        'path': path,
        'raw_path': path.encode(),
        'root_path': '',
        'query_string': urlencode(query).encode(),
        'headers': raw_headers,
        'client': ('127.0.0.1', 1),
        'server': ('lab.local', 80),
    }
    requested = False

    async def receive() -> Mapping[str, Any]:
        nonlocal requested
        if not requested:
            requested = True
            return {'type': 'http.request', 'body': b'', 'more_body': False}
        await asyncio.sleep(3600)  # the client never disconnects mid-request
        return {'type': 'http.disconnect'}

    async def send(message: Mapping[str, Any]) -> None:
        sent.append(message)

    await app(scope, receive, send)
    start = next((m for m in sent if m['type'] == 'http.response.start'), {})
    status = int(start.get('status') or 0)
    response_headers = {
        (k.decode('latin-1') if isinstance(k, bytes) else str(k)).lower(): (
            v.decode('latin-1') if isinstance(v, bytes) else str(v)
        )
        for k, v in start.get('headers') or []
    }
    body = b''.join(m.get('body', b'') for m in sent if m['type'] == 'http.response.body')
    try:
        return status, (json.loads(body.decode('utf-8')) if body else None), response_headers
    except (UnicodeDecodeError, json.JSONDecodeError):
        return status, {'unparsed_body_bytes': len(body)}, response_headers


def _int(value: Any) -> Optional[int]:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


async def walk_pages(app: Any, *, page_size: int = PAGE_SIZE, max_pages: int = MAX_PAGES) -> dict[str, Any]:
    """Page ``GET /v1/conversations`` to its end the way the app does. Returns the pages (counts and flags
    only) and the handles in the order they arrived; ``error`` when a page did not answer 200 or the walk
    did not end."""
    offset, cursor, mode = 0, None, LIST_HEADERS['X-Omi-Home-Page-Mode']
    pages: list[dict[str, Any]] = []
    handles: list[str] = []
    for _ in range(max_pages):
        query = {**LIST_QUERY, 'limit': str(page_size), 'offset': str(offset)}
        if cursor:
            query['cursor'] = cursor
        status, body, headers = await asgi_request(
            app, LIST_PATH, query, {**LIST_HEADERS, 'X-Omi-Home-Page-Mode': mode}
        )
        if status != 200 or not isinstance(body, list):
            return {'pages': pages, 'handles': handles, 'error': f'{ROUTE} {status} at offset {offset}'}
        ids = list_ids(body)
        storage = _int(headers.get('x-omi-conversation-page-size'))
        storage = len(ids) if storage is None else storage
        more_header = headers.get('x-omi-has-more')
        truncated = headers.get('x-omi-list-truncated') == 'true'
        has_more = (
            more_header == 'true' if more_header in ('true', 'false') else (not truncated and storage >= page_size)
        )
        pages.append(
            {
                'offset': offset,
                'rows': len(ids),
                'storage_rows': storage,
                'has_more': has_more,
                'cursor': bool(cursor),
                'mode': headers.get('x-omi-home-page-mode'),
                'truncated': truncated,
            }
        )
        handles.extend(handle_of(i) for i in ids)
        offset += storage
        cursor = headers.get('x-omi-next-cursor') or None
        if headers.get('x-omi-home-page-mode') in ('indexed', 'legacy'):
            mode = headers['x-omi-home-page-mode']
        if not has_more:
            return {'pages': pages, 'handles': handles}
        if storage <= 0 and not cursor:
            return {'pages': pages, 'handles': handles, 'error': 'the server said more but did not advance'}
    return {'pages': pages, 'handles': handles, 'error': f'no end after {max_pages} pages'}


def paging_verdict(walk: Mapping[str, Any], visible: Sequence[str], hidden: Sequence[str]) -> dict[str, Any]:
    """Every handle in ``visible`` exactly once, none of ``hidden``: the ``home_paging`` facts."""
    seen = list(walk.get('handles') or [])
    counts: dict[str, int] = {}
    for handle in seen:
        counts[handle] = counts.get(handle, 0) + 1
    out: dict[str, Any] = {
        'pages': len(walk.get('pages') or []),
        'expected': len(visible),
        'seen': sum(1 for h in visible if counts.get(h)),
        'missing': sorted(h for h in visible if not counts.get(h)),
        'duplicated': sorted(h for h, n in counts.items() if n > 1),
        'hidden_seen': sorted(h for h in hidden if counts.get(h)),
        'requests': walk.get('pages') or [],
    }
    if walk.get('error'):
        out['error'] = walk['error']
    return out


class HomeRecorder:
    """Calls the Home routes at each ``expect`` checkpoint and at the end; writes ``home.json``.

    The run's ``ScenarioOps`` holds the recorder (``ops.home``) and calls it explicitly: at a checkpoint,
    :meth:`write_home_snapshot` first (Home at the checkpoint's instant, before ops reads its own snapshot),
    and every ``ops.snapshot`` passes its rows through :meth:`annotate_rows` (``on_home`` from the latest
    capture), so the checks read ``on_home``. ``scenario/run.py`` makes the final call (``at=None``) before
    the final snapshot. No method of the runner is wrapped.
    """

    def __init__(
        self,
        *,
        uid: str,
        out_dir: Path,
        offset: Callable[[Any], float],
        now: Callable[[], Any],
        app_factory: Callable[[str], Any] = build_app,
    ):
        self.uid = uid
        self.out_dir = Path(out_dir)
        self.offset = offset
        self.now = now
        self._app_factory = app_factory
        self._app: Any = None
        self.snapshots: list[dict[str, Any]] = []
        self.disagreements: list[dict[str, Any]] = []
        self.errors: list[str] = []
        self._handles: Optional[set[str]] = None
        self._route_rows: dict[str, Mapping[str, Any]] = {}
        self._label: Optional[str] = None
        self.paging: Optional[dict[str, Any]] = None

    # ---- capture

    def _call(self) -> dict[str, Any]:
        if self._app is None:
            self._app = self._app_factory(self.uid)
        app = self._app

        async def both() -> tuple[tuple[int, Any], tuple[int, Any]]:
            listed = await asgi_get(app, LIST_PATH, LIST_QUERY, LIST_HEADERS)
            live = await asgi_get(app, LIVE_PATH, {}, {})
            return listed, live

        (status, body), (live_status, live_body) = asyncio.run(both())
        return {
            'status': status,
            'response': body,
            'live': {'route': LIVE_ROUTE, 'status': live_status, 'response': live_body},
        }

    def capture(self, label: str) -> dict[str, Any]:
        """Call the routes now (blocking; run it off the event loop) and keep the snapshot."""
        at = self.offset(self.now())
        try:
            called = self._call()
        except Exception as error:  # noqa: BLE001 - recorded on the snapshot, the run goes on
            self.errors.append(f'{label}: {type(error).__name__}: {error}')
            called = {'status': 0, 'response': None, 'error': f'{type(error).__name__}: {error}'}
        snapshot = {'at': at, 'label': label, **called}
        self.snapshots.append(snapshot)
        self._handles = home_handles(snapshot)
        self._route_rows = home_rows(snapshot)
        self._label = label
        return snapshot

    def page_to_end(self, visible: Sequence[str], hidden: Sequence[str]) -> dict[str, Any]:
        """Page Home to its end (``walk_pages``) and judge it against ``visible`` / ``hidden`` handles; kept in
        ``home.json`` (``paging``). Blocking: call it with ``asyncio.to_thread``."""
        if self._app is None:
            self._app = self._app_factory(self.uid)
        try:
            walk = asyncio.run(walk_pages(self._app))
        except Exception as error:  # noqa: BLE001 - recorded, the check fails
            walk = {'pages': [], 'handles': [], 'error': f'{type(error).__name__}: {error}'}
        self.paging = paging_verdict(walk, visible, hidden)
        self.write()
        return self.paging

    # ---- called by the run (ops.py at each checkpoint, run.py at the end)

    def write_home_snapshot(self, at: Optional[float]) -> Optional[dict[str, Any]]:
        """Capture Home and rewrite ``home.json``. ``at``: the checkpoint's offset in seconds, ``None`` for the
        end of the run. Blocking (it runs the ASGI app in its own loop): call it with ``asyncio.to_thread``.
        Two checks at one instant share one capture."""
        label = FINAL if at is None else f'checkpoint@{at:g}'
        if self.snapshots and self.snapshots[-1]['label'] == label:
            return None
        snapshot = self.capture(label)
        self.write()
        return snapshot

    def annotate_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """``on_home`` on each row from the latest capture; disagreements with ``visible`` are kept."""
        annotated = annotate(rows, self._handles, self._route_rows)
        found = disagreements(self._label or '', annotated, self._handles)
        new = [d for d in found if d not in self.disagreements]
        if new:
            # home.json was written at capture, before this comparison: rewrite it so the file and
            # result.json report the same disagreements.
            self.disagreements.extend(new)
            self.write()
        return annotated

    def document(self) -> dict[str, Any]:
        doc: dict[str, Any] = {
            'schema': SCHEMA,
            'route': ROUTE,
            'evidence': EVIDENCE,
            'evidence_detail': list(EVIDENCE_DETAIL),
            'request': {'path': LIST_PATH, 'query': LIST_QUERY, 'headers': LIST_HEADERS},
            'auth': 'app.dependency_overrides[get_current_user_uid] = lab uid (hermetic-test seam)',
            'snapshots': self.snapshots,
            'disagreements': self.disagreements,
        }
        if self.errors:
            doc['errors'] = self.errors
        if self.paging is not None:
            doc['paging'] = {'evidence': PAGING_EVIDENCE, **self.paging}
        return doc

    def write(self) -> Path:
        path = self.out_dir / 'home.json'
        path.write_text(json.dumps(self.document(), indent=1, default=str))
        return path

    def failures(self) -> list[str]:
        """Each capture where either Home route raised or did not answer 200, as ``label: route status``.

        A broken Home route makes the scenario an error even when no check reads ``on_home``."""
        out = []
        for snap in self.snapshots:
            label = snap.get('label')
            if snap.get('status') != 200:
                out.append(
                    f"{label}: {ROUTE} {snap.get('status')}" + (f" ({snap['error']})" if snap.get('error') else '')
                )
            live = snap.get('live') or {}
            if live and live.get('status') != 200:
                out.append(f"{label}: {live.get('route', LIVE_ROUTE)} {live.get('status')}")
        return out

    def summary(self) -> dict[str, Any]:
        """For ``result.json``: counts only."""
        return {
            'route': ROUTE,
            'snapshots': len(self.snapshots),
            'disagreements': len(self.disagreements),
            'errors': len(self.errors),
            'failures': self.failures(),
        }
