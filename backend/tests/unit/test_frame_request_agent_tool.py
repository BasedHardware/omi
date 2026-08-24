from datetime import datetime, timedelta, timezone
import json
import asyncio
from types import SimpleNamespace

import pytest

from models.frame_request import FrameRequest, FrameRequestState
from utils.retrieval.tools import frame_request_tools


def _config():
    return {
        "configurable": {
            "user_id": "uid-1",
            "thread_id": "turn-1",
            "frame_request_turn_id": "message-1",
            "frame_request_session_id": "session-1",
            "frame_request_budget": {"reserved": False},
            "evidence_references": [
                {"id": "screen:mac-1-42", "kind": "screen", "frame_id": "mac-1-42", "state": "available"}
            ],
        }
    }


def _request(state=FrameRequestState.requested):
    now = datetime.now(timezone.utc)
    return FrameRequest(
        request_id="frame-1",
        uid="uid-1",
        device_id="mac-1",
        account_generation=3,
        dedupe_key="dedupe",
        screenshot_id="42",
        state=state,
        created_at=now,
        expires_at=now + timedelta(days=7),
        storage_id="temporary-object" if state == FrameRequestState.uploaded else None,
    )


@pytest.mark.asyncio
async def test_look_at_frame_rejects_unadmitted_screenshot():
    result = await frame_request_tools.look_at_frame_tool.ainvoke({"screenshot_id": "99"}, config=_config())
    assert "screen_reference_not_admitted" in result


def test_screen_delivery_route_recovers_legacy_device_qualified_id(monkeypatch):
    class Snapshot:
        exists = True

        @staticmethod
        def to_dict():
            return {"clientDeviceId": "mac-with-hyphen"}

    class Node:
        def collection(self, _name):
            return self

        def document(self, _name):
            return self

        def get(self):
            return Snapshot()

    monkeypatch.setattr(frame_request_tools, "get_firestore_client", lambda: Node())

    assert frame_request_tools._screen_delivery_route("uid-1", "mac-with-hyphen-42") == (
        "mac-with-hyphen",
        "42",
        None,
    )


@pytest.mark.asyncio
async def test_look_at_frame_enqueues_then_reports_asked_mac(monkeypatch):
    request = _request()
    monkeypatch.setattr(
        frame_request_tools, "decision_for", lambda _uid: SimpleNamespace(enabled=True, account_generation=3)
    )
    monkeypatch.setattr(frame_request_tools, "_screen_delivery_route", lambda *_args: ("mac-1", "42", None))
    monkeypatch.setattr(frame_request_tools, "enqueue_frame_request", lambda *_args, **_kwargs: (request, False))
    monkeypatch.setattr(frame_request_tools, "get_frame_request", lambda *_args: request)

    result = await frame_request_tools.look_at_frame_tool.ainvoke({"screenshot_id": "mac-1-42"}, config=_config())

    assert '"state": "asked_mac"' in result


@pytest.mark.asyncio
async def test_look_at_frame_consumes_uploaded_pixels_without_promotion(monkeypatch):
    request = _request(FrameRequestState.uploaded)
    monkeypatch.setattr(
        frame_request_tools, "decision_for", lambda _uid: SimpleNamespace(enabled=True, account_generation=3)
    )
    monkeypatch.setattr(frame_request_tools, "_screen_delivery_route", lambda *_args: ("mac-1", "42", None))
    monkeypatch.setattr(frame_request_tools, "enqueue_frame_request", lambda *_args, **_kwargs: (request, True))
    monkeypatch.setattr(frame_request_tools, "get_frame_request", lambda *_args: request)
    monkeypatch.setattr(frame_request_tools, "download_frame_request_pixels", lambda *_args: b"jpeg")
    monkeypatch.setattr(
        frame_request_tools,
        "reserve_frame_vision_invocation",
        lambda *_args, **_kwargs: {"state": "invoked", "reserved": True},
    )
    monkeypatch.setattr(frame_request_tools, "complete_frame_vision_invocation", lambda *_args, **_kwargs: None)

    async def describe(_uid, _payload, _content_type):
        return "A budget spreadsheet is visible."

    monkeypatch.setattr(frame_request_tools, "describe_image", describe)

    result = await frame_request_tools.look_at_frame_tool.ainvoke({"screenshot_id": "mac-1-42"}, config=_config())

    assert '"state": "available"' in result
    assert "budget spreadsheet" in result


