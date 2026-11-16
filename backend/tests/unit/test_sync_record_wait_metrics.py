"""Record-wait counters are bounded, declared and independent of log sampling."""

import json
from pathlib import Path

from prometheus_client import REGISTRY

from utils.batch_pipeline.live_upload import RecordUploadWait, _pending
from utils.metrics import OMI_PIPELINE_RECORD_WAIT_ANSWERS_TOTAL, OMI_PIPELINE_RECORD_WAIT_MEMO_HITS_TOTAL

BACKEND = Path(__file__).resolve().parents[2]


def _sample(name, labels):
    return REGISTRY.get_sample_value(name, labels) or 0


def test_record_wait_counters_have_bounded_labels_and_are_declared():
    inventory = json.loads((BACKEND / 'charts/monitoring/metric-inventory.prod.json').read_text())
    declared = set(inventory['declared_metrics'])

    assert OMI_PIPELINE_RECORD_WAIT_ANSWERS_TOTAL._labelnames == ('reason',)
    assert OMI_PIPELINE_RECORD_WAIT_MEMO_HITS_TOTAL._labelnames == ('memo',)
    assert {
        'omi_pipeline_record_wait_answers_total',
        'omi_pipeline_record_wait_memo_hits_total',
    } <= declared


def test_record_wait_answer_and_coverage_memo_hit_increment_counters():
    reason_labels = {'reason': RecordUploadWait.AUDIO_COVERAGE_UNPROVEN.value}
    memo_labels = {'memo': 'coverage'}
    answers_before = _sample('omi_pipeline_record_wait_answers_total', reason_labels)
    memo_hits_before = _sample('omi_pipeline_record_wait_memo_hits_total', memo_labels)

    response = _pending(
        RecordUploadWait.AUDIO_COVERAGE_UNPROVEN,
        record='synthetic-record-hash',
        path='coverage',
        memo='hit',
    )

    assert response.status_code == 503
    assert _sample('omi_pipeline_record_wait_answers_total', reason_labels) == answers_before + 1
    assert _sample('omi_pipeline_record_wait_memo_hits_total', memo_labels) == memo_hits_before + 1
