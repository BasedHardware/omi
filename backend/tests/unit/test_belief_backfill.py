from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from utils.memory.belief_backfill import (
    BELIEF_BACKFILL_MUTATION_KIND,
    BeliefBackfillPage,
    BeliefBackfillRow,
    _default_applier,
    backfill_belief_classes,
    patch_for_belief_backfill,
)
from utils.memory.belief_model import derive_half_life_days

NOW = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def canonical_memory_adapter_module():
    """Load the canonical writer during fixture setup, outside call timing."""

    import utils.memory.canonical_memory_adapter as canonical_adapter

    return canonical_adapter


def _item(**updates) -> SimpleNamespace:
    data = {
        "memory_id": "mem-1",
        "uid": "uid-1",
        "content": "User lives in NYC",
        "status": "active",
        "tier": "long_term",
        "belief_class": None,
        "subject_scope": "primary_user",
        "half_life_days": None,
        "user_asserted": False,
        "expires_at": None,
        "captured_at": NOW,
    }
    data.update(updates)
    return SimpleNamespace(**data)


def _classify_identity(rows, _user_name=None):
    return [
        BeliefBackfillRow(memory_id=row.memory_id, belief_class="identity", subject_scope="primary_user")
        for row in rows
    ]


def test_backfill_reports_class_and_scope_distribution(monkeypatch):
    monkeypatch.setenv("MEMORY_BELIEF_MODEL_ENABLED", "true")
    items = [
        _item(memory_id="mem-id", content="Name is David"),
        _item(memory_id="mem-pref", content="Prefers dark mode"),
        _item(memory_id="mem-sam", content="Sam is a teammate"),
    ]

    def classify(rows, _user_name=None):
        mapping = {
            "mem-id": ("identity", "primary_user"),
            "mem-pref": ("preference", "primary_user"),
            "mem-sam": ("relationship", "third_party"),
        }
        return [
            BeliefBackfillRow(
                memory_id=row.memory_id, belief_class=mapping[row.memory_id][0], subject_scope=mapping[row.memory_id][1]
            )
            for row in rows
        ]

    applied = []
    report = backfill_belief_classes(
        "uid-1",
        db_client=SimpleNamespace(),
        dry_run=False,
        item_reader=lambda *_: items,
        classifier=classify,
        applier=lambda uid, item, classification, db: applied.append((item.memory_id, classification)),
    )
    assert report.classified == 3
    assert report.written == 3
    assert report.class_counts == {"identity": 1, "preference": 1, "relationship": 1}
    assert report.scope_counts == {"primary_user": 2, "third_party": 1}
    assert [row[0] for row in applied] == ["mem-id", "mem-pref", "mem-sam"]


def test_backfill_is_idempotent_when_class_is_set(monkeypatch):
    monkeypatch.setenv("MEMORY_BELIEF_MODEL_ENABLED", "true")
    items = [
        _item(memory_id="mem-done", belief_class="identity"),
        _item(memory_id="mem-todo", content="Lives in NYC"),
    ]
    applied = []
    report = backfill_belief_classes(
        "uid-1",
        db_client=SimpleNamespace(),
        dry_run=False,
        item_reader=lambda *_: items,
        classifier=_classify_identity,
        applier=lambda uid, item, classification, db: applied.append(item.memory_id),
    )
    assert report.classified == 1
    assert report.written == 1
    assert applied == ["mem-todo"]


def test_backfill_keeps_user_asserted_temporary_horizon(monkeypatch):
    monkeypatch.setenv("MEMORY_BELIEF_MODEL_ENABLED", "true")
    item = _item(memory_id="mem-user", user_asserted=True, content="Remember that I hate celery")
    classification = BeliefBackfillRow(
        memory_id="mem-user",
        belief_class="preference",
        subject_scope="primary_user",
        half_life_days=7,
    )
    logical, extra = patch_for_belief_backfill(item, classification)
    assert extra["half_life_days"] == 7
    assert extra["belief_class"] == "preference"
    assert logical["result_status"] == "active"
    assert "memory_text" not in logical
    assert item.status == "active"
    assert item.content == "Remember that I hate celery"

    applied = []
    report = backfill_belief_classes(
        "uid-1",
        db_client=SimpleNamespace(),
        dry_run=False,
        item_reader=lambda *_: [item],
        classifier=lambda rows, _n=None: [classification],
        applier=lambda uid, row, row_class, db: applied.append(patch_for_belief_backfill(row, row_class)),
    )
    assert report.written == 1
    assert applied[0][1]["half_life_days"] == 7


