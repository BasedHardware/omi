from datetime import datetime, timezone

from models.other import Person, PersonConfidence
from models.person_confidence import (
    AUTO_CONFIRMED,
    AUTO_CORRECTED,
    CARD_CONFIRMS,
    CARD_PICKS,
    COUNTED_KEYS_LIMIT,
    MANUAL_LABELS,
    SOURCE_CARD,
    SOURCE_MANUAL,
    Band,
    person_confidence,
)
from utils.person_evidence import apply_evidence, assignment_evidence, merge_backfill, receipt_person_ids

NOW = datetime(2026, 9, 30, 12, tzinfo=timezone.utc)
READY = dict(speech_samples=['s'], speech_samples_version=3, speaker_embedding=[0.1, 0.2])


def codes(result):
    return [code for code, _ in result.reasons]


def test_automatic_matches_alone_stay_unverified():
    result = person_confidence({}, voice_ready=True, conversation_count=4, auto_conversation_count=4)
    assert result.band == Band.unverified
    assert 'never_confirmed' in codes(result) and ('auto_unconfirmed', 4) in result.reasons
    assert result.labels_to_confirm == 2


def test_one_hand_label_with_voice_is_likely_and_two_is_confirmed():
    assert person_confidence({MANUAL_LABELS: 1}, voice_ready=True).band == Band.likely
    assert person_confidence({MANUAL_LABELS: 1}, voice_ready=True).labels_to_confirm == 1
    confirmed = person_confidence({MANUAL_LABELS: 2}, voice_ready=True)
    assert confirmed.band == Band.confirmed and confirmed.labels_to_confirm is None


def test_confirmed_needs_a_voice_sample():
    result = person_confidence({MANUAL_LABELS: 6}, voice_ready=False)
    assert result.band == Band.likely
    assert result.needs_voice and 'needs_voice' in codes(result)
    # Enough labels already: only the voice sample is missing.
    assert result.labels_to_confirm is None


def test_card_answers_are_medium_and_corrections_count_against():
    result = person_confidence({CARD_PICKS: 2, AUTO_CONFIRMED: 1, AUTO_CORRECTED: 1}, voice_ready=True)
    assert result.band == Band.likely
    assert result.labels_to_confirm == 1
    assert person_confidence({CARD_CONFIRMS: 1, AUTO_CORRECTED: 2}, voice_ready=True).band == Band.unverified


def test_malformed_counters_are_ignored():
    result = person_confidence({MANUAL_LABELS: 'lots', CARD_PICKS: True, AUTO_CORRECTED: -3}, voice_ready=False)
    assert result.band == Band.unknown
    assert person_confidence(None, voice_ready=False).band == Band.unknown


def test_legacy_evidence_is_unknown_even_after_stats_refresh():
    person = Person(id='legacy', name='Maya', **READY)
    assert person.confidence.value == 'unknown'
    person.conversation_count = 0
    person.refresh_confidence()
    assert person.confidence.value == 'unknown'
    assert 'never_confirmed' not in [r.code for r in person.confidence_reasons]
    assert person.labels_to_confirm is None


def test_stats_only_add_reasons():
    base = person_confidence({MANUAL_LABELS: 1}, voice_ready=False)
    with_stats = person_confidence({MANUAL_LABELS: 1}, voice_ready=False, conversation_count=0)
    assert base.band == with_stats.band
    assert 'not_heard' in codes(with_stats) and 'not_heard' not in codes(base)


def test_person_model_derives_confidence_from_stored_tally():
    person = Person(id='p', name='Maya', label_evidence={MANUAL_LABELS: 6, 'last_labeled_at': NOW}, **READY)
    assert person.confidence == PersonConfidence.confirmed
    assert person.last_labeled_at == NOW
    dumped = person.model_dump(mode='json')
    assert 'label_evidence' not in dumped and dumped['confidence'] == 'confirmed'
    assert dumped['pinned'] is False
    # A dumped person re-validates to the same claim without its private tally.
    assert Person(**dumped).confidence == PersonConfidence.confirmed


