"""One Google calendar catalog/selection and calendar-qualified event identity."""

import base64
import json
from typing import Any
from urllib.parse import quote

from database import google_calendar_preferences as preferences
from utils.executors import db_executor, run_blocking

BASE = 'https://www.googleapis.com/calendar/v3'
MAX_SELECTED = 25
MAX_CATALOG_PAGES = 20
EVENT_PREFIX = 'omi-gcal:'


async def google_api_request(*args: Any, **kwargs: Any) -> Any:
    # tools/__init__.py eagerly imports calendar_tools. Resolve this transport at
    # call time so importing the pure catalog/identity helpers cannot cycle back.
    from utils.retrieval.tools.google_utils import google_api_request as request

    return await request(*args, **kwargs)


async def readable_calendars(access_token: str) -> tuple[str, list[dict[str, Any]]]:
    """Read every catalog page, including hidden readable calendars; never persist credentials."""
    calendars: dict[str, dict[str, Any]] = {}
    page = None
    seen: set[str] = set()
    for _ in range(MAX_CATALOG_PAGES):
        params: dict[str, Any] = {'maxResults': 250, 'minAccessRole': 'reader', 'showHidden': 'true'}
        if page:
            params['pageToken'] = page
        data = await google_api_request('GET', f'{BASE}/users/me/calendarList', access_token, params=params)
        for row in data.get('items', []):
            if not isinstance(row, dict) or not isinstance(row.get('id'), str) or not row['id']:
                continue
            if row.get('deleted') or row.get('accessRole') not in {
                'reader',
                'writer',
                'owner',
                'writerWithoutPrivateAccess',
            }:
                continue
            calendars[row['id']] = {
                'id': row['id'],
                'name': str(row.get('summaryOverride') or row.get('summary') or row['id']),
                'primary': row.get('primary') is True,
                'available': True,
            }
        page = data.get('nextPageToken')
        if not page:
            break
        if not isinstance(page, str) or page in seen:
            raise ValueError('invalid_calendar_catalog_pagination')
        seen.add(page)
    else:
        raise ValueError('calendar_catalog_limit_exceeded')
    primary = next((row['id'] for row in calendars.values() if row['primary']), None)
    if primary is None:
        # Never attach a saved selection to an unverified or different Google account.
        raise ValueError('google_primary_calendar_unavailable')
    return primary, list(calendars.values())


def selected_ids(selections: dict, primary: str) -> list[str]:
    key = preferences.account_key(primary)
    if key not in selections:
        return ['primary']
    saved = selections[key]
    if (
        not isinstance(saved, list)
        or not 1 <= len(saved) <= MAX_SELECTED
        or any(not isinstance(value, str) or not value or len(value) > 1024 for value in saved)
    ):
        raise ValueError('invalid_calendar_selection')
    return list(dict.fromkeys(saved))


async def catalog(uid: str, access_token: str) -> dict[str, Any]:
    primary, rows = await readable_calendars(access_token)
    selections = await run_blocking(db_executor, preferences.get_selections, uid)
    ids = selected_ids(selections, primary)
    ids = [primary if value == 'primary' else value for value in ids]
    known = {row['id'] for row in rows}
    # Retain unavailable selections visibly so the user can remove them. Do not
    # replace them with primary and silently broaden the chosen read scope.
    rows.extend({'id': value, 'name': '', 'primary': False, 'available': False} for value in ids if value not in known)
    return {'account_id': primary, 'calendars': rows, 'selected_ids': ids, 'write_calendar_id': 'primary'}


async def read_ids(uid: str, access_token: str) -> list[str]:
    selections = await run_blocking(db_executor, preferences.get_selections, uid)
    if not selections:
        # Released users retain the exact primary-only lane, including legacy
        # grants that can read events but cannot enumerate the calendar catalog.
        return ['primary']
    primary, rows = await readable_calendars(access_token)
    readable = {row['id'] for row in rows}
    return [
        'primary' if value == primary else value
        for value in selected_ids(selections, primary)
        if value == 'primary' or value in readable
    ]


def event_reference(calendar_id: str, event_id: str) -> str:
    if calendar_id == 'primary':
        return event_id
    payload = json.dumps([calendar_id, event_id], separators=(',', ':')).encode()
    return EVENT_PREFIX + base64.urlsafe_b64encode(payload).decode().rstrip('=')


def event_path(reference: str) -> str:
    calendar_id, event_id = 'primary', reference
    if reference.startswith(EVENT_PREFIX):
        encoded = reference[len(EVENT_PREFIX) :]
        if len(encoded) > 8192:
            raise ValueError('invalid_calendar_event_reference')
        try:
            values = json.loads(base64.b64decode(encoded + '=' * (-len(encoded) % 4), altchars=b'-_', validate=True))
            if not isinstance(values, list) or len(values) != 2:
                raise ValueError('invalid_calendar_event_reference')
            calendar_id, event_id = values
        except (ValueError, UnicodeDecodeError) as error:
            raise ValueError('invalid_calendar_event_reference') from error
    if any(not isinstance(value, str) or not value or len(value) > 2048 for value in [calendar_id, event_id]):
        raise ValueError('invalid_calendar_event_reference')
    return f'{BASE}/calendars/{quote(calendar_id, safe="")}/events/{quote(event_id, safe="")}'
