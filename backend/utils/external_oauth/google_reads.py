"""Google REST semantic read adapters.

These adapters accept only Omi product vocabulary and return normalized DTOs.
The provider token is injected inside a purpose-bound secret lease and never
returned to a route or caller.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from typing import Any, Mapping, Protocol, Sequence

import httpx

from utils.external_oauth.contracts import (
    CalendarEvent,
    Capability,
    Connector,
    ExternalAuthorizationComposer,
    ExternalSecretExecutor,
    MailMessage,
)

GMAIL_MESSAGES_URL = 'https://gmail.googleapis.com/gmail/v1/users/me/messages'
CALENDAR_EVENTS_URL = 'https://www.googleapis.com/calendar/v3/calendars/primary/events'
MAX_PROVIDER_RESPONSE_BYTES = 2 * 1024 * 1024


class CredentialLocator(Protocol):
    async def active_secret_id(self, *, connection_id: str, generation: int) -> str: ...


def _google_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _access_token(secret: memoryview) -> str:
    record = json.loads(bytes(secret))
    encoded = record.get('access_token')
    if not isinstance(encoded, str):
        raise PermissionError('active credential has no access token')
    return base64.b64decode(encoded, validate=True).decode()


def _bounded_json(response: httpx.Response) -> Mapping[str, Any]:
    if len(response.content) > MAX_PROVIDER_RESPONSE_BYTES:
        raise ValueError('provider_response_too_large')
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError('provider_response_shape_invalid')
    return payload


class GoogleMailReadAdapter:
    def __init__(
        self,
        *,
        authorization: ExternalAuthorizationComposer,
        secrets_executor: ExternalSecretExecutor,
        credential_locator: CredentialLocator,
        http: httpx.AsyncClient,
    ):
        self._authorization = authorization
        self._secrets = secrets_executor
        self._locator = credential_locator
        self._http = http

    async def list_messages(self, *, external_owner_id: str, limit: int = 25) -> Sequence[MailMessage]:
        if limit < 1 or limit > 100:
            raise ValueError('mail limit must be between 1 and 100')
        context = await self._authorization.authorize(
            external_owner_id=external_owner_id,
            connector=Connector.GMAIL,
            capability=Capability.MAIL_MESSAGES_READ,
            operation_id=f'mail-list:{external_owner_id}',
        )
        secret_id = await self._locator.active_secret_id(
            connection_id=context.connection_id, generation=context.generation
        )

        async def execute(secret: memoryview) -> Sequence[MailMessage]:
            token = _access_token(secret)
            listing = await self._http.get(
                GMAIL_MESSAGES_URL,
                headers={'Authorization': f'Bearer {token}'},
                params={'maxResults': limit},
                follow_redirects=False,
            )
            refs = _bounded_json(listing).get('messages', [])
            if not isinstance(refs, list):
                raise ValueError('provider_response_shape_invalid')
            messages: list[MailMessage] = []
            for ref in refs[:limit]:
                if not isinstance(ref, dict) or not isinstance(ref.get('id'), str):
                    continue
                detail = await self._http.get(
                    f'{GMAIL_MESSAGES_URL}/{ref["id"]}',
                    headers={'Authorization': f'Bearer {token}'},
                    params={
                        'format': 'metadata',
                        'metadataHeaders': ['From', 'Subject', 'Date'],
                    },
                    follow_redirects=False,
                )
                payload = _bounded_json(detail)
                headers = {
                    item.get('name', '').lower(): item.get('value', '')
                    for item in payload.get('payload', {}).get('headers', [])
                    if isinstance(item, dict)
                }
                messages.append(
                    MailMessage(
                        message_id=str(payload['id']),
                        thread_id=str(payload.get('threadId', '')),
                        sender=str(headers.get('from', '')),
                        subject=str(headers.get('subject', '')),
                        snippet=str(payload.get('snippet', '')),
                        received_at=datetime.fromtimestamp(int(payload.get('internalDate', 0)) / 1000, tz=timezone.utc),
                    )
                )
            return messages

        return await self._secrets.with_secret_lease(secret_id=secret_id, context=context, operation=execute)


class GoogleCalendarReadAdapter:
    def __init__(
        self,
        *,
        authorization: ExternalAuthorizationComposer,
        secrets_executor: ExternalSecretExecutor,
        credential_locator: CredentialLocator,
        http: httpx.AsyncClient,
    ):
        self._authorization = authorization
        self._secrets = secrets_executor
        self._locator = credential_locator
        self._http = http

    async def list_events(
        self, *, external_owner_id: str, starts_after: datetime, ends_before: datetime, limit: int = 100
    ) -> Sequence[CalendarEvent]:
        if limit < 1 or limit > 250 or starts_after >= ends_before:
            raise ValueError('invalid calendar read bounds')
        context = await self._authorization.authorize(
            external_owner_id=external_owner_id,
            connector=Connector.GOOGLE_CALENDAR,
            capability=Capability.CALENDAR_EVENTS_READ,
            operation_id=f'calendar-list:{external_owner_id}',
        )
        secret_id = await self._locator.active_secret_id(
            connection_id=context.connection_id, generation=context.generation
        )

        async def execute(secret: memoryview) -> Sequence[CalendarEvent]:
            token = _access_token(secret)
            response = await self._http.get(
                CALENDAR_EVENTS_URL,
                headers={'Authorization': f'Bearer {token}'},
                params={
                    'timeMin': starts_after.isoformat(),
                    'timeMax': ends_before.isoformat(),
                    'singleEvents': 'true',
                    'orderBy': 'startTime',
                    'maxResults': limit,
                },
                follow_redirects=False,
            )
            items = _bounded_json(response).get('items', [])
            if not isinstance(items, list):
                raise ValueError('provider_response_shape_invalid')
            events: list[CalendarEvent] = []
            for item in items[:limit]:
                if not isinstance(item, dict) or not isinstance(item.get('id'), str):
                    continue
                start = item.get('start', {})
                end = item.get('end', {})
                starts_at = start.get('dateTime') or start.get('date')
                ends_at = end.get('dateTime') or end.get('date')
                if not isinstance(starts_at, str) or not isinstance(ends_at, str):
                    continue
                events.append(
                    CalendarEvent(
                        event_id=item['id'],
                        calendar_id='primary',
                        title=str(item.get('summary', '')),
                        starts_at=_google_datetime(starts_at),
                        ends_at=_google_datetime(ends_at),
                        attendee_count=(
                            len(item.get('attendees', [])) if isinstance(item.get('attendees', []), list) else 0
                        ),
                    )
                )
            return events

        return await self._secrets.with_secret_lease(secret_id=secret_id, context=context, operation=execute)
