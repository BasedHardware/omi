"""Grouping sidecar telemetry storms: one degradation event per call.

Prod backend-listen 2026-10-28: ``event=speaker_grouping_storage
outcome=evidence_unavailable`` and its paired ``omi_fallback_event`` climbed
through ~1.6k+/hour (968 -> 1659 -> ~1.9k across 12:00-14:30 UTC) because the
codec emitted one warning and one degradation counter per failing sidecar --
and a read-path failure (key material that no longer authenticates, one
oversized or corrupted envelope) fails every sidecar of the conversation on
every read and rewrite. The fix keeps the per-segment drop semantics exactly
and changes the event shape: one ``omi_fallback_total`` and one warning per
call, carrying the failing-sidecar count and the most instructive fault
shape; ``protect_segments`` additionally drops an unverifiable stored sidecar
alone instead of letting it re-drop the whole conversation's evidence on
every rewrite.
"""

import json
import zlib

import pytest

from database import conversations as db
from models.transcript_segment import GROUPING_INTERNAL_FIELDS
from tests.unit.test_speaker_grouping_shadow import segment
from utils import encryption
from utils.conversations import speaker_grouping_storage as storage

PLAIN_VALUES = {'provider_speaker': ['soniox', 'a1', 7]}


def sidecar(segment_id: str, uid: str = 'owner', values: dict | None = None) -> str:
    record = {'id': segment_id, 'values': values if values is not None else dict(PLAIN_VALUES)}
    return encryption.encrypt(json.dumps(record), uid)


def sealed_row(segment_index: int, *, uid: str = 'owner', values: dict | None = None) -> dict:
    """A stored row whose sidecar verifies for ``uid`` and reveals PLAIN_VALUES."""
    row = segment(segment_index).model_dump()
    row[storage.FIELD] = sidecar(str(segment_index), uid=uid, values=values)
    return row


def poisoned_row(segment_index: int) -> dict:
    row = segment(segment_index).model_dump()
    row[storage.FIELD] = 'definitely-not-a-sidecar'
    return row


class EventSink:
    """Capture the degraded-event count and each warning's bounded detail."""

    def __init__(self, monkeypatch):
        self.fallbacks = 0
        self.lines: list[str] = []
        real_unavailable = storage._unavailable

        def fake_record(**_kwargs):
            self.fallbacks += 1

        def spy_unavailable(outcome, *, segments=1, fault=None):
            real_unavailable(outcome, segments=segments, fault=fault)
            self.lines.append(f'outcome={outcome} segments={segments} fault={fault}')

        monkeypatch.setattr(storage, 'record_fallback', fake_record)
        monkeypatch.setattr(storage, '_unavailable', spy_unavailable)

    @property
    def events(self):
        return len(self.lines)


# ---------------------------------------------------------------------------
# reveal_segments: one degradation event per read, with fault attribution
# ---------------------------------------------------------------------------


def test_reveal_aggregates_a_failing_conversation_into_one_event(monkeypatch):
    sink = EventSink(monkeypatch)
    rows = [poisoned_row(i) for i in range(30)]
    storage.reveal_segments(rows, 'owner')
    assert sink.events == 1
    assert sink.fallbacks == 1


def test_reveal_single_failure_reports_the_fault_shape(monkeypatch):
    sink = EventSink(monkeypatch)
    storage.reveal_segments([poisoned_row(0)], 'owner')
    assert sink.fallbacks == 1
    assert sink.lines == ['outcome=evidence_unavailable segments=1 fault=unwritable']


def test_reveal_reports_the_failing_sidecar_count(monkeypatch):
    sink = EventSink(monkeypatch)
    rows = [poisoned_row(i) for i in range(4)] + [segment(9).model_dump()]
    storage.reveal_segments(rows, 'owner')
    assert sink.events == 1
    assert sink.lines == ['outcome=evidence_unavailable segments=4 fault=unwritable']


def test_reveal_keeps_healthy_sidecars_beside_poisoned_ones(monkeypatch):
    sink = EventSink(monkeypatch)
    rows = [sealed_row(0), poisoned_row(1)]
    storage.reveal_segments(rows, 'owner')
    assert rows[0]['provider_speaker'] == PLAIN_VALUES['provider_speaker']
    assert storage.FIELD not in rows[0]
    assert storage.FIELD not in rows[1]
    assert sink.events == 1


