"""Characterization tests for listen WebSocket connect bootstrap (#9239)."""

import ast
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
BOOTSTRAP_PATH = BACKEND_DIR / "utils" / "listen_session_bootstrap.py"
TRANSCRIBE_PATH = BACKEND_DIR / "routers" / "transcribe.py"


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


def test_stream_handler_uses_listen_connect_bootstrap():
    source = TRANSCRIBE_PATH.read_text(encoding="utf-8")
    handler_start = source.index("async def _stream_handler(")
    handler_end = source.index('logger.info(f"_stream_handler ended', handler_start)
    handler = source[handler_start:handler_end]
    assert "load_listen_connect_base" in handler
    assert "finalize_listen_connect_context" in handler
    assert "get_user_transcription_preferences(uid)" not in handler
    assert "has_transcription_credits(uid" not in handler


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
