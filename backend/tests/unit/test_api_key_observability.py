import logging
from unittest.mock import MagicMock

import utils.observability.api_keys as api_key_observability


def test_healthy_key_operation_emits_nothing(monkeypatch):
    fallback = MagicMock()
    monkeypatch.setattr(api_key_observability, "record_fallback", fallback)

    api_key_observability.record_api_key_repairs(
        key_kind="mcp",
        operation="list",
        repairs=frozenset(),
        log=logging.getLogger("test"),
    )

    fallback.assert_not_called()


def test_repair_outcomes_distinguish_degraded_dev_scopes_from_recovered_auth(monkeypatch):
    fallback = MagicMock()
    logger = logging.getLogger("test")
    monkeypatch.setattr(api_key_observability, "record_fallback", fallback)

    api_key_observability.record_api_key_repairs(
        key_kind="mcp",
        operation="list",
        repairs=frozenset({"name", "key_prefix"}),
        log=logger,
    )
    api_key_observability.record_api_key_repairs(
        key_kind="dev",
        operation="auth",
        repairs=frozenset({"cache_write"}),
        log=logger,
    )
    api_key_observability.record_api_key_repairs(
        key_kind="dev",
        operation="auth",
        repairs=frozenset({"scopes"}),
        log=logger,
    )
    api_key_observability.record_api_key_repairs(
        key_kind="mcp",
        operation="auth",
        repairs=frozenset({"scopes"}),
        log=logger,
    )

    assert [call.kwargs["outcome"] for call in fallback.call_args_list] == [
        "degraded",
        "recovered",
        "degraded",
        "recovered",
    ]
    assert all(call.kwargs["reason"] == "local_heal" for call in fallback.call_args_list)
    assert [call.kwargs["from_mode"] for call in fallback.call_args_list] == [
        "mcp_stored_list",
        "dev_stored_auth",
        "dev_stored_auth",
        "mcp_stored_auth",
    ]
    assert [call.kwargs["to_mode"] for call in fallback.call_args_list] == [
        "mcp_safe_list",
        "dev_safe_auth",
        "dev_safe_auth",
        "mcp_safe_auth",
    ]


def test_failed_revocation_is_exhausted(monkeypatch):
    fallback = MagicMock()
    logger = logging.getLogger("test")
    monkeypatch.setattr(api_key_observability, "record_fallback", fallback)

    api_key_observability.record_api_key_revocation_exhausted(key_kind="dev", log=logger)

    fallback.assert_called_once_with(
        component="other",
        from_mode="dev_revocation_cache",
        to_mode="dev_revocation_blocked",
        reason="auth",
        outcome="exhausted",
        log=logger,
    )