def test_reveal_classifies_oversized_envelopes(monkeypatch):
    sink = EventSink(monkeypatch)
    row = segment(0).model_dump()
    row[storage.FIELD] = 'x' * (storage.MAX_ENCODED_BYTES + 1)
    storage.reveal_segments([row], 'owner')
    assert sink.lines == ['outcome=evidence_unavailable segments=1 fault=oversized']


def test_reveal_classifies_binding_mismatch_as_unwritable(monkeypatch):
    sink = EventSink(monkeypatch)
    row = segment(0).model_dump()
    row[storage.FIELD] = sidecar('some-other-segment')
    storage.reveal_segments([row], 'owner')
    assert sink.lines == ['outcome=evidence_unavailable segments=1 fault=unwritable']
    assert storage.FIELD not in row


def test_reveal_classifies_key_faults_as_key_unavailable(monkeypatch):
    sink = EventSink(monkeypatch)

    def broken_decrypt(_payload, _uid):
        raise RuntimeError('key derivation unavailable')

    monkeypatch.setattr(encryption, 'decrypt', broken_decrypt)
    storage.reveal_segments([poisoned_row(0)], 'owner')
    assert sink.lines == ['outcome=evidence_unavailable segments=1 fault=key_unavailable']


def test_reveal_classifies_unrecognized_value_errors_as_unknown(monkeypatch):
    sink = EventSink(monkeypatch)

    def odd_decrypt(_payload, _uid):
        raise ValueError('surprise')

    monkeypatch.setattr(encryption, 'decrypt', odd_decrypt)
    storage.reveal_segments([poisoned_row(0)], 'owner')
    assert sink.lines == ['outcome=evidence_unavailable segments=1 fault=unknown']


def test_reveal_primary_fault_prefers_oversized_over_unwritable(monkeypatch):
    sink = EventSink(monkeypatch)
    oversized = segment(0).model_dump()
    oversized[storage.FIELD] = 'x' * (storage.MAX_ENCODED_BYTES + 1)
    storage.reveal_segments([oversized, poisoned_row(1)], 'owner')
    assert sink.lines == ['outcome=evidence_unavailable segments=2 fault=oversized']


def test_reveal_primary_fault_reports_key_fault_over_named_shapes(monkeypatch):
    sink = EventSink(monkeypatch)

    def broken_decrypt(payload, _uid):
        if payload == 'definitely-not-a-sidecar':
            return payload  # decrypt swallows AES failure: envelope unchanged
        raise RuntimeError('key derivation unavailable')

    monkeypatch.setattr(encryption, 'decrypt', broken_decrypt)
    foreign = segment(2).model_dump()
    foreign[storage.FIELD] = 'another-not-a-sidecar'
    storage.reveal_segments([poisoned_row(0), poisoned_row(1), foreign], 'owner')
    assert sink.lines == ['outcome=evidence_unavailable segments=3 fault=key_unavailable']


def test_reveal_primary_fault_tie_goes_to_unwritable_over_unknown():
    assert storage._primary_fault({'unknown': 2, 'unwritable': 2}) == 'unwritable'


def test_reveal_primary_fault_unknown_only():
    assert storage._primary_fault({'unknown': 3}) == 'unknown'
    assert storage._primary_fault({}) == 'unknown'


def test_reveal_mixed_faults_report_primary_not_per_fault(monkeypatch):
    sink = EventSink(monkeypatch)
    oversized = segment(0).model_dump()
    oversized[storage.FIELD] = 'x' * (storage.MAX_ENCODED_BYTES + 1)

    def broken_decrypt(payload, _uid):
        if payload.startswith('x'):
            return payload
        raise RuntimeError('key derivation unavailable')

    monkeypatch.setattr(encryption, 'decrypt', broken_decrypt)
    storage.reveal_segments([oversized, poisoned_row(1)], 'owner')
    assert sink.events == 1
    assert sink.lines == ['outcome=evidence_unavailable segments=2 fault=oversized']


def test_reveal_without_failures_emits_nothing(monkeypatch):
    sink = EventSink(monkeypatch)
    rows = [sealed_row(0), {'id': '1', 'text': 'plain'}]
    storage.reveal_segments(rows, 'owner')
    assert sink.events == 0
    assert sink.fallbacks == 0
    assert rows[0]['provider_speaker'] == PLAIN_VALUES['provider_speaker']


