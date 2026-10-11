import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from utils.observability import capture_loss as metrics

START = datetime(2026, 10, 7, tzinfo=timezone.utc)


def conversation(coverage='incomplete', runs=None):
    return SimpleNamespace(
        started_at=START,
        finished_at=START + timedelta(minutes=70),
        capture_evidence={'coverage': coverage, 'runs': runs},
    )


def run(start, end):
    return {'receipt_wall_start': START.timestamp() + start, 'receipt_wall_end': START.timestamp() + end}


def test_incomplete_receipt_union_clips_overlap_to_conversation_span():
    coverage, span, covered = metrics.coverage_accounting(
        conversation(runs=[run(-20, 60), run(30, 120), run(200, 260), run(4190, 4300)])
    )
    assert coverage == 'incomplete'
    assert span == 4200
    assert covered == 190


@pytest.mark.parametrize('coverage', ['incomplete', 'mapped', 'unknown'])
def test_coverage_classification_does_not_claim_meeting_completeness(coverage):
    assert metrics.coverage_accounting(conversation(coverage, [run(0, 10)])) == (coverage, 4200, 10)


@pytest.mark.parametrize('evidence', [None, {}, {'coverage': 'incomplete', 'receipts': [{'source_start_frame': 0}]}])
def test_unanchored_legacy_or_sync_evidence_is_unmeasurable(evidence):
    item = conversation()
    item.capture_evidence = evidence
    coverage, span, covered = metrics.coverage_accounting(item)
    assert coverage == ('incomplete' if evidence and evidence.get('coverage') == 'incomplete' else 'unknown')
    assert span == 4200
    assert covered is None


@pytest.mark.parametrize(
    'bad_run',
    [
        {},
        {'receipt_wall_start': float('nan'), 'receipt_wall_end': 20},
        {'receipt_wall_start': True, 'receipt_wall_end': 20},
        run(20, 10),
    ],
)
def test_invalid_anchors_do_not_count_as_zero_coverage(bad_run):
    assert metrics.coverage_accounting(conversation(runs=[bad_run]))[2] is None


def test_metrics_record_partial_seconds_with_static_labels(monkeypatch):
    total, seconds = MagicMock(), MagicMock()
    monkeypatch.setattr(metrics, 'CAPTURE_FINALIZED_TOTAL', total)
    monkeypatch.setattr(metrics, 'CAPTURE_FINALIZED_SECONDS', seconds)
    metrics.record_capture_loss(conversation(runs=[run(0, 90)]))
    total.labels.assert_called_once_with(coverage='incomplete', span_measurement='known')
    total.labels.return_value.inc.assert_called_once_with()
    assert seconds.labels.call_args_list[0].kwargs == {
        'coverage': 'incomplete',
        'span_measurement': 'known',
        'span': 'conversation',
    }
    assert seconds.labels.call_args_list[1].kwargs == {
        'coverage': 'incomplete',
        'span_measurement': 'known',
        'span': 'covered',
    }
    assert [call.args[0] for call in seconds.labels.return_value.inc.call_args_list] == [4200, 90]


def test_invalid_bounds_and_metric_failure_never_block_finalize(monkeypatch):
    item = conversation()
    item.finished_at = None
    assert metrics.coverage_accounting(item) == ('incomplete', None, None)
    total = MagicMock()
    total.labels.side_effect = RuntimeError('metrics unavailable')
    monkeypatch.setattr(metrics, 'CAPTURE_FINALIZED_TOTAL', total)
    metrics.record_capture_loss(item)


def persistence_hook(record):
    # Execute the production nested hook without importing LLM/DB providers.
    tree = ast.parse((Path(__file__).parents[2] / 'utils/conversations/process_conversation.py').read_text())
    process = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'process_conversation'
    )
    hook = next(
        node for node in process.body if isinstance(node, ast.FunctionDef) and node.name == 'report_persistence'
    )
    module = ast.Module(
        body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), hook],
        type_ignores=[],
    )
    namespace = {
        'record_capture_loss': record,
        'persistence_observer': None,
        'derived_effects_disposition_observer': None,
        'DerivedEffectsDisposition': SimpleNamespace(RUN='run'),
        'defer_derived_effects': True,
        # Owner-recognition observation is a separate counter. This hook only
        # proves capture-loss accounting still runs on an accepted persist.
        '_observe_owner_recognition_completion': lambda _completed: None,
    }
    exec(compile(ast.fix_missing_locations(module), '<production persistence hook>', 'exec'), namespace)
    return namespace['report_persistence']


def test_processing_hook_counts_only_accepted_persistence():
    record = MagicMock()
    report = persistence_hook(record)
    item = conversation(runs=[run(0, 10)])
    report(False, completed=item)
    report(True)
    record.assert_not_called()
    report(True, completed=item)
    record.assert_called_once_with(item)


def test_pydantic_internal_evidence_survives_wire_exclusion_for_finalize_accounting(monkeypatch):
    from models.conversation import CaptureEvidenceMetadata, Conversation

    item = Conversation(
        id='synthetic-pydantic-evidence',
        created_at=START,
        started_at=START,
        finished_at=START + timedelta(minutes=70),
        structured={},
        capture_evidence={'capability': 'source_position', 'coverage': 'incomplete', 'runs': [run(0, 90)]},
    )
    assert isinstance(item.capture_evidence, CaptureEvidenceMetadata)
    assert 'capture_evidence' not in item.model_dump()
    total, seconds = MagicMock(), MagicMock()
    monkeypatch.setattr(metrics, 'CAPTURE_FINALIZED_TOTAL', total)
    monkeypatch.setattr(metrics, 'CAPTURE_FINALIZED_SECONDS', seconds)
    report = persistence_hook(metrics.record_capture_loss)
    report(False, completed=item)
    total.labels.assert_not_called()
    report(True, completed=item)
    total.labels.assert_called_once_with(coverage='incomplete', span_measurement='known')
    assert [call.args[0] for call in seconds.labels.return_value.inc.call_args_list] == [4200, 90]