@pytest.mark.asyncio
async def test_look_at_frame_request_budget_invokes_vision_at_most_once(monkeypatch):
    request = _request(FrameRequestState.uploaded)
    config = _config()
    vision_calls = []
    telemetry = []
    monkeypatch.setattr(
        frame_request_tools, "decision_for", lambda _uid: SimpleNamespace(enabled=True, account_generation=3)
    )
    monkeypatch.setattr(frame_request_tools, "_screen_delivery_route", lambda *_args: ("mac-1", "42", None))
    monkeypatch.setattr(frame_request_tools, "enqueue_frame_request", lambda *_args, **_kwargs: (request, True))
    monkeypatch.setattr(frame_request_tools, "get_frame_request", lambda *_args: request)
    monkeypatch.setattr(frame_request_tools, "download_frame_request_pixels", lambda *_args: b"secret-pixels")
    monkeypatch.setattr(frame_request_tools, "emit_product_event", lambda **kwargs: telemetry.append(kwargs))
    monkeypatch.setattr(
        frame_request_tools,
        "reserve_frame_vision_invocation",
        lambda *_args, **_kwargs: {"state": "invoked", "reserved": True},
    )
    monkeypatch.setattr(frame_request_tools, "complete_frame_vision_invocation", lambda *_args, **_kwargs: None)

    async def describe(*args):
        vision_calls.append(args)
        return "secret-description"

    monkeypatch.setattr(frame_request_tools, "describe_image", describe)

    first = await frame_request_tools.look_at_frame_tool.ainvoke({"screenshot_id": "mac-1-42"}, config=config)
    second = await frame_request_tools.look_at_frame_tool.ainvoke({"screenshot_id": "mac-1-42"}, config=config)

    assert '"state": "available"' in first
    assert '"state": "budget_exhausted"' in second
    assert len(vision_calls) == 1
    assert telemetry == [
        {
            "uid": "uid-1",
            "event": "JIT Frame Retrieval",
            "properties": {"outcome": "available", "vision_invoked": True},
        },
        {
            "uid": "uid-1",
            "event": "JIT Frame Retrieval",
            "properties": {"outcome": "budget_exhausted", "vision_invoked": False},
        },
    ]
    assert "mac-1-42" not in repr(telemetry)
    assert "secret" not in repr(telemetry)


@pytest.mark.asyncio
async def test_fresh_config_retry_uses_durable_result_without_second_paid_call(monkeypatch):
    request = _request(FrameRequestState.uploaded)
    receipt = {}
    calls = []
    monkeypatch.setattr(
        frame_request_tools, "decision_for", lambda _uid: SimpleNamespace(enabled=True, account_generation=3)
    )
    monkeypatch.setattr(frame_request_tools, "_screen_delivery_route", lambda *_args: ("mac-1", "42", 86400))
    monkeypatch.setattr(frame_request_tools, "enqueue_frame_request", lambda *_args, **_kwargs: (request, True))
    monkeypatch.setattr(frame_request_tools, "get_frame_request", lambda *_args: request)
    monkeypatch.setattr(frame_request_tools, "download_frame_request_pixels", lambda *_args: b"pixels")

    def reserve(*_args, **_kwargs):
        return dict(receipt) if receipt else {"state": "invoked", "reserved": True}

    def complete(*_args, description, **_kwargs):
        receipt.update({"state": "completed", "description": description})

    async def describe(*_args):
        calls.append(1)
        return "bounded result"

    monkeypatch.setattr(frame_request_tools, "reserve_frame_vision_invocation", reserve)
    monkeypatch.setattr(frame_request_tools, "complete_frame_vision_invocation", complete)
    monkeypatch.setattr(frame_request_tools, "describe_image", describe)

    first = await frame_request_tools.look_at_frame_tool.ainvoke({"screenshot_id": "mac-1-42"}, config=_config())
    retry = await frame_request_tools.look_at_frame_tool.ainvoke({"screenshot_id": "mac-1-42"}, config=_config())

    assert json.loads(first)["description"] == json.loads(retry)["description"] == "bounded result"
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_missing_pixels_never_invokes_paid_vision(monkeypatch):
    request = _request(FrameRequestState.uploaded)
    calls = []
    monkeypatch.setattr(
        frame_request_tools, "decision_for", lambda _uid: SimpleNamespace(enabled=True, account_generation=3)
    )
    monkeypatch.setattr(frame_request_tools, "_screen_delivery_route", lambda *_args: ("mac-1", "42", None))
    monkeypatch.setattr(frame_request_tools, "enqueue_frame_request", lambda *_args, **_kwargs: (request, True))
    monkeypatch.setattr(frame_request_tools, "get_frame_request", lambda *_args: request)
    monkeypatch.setattr(
        frame_request_tools, "download_frame_request_pixels", lambda *_args: (_ for _ in ()).throw(FileNotFoundError())
    )
    monkeypatch.setattr(
        frame_request_tools, "reserve_frame_vision_invocation", lambda *_args, **_kwargs: calls.append(1)
    )

    result = await frame_request_tools.look_at_frame_tool.ainvoke({"screenshot_id": "mac-1-42"}, config=_config())

    assert json.loads(result) == {"state": "pruned", "reason": "pixels_unavailable"}
    assert calls == []