def test_reveal_non_dict_rows_are_skipped_silently(monkeypatch):
    sink = EventSink(monkeypatch)
    storage.reveal_segments([None, 'junk', 3], 'owner')
    assert sink.events == 0


def test_reveal_expired_predictions_still_expire(monkeypatch):
    sink = EventSink(monkeypatch)
    expired_values = dict(PLAIN_VALUES)
    expired_values['speaker_grouping_shadow'] = {'owner_link': 'user'}
    expired_values['speaker_grouping_shadow_expires_at'] = 1.0
    row = sealed_row(0, values=expired_values)
    storage.reveal_segments([row], 'owner')
    assert 'speaker_grouping_shadow' not in row
    assert row['provider_speaker'] == PLAIN_VALUES['provider_speaker']
    assert sink.events == 0


def test_reveal_cross_owner_sidecar_aggregates_as_unwritable(monkeypatch):
    sink = EventSink(monkeypatch)
    storage.reveal_segments([sealed_row(0, uid='someone-else')], 'owner')
    assert sink.lines == ['outcome=evidence_unavailable segments=1 fault=unwritable']


def test_reveal_index_cap_reports_the_overflow_as_oversized(monkeypatch):
    sink = EventSink(monkeypatch)
    monkeypatch.setattr(storage, 'MAX_SEGMENTS', 2)
    rows = [{'id': '0', 'text': 'a'}, {'id': '1', 'text': 'b'}, poisoned_row(2), poisoned_row(3)]
    storage.reveal_segments(rows, 'owner')
    assert sink.events == 1
    assert sink.lines == ['outcome=evidence_unavailable segments=2 fault=oversized']


def test_reveal_cumulative_byte_bound_reports_one_oversized_failure(monkeypatch):
    sink = EventSink(monkeypatch)
    first = sealed_row(0)
    second = sealed_row(1)
    envelope = len(first[storage.FIELD])
    monkeypatch.setattr(storage, 'MAX_ENCODED_BYTES', envelope + len(second[storage.FIELD]) - 1)
    storage.reveal_segments([first, second], 'owner')
    assert sink.events == 1
    assert sink.lines == ['outcome=evidence_unavailable segments=1 fault=oversized']
    assert first.get('provider_speaker') == PLAIN_VALUES['provider_speaker']


def test_reveal_failed_rows_carry_no_grouping_residue():
    rows = [poisoned_row(0), poisoned_row(1)]
    storage.reveal_segments(rows, 'owner')
    for row in rows:
        assert not set(GROUPING_INTERNAL_FIELDS) & set(row)


# ---------------------------------------------------------------------------
# protect_segments: one poisoned stored sidecar no longer drops the rest
# ---------------------------------------------------------------------------


def test_protect_drops_only_the_unverifiable_sidecar():
    stored = db.encode_conversation_for_write('owner', {'transcript_segments': [sealed_row(0), poisoned_row(1)]})
    rows = json.loads(zlib.decompress(stored['transcript_segments']))
    by_id = {row['id']: row for row in rows}
    assert storage.FIELD in by_id['0'], 'healthy evidence must survive a poisoned neighbor'
    assert storage.FIELD not in by_id['1']


def test_protect_reports_individual_rejections_once_with_fault(monkeypatch):
    sink = EventSink(monkeypatch)
    db.encode_conversation_for_write('owner', {'transcript_segments': [sealed_row(0), poisoned_row(1)]})
    assert sink.events == 1
    assert sink.fallbacks == 1
    assert sink.lines == ['outcome=evidence_dropped segments=1 fault=unwritable']


def test_protect_keeps_the_whole_drop_on_encryption_fault(monkeypatch):
    sink = EventSink(monkeypatch)
    row = sealed_row(0)
    row['provider_speaker'] = PLAIN_VALUES['provider_speaker']
    monkeypatch.setattr(encryption, 'encrypt', lambda *a: (_ for _ in ()).throw(ValueError('failed')))
    stored = db.encode_conversation_for_write('owner', {'transcript_segments': [row]})
    rows = json.loads(zlib.decompress(stored['transcript_segments']))
    assert not set(GROUPING_INTERNAL_FIELDS) & set(rows[0])
    assert sink.events == 1