def test_backfill_does_not_change_status(monkeypatch):
    monkeypatch.setenv("MEMORY_BELIEF_MODEL_ENABLED", "true")
    hidden = _item(memory_id="mem-hidden", status="hidden", content="Old residue")
    classification = BeliefBackfillRow(
        memory_id="mem-hidden", belief_class="meta_residue", subject_scope="primary_user"
    )
    logical, extra = patch_for_belief_backfill(hidden, classification)
    assert logical["result_status"] == "hidden"
    assert extra["belief_class"] == "meta_residue"
    applied = []
    backfill_belief_classes(
        "uid-1",
        db_client=SimpleNamespace(),
        dry_run=False,
        item_reader=lambda *_: [hidden],
        classifier=lambda rows, _n=None: [classification],
        applier=lambda uid, row, row_class, db: applied.append((row.memory_id, row.status, row_class.belief_class)),
    )
    assert applied == [("mem-hidden", "hidden", "meta_residue")]
    assert hidden.status == "hidden"


def test_dry_run_writes_nothing(monkeypatch):
    monkeypatch.setenv("MEMORY_BELIEF_MODEL_ENABLED", "true")
    applied = []
    report = backfill_belief_classes(
        "uid-1",
        db_client=SimpleNamespace(),
        dry_run=True,
        item_reader=lambda *_: [_item()],
        classifier=_classify_identity,
        applier=lambda *args: applied.append(args),
    )
    assert report.dry_run is True
    assert report.classified == 1
    assert report.written == 0
    assert report.class_counts == {"identity": 1}
    assert applied == []


def test_apply_requires_flag(monkeypatch):
    monkeypatch.delenv("MEMORY_BELIEF_MODEL_ENABLED", raising=False)
    with pytest.raises(ValueError, match="MEMORY_BELIEF_MODEL_ENABLED"):
        backfill_belief_classes(
            "uid-1",
            db_client=SimpleNamespace(),
            dry_run=False,
            item_reader=lambda *_: [_item()],
            classifier=_classify_identity,
            applier=lambda *args: None,
        )


def test_backfill_honors_automation_pause(monkeypatch):
    monkeypatch.setenv("MEMORY_BELIEF_MODEL_ENABLED", "true")
    monkeypatch.setenv("MEMORY_BELIEF_AUTOMATION_PAUSED", "true")
    with pytest.raises(ValueError, match="belief automation is paused"):
        backfill_belief_classes(
            "uid-1",
            db_client=SimpleNamespace(),
            dry_run=True,
            item_reader=lambda *_: [_item()],
            classifier=_classify_identity,
        )


def test_default_applier_uses_backfill_mutation_kind():
    assert BELIEF_BACKFILL_MUTATION_KIND == "belief_backfill"


def test_unclassified_long_term_does_not_decay():
    assert derive_half_life_days(tier="long_term") is None
    assert derive_half_life_days(tier="archive") is None
    assert derive_half_life_days(category="system", tier="long_term") is None
    assert derive_half_life_days(category="manual", tier="long_term") is None
    assert derive_half_life_days(tier="short_term") == 30
    assert derive_half_life_days(category="interesting", tier="short_term") == 30


def test_classification_patch_ignores_scope_and_validity_and_supports_unknown():
    item = _item(subject_scope="primary_user")
    classification = BeliefBackfillRow(
        memory_id=item.memory_id,
        belief_class="preference",
        subject_scope="third_party",
        valid_to=NOW,
        half_life_days=7,
    )
    logical, extra = patch_for_belief_backfill(item, classification)
    assert "subject_scope" not in logical
    assert "valid_to" not in logical
    assert extra == {"belief_class": "preference", "half_life_days": 7.0}

    unknown = BeliefBackfillRow(memory_id=item.memory_id, classification_status="unknown")
    assert patch_for_belief_backfill(item, unknown) == ({}, {})


