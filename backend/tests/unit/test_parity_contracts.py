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
from pydantic import ValidationError

from models.action_item import ActionItemResponse

ROOT_DIR = Path(__file__).resolve().parents[3]
PARITY_DIR = ROOT_DIR / 'contracts' / 'parity'

BUCKET_VOCABULARY = {'today', 'tomorrow', 'later', 'no_deadline', 'overdue'}


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


def test_backend_round_trips_the_agreement_set_wire_cases():
    for case in _fixture('wire_action_item.json')['cases']:
        if 'expected_by_model' in case:
            continue  # strict-vs-tolerant divergence cases, covered below
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


def test_backend_rejects_the_divergence_case_junk_forms():
    """The expected_by_model cases pin the strict-vs-tolerant client split on
    unparseable due_at strings (Dart wire rejects the item, Windows maps it to
    no-due-date). The backend sits on the strict side: it must never accept,
    and therefore never re-emit, these forms."""
    divergence_cases = [c for c in _fixture('wire_action_item.json')['cases'] if 'expected_by_model' in c]
    assert divergence_cases, 'expected the strict-vs-tolerant wire cases to exist'
    for case in divergence_cases:
        assert case['expected_by_model']['strict_decode']['parses'] is False, case['name']
        assert case['expected_by_model']['tolerant_decode']['parses'] is True, case['name']
        # ValidationError specifically: a broader except would also swallow a
        # rotted fixture (missing keys raise KeyError above, loudly).
        with pytest.raises(ValidationError):
            ActionItemResponse.model_validate(case['payload'])


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


def test_semantically_naive_tzinfo_serializes_with_an_explicit_utc_offset():
    """A tzinfo whose utcoffset() returns None is still naive for serialization
    purposes; the guard must key off utcoffset(), not tzinfo presence."""
    import datetime as datetime_module

    class _OffsetlessTzinfo(datetime_module.tzinfo):
        def utcoffset(self, dt):
            return None

        def dst(self, dt):
            return None

        def tzname(self, dt):
            return 'offsetless'

    semi_naive = datetime(2026, 8, 20, 16, 0, 0, tzinfo=_OffsetlessTzinfo())
    item = ActionItemResponse.model_validate(
        {'id': 'ai_parity_semi', 'description': 'semantically naive', 'completed': False, 'due_at': semi_naive}
    )
    emitted = item.model_dump(mode='json')['due_at']
    assert emitted.endswith('Z') or '+00:00' in emitted, f'no offset emitted: {emitted!r}'
    assert datetime.fromisoformat(emitted.replace('Z', '+00:00')) == semi_naive.replace(tzinfo=timezone.utc)
