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
        source="desktop",
        get_person_ids=lambda: [],
    )


def _install_common(monkeypatch, conversation, completed: list[str]) -> None:
    monkeypatch.setattr(processing, "deserialize_conversation", lambda _row: conversation)
    monkeypatch.setattr(
        processing.conversations_db,
        "complete_first_open_effect",
        lambda _uid, _cid, _token, effect, **_kwargs: completed.append(effect) or True,
    )
    monkeypatch.setattr(processing.conversations_db, "first_open_effect_is_authorized", lambda *_args: True)
    monkeypatch.setattr(processing.conversations_db, "commit_first_open_folder_count", lambda *_args: True)
    monkeypatch.setattr(processing.conversations_db, "commit_first_open_app_result", lambda *_args: True)
    monkeypatch.setattr(processing.conversations_db, "commit_first_open_app_usage", lambda *_args: True)
    monkeypatch.setattr(
        processing,
        "resolve_authorized_first_open_plan",
        lambda **_kwargs: SimpleNamespace(defer_derived_work=True),
    )
    monkeypatch.setattr(
        processing,
        "update_goal_progress",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("automatic goal updates are not part of the JIT featureset")
        ),
    )
    monkeypatch.setattr(processing, "trigger_conversation_apps", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(processing, "conversation_apps_opt_in_only", lambda: False)


def test_retry_skips_completed_effects_and_ignores_legacy_goal_rows(monkeypatch) -> None:
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

    # The legacy pending goal_progress row is ignored, never executed.
    assert completed == ["app_fanout"]


def test_retry_repairs_folder_count_after_folder_id_persisted(monkeypatch) -> None:
    conversation = _conversation(folder_id="folder")
    completed: list[str] = []
    counts: list[str] = []
    _install_common(monkeypatch, conversation, completed)
    monkeypatch.setattr(
        processing.conversations_db,
        "commit_first_open_folder_count",
        lambda _uid, _cid, _token, folder_id: counts.append(folder_id) or True,
    )

    processing.run_first_open_derived_work(
        "owner",
        {"id": "conversation", "jit_first_open": {"effects": {}}},
        "lease",
    )

    assert counts == ["folder"]
    assert completed == ["folder_assignment", "app_fanout"]


def test_kill_flip_during_folder_effect_blocks_commit_and_suffix(monkeypatch) -> None:
    conversation = _conversation(folder_id="folder")
    completed: list[str] = []
    _install_common(monkeypatch, conversation, completed)
    decisions = iter([True, False])
    monkeypatch.setattr(
        processing,
        "resolve_authorized_first_open_plan",
        lambda **_kwargs: SimpleNamespace(defer_derived_work=next(decisions)),
    )
    monkeypatch.setattr(
        processing,
        "update_goal_progress",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("goal work must remain suspended")),
    )
    monkeypatch.setattr(
        processing,
        "trigger_conversation_apps",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("app work must remain suspended")),
    )

    try:
        processing.run_first_open_derived_work(
            "owner", {"id": "conversation", "jit_first_open": {"effects": {}}}, "lease"
        )
    except RuntimeError as error:
        assert "authority suspended before folder_assignment" in str(error)
    else:
        raise AssertionError("kill must suspend the outstanding suffix")

    assert completed == []


def test_first_open_initializes_empty_folders_then_assigns(monkeypatch) -> None:
    conversation = _conversation()
    conversation.structured = SimpleNamespace(
        title="Standup", overview="Weekly sync", category=SimpleNamespace(value="work")
    )
    completed: list[str] = []
    initialized: list[str] = []
    assigned: list[str] = []
    _install_common(monkeypatch, conversation, completed)
    monkeypatch.setattr(processing.folders_db, "get_folders", lambda _uid: [])
    monkeypatch.setattr(
        processing.folders_db,
        "initialize_system_folders",
        lambda uid: initialized.append(uid) or [{"id": "work", "name": "Work"}],
    )
    monkeypatch.setattr(processing.folders_db, "resolve_category_folder_id", lambda *_args: "work")

    class _Usage:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(processing, "track_usage", lambda *_args, **_kwargs: _Usage())
    monkeypatch.setattr(
        processing,
        "assign_conversation_to_folder",
        lambda **_kwargs: assigned.append("work") or ("work", 1.0, "category"),
    )
    monkeypatch.setattr(
        processing.conversations_db, "commit_first_open_conversation_patch", lambda *_args, **_kwargs: True
    )

    processing.run_first_open_derived_work("owner", {"id": "conversation", "jit_first_open": {"effects": {}}}, "lease")

    assert initialized == ["owner"]
    assert assigned == ["work"]
    assert conversation.folder_id == "work"
    assert completed == ["folder_assignment", "app_fanout"]


def test_first_open_does_not_complete_folder_assignment_on_skip(monkeypatch) -> None:
    conversation = _conversation()
    completed: list[str] = []
    _install_common(monkeypatch, conversation, completed)
    monkeypatch.setattr(processing.folders_db, "get_folders", lambda _uid: [])
    monkeypatch.setattr(
        processing.folders_db,
        "initialize_system_folders",
        lambda _uid: [],
    )

    processing.run_first_open_derived_work("owner", {"id": "conversation", "jit_first_open": {"effects": {}}}, "lease")

    assert completed == ["app_fanout"]


