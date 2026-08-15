"""Conformance + integrity tests for the shared cross-platform parity contracts
(contracts/parity/README.md).

The backend owns two legs:

- Fixture integrity: every fixture parses, expectations are complete and use the
  sanctioned vocabulary, and the day-key vectors are arithmetically
  self-consistent. The client suites all trust these files, so a malformed or
  self-contradictory fixture would let every platform pass vacuously at once;
  this suite is the independent check that the vectors themselves are true.
- The serialization side of the action-item wire contract: ActionItemResponse
  timestamps always serialize with an explicit UTC offset. Dart and JS interpret
  a naive ISO string as LOCAL wall time while Swift's ISO8601 decoder rejects it
  outright, so a naive emission is the one wire form guaranteed to diverge
  across first-party clients.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from models.action_item import ActionItemResponse

ROOT_DIR = Path(__file__).resolve().parents[3]
PARITY_DIR = ROOT_DIR / 'contracts' / 'parity'

BUCKET_VOCABULARY = {'today', 'tomorrow', 'later', 'no_deadline', 'overdue'}
# The parseable due_at forms in the wire fixture; the remaining cases exist to
# pin CLIENT-side tolerance for junk the backend itself refuses to emit.
CLIENT_ONLY_WIRE_CASES = {'due_empty_string', 'due_unparseable_string'}


def _fixture(name: str) -> dict:
    return json.loads((PARITY_DIR / name).read_text(encoding='utf-8'))


def test_bucket_fixture_expectations_are_complete():
    cases = _fixture('task_due_buckets.json')['cases']
    assert cases, 'bucket fixture must not be empty'
    seen = set()
    for case in cases:
        assert case['name'] not in seen, f"duplicate case name {case['name']}"
        seen.add(case['name'])
        assert 'now' in case and 'due' in case and 'created' in case, case['name']
        expected = case['expected']
        # Every case pins BOTH sanctioned models so a platform switching models
        # is a fixture edit, not silent drift.
        assert set(expected) == {'fold_overdue', 'separate_overdue'}, case['name']
        for model, bucket in expected.items():
            assert bucket in BUCKET_VOCABULARY, f"{case['name']}: {bucket}"
        # The fold model has no overdue bucket by definition.
        assert expected['fold_overdue'] != 'overdue', case['name']


def test_day_key_fixture_is_arithmetically_consistent():
    cases = _fixture('day_keys.json')['cases']
    assert cases, 'day-key fixture must not be empty'
    for case in cases:
        instant = datetime.fromisoformat(case['utc'].replace('Z', '+00:00'))
        offsets = case['expected_by_offset']
        assert '0' in offsets, f"{case['name']}: offset 0 must be present so UTC CI runs every case"
        for offset_minutes, expected_day in offsets.items():
            local = instant + timedelta(minutes=int(offset_minutes))
            assert local.date().isoformat() == expected_day, (
                f"{case['name']} offset {offset_minutes}: fixture says {expected_day}, "
                f"arithmetic says {local.date().isoformat()}"
            )


def test_label_fixture_structure():
    cases = _fixture('section_labels.json')['cases']
    assert cases, 'label fixture must not be empty'
    for case in cases:
        labels = case['labels']
        assert set(labels) == {'conversation_section', 'due_badge'}, case['name']
        for value in labels.values():
            assert value is None or value in {'Today', 'Yesterday', 'Tomorrow'}, f"{case['name']}: {value}"
        if 'requires_dst_transition_between' in case:
            pair = case['requires_dst_transition_between']
            assert len(pair) == 2, case['name']
            for day in pair:
                datetime(day[0], day[1], day[2])  # must be a real calendar day


def test_wire_fixture_field_names_exist_on_backend_model():
    """Guards fixture rot: if the backend renames a serialized field, the wire
    fixture must move with it instead of silently testing a dead key."""
    known_fields = set(ActionItemResponse.model_fields)
    for case in _fixture('wire_action_item.json')['cases']:
        for key in case['payload']:
            if key.startswith('parity_probe_'):
                continue  # the deliberate unknown-field tolerance probe
            assert key in known_fields, f"{case['name']}: payload key {key} is not an ActionItemResponse field"


def test_backend_round_trips_the_parseable_wire_cases():
    for case in _fixture('wire_action_item.json')['cases']:
        if case['name'] in CLIENT_ONLY_WIRE_CASES:
            continue
        item = ActionItemResponse.model_validate(case['payload'])
        dumped = item.model_dump(mode='json')
        expected = case['expected']
        assert dumped['description'] == expected['description'], case['name']
        assert dumped['completed'] == expected['completed'], case['name']
        if expected['due_utc'] is None:
            assert dumped['due_at'] is None, case['name']
        else:
            emitted = datetime.fromisoformat(dumped['due_at'].replace('Z', '+00:00'))
            target = datetime.fromisoformat(expected['due_utc'].replace('Z', '+00:00'))
            assert emitted == target, case['name']


def test_backend_rejects_the_client_only_junk_forms():
    """Clients tolerate junk due_at strings defensively; the backend must never
    accept (and therefore never re-emit) them."""
    cases = {c['name']: c for c in _fixture('wire_action_item.json')['cases']}
    for name in CLIENT_ONLY_WIRE_CASES:
        with pytest.raises(Exception):
            ActionItemResponse.model_validate(cases[name]['payload'])


@pytest.mark.parametrize('field', ['due_at', 'created_at', 'updated_at', 'completed_at'])
def test_naive_datetimes_serialize_with_an_explicit_utc_offset(field):
    """Firestore timestamps are UTC; if a naive datetime reaches the response
    model it must serialize as that UTC instant with an explicit offset, never
    as an offsetless local-looking string."""
    naive = datetime(2026, 8, 20, 16, 0, 0)
    item = ActionItemResponse.model_validate(
        {'id': 'ai_parity_naive', 'description': 'naive timestamp', 'completed': False, field: naive}
    )
    emitted = item.model_dump(mode='json')[field]
    assert emitted.endswith('Z') or '+00:00' in emitted, (
        f"{field} serialized without an offset: {emitted!r}; Dart/JS read this as local wall "
        "time and Swift ISO8601 decoding rejects it (contracts/parity/README.md)"
    )
    assert datetime.fromisoformat(emitted.replace('Z', '+00:00')) == naive.replace(tzinfo=timezone.utc)


def test_aware_datetimes_keep_their_instant():
    aware = datetime(2026, 8, 20, 18, 0, 0, tzinfo=timezone(timedelta(hours=2)))
    item = ActionItemResponse.model_validate(
        {'id': 'ai_parity_aware', 'description': 'aware timestamp', 'completed': False, 'due_at': aware}
    )
    emitted = item.model_dump(mode='json')['due_at']
    assert datetime.fromisoformat(emitted.replace('Z', '+00:00')) == aware
