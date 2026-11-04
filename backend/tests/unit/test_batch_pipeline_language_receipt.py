import json

import pytest

from utils.batch_pipeline.contracts import Priority, WorkItem, WorkResult
from utils.batch_pipeline.language_receipt import (
    admission,
    auto_language_cohort,
    observation,
    validate,
    validate_admission,
)


def test_admission_receipt_has_closed_normalized_labels():
    assert admission({'stt_language': 'en-US', 'stt_language_evidence': 'audio_lid'}) == {
        'version': 1,
        'language': 'en',
        'evidence': 'audio_lid',
    }
    assert admission({'stt_language': 'ja', 'stt_language_evidence': ['private']}) == {
        'version': 1,
        'language': 'unsupported',
        'evidence': 'unavailable',
    }
    with pytest.raises(ValueError):
        validate_admission({'version': 1, 'language': 'en', 'evidence': 'email@example.com'})


def test_observation_counts_script_without_retaining_transcript_text():
    receipt = observation('ru', 'parakeet', [{'word': 'Привет'}, {'word': 'hello'}])
    assert receipt == {
        'version': 1,
        'language': 'ru',
        'route': 'parakeet',
        'word_count': 2,
        'letters': 11,
        'incompatible_letters': 5,
        'scripts': {'cyrillic': 6, 'greek': 0, 'latin': 5, 'other': 0},
    }
    encoded = json.dumps(receipt, ensure_ascii=False)
    assert 'Привет' not in encoded and 'hello' not in encoded
    validate(receipt)


def test_unknown_language_records_route_without_claiming_script_match():
    receipt = observation('multi', 'parakeet', [{'word': 'hello'}])
    assert receipt['language'] == 'und'
    assert receipt['route'] == 'parakeet'
    assert receipt['incompatible_letters'] is None


def test_receipts_are_limited_to_the_marked_mobile_native_auto_language_cohort():
    assert auto_language_cohort(server_batch_only=True, client_platform='ios', native_record=True, language='multi')
    assert not auto_language_cohort(server_batch_only=True, client_platform='ios', native_record=True, language='en')
    assert not auto_language_cohort(
        server_batch_only=False, client_platform='ios', native_record=True, language='multi'
    )
    assert not auto_language_cohort(server_batch_only=True, client_platform='web', native_record=True, language='multi')


def test_result_omits_absent_receipt_and_matches_old_result_shape():
    result = WorkResult('segment', 'gs://synthetic/result')
    assert result.to_dict() == {
        'segment_id': 'segment',
        'result_uri': 'gs://synthetic/result',
        'outcome': 'success',
    }
    assert result.matches_persisted(result.to_dict())
    with pytest.raises(ValueError):
        WorkResult('segment', 'gs://synthetic/result', language_receipt={'text': 'must not be stored'})


def test_work_item_omits_absent_receipt_gate_and_persists_only_explicit_cohort_marker():
    base = WorkItem('segment', 'owner', 1, 'gs://synthetic/audio', 1, Priority.FRESH)
    assert 'language_receipt_enabled' not in base.to_dict()
    cohort = WorkItem('cohort', 'owner', 1, 'gs://synthetic/audio', 1, Priority.FRESH, language_receipt_enabled=True)
    assert cohort.to_dict()['language_receipt_enabled'] is True
