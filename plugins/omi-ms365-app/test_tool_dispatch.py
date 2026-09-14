"""Unit tests for tool-call argument extraction (issue #13864).

OMI posts a tool call as one flat JSON object; the plugin used to read the
arguments from a nested ``args`` key that OMI never sends, so every tool with a
required parameter answered HTTP 400.
"""

import inspect
import json
import os
from pathlib import Path

import pytest

# main.py builds Settings at import time; these are never used by these tests.
os.environ.setdefault("MICROSOFT_CLIENT_ID", "test-client-id")
os.environ.setdefault("MICROSOFT_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("SESSION_SECRET", "test-session-secret")

from main import _tool_args  # noqa: E402

MANIFEST = json.loads((Path(__file__).parent / "omi-tools.json").read_text())
TOOLS = MANIFEST["tools"]


def _omi_payload(tool, geolocation=True):
    """Rebuild the body exactly as backend _call_tool_endpoint sends it."""
    params = tool.get("parameters") or {}
    kwargs = {name: f"<{name}>" for name in (params.get("properties") or {})}
    payload = {**kwargs, "uid": "u_123", "app_id": "app_ms365", "tool_name": tool["name"]}
    if geolocation:
        payload["geolocation"] = {"latitude": 1.0, "longitude": 2.0}
    return payload


def _handler_for(tool):
    """A stub with the tool's real signature: (uid, *required, **optional)."""
    params = tool.get("parameters") or {}
    props = list((params.get("properties") or {}).keys())
    required = params.get("required") or []
    sig = ["uid"] + list(required) + [f"{p}=None" for p in props if p not in required]
    ns: dict = {}
    exec(f"def handler({', '.join(sig)}): pass", ns)
    return ns["handler"]


@pytest.mark.parametrize("tool", TOOLS, ids=[t["name"] for t in TOOLS])
def test_every_tool_binds_its_arguments(tool):
    """Each tool must dispatch without the TypeError that became HTTP 400."""
    body = _omi_payload(tool)
    args = _tool_args(body)
    inspect.signature(_handler_for(tool)).bind(body["uid"], **args)


@pytest.mark.parametrize("tool", TOOLS, ids=[t["name"] for t in TOOLS])
def test_no_declared_parameter_is_dropped(tool):
    """Optional parameters (limit, unread_only, days) must survive too."""
    declared = set(((tool.get("parameters") or {}).get("properties") or {}))
    assert set(_tool_args(_omi_payload(tool))) == declared


def test_envelope_keys_are_never_passed_through():
    body = {"query": "hello", "uid": "u", "app_id": "a", "tool_name": "search_emails",
            "geolocation": {"latitude": 0.0, "longitude": 0.0}}
    assert _tool_args(body) == {"query": "hello"}


def test_payload_without_geolocation():
    body = {"query": "hello", "uid": "u", "app_id": "a", "tool_name": "search_emails"}
    assert _tool_args(body) == {"query": "hello"}


def test_nested_args_still_honoured():
    """Backward compatibility for any caller that does send a nested object."""
    body = {"args": {"query": "hello"}, "uid": "u", "app_id": "a", "tool_name": "t"}
    assert _tool_args(body) == {"query": "hello"}


def test_empty_nested_args_falls_back_to_flat_params():
    """An empty "args" must not shadow flat parameters, nor leak itself through."""
    body = {"args": {}, "query": "hello", "uid": "u", "app_id": "a", "tool_name": "t"}
    assert _tool_args(body) == {"query": "hello"}


def test_tool_without_parameters():
    body = {"uid": "u", "app_id": "a", "tool_name": "get_me"}
    assert _tool_args(body) == {}