@pytest.mark.asyncio
async def test_concurrent_fresh_configs_reserve_one_paid_invocation(monkeypatch):
    request = _request(FrameRequestState.uploaded)
    invoked = False
    calls = []
    gate = asyncio.Event()
    monkeypatch.setattr(
        frame_request_tools, "decision_for", lambda _uid: SimpleNamespace(enabled=True, account_generation=3)
    )
    monkeypatch.setattr(frame_request_tools, "_screen_delivery_route", lambda *_args: ("mac-1", "42", None))
    monkeypatch.setattr(frame_request_tools, "enqueue_frame_request", lambda *_args, **_kwargs: (request, True))
    monkeypatch.setattr(frame_request_tools, "get_frame_request", lambda *_args: request)
    monkeypatch.setattr(frame_request_tools, "download_frame_request_pixels", lambda *_args: b"pixels")

    def reserve(*_args, **_kwargs):
        nonlocal invoked
        if invoked:
            return {"state": "invoked"}
        invoked = True
        return {"state": "invoked", "reserved": True}

    async def describe(*_args):
        calls.append(1)
        await gate.wait()
        return "result"

    monkeypatch.setattr(frame_request_tools, "reserve_frame_vision_invocation", reserve)
    monkeypatch.setattr(frame_request_tools, "complete_frame_vision_invocation", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(frame_request_tools, "describe_image", describe)
    first = asyncio.create_task(
        frame_request_tools.look_at_frame_tool.ainvoke({"screenshot_id": "mac-1-42"}, config=_config())
    )
    second = asyncio.create_task(
        frame_request_tools.look_at_frame_tool.ainvoke({"screenshot_id": "mac-1-42"}, config=_config())
    )
    await asyncio.sleep(0.05)
    gate.set()
    results = await asyncio.gather(first, second)
    assert any(json.loads(result).get("reason") == "vision_outcome_pending_or_unknown" for result in results)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_crash_after_durable_reservation_never_reinvokes_paid_vision(monkeypatch):
    request = _request(FrameRequestState.uploaded)
    reserved = False
    calls = []
    monkeypatch.setattr(
        frame_request_tools, "decision_for", lambda _uid: SimpleNamespace(enabled=True, account_generation=3)
    )
    monkeypatch.setattr(frame_request_tools, "_screen_delivery_route", lambda *_args: ("mac-1", "42", None))
    monkeypatch.setattr(frame_request_tools, "enqueue_frame_request", lambda *_args, **_kwargs: (request, True))
    monkeypatch.setattr(frame_request_tools, "get_frame_request", lambda *_args: request)
    monkeypatch.setattr(frame_request_tools, "download_frame_request_pixels", lambda *_args: b"pixels")

    def reserve(*_args, **_kwargs):
        nonlocal reserved
        if reserved:
            return {"state": "invoked"}
        reserved = True
        return {"state": "invoked", "reserved": True}

    async def crash(*_args):
        calls.append(1)
        raise RuntimeError("provider response lost")

    monkeypatch.setattr(frame_request_tools, "reserve_frame_vision_invocation", reserve)
    monkeypatch.setattr(frame_request_tools, "describe_image", crash)
    with pytest.raises(RuntimeError):
        await frame_request_tools.look_at_frame_tool.ainvoke({"screenshot_id": "mac-1-42"}, config=_config())
    retry = await frame_request_tools.look_at_frame_tool.ainvoke({"screenshot_id": "mac-1-42"}, config=_config())
    assert json.loads(retry)["reason"] == "vision_outcome_pending_or_unknown"
    assert len(calls) == 1