def test_protect_keeps_the_whole_drop_on_envelope_capacity(monkeypatch):
    sink = EventSink(monkeypatch)
    row = sealed_row(0)
    row['provider_speaker'] = PLAIN_VALUES['provider_speaker']
    monkeypatch.setattr(storage, 'MAX_BYTES', 1)
    stored = db.encode_conversation_for_write('owner', {'transcript_segments': [row]})
    rows = json.loads(zlib.decompress(stored['transcript_segments']))
    assert not set(GROUPING_INTERNAL_FIELDS) & set(rows[0])
    assert sink.events == 1


def test_protect_non_string_sidecar_dropped_alone():
    junk = segment(1).model_dump()
    junk[storage.FIELD] = {'not': 'a string'}
    stored = db.encode_conversation_for_write('owner', {'transcript_segments': [sealed_row(0), junk]})
    rows = json.loads(zlib.decompress(stored['transcript_segments']))
    by_id = {row['id']: row for row in rows}
    assert storage.FIELD in by_id['0']
    assert storage.FIELD not in by_id['1']


def test_protect_oversized_sidecar_dropped_alone():
    oversized = segment(1).model_dump()
    oversized[storage.FIELD] = 'x' * (storage.MAX_ENCODED_BYTES + 1)
    stored = db.encode_conversation_for_write('owner', {'transcript_segments': [sealed_row(0), oversized]})
    rows = json.loads(zlib.decompress(stored['transcript_segments']))
    by_id = {row['id']: row for row in rows}
    assert storage.FIELD in by_id['0']
    assert storage.FIELD not in by_id['1']


def test_protect_mixed_rejections_headline_the_primary_fault(monkeypatch):
    sink = EventSink(monkeypatch)
    junk = segment(1).model_dump()
    junk[storage.FIELD] = {'not': 'a string'}
    oversized = segment(2).model_dump()
    oversized[storage.FIELD] = 'x' * (storage.MAX_ENCODED_BYTES + 1)
    db.encode_conversation_for_write('owner', {'transcript_segments': [sealed_row(0), junk, oversized]})
    assert sink.events == 1
    assert sink.lines == ['outcome=evidence_dropped segments=2 fault=oversized']


def test_protect_still_strips_legacy_plaintext_values():
    stored = db.encode_conversation_for_write('owner', {'transcript_segments': [sealed_row(0), poisoned_row(1)]})
    rows = json.loads(zlib.decompress(stored['transcript_segments']))
    assert all(not (set(GROUPING_INTERNAL_FIELDS) - {storage.FIELD}) & set(row) for row in rows)


def test_protect_sealed_neighbor_still_reveals_after_a_rejection():
    stored = db.encode_conversation_for_write('owner', {'transcript_segments': [sealed_row(0), poisoned_row(1)]})
    restored = db.prepare_conversation_for_read(stored, 'owner')['transcript_segments']
    by_id = {row['id']: row for row in restored}
    assert by_id['0'].get('provider_speaker') == PLAIN_VALUES['provider_speaker']
    assert storage.FIELD not in by_id['0']
    assert not set(GROUPING_INTERNAL_FIELDS) & set(by_id['1'])


def test_protect_clean_write_emits_no_event(monkeypatch):
    sink = EventSink(monkeypatch)
    db.encode_conversation_for_write('owner', {'transcript_segments': [sealed_row(0)]})
    assert sink.events == 0
    assert sink.fallbacks == 0


def test_protect_expired_sidecar_reseals_without_rejection(monkeypatch):
    sink = EventSink(monkeypatch)
    expired_values = dict(PLAIN_VALUES)
    expired_values['speaker_grouping_shadow'] = {'owner_link': 'user'}
    expired_values['speaker_grouping_shadow_expires_at'] = 1.0
    stored = db.encode_conversation_for_write('owner', {'transcript_segments': [sealed_row(0, values=expired_values)]})
    restored = db.prepare_conversation_for_read(stored, 'owner')['transcript_segments']
    assert restored[0].get('provider_speaker') == PLAIN_VALUES['provider_speaker']
    assert 'speaker_grouping_shadow' not in restored[0]
    assert sink.events == 0


# ---------------------------------------------------------------------------
# database read path: the storm conversation produces one event
# ---------------------------------------------------------------------------


def test_db_read_of_a_storm_conversation_emits_one_grouping_event(monkeypatch):
    sink = EventSink(monkeypatch)
    data = {'transcript_segments': [poisoned_row(i) for i in range(30)]}
    db.prepare_conversation_for_read(data, 'owner')
    assert sink.events == 1
    assert sink.fallbacks == 1
    assert sink.lines == ['outcome=evidence_unavailable segments=30 fault=unwritable']


