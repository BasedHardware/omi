from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from utils.messaging.contracts import ChannelMessage, Artifact, InboundAttachment
from utils.messaging.identity import advances_inbound_head, coerce_utc_datetime
from utils.messaging.album_turn import inbox_message
from utils.messaging.gateway import Gateway


def test_coerce_utc_datetime_handles_all_variants():
    # Naive datetime
    naive_dt = datetime(2026, 10, 28, 10, 0, 0)
    coerced = coerce_utc_datetime(naive_dt)
    assert coerced is not None
    assert coerced.tzinfo == timezone.utc
    assert coerced.year == 2026 and coerced.hour == 10

    # Aware datetime (non-UTC)
    offset_tz = timezone(timedelta(hours=2))
    aware_dt = datetime(2026, 10, 28, 12, 0, 0, tzinfo=offset_tz)
    coerced = coerce_utc_datetime(aware_dt)
    assert coerced is not None
    assert coerced.tzinfo == timezone.utc
    assert coerced.hour == 10

    # Naive ISO string
    naive_str = "2026-10-28T10:00:00"
    coerced = coerce_utc_datetime(naive_str)
    assert coerced is not None
    assert coerced.tzinfo == timezone.utc
    assert coerced.hour == 10

    # Aware ISO string with Z
    iso_z = "2026-10-28T10:00:00Z"
    coerced = coerce_utc_datetime(iso_z)
    assert coerced is not None
    assert coerced.tzinfo == timezone.utc
    assert coerced.hour == 10

    # None and invalid inputs
    assert coerce_utc_datetime(None) is None
    assert coerce_utc_datetime("invalid-date") is None
    assert coerce_utc_datetime(12345) is None


def test_advances_inbound_head_with_naive_and_iso_timestamps():
    now_utc = datetime(2026, 10, 28, 10, 0, 0, tzinfo=timezone.utc)
    earlier_utc = datetime(2026, 10, 28, 9, 0, 0, tzinfo=timezone.utc)

    msg = ChannelMessage(
        channel="telegram",
        provider="bot",
        external_user_id="user1",
        external_chat_id="chat1",
        provider_message_id="100",
        text="hello",
        received_at=now_utc,
    )

    # 1. Prior has naive ISO string earlier than message
    assert advances_inbound_head(msg, {"received_at": "2026-10-28T09:00:00", "provider_message_id": "90"}) is True

    # 2. Prior has naive ISO string later than message
    assert advances_inbound_head(msg, {"received_at": "2026-10-28T11:00:00", "provider_message_id": "110"}) is False

    # 3. Prior has naive datetime earlier
    assert advances_inbound_head(msg, {"received_at": earlier_utc.replace(tzinfo=None), "provider_message_id": "90"}) is True

    # 4. Prior has None received_at
    assert advances_inbound_head(msg, {"received_at": None, "provider_message_id": "90"}) is True


def test_inbox_message_coerces_naive_and_datetime_and_guards_none_media():
    base_payload = {
        "channel": "telegram",
        "provider": "bot",
        "external_user_id": "u1",
        "external_chat_id": "c1",
        "provider_message_id": "m1",
        "text": "test",
    }

    # 1. Naive ISO string should be coerced to UTC aware ChannelMessage
    p1 = dict(base_payload, received_at="2026-10-28T10:00:00")
    msg1 = inbox_message(p1)
    assert msg1.received_at.tzinfo == timezone.utc
    assert msg1.received_at.hour == 10

    # 2. Already datetime object (naive or aware)
    p2 = dict(base_payload, received_at=datetime(2026, 10, 28, 10, 0, 0))
    msg2 = inbox_message(p2)
    assert msg2.received_at.tzinfo == timezone.utc

    p2_aware = dict(base_payload, received_at=datetime(2026, 10, 28, 10, 0, 0, tzinfo=timezone.utc))
    msg2_aware = inbox_message(p2_aware)
    assert msg2_aware.received_at.tzinfo == timezone.utc

    # 3. Explicit None for media and attachments
    p3 = dict(base_payload, received_at="2026-10-28T10:00:00Z", media=None, attachments=None)
    msg3 = inbox_message(p3)
    assert msg3.media == ()
    assert msg3.attachments == ()


@pytest.mark.asyncio
async def test_gateway_process_with_naive_iso_and_settlement_on_error():
    store = MagicMock()
    adapter = MagicMock()
    adapter.channel = "telegram"
    adapter.provider = "bot"

    gw = Gateway(adapter=adapter, store=store)

    payload = {
        "channel": "telegram",
        "provider": "bot",
        "external_user_id": "u1",
        "external_chat_id": "c1",
        "provider_message_id": "m1",
        "text": "hi",
        "received_at": "2026-10-28T10:00:00",  # naive ISO string
        "media": None,
        "attachments": None,
    }

    store.claim_next.return_value = ("inbox/path/1", payload)

    with patch.object(gw, "_process_claimed", AsyncMock(side_effect=RuntimeError("processing exploded"))):
        with patch.object(gw, "_wake_pending", AsyncMock()) as mock_wake:
            res = await gw._process("inbox/path/1")
            assert res is None  # settled failure
            # Verify store.settle was called despite naive timestamp and exception
            store.settle.assert_called_once_with("inbox/path/1")
            # Verify wake_pending was called with properly hydrated ChannelMessage
            mock_wake.assert_called_once()
            woken_msg = mock_wake.call_args[0][0]
            assert isinstance(woken_msg, ChannelMessage)
            assert woken_msg.received_at.tzinfo == timezone.utc
