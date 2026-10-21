"""Characterization tests for listen WebSocket connect bootstrap (#9239)."""

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
BOOTSTRAP_PATH = BACKEND_DIR / "utils" / "listen_session_bootstrap.py"
RUNTIME_PATH = BACKEND_DIR / "routers" / "listen" / "runtime.py"


def test_bootstrap_offloads_firestore_reads():
    tree = ast.parse(BOOTSTRAP_PATH.read_text(encoding="utf-8"))
    awaited_targets = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Await):
            continue
        call = node.value
        if isinstance(call, ast.Call) and getattr(call.func, "id", None) == "run_blocking":
            if len(call.args) >= 2 and isinstance(call.args[1], ast.Attribute):
                awaited_targets.append(call.args[1].attr)
            elif len(call.args) >= 2 and isinstance(call.args[1], ast.Name):
                awaited_targets.append(call.args[1].id)
    for required in (
        "is_exists_user",
        "has_transcription_credits",
        "get_user_transcription_preferences",
        "get_enforcement_stage",
        "is_dg_budget_exhausted",
    ):
        assert required in awaited_targets


def test_runtime_uses_listen_connect_bootstrap():
    source = RUNTIME_PATH.read_text(encoding="utf-8")
    bootstrap_start = source.index("async def _bootstrap(")
    bootstrap_end = source.index("    async def _heartbeat", bootstrap_start)
    bootstrap = source[bootstrap_start:bootstrap_end]
    assert "load_listen_connect_base" in bootstrap
    assert "finalize_listen_connect_context" in bootstrap
    assert "get_user_transcription_preferences(" not in bootstrap
    assert "has_transcription_credits(" not in bootstrap


def test_project_listen_connect_decisions_pins_vocabulary_and_translation():
    from utils.listen_session_bootstrap import project_listen_connect_decisions

    single_language_mode, vocabulary, language, translation_language = project_listen_connect_decisions(
        language="auto",
        onboarding_mode=False,
        transcription_prefs={
            "single_language_mode": False,
            "vocabulary": ["Acme"],
            "language": "es",
        },
        stt_language="multi",
    )
    assert single_language_mode is False
    assert "Omi" in vocabulary
    assert "Acme" in vocabulary
    assert language == "multi"
    assert translation_language == "es"


@pytest.mark.asyncio
async def test_load_listen_connect_context_returns_offloaded_state():
    from utils.listen_session_bootstrap import load_listen_connect_context

    prefs = {"single_language_mode": True, "vocabulary": [], "language": "en", "uses_custom_stt": False}

    with patch(
        "utils.listen_session_bootstrap.run_blocking",
        new=AsyncMock(
            side_effect=[
                True,
                True,
                prefs,
                "none",
                False,
            ]
        ),
    ) as mock_run_blocking:
        ctx = await load_listen_connect_context(
            "uid-bootstrap",
            language="en",
            source="omi",
            use_custom_stt=False,
            onboarding_mode=False,
            stt_language="en",
        )

    assert ctx.user_exists is True
    assert ctx.user_has_credits is True
    assert ctx.transcription_prefs == prefs
    assert ctx.language == "en"
    assert mock_run_blocking.await_count >= 3


@pytest.mark.asyncio
async def test_custom_stt_skips_stt_credits_but_still_admits(monkeypatch):
    """#7690: custom-STT never asks has_transcription_credits; connect still admits."""
    from utils import listen_session_bootstrap as bootstrap

    called: list[str] = []

    async def fake_run_blocking(_executor, fn, *args, **kwargs):
        name = getattr(fn, "__name__", "")
        called.append(name)
        if name == "has_transcription_credits":
            raise AssertionError("custom-STT must skip STT credits")
        if name == "is_exists_user":
            return True
        if name == "get_user_transcription_preferences":
            return {"single_language_mode": True, "vocabulary": [], "language": "en", "uses_custom_stt": True}
        raise AssertionError(f"unexpected offload {name}")

    monkeypatch.setattr(bootstrap, "FAIR_USE_ENABLED", False)
    monkeypatch.setattr(bootstrap, "run_blocking", fake_run_blocking)

    ctx = await bootstrap.load_listen_connect_context(
        "uid-custom-stt",
        language="en",
        source="omi",
        use_custom_stt=True,
        onboarding_mode=False,
        stt_language="en",
    )

    assert ctx.user_has_credits is True
    assert "has_transcription_credits" not in called
    assert "is_exists_user" in called


@pytest.mark.asyncio
async def test_expired_fair_use_restriction_does_not_meter_dg_budget(monkeypatch):
    """A restriction past restrict_until must not keep the restrict-stage DG budget cap on listen."""
    import utils.fair_use as fair_use
    from utils import listen_session_bootstrap as bootstrap

    fair_use_db = MagicMock(name="fair_use_db")
    fair_use_db.get_fair_use_state.return_value = {
        "stage": "restrict",
        "restrict_until": datetime.now(timezone.utc) - timedelta(days=1),
    }
    redis_client = MagicMock(name="redis_client")
    redis_client.get.return_value = None
    monkeypatch.setattr(fair_use, "fair_use_db", fair_use_db)
    monkeypatch.setattr(fair_use, "redis_client", redis_client)

    async def fake_run_blocking(_executor, fn, *args, **kwargs):
        name = getattr(fn, "__name__", "")
        if name == "get_enforcement_stage":
            return fn(*args, **kwargs)
        if name == "is_dg_budget_exhausted":
            raise AssertionError("an expired restriction must not meter the DG budget")
        if name in ("is_exists_user", "has_transcription_credits"):
            return True
        if name == "get_user_transcription_preferences":
            return {"single_language_mode": True, "vocabulary": [], "language": "en"}
        raise AssertionError(f"unexpected offload {name}")

    monkeypatch.setattr(bootstrap, "FAIR_USE_ENABLED", True)
    monkeypatch.setattr(bootstrap, "FAIR_USE_RESTRICT_DAILY_DG_MS", 1800000)
    monkeypatch.setattr(bootstrap, "run_blocking", fake_run_blocking)

    base = await bootstrap.load_listen_connect_base("uid-expired-restrict", source="omi", use_custom_stt=False)

    assert base.fair_use_init_stage == "throttle"
    assert base.fair_use_track_dg_usage is False
    assert base.fair_use_dg_budget_exhausted is False
    fair_use_db.update_fair_use_state.assert_called_once_with(
        "uid-expired-restrict", {"stage": "throttle", "restrict_until": None}
    )