def test_worker_never_runs_goal_progress(monkeypatch) -> None:
    """Goals change only through explicit user action for JIT conversations.

    The common stub raises on any ``update_goal_progress`` call; a fully
    pending obligation must therefore complete without touching goals.
    """

    conversation = _conversation(folder_id="folder")
    completed: list[str] = []
    _install_common(monkeypatch, conversation, completed)

    processing.run_first_open_derived_work("owner", {"id": "conversation", "jit_first_open": {"effects": {}}}, "lease")

    assert completed == ["folder_assignment", "app_fanout"]


def test_kill_flip_after_app_llm_blocks_result_and_usage_commits(monkeypatch) -> None:
    conversation = _conversation()
    completed: list[str] = []
    _install_common(monkeypatch, conversation, completed)
    decisions = iter([True, False])
    monkeypatch.setattr(
        processing,
        "resolve_authorized_first_open_plan",
        lambda **_kwargs: SimpleNamespace(defer_derived_work=next(decisions)),
    )

    def app_work(*_args, **kwargs):
        kwargs["resumable_result_commit"]("app-1", {"apps_results": []})
        raise AssertionError("fresh kill authority must interrupt before app output commit")

    monkeypatch.setattr(processing, "trigger_conversation_apps", app_work)
    state = {
        "effects": {
            "folder_assignment": {"state": "complete"},
            "goal_progress": {"state": "complete"},
            "app_fanout": {"state": "pending"},
        }
    }
    try:
        processing.run_first_open_derived_work("owner", {"id": "conversation", "jit_first_open": state}, "lease")
    except RuntimeError as error:
        assert "authority suspended before app_fanout" in str(error)
    else:
        raise AssertionError("kill must block app result and usage mutation")

    assert completed == []


def test_kill_flip_after_app_result_blocks_usage_and_completion(monkeypatch) -> None:
    conversation = _conversation()
    conversation.apps_results = [AppResult(app_id="app-1", content="durable result")]
    completed: list[str] = []
    result_commits: list[str] = []
    _install_common(monkeypatch, conversation, completed)
    decisions = iter([True, True, False])
    monkeypatch.setattr(
        processing,
        "resolve_authorized_first_open_plan",
        lambda **_kwargs: SimpleNamespace(defer_derived_work=next(decisions)),
    )
    monkeypatch.setattr(
        processing.conversations_db,
        "commit_first_open_app_result",
        lambda _uid, _cid, _token, app_id, _patch: result_commits.append(app_id) or True,
    )
    monkeypatch.setattr(
        processing,
        "trigger_conversation_apps",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("selection must not run after kill")),
    )
    state = {
        "effects": {
            "folder_assignment": {"state": "complete"},
            "goal_progress": {"state": "complete"},
            "app_fanout": {"state": "pending"},
        }
    }

    try:
        processing.run_first_open_derived_work("owner", {"id": "conversation", "jit_first_open": state}, "lease")
    except RuntimeError as error:
        assert "authority suspended before app_fanout" in str(error)
    else:
        raise AssertionError("kill must suspend the suffix after the durable app result")

    assert result_commits == ["app-1"]
    assert completed == []


def test_retry_repairs_usage_after_crash_without_replaying_app(monkeypatch) -> None:
    conversation = _conversation()
    conversation.apps_results = [AppResult(app_id="app-1", content="durable result")]
    conversation.suggested_summarization_apps = ["app-1"]
    completed: list[str] = []
    calls: list[str] = []
    _install_common(monkeypatch, conversation, completed)
    monkeypatch.setattr(
        processing.conversations_db,
        "commit_first_open_app_result",
        lambda _uid, _cid, _token, app_id, _patch: calls.append(f"result:{app_id}") or True,
    )
    monkeypatch.setattr(
        processing.conversations_db,
        "commit_first_open_app_usage",
        lambda _uid, _cid, _token, app_id, _usage: calls.append(f"usage:{app_id}") or True,
    )
    monkeypatch.setattr(
        processing,
        "trigger_conversation_apps",
        lambda *_args, **_kwargs: calls.append("selection") or True,
    )
    state = {
        "effects": {
            "folder_assignment": {"state": "complete"},
            "goal_progress": {"state": "complete"},
            "app_fanout": {"state": "pending"},
        }
    }

    processing.run_first_open_derived_work("owner", {"id": "conversation", "jit_first_open": state}, "lease")

    assert calls == ["result:app-1", "usage:app-1", "selection"]
    assert completed == ["app_fanout"]


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
        source="desktop",
    )
    monkeypatch.setattr(processing, "conversation_apps_opt_in_only", lambda: False)
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

    assert processing.trigger_conversation_apps("owner", conversation, preserve_existing_results=True)
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
        source="desktop",
    )
    calls: list[str] = []
    monkeypatch.setattr(processing, "conversation_apps_opt_in_only", lambda: False)
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

    assert processing.trigger_conversation_apps(
        "owner",
        conversation,
        preserve_existing_results=True,
        resumable_effect_authorizer=lambda: calls.append("authorize"),
    )
    assert calls == ["authorize", "persist", "usage"]
