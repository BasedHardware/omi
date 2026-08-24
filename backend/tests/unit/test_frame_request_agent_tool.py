from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from models.frame_request import FrameRequest, FrameRequestState
from utils.retrieval.tools import frame_request_tools


def _config():
    return {
        "configurable": {
            "user_id": "uid-1",
            "thread_id": "turn-1",
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
    )


@pytest.mark.asyncio
async def test_look_at_frame_enqueues_then_reports_asked_mac(monkeypatch):
    request = _request()
    monkeypatch.setattr(
        frame_request_tools, "decision_for", lambda _uid: SimpleNamespace(enabled=True, account_generation=3)
    )
    monkeypatch.setattr(frame_request_tools, "_screen_delivery_route", lambda *_args: ("mac-1", "42"))
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
    monkeypatch.setattr(frame_request_tools, "_screen_delivery_route", lambda *_args: ("mac-1", "42"))
    monkeypatch.setattr(frame_request_tools, "enqueue_frame_request", lambda *_args, **_kwargs: (request, True))
    monkeypatch.setattr(frame_request_tools, "get_frame_request", lambda *_args: request)
    monkeypatch.setattr(frame_request_tools, "download_frame_request_pixels", lambda *_args: b"jpeg")

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
    monkeypatch.setattr(frame_request_tools, "_screen_delivery_route", lambda *_args: ("mac-1", "42"))
    monkeypatch.setattr(frame_request_tools, "enqueue_frame_request", lambda *_args, **_kwargs: (request, True))
    monkeypatch.setattr(frame_request_tools, "get_frame_request", lambda *_args: request)
    monkeypatch.setattr(frame_request_tools, "download_frame_request_pixels", lambda *_args: b"secret-pixels")
    monkeypatch.setattr(frame_request_tools, "emit_product_event", lambda **kwargs: telemetry.append(kwargs))

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