def test_bounded_checkpoint_reuses_cached_classification_after_apply_failure(monkeypatch):
    monkeypatch.setenv("MEMORY_BELIEF_MODEL_ENABLED", "true")
    items = [_item(memory_id="mem-a"), _item(memory_id="mem-b")]
    checkpoint = {}
    classify_calls = []
    apply_calls = []
    fail_once = {"value": True}

    def reader(_uid, _db, *, start_after=None, limit=None):
        assert limit == 1
        return [item for item in items if start_after is None or item.memory_id > start_after][:limit]

    def classify(rows, _user_name=None):
        classify_calls.append([row.memory_id for row in rows])
        return [BeliefBackfillRow(memory_id=row.memory_id, belief_class="identity") for row in rows]

    def apply(_uid, item, _classification, _db):
        apply_calls.append(item.memory_id)
        if fail_once["value"]:
            fail_once["value"] = False
            raise RuntimeError("temporary apply failure")

    first = backfill_belief_classes(
        "uid-1",
        db_client=SimpleNamespace(),
        dry_run=False,
        page_size=1,
        item_reader=reader,
        classifier=classify,
        applier=apply,
        checkpoint=checkpoint,
    )
    assert first.partial is True
    assert first.errors == 1
    assert checkpoint["cursor"] is None

    second = backfill_belief_classes(
        "uid-1",
        db_client=SimpleNamespace(),
        dry_run=False,
        page_size=1,
        item_reader=reader,
        classifier=classify,
        applier=apply,
        checkpoint=checkpoint,
    )
    assert second.written == 1
    assert classify_calls == [["mem-a"]]
    assert apply_calls == ["mem-a", "mem-a"]


def test_dry_run_checkpoint_then_apply_applies_the_cached_page(monkeypatch):
    monkeypatch.setenv("MEMORY_BELIEF_MODEL_ENABLED", "true")
    items = [_item(memory_id="mem-a", item_revision=1), _item(memory_id="mem-b", item_revision=1)]
    checkpoint = {}
    classify_calls = []
    apply_calls = []
    read_cursors = []

    def reader(_uid, _db, *, start_after=None, limit=None):
        read_cursors.append(start_after)
        return [item for item in items if start_after is None or item.memory_id > start_after][:limit]

    def classify(rows, _user_name=None):
        classify_calls.append([row.memory_id for row in rows])
        return [BeliefBackfillRow(memory_id=row.memory_id, belief_class="identity") for row in rows]

    def apply(_uid, item, _classification, _db):
        apply_calls.append(item.memory_id)

    dry = backfill_belief_classes(
        "uid-1",
        db_client=SimpleNamespace(),
        dry_run=True,
        page_size=1,
        item_reader=reader,
        classifier=classify,
        applier=apply,
        checkpoint=checkpoint,
    )
    assert dry.classified == 1
    assert apply_calls == []
    # The dry-run preview advances the physical cursor (unreadable rows must
    # not be re-paid), but its cached page stays pending for the apply run.
    assert checkpoint["cursor"] == "mem-a"
    assert checkpoint["results"]["mem-a"]["page_start"] is None

    applied_report = backfill_belief_classes(
        "uid-1",
        db_client=SimpleNamespace(),
        dry_run=False,
        page_size=1,
        item_reader=reader,
        classifier=classify,
        applier=apply,
        checkpoint=checkpoint,
    )
    assert applied_report.written == 1
    assert apply_calls == ["mem-a"]
    # The apply run must re-read the stranded dry-run page from its recorded
    # page start instead of resuming past it.
    assert read_cursors == [None, None]
    # The cached dry-run classification must be reused, not paid for twice.
    assert classify_calls == [["mem-a"]]


def test_checkpoint_completed_entry_is_invalidated_when_revision_changes(monkeypatch):
    monkeypatch.setenv("MEMORY_BELIEF_MODEL_ENABLED", "true")
    items = [_item(memory_id="mem-a", item_revision=1), _item(memory_id="mem-b", item_revision=1)]
    checkpoint = {}
    classify_calls = []
    apply_calls = []
    fail_b = {"value": True}

    def reader(_uid, _db, *, start_after=None, limit=None):
        return [item for item in items if start_after is None or item.memory_id > start_after][:limit]

    def classify(rows, _user_name=None):
        classify_calls.append([row.memory_id for row in rows])
        return [BeliefBackfillRow(memory_id=row.memory_id, belief_class="identity") for row in rows]

    def apply(_uid, item, _classification, _db):
        apply_calls.append(item.memory_id)
        if item.memory_id == "mem-b" and fail_b["value"]:
            fail_b["value"] = False
            raise RuntimeError("temporary apply failure")

    first = backfill_belief_classes(
        "uid-1",
        db_client=SimpleNamespace(),
        dry_run=False,
        page_size=2,
        item_reader=reader,
        classifier=classify,
        applier=apply,
        checkpoint=checkpoint,
    )
    assert first.written == 1
    assert checkpoint["completed"]["mem-a"] == {"status": "written", "revision": 1}
    # The failed page keeps the cursor at the page start for the rerun.
    assert checkpoint["cursor"] is None

    # Owner edits mem-a after the checkpoint recorded its terminal outcome.
    items[0] = _item(memory_id="mem-a", item_revision=2)

    second = backfill_belief_classes(
        "uid-1",
        db_client=SimpleNamespace(),
        dry_run=False,
        page_size=2,
        item_reader=reader,
        classifier=classify,
        applier=apply,
        checkpoint=checkpoint,
    )
    # The stale completed entry must be invalidated and mem-a reclassified.
    assert classify_calls[-1] == ["mem-a"]
    assert second.written == 2
    assert apply_calls == ["mem-a", "mem-b", "mem-a", "mem-b"]


