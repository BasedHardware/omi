from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from utils.memory.belief_backfill import (
    BELIEF_BACKFILL_MUTATION_KIND,
    BeliefBackfillRow,
    backfill_belief_classes,
    patch_for_belief_backfill,
)
from utils.memory.belief_model import derive_half_life_days

NOW = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)


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


def test_backfill_keeps_user_asserted_half_life_null(monkeypatch):
    monkeypatch.setenv("MEMORY_BELIEF_MODEL_ENABLED", "true")
    item = _item(memory_id="mem-user", user_asserted=True, content="Remember that I hate celery")
    classification = BeliefBackfillRow(
        memory_id="mem-user",
        belief_class="preference",
        subject_scope="primary_user",
        half_life_days=7,
    )
    logical, extra = patch_for_belief_backfill(item, classification)
    assert extra["half_life_days"] is None
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
    assert applied[0][1]["half_life_days"] is None


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


def test_default_applier_uses_backfill_mutation_kind():
    assert BELIEF_BACKFILL_MUTATION_KIND == "belief_backfill"


def test_unclassified_long_term_does_not_decay():
    assert derive_half_life_days(tier="long_term") is None
    assert derive_half_life_days(tier="archive") is None
    assert derive_half_life_days(category="system", tier="long_term") is None
    assert derive_half_life_days(category="manual", tier="long_term") is None
    assert derive_half_life_days(tier="short_term") == 30
    assert derive_half_life_days(category="interesting", tier="short_term") == 30
