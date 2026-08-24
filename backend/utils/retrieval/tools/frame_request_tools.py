"""Agent-owned JIT frame request and vision consumer.

This server tool is intentionally separate from macOS's local ``look_at_frame``
alias. It can act only on a screen reference admitted by a prior retrieval tool
in the same request and never promotes temporary pixels.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
from typing import Any, cast

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from database._client import get_firestore_client
from database.frame_requests import enqueue_frame_request, get_frame_request
from models.frame_request import FrameRequestState
from utils.executors import db_executor, run_blocking, storage_executor
from utils.llm.openglass import describe_image
from utils.product_telemetry import emit_product_event
from utils.retrieval.frame_request_authority import decision_for
from utils.retrieval.frame_request_storage import download_frame_request_pixels

logger = logging.getLogger(__name__)


def _configurable(config: RunnableConfig) -> dict[str, Any]:
    raw = cast(Any, config)
    if not isinstance(raw, dict) or not isinstance(raw.get("configurable"), dict):
        return {}
    return cast(dict[str, Any], raw["configurable"])


def _admitted_screen_reference(configurable: dict[str, Any], screenshot_id: str) -> bool:
    references = configurable.get("evidence_references")
    return isinstance(references, list) and any(
        isinstance(item, dict)
        and item.get("id") == f"screen:{screenshot_id}"
        and item.get("kind") == "screen"
        and item.get("frame_id") == screenshot_id
        for item in references
    )


def _screen_delivery_route(uid: str, screenshot_id: str) -> tuple[str, str]:
    snapshot = (
        get_firestore_client()
        .collection("users")
        .document(uid)
        .collection("screen_activity")
        .document(screenshot_id)
        .get()
    )
    if not snapshot.exists:
        raise KeyError("screen frame not found")
    data = snapshot.to_dict() or {}
    value = data.get("clientDeviceId")
    if not isinstance(value, str) or not value.strip():
        raise KeyError("screen frame has no routable device")
    device_id = value.strip()
    local_id = data.get("localScreenshotId")
    if not isinstance(local_id, str) or not local_id.isdigit():
        prefix = f"{device_id}-"
        local_id = screenshot_id[len(prefix) :] if screenshot_id.startswith(prefix) else ""
    if not local_id.isdigit():
        raise KeyError("screen frame has no routable local ID")
    return device_id, local_id


def _audit(uid: str, state: str, *, vision_invoked: bool = False) -> None:
    """Emit only closed, content-free dimensions for frame retrieval usage."""
    logger.info("look_at_frame outcome=%s vision_invoked=%s", state, vision_invoked)
    emit_product_event(
        uid=uid,
        event="JIT Frame Retrieval",
        properties={"outcome": state, "vision_invoked": vision_invoked},
    )


def _result(uid: str, state: str, **fields: Any) -> str:
    _audit(uid, state, vision_invoked=state == "available")
    return json.dumps({"state": state, **fields})


@tool("look_at_frame")
async def look_at_frame_tool(
    screenshot_id: str,
    config: RunnableConfig = None,  # type: ignore[reportAssignmentType]
) -> str:
    """Inspect one screen frame returned by screen search.

    Call only after ``search_screen_activity_tool`` returned the exact frame in
    this request. The first call may return ``asked_mac`` while the desktop is
    offline or syncing. At most one invocation is admitted per agent request.
    """

    configurable = _configurable(config)
    uid = configurable.get("user_id")
    screen_id = str(screenshot_id).strip()
    if not isinstance(uid, str) or not uid.strip() or not _admitted_screen_reference(configurable, screen_id):
        return json.dumps({"state": "unavailable", "reason": "screen_reference_not_admitted"})
    # Reserve before any queue or vision work. Mutating the request's shared
    # configurable map makes repeat and distinct calls deterministic and keeps
    # a single agent turn from turning into continuous vision.
    budget = configurable.get("frame_request_budget")
    if not isinstance(budget, dict):
        return _result(uid, "budget_exhausted", reason="request_budget_unavailable")
    if budget.get("reserved") is True:
        return _result(uid, "budget_exhausted", reason="one_frame_per_request")
    budget["reserved"] = True
    decision = await run_blocking(db_executor, decision_for, uid)
    if not decision.enabled or decision.account_generation is None:
        return _result(uid, "unavailable", reason="frame_requests_disabled")
    try:
        device_id, local_screenshot_id = await run_blocking(db_executor, _screen_delivery_route, uid, screen_id)
    except KeyError:
        return _result(uid, "pruned", reason="screen_metadata_unavailable")
    thread_id = str(configurable.get("thread_id") or "request")
    dedupe_key = hashlib.sha256(f"look_at_frame\0{thread_id}\0{screen_id}".encode("utf-8")).hexdigest()
    request, _ = await run_blocking(
        db_executor,
        enqueue_frame_request,
        uid,
        device_id=device_id,
        account_generation=decision.account_generation,
        dedupe_key=dedupe_key,
        screenshot_id=local_screenshot_id,
        requested_ttl_seconds=7 * 24 * 60 * 60,
    )
    # Refresh after enqueue so a concurrent desktop upload is observable.
    request = await run_blocking(db_executor, get_frame_request, uid, request.request_id)
    if request.state in {FrameRequestState.requested, FrameRequestState.claimed}:
        return _result(uid, "asked_mac", request_id=request.request_id)
    if request.state != FrameRequestState.uploaded or not request.storage_id:
        return _result(uid, request.state.value, reason=request.terminal_reason or "frame_not_available")
    payload = await run_blocking(storage_executor, download_frame_request_pixels, uid, request.storage_id)
    description = await describe_image(
        uid, base64.b64encode(payload).decode("ascii"), request.content_type or "image/jpeg"
    )
    return _result(
        uid,
        "available",
        request_id=request.request_id,
        evidence_id=f"screen:{screen_id}",
        description=description[:4000],
    )


__all__ = ["look_at_frame_tool"]
