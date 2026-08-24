from __future__ import annotations

from types import SimpleNamespace

from models.app import App
from models.conversation import AppResult
from utils.conversations import process_conversation as processing


def _conversation(*, folder_id: str | None = None):
    return SimpleNamespace(
        id="conversation",
        discarded=False,
        folder_id=folder_id,
        structured=None,
        language="en",
        apps_results=[],
        suggested_summarization_apps=[],
        get_person_ids=lambda: [],
    )


def _install_common(monkeypatch, conversation, completed: list[str]) -> None:
    monkeypatch.setattr(processing, "deserialize_conversation", lambda _row: conversation)
    monkeypatch.setattr(
        processing.conversations_db,
        "complete_first_open_effect",
        lambda _uid, _cid, _token, effect: completed.append(effect) or True,
    )
    monkeypatch.setattr(processing, "_update_goal_progress", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(processing, "_trigger_apps", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(processing, "_conversation_apps_opt_in_only", lambda: False)


def test_retry_skips_effects_with_durable_completion_receipts(monkeypatch) -> None:
    conversation = _conversation(folder_id="folder")
    completed: list[str] = []
    _install_common(monkeypatch, conversation, completed)
    monkeypatch.setattr(
        processing.folders_db,
        "update_folder_conversation_count",
        lambda *_args: (_ for _ in ()).throw(AssertionError("completed folder effect must not replay")),
    )

    processing.run_first_open_derived_work(
        "owner",
        {
            "id": "conversation",
            "jit_first_open": {
                "effects": {
                    "folder_assignment": {"state": "complete"},
                    "goal_progress": {"state": "pending"},
                    "app_fanout": {"state": "pending"},
                }
            },
        },
        "lease",
    )

    assert completed == ["goal_progress", "app_fanout"]


def test_retry_repairs_folder_count_after_folder_id_persisted(monkeypatch) -> None:
    conversation = _conversation(folder_id="folder")
    completed: list[str] = []
    counts: list[str] = []
    _install_common(monkeypatch, conversation, completed)
    monkeypatch.setattr(
        processing.folders_db,
        "update_folder_conversation_count",
        lambda _uid, folder_id: counts.append(folder_id),
    )

    processing.run_first_open_derived_work(
        "owner",
        {"id": "conversation", "jit_first_open": {"effects": {}}},
        "lease",
    )

    assert counts == ["folder"]
    assert completed == ["folder_assignment", "goal_progress", "app_fanout"]


def test_first_open_app_retry_preserves_already_persisted_result(monkeypatch) -> None:
    app = App(
        id="app-1",
        name="Summary",
        category="productivity",
        author="Omi",
        description="summary",
        image="/app.png",
        capabilities={"memories"},
    )
    conversation = SimpleNamespace(
        id="conversation",
        started_at=None,
        photos=[],
        apps_results=[AppResult(app_id="app-1", content="durable result")],
        suggested_summarization_apps=["app-1"],
    )
    monkeypatch.setattr(processing, "_conversation_apps_opt_in_only", lambda: False)
    monkeypatch.setattr(processing, "get_default_conversation_summarized_apps", lambda: [app])
    monkeypatch.setattr(processing, "get_available_apps", lambda _uid: [])
    monkeypatch.setattr(processing.redis_db, "get_user_preferred_app", lambda _uid: None)
    monkeypatch.setattr(
        processing,
        "get_app_result",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("persisted app result must not rerun")),
    )
    monkeypatch.setattr(
        processing,
        "record_app_usage",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("persisted usage must not replay")),
    )
    monkeypatch.setattr(
        processing.conversations_db,
        "update_conversation",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("persisted result must not rewrite")),
    )

    assert processing._trigger_apps(  # pyright: ignore[reportPrivateUsage]
        "owner", conversation, preserve_existing_results=True
    )
    assert conversation.apps_results == [AppResult(app_id="app-1", content="durable result")]


def test_first_open_app_result_is_persisted_before_usage(monkeypatch) -> None:
    app = App(
        id="app-1",
        name="Summary",
        category="productivity",
        author="Omi",
        description="summary",
        image="/app.png",
        capabilities={"memories"},
    )
    conversation = SimpleNamespace(
        id="conversation",
        started_at=None,
        photos=[],
        apps_results=[],
        suggested_summarization_apps=["app-1"],
    )
    calls: list[str] = []
    monkeypatch.setattr(processing, "_conversation_apps_opt_in_only", lambda: False)
    monkeypatch.setattr(processing, "get_default_conversation_summarized_apps", lambda: [app])
    monkeypatch.setattr(processing, "get_available_apps", lambda _uid: [])
    monkeypatch.setattr(processing.redis_db, "get_user_preferred_app", lambda _uid: None)
    monkeypatch.setattr(processing, "conversation_transcript_for_llm", lambda *_args: "transcript")
    monkeypatch.setattr(processing, "get_app_result", lambda *_args, **_kwargs: "durable result")

    def persist(_uid, _cid, patch):
        assert patch["apps_results"] == [{"app_id": "app-1", "content": "durable result"}]
        calls.append("persist")
        return True

    monkeypatch.setattr(processing.conversations_db, "update_conversation", persist)
    monkeypatch.setattr(processing, "record_app_usage", lambda *_args, **_kwargs: calls.append("usage"))

    assert processing._trigger_apps(  # pyright: ignore[reportPrivateUsage]
        "owner", conversation, preserve_existing_results=True
    )
    assert calls == ["persist", "usage"]