def test_assignment_evidence_by_source_and_prior_label():
    unnamed = [{'person_id': None}]
    auto_same = [{'person_id': 'p', 'speaker_match_source': 'live_embedding'}]
    auto_other = [{'person_id': 'q', 'speaker_match_source': 'sync_embedding'}]
    assert assignment_evidence(unnamed, person_id='p', source=SOURCE_MANUAL) == {'p': MANUAL_LABELS}
    assert assignment_evidence(unnamed, person_id='p', source=SOURCE_CARD) == {'p': CARD_PICKS}
    assert assignment_evidence(auto_same, person_id='p', source=SOURCE_CARD) == {'p': CARD_CONFIRMS}
    assert assignment_evidence(auto_same, person_id='p', source=SOURCE_MANUAL) == {'p': AUTO_CONFIRMED}
    assert assignment_evidence(auto_other, person_id='p', source=SOURCE_MANUAL) == {
        'p': MANUAL_LABELS,
        'q': AUTO_CORRECTED,
    }
    # Clearing an automatic label (no target) is only a correction.
    assert assignment_evidence(auto_other, person_id=None, source=SOURCE_CARD) == {'q': AUTO_CORRECTED}
    # A manual label moved away is not a correction of Omi, and relabeling the same person earns nothing.
    assert assignment_evidence([{'person_id': 'q'}], person_id='p', source=SOURCE_MANUAL) == {'p': MANUAL_LABELS}
    assert assignment_evidence([{'person_id': 'p'}], person_id='p', source=SOURCE_MANUAL) == {}


def test_apply_evidence_counts_each_conversation_once():
    first = apply_evidence(None, MANUAL_LABELS, 'c1', NOW)
    assert first[MANUAL_LABELS] == 1 and first['last_labeled_at'] == NOW
    assert apply_evidence(first, MANUAL_LABELS, 'c1', NOW) is None
    second = apply_evidence(first, CARD_PICKS, 'c1', NOW)
    assert second[CARD_PICKS] == 1 and second[MANUAL_LABELS] == 1
    corrected = apply_evidence({}, AUTO_CORRECTED, 'c2', NOW)
    assert corrected[AUTO_CORRECTED] == 1 and 'last_labeled_at' not in corrected


def test_counted_keys_are_bounded():
    evidence = None
    for index in range(COUNTED_KEYS_LIMIT + 5):
        evidence = apply_evidence(evidence, MANUAL_LABELS, f'c{index}', NOW)
    assert len(evidence['counted']) == COUNTED_KEYS_LIMIT
    assert evidence[MANUAL_LABELS] == COUNTED_KEYS_LIMIT + 5


def test_receipt_person_ids_skips_owner_and_malformed_entries():
    receipt = {
        'speakers': {'1': {'person_id': 'p', 'generation': 1}, '2': {'is_user': True}, '3': 'junk'},
        'segments': {'a': {'person_id': 'q'}, 'b': {'person_id': 'p'}, 'c': {'person_id': ''}},
    }
    assert receipt_person_ids(receipt) == ['p', 'q']
    assert receipt_person_ids(None) == [] and receipt_person_ids({'speakers': []}) == []


def test_merge_backfill_is_idempotent_and_respects_live_counts():
    live = apply_evidence(None, MANUAL_LABELS, 'c1', NOW)
    merged = merge_backfill(live, ['c1', 'c2'], NOW)
    assert merged[MANUAL_LABELS] == 2 and merged['last_labeled_at'] == NOW
    assert merge_backfill(merged, ['c1', 'c2'], NOW) is None
    fresh = merge_backfill(None, ['c9'], NOW)
    assert fresh[MANUAL_LABELS] == 1 and 'last_labeled_at' not in fresh
