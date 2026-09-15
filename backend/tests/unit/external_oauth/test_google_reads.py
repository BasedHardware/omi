import base64
import json
import os
from datetime import datetime, timezone

import httpx
import pytest
from cryptography.hazmat.primitives.keywrap import aes_key_unwrap, aes_key_wrap

from utils.external_oauth.contracts import Capability, Connector, SecretBinding, SecretLeaseContext, SecretPurpose
from utils.external_oauth.google_reads import GoogleCalendarReadAdapter, GoogleMailReadAdapter
from utils.external_oauth.vault import EnvelopeSecretExecutor, InMemoryCiphertextStore


class FakeKeyWrapper:
    key_version = 'fake-kms/versions/1'

    def __init__(self):
        self.kek = os.urandom(32)

    async def wrap(self, dek: bytes) -> bytes:
        return aes_key_wrap(self.kek, dek)

    async def unwrap(self, wrapped_dek: bytes, *, key_version: str) -> bytes:
        return aes_key_unwrap(self.kek, wrapped_dek)


async def _allow_read(secret, context):
    assert context.purpose == SecretPurpose.READ


class FakeAuthorization:
    async def authorize(self, *, external_owner_id, connector, capability, operation_id):
        expected = {
            Connector.GMAIL: Capability.MAIL_MESSAGES_READ,
            Connector.GOOGLE_CALENDAR: Capability.CALENDAR_EVENTS_READ,
        }
        assert expected[connector] == capability
        return SecretLeaseContext('connection-1', 1, 0, operation_id, SecretPurpose.READ)


class FakeLocator:
    def __init__(self, secret_id):
        self.secret_id = secret_id

    async def active_secret_id(self, *, connection_id, generation):
        assert connection_id == 'connection-1' and generation == 1
        return self.secret_id


async def _vault():
    executor = EnvelopeSecretExecutor(
        key_wrapper=FakeKeyWrapper(), store=InMemoryCiphertextStore(), authorize=_allow_read
    )
    credential = json.dumps({'access_token': base64.b64encode(b'leased-token').decode()}).encode()
    secret = await executor.create(
        binding=SecretBinding('owner-1', 'connection-1', 'google', 'client-1', 1, 1), plaintext=credential
    )
    return executor, secret.secret_id


@pytest.mark.asyncio
async def test_gmail_adapter_uses_fixed_metadata_reads_and_returns_semantic_dto():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers['authorization'] == 'Bearer leased-token'
        if request.url.path.endswith('/messages'):
            return httpx.Response(200, json={'messages': [{'id': 'm1'}]})
        return httpx.Response(
            200,
            json={
                'id': 'm1',
                'threadId': 't1',
                'snippet': 'hello',
                'internalDate': '1000',
                'payload': {'headers': [{'name': 'From', 'value': 'sender'}, {'name': 'Subject', 'value': 'subject'}]},
            },
        )

    vault, secret_id = await _vault()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = GoogleMailReadAdapter(
            authorization=FakeAuthorization(),
            secrets_executor=vault,
            credential_locator=FakeLocator(secret_id),
            http=client,
        )
        messages = await adapter.list_messages(external_owner_id='owner-1', limit=1)
    assert messages[0].message_id == 'm1'
    assert messages[0].subject == 'subject'
    assert all(request.url.host == 'gmail.googleapis.com' for request in requests)
    assert 'leased-token' not in repr(messages)


@pytest.mark.asyncio
async def test_calendar_adapter_uses_fixed_primary_calendar_and_returns_semantic_dto():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == 'www.googleapis.com'
        assert request.url.path == '/calendar/v3/calendars/primary/events'
        assert request.headers['authorization'] == 'Bearer leased-token'
        return httpx.Response(
            200,
            json={
                'items': [
                    {
                        'id': 'event-1',
                        'summary': 'Planning',
                        'start': {'dateTime': '2026-08-30T10:00:00Z'},
                        'end': {'dateTime': '2026-08-30T11:00:00Z'},
                        'attendees': [{}, {}],
                    }
                ]
            },
        )

    vault, secret_id = await _vault()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = GoogleCalendarReadAdapter(
            authorization=FakeAuthorization(),
            secrets_executor=vault,
            credential_locator=FakeLocator(secret_id),
            http=client,
        )
        events = await adapter.list_events(
            external_owner_id='owner-1',
            starts_after=datetime(2026, 8, 30, tzinfo=timezone.utc),
            ends_before=datetime(2026, 8, 31, tzinfo=timezone.utc),
            limit=10,
        )
    assert events[0].event_id == 'event-1'
    assert events[0].attendee_count == 2
    assert 'leased-token' not in repr(events)


@pytest.mark.asyncio
async def test_calendar_all_day_dates_are_normalized_to_utc():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                'items': [
                    {
                        'id': 'all-day',
                        'start': {'date': '2026-08-30'},
                        'end': {'date': '2026-08-31'},
                    }
                ]
            },
        )

    vault, secret_id = await _vault()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = GoogleCalendarReadAdapter(
            authorization=FakeAuthorization(),
            secrets_executor=vault,
            credential_locator=FakeLocator(secret_id),
            http=client,
        )
        events = await adapter.list_events(
            external_owner_id='owner-1',
            starts_after=datetime(2026, 8, 30, tzinfo=timezone.utc),
            ends_before=datetime(2026, 9, 1, tzinfo=timezone.utc),
        )
    assert events[0].starts_at == datetime(2026, 8, 30, tzinfo=timezone.utc)