def test_default_item_reader_uses_document_reference_cursor():
    captured = {}

    class _Query:
        def order_by(self, _field):
            return self

        def start_after(self, cursor):
            captured["cursor"] = cursor
            return self

        def limit(self, _count):
            return self

        def stream(self):
            return iter([])

    class _Collection:
        def document(self, doc_id):
            captured.setdefault("documents", []).append(doc_id)
            return SimpleNamespace(id=doc_id, path=f"users/uid-1/memory_items/{doc_id}")

        def order_by(self, field):
            return _Query().order_by(field)

    class _Db:
        def collection(self, _name):
            return _Collection()

    from utils.memory.belief_backfill import _default_item_reader

    _default_item_reader("uid-1", _Db(), start_after="mem-b", limit=5)

    name_cursor = captured["cursor"]["__name__"]
    assert not isinstance(name_cursor, str)
    assert name_cursor.id == "mem-b"
    assert captured["documents"] == ["mem-b"]


def test_unknown_is_counted_and_does_not_apply(monkeypatch):
    monkeypatch.setenv("MEMORY_BELIEF_MODEL_ENABLED", "true")
    applied = []
    report = backfill_belief_classes(
        "uid-1",
        db_client=SimpleNamespace(),
        dry_run=False,
        page_size=10,
        item_reader=lambda *_: [_item()],
        classifier=lambda rows, _name=None: [
            BeliefBackfillRow(memory_id=rows[0].memory_id, classification_status="unknown")
        ],
        applier=lambda *args: applied.append(args),
    )
    assert report.unknown == 1
    assert report.written == 0
    assert applied == []


def test_default_applier_uses_automated_source_fence_and_class_only_patch(monkeypatch, canonical_memory_adapter_module):
    item = _item(item_revision=4, subject_scope="third_party", valid_to=NOW)
    classification = BeliefBackfillRow(
        memory_id=item.memory_id,
        belief_class="preference",
        half_life_days=7,
        subject_scope="primary_user",
        valid_to=NOW.replace(day=3),
    )
    captured = {}

    def fake_apply(uid, memory_id, **kwargs):
        captured.update(uid=uid, memory_id=memory_id, kwargs=kwargs)
        logical, extra = kwargs["build_patch"](item, NOW)
        captured.update(logical=logical, extra=extra)
        return item, item

    monkeypatch.setattr(canonical_memory_adapter_module, "apply_canonical_user_mutation", fake_apply)
    _default_applier("uid-1", item, classification, SimpleNamespace())

    assert captured["kwargs"]["automated"] is True
    assert captured["kwargs"]["required_source_item"] is item
    assert "subject_scope" not in captured["logical"]
    assert "valid_to" not in captured["logical"]
    assert captured["extra"] == {"belief_class": "preference", "half_life_days": 7.0}
    with pytest.raises(ValueError, match="source revision changed"):
        captured["kwargs"]["build_patch"](_item(item_revision=5), NOW)


def test_physical_reader_errors_advance_physical_cursor_and_stay_partial(monkeypatch):
    monkeypatch.setenv("MEMORY_BELIEF_MODEL_ENABLED", "true")
    checkpoint = {}
    page = BeliefBackfillPage(
        [_item(memory_id="valid")],
        next_cursor="malformed-row-id",
        scanned=2,
        errors=1,
        has_more=False,
    )
    report = backfill_belief_classes(
        "uid-1",
        db_client=SimpleNamespace(),
        dry_run=True,
        page_size=2,
        item_reader=lambda *_: page,
        classifier=lambda rows, _name=None: [BeliefBackfillRow(memory_id=rows[0].memory_id, belief_class="identity")],
        checkpoint=checkpoint,
    )
    assert report.errors == 1
    assert report.partial is True
    assert report.next_cursor == "malformed-row-id"
    assert checkpoint["cursor"] == "malformed-row-id"
