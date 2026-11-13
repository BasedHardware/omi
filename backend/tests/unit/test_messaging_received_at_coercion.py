"""Unit tests for UTC datetime coercion and null attachment guards in utils.messaging."""

import asyncio
from datetime import datetime, timezone
import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock

for _mod_name, _attrs in (
    ('stripe', {}),
    ('utils.chat_turn', {'run_chat_turn': MagicMock()}),
    ('utils.messaging.history', {'history_tool': MagicMock()}),
):
    if _mod_name not in sys.modules:
        _mod = ModuleType(_mod_name)
        for _k, _v in _attrs.items():
            setattr(_mod, _k, _v)
        sys.modules[_mod_name] = _mod

from utils.messaging.album_turn import inbox_message
from utils.messaging.contracts import ChannelMessage
from utils.messaging.gateway import Gateway
from utils.messaging.identity import advances_inbound_head


def _sample_payload(**overrides):
    base = {
        'channel': 'telegram',
        'provider': 'telegram',
        'external_user_id': 'u-1',
        'external_chat_id': 'c-1',
        'provider_message_id': '101',
        'text': 'hello',
        'received_at': '2026-04-21T10:00:00',  # naive ISO-8601 string
    }
    base.update(overrides)
    return base


def test_inbox_message_coerces_naive_iso_and_datetime_to_utc_and_guards_null_tuples():
    """inbox_message() should normalize naive ISO strings/datetimes to UTC and handle explicit None media/attachments."""
    msg_naive_str = inbox_message(_sample_payload(received_at='2026-04-21T10:00:00', media=None, attachments=None))
    assert msg_naive_str.received_at == datetime(2026, 4, 21, 10, 0, 0, tzinfo=timezone.utc)
    assert msg_naive_str.media == ()
    assert msg_naive_str.attachments == ()

    naive_dt = datetime(2026, 4, 21, 11, 30, 0)
    msg_naive_dt = inbox_message(_sample_payload(received_at=naive_dt))
    assert msg_naive_dt.received_at == datetime(2026, 4, 21, 11, 30, 0, tzinfo=timezone.utc)


def test_advances_inbound_head_handles_mixed_naive_aware_and_iso_timestamps():
    """advances_inbound_head() should not raise TypeError when message.received_at and prior['received_at'] mix naive/aware/ISO."""
    msg = ChannelMessage(
        channel='telegram',
        provider='telegram',
        external_user_id='u-1',
        external_chat_id='c-1',
        provider_message_id='102',
        text='hi',
        received_at=datetime(2026, 4, 21, 12, 0, 5, tzinfo=timezone.utc),
    )
    # Prior stored as naive datetime
    assert advances_inbound_head(msg, {'received_at': datetime(2026, 4, 21, 12, 0, 0)}) is True
    # Prior stored as ISO-8601 string in the future
    assert advances_inbound_head(msg, {'received_at': '2026-04-21T12:00:10Z'}) is False


def test_gateway_process_does_not_crash_before_settle_on_naive_or_datetime_received_at():
    """Gateway._process() must not raise TypeError before entering try/finally when payload['received_at'] is naive ISO or datetime."""
    adapter = MagicMock()
    adapter.channel = 'telegram'
    adapter.provider = 'telegram'

    store = MagicMock()
    payload = _sample_payload(
        received_at='2026-04-21T10:00:00',  # naive ISO-8601 string that previously raised TypeError on subtraction
        media=None,
        attachments=None,
    )
    store.claim_next.return_value = ('inbox/path/1', payload)
    store.pending.return_value = []

    gw = Gateway(
        adapter=adapter,
        store=store,
        turn=MagicMock(),
        admission=MagicMock(),
        rate_limit=MagicMock(),
        wake=AsyncMock(),
    )
    gw._process_claimed = AsyncMock(return_value=True)

    result = asyncio.run(gw._process('inbox/path/1'))
    assert result is True
    gw._process_claimed.assert_awaited_once_with('inbox/path/1', payload)
    gw.wake.assert_not_awaited()