def test_db_write_of_a_storm_conversation_emits_one_grouping_event(monkeypatch):
    sink = EventSink(monkeypatch)
    rows = [sealed_row(0)] + [poisoned_row(i) for i in range(1, 10)]
    stored = db.encode_conversation_for_write('owner', {'transcript_segments': rows})
    restored_rows = json.loads(zlib.decompress(stored['transcript_segments']))
    assert sink.events == 1
    assert storage.FIELD in next(r for r in restored_rows if r['id'] == '0')


def test_protect_drops_poisoned_sidecar_but_seals_new_values_in_same_call(monkeypatch):
    """A poisoned stored sidecar must not forfeit NEW plaintext evidence either."""
    fresh = segment(1).model_dump()
    fresh['provider_speaker'] = PLAIN_VALUES['provider_speaker']
    stored = db.encode_conversation_for_write('owner', {'transcript_segments': [poisoned_row(0), fresh]})
    rows = json.loads(zlib.decompress(stored['transcript_segments']))
    by_id = {row['id']: row for row in rows}
    assert storage.FIELD in by_id['1'], 'fresh plaintext evidence must be sealed'
    assert storage.FIELD not in by_id['0']


def test_reveal_counts_index_cap_and_binding_failures_together(monkeypatch):
    """segments=N sums every rejected sidecar, whatever fault each hit."""
    sink = EventSink(monkeypatch)
    monkeypatch.setattr(storage, 'MAX_SEGMENTS', 2)
    late_poisoned = poisoned_row(3)
    late_binding = segment(4).model_dump()
    late_binding[storage.FIELD] = sidecar('not-this-segment')
    rows = [sealed_row(0), sealed_row(1), late_poisoned, late_binding]
    storage.reveal_segments(rows, 'owner')
    assert sink.events == 1
    assert sink.lines == ['outcome=evidence_unavailable segments=2 fault=oversized']


def test_db_read_of_a_non_list_transcript_skips_grouping_telemetry(monkeypatch):
    sink = EventSink(monkeypatch)
    db.prepare_conversation_for_read({'transcript_segments': 'not-a-list'}, 'owner')
    db.prepare_conversation_for_read({}, 'owner')
    assert sink.events == 0
    assert sink.fallbacks == 0


def test_unavailable_log_line_carries_count_and_fault_tokens(monkeypatch):
    captured: list[str] = []

    def capture(fmt, *args):
        captured.append(fmt % args)

    monkeypatch.setattr(storage.logger, 'warning', capture)
    storage._unavailable('evidence_unavailable', segments=30, fault='unwritable')
    assert captured[-1] == ('event=speaker_grouping_storage outcome=evidence_unavailable segments=30 fault=unwritable')


def test_unavailable_single_shape_keeps_the_plain_event(monkeypatch):
    sink = EventSink(monkeypatch)
    storage._unavailable('evidence_dropped')
    assert sink.fallbacks == 1
    assert sink.lines == ['outcome=evidence_dropped segments=1 fault=None']


def test_unavailable_records_exactly_one_fallback_per_call(monkeypatch):
    sink = EventSink(monkeypatch)
    storage._unavailable('evidence_unavailable', segments=200, fault='key_unavailable')
    assert sink.fallbacks == 1
    assert sink.events == 1


# ---------------------------------------------------------------------------
# fault vocabulary units
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ('error', 'expected'),
    [
        (ValueError('capacity'), 'oversized'),
        (ValueError('authentication'), 'unwritable'),
        (ValueError('binding'), 'unwritable'),
        (ValueError('something else'), 'unknown'),
        (RuntimeError('nope'), 'key_unavailable'),
        (TypeError('nope'), 'key_unavailable'),
    ],
)
def test_reveal_fault_vocabulary(error, expected):
    assert storage._reveal_fault(error) == expected


def test_reveal_fault_prefers_unwritable_at_equal_counts_with_unknown():
    assert storage._primary_fault({'unwritable': 1, 'unknown': 1}) == 'unwritable'


def test_reveal_fault_prefers_unknown_when_it_dominates():
    assert storage._primary_fault({'unwritable': 1, 'unknown': 5}) == 'unknown'
