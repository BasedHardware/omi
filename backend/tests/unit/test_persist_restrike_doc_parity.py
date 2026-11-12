#!/usr/bin/env python3
"""Doc parity for backend/docs/persist-restrike-lane.md.

Every factual sentence of the lane doc is mirrored against the code it describes: the
schedule constants, the classifier family, the telemetry event names, the registry entry,
the rollback switch and the deliberate non-changes. Any doc drift or code retune fails
here first.

Failure-Class: FC-persist-transport-loss-discards-completed-gpu-results
"""

import datetime
import json
import logging
import os
import re

import pytest
from google.api_core.exceptions import InvalidArgument, InternalServerError, ServiceUnavailable
from google.api_core.exceptions import DeadlineExceeded, NotFound, ResourceExhausted, RetryError
from google.api_core.exceptions import Aborted, BadRequest, Cancelled, Conflict, FailedPrecondition
from google.api_core.exceptions import Forbidden, GoogleAPIError, PreconditionFailed
from google.api_core.exceptions import Unauthenticated, Unknown

from dataclasses import replace

from config.batch_pipeline import persist_restrike_enabled
from diarizer import batch_pipeline as bp
from utils.batch_pipeline import pump as pump_module
from utils.batch_pipeline.contracts import FailedWork, WorkResult
from tests.unit.persist_lane_harness import (  # noqa: F401
    GATE,
    PerSegmentPersist,
    RecordingTimings,
    Samples,
    ScriptedPersist,
    SleepRecorder,
    WORKER_LOGGER,
    build_worker,
    exhaust_script,
    item,
    pin_full_gpu_stages,
    run_lane,
    run_two_units,
    script_for,
)

FC = 'FC-persist-transport-loss-discards-completed-gpu-results'

DOC_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'docs', 'persist-restrike-lane.md')

BUDGET_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'config', 'flag_budget.json')


@pytest.fixture(autouse=True)
def _lane_env(monkeypatch):
    pin_full_gpu_stages(monkeypatch)


def flat(s):
    return ' '.join(s.split())


NORMALIZED = flat(open(DOC_PATH).read())


def test_doc_doc_names_the_failure_class():
    assert 'Failure-Class: FC-persist-transport-loss-discards-completed-gpu-results' in NORMALIZED


def test_doc_doc_names_the_worker_module():
    assert 'diarizer/batch_pipeline.py' in NORMALIZED


def test_doc_doc_names_the_lane_method():
    assert '_persist_with_restrike' in NORMALIZED


def test_doc_doc_names_the_serial_and_io_call_sites():
    assert 'IO-executor overlap path' in NORMALIZED


def test_doc_doc_names_the_classifier():
    assert 'persist_loss_is_restrikeable' in NORMALIZED


def test_doc_doc_names_the_google_family():
    assert 'GoogleAPIError' in NORMALIZED


def test_doc_doc_names_staged_audio_custody_faults():
    assert 'StagedAudioInvalid' in NORMALIZED


def test_doc_doc_names_privacy_fences():
    assert 'BatchPrivacyBlocked' in NORMALIZED


def test_doc_doc_names_permission_refusals():
    assert 'PermissionError' in NORMALIZED


def test_doc_doc_names_the_upload_deadline():
    assert 'upload deadline' in NORMALIZED


def test_doc_doc_names_firestore_contention_wrapper():
    assert 'FirestoreContentionExhausted' in NORMALIZED


def test_doc_doc_names_the_wait_event():
    assert 'outcome=restrike_wait' in NORMALIZED


def test_doc_doc_names_the_committed_event():
    assert 'outcome=restrike_committed' in NORMALIZED


def test_doc_doc_names_the_persist_event_prefix():
    assert 'event=batch_persist' in NORMALIZED


def test_doc_doc_names_the_sensor_family_line():
    assert 'event=batch_worker_failed' in NORMALIZED


def test_doc_doc_names_the_sensor_class():
    assert 'error_class=InvalidArgument stage=persist' in NORMALIZED


def test_doc_doc_names_the_site_suffix():
    assert 'site=' in NORMALIZED


def test_doc_doc_names_error_site_field_helper():
    assert 'error_site_field' in NORMALIZED


def test_doc_doc_says_site_never_carries_messages():
    assert 'never an\nexception message' in NORMALIZED or 'never an exception message' in NORMALIZED


def test_doc_doc_names_the_projection_precedent():
    assert 'projection' in NORMALIZED


def test_doc_doc_names_the_pump_precedent():
    assert 'publication re-strike lane' in NORMALIZED


def test_doc_doc_names_the_config_module():
    assert 'config/batch_pipeline.py' in NORMALIZED


def test_doc_doc_names_the_registry_file():
    assert 'config/flag_budget.json' in NORMALIZED


def test_doc_doc_names_the_registry_owner():
    assert 'batch record lane /' in NORMALIZED


def test_doc_doc_says_persist_stays_unevidenced():
    assert 'unevidenced' in NORMALIZED


def test_doc_doc_names_transient_failure_evidence_contract():
    assert 'transient_failure_evidence' in NORMALIZED


def test_doc_doc_says_the_outbox_registers_each_attempt():
    assert 'registers every attempt before its upload' in NORMALIZED


def test_doc_doc_says_strikes_get_fresh_sealed_streams():
    assert 'fresh sealed' in NORMALIZED


def test_doc_doc_says_io_thread_never_blocks_the_event_loop():
    assert 'never blocks the\nevent loop' in NORMALIZED or 'never blocks the event loop' in NORMALIZED


def test_doc_doc_has_a_rollback_section():
    assert '## Rollback' in NORMALIZED


def test_doc_doc_rollback_names_the_kill_switch():
    assert 'BATCH_PIPELINE_PERSIST_RESTRIKE_ENABLED=false' in NORMALIZED


def test_doc_doc_rollback_says_site_survives():
    assert 'survives the kill switch' in NORMALIZED


def test_doc_doc_has_what_changed_section():
    assert '## What changed' in NORMALIZED


def test_doc_doc_has_what_did_not_change_section():
    assert '## What deliberately did not change' in NORMALIZED


def test_doc_doc_says_first_call_is_legacy_verbatim():
    assert 'byte-for-byte' in NORMALIZED


def test_doc_doc_names_the_storm_damper_sibling():
    assert 'storm damper' in NORMALIZED


def test_doc_doc_names_the_recovery_sweeps_unchanged():
    assert 'recovery\nsweeps are unchanged' in NORMALIZED or 'recovery sweeps are unchanged' in NORMALIZED


def test_doc_schedule_matches_worker_constants():
    text = open(DOC_PATH).read()
    assert '0.25s at strike 1, 0.5s at 2, 1.0s at 3' in text


def test_code_lane_method_exists_on_the_worker():
    assert hasattr(bp.PipelineWorker, '_persist_with_restrike')


def test_code_classifier_exists():
    assert callable(bp.persist_loss_is_restrikeable)


def test_code_delay_exists():
    assert callable(bp.persist_restrike_delay)


def test_code_constants_exist():
    assert bp.PERSIST_RESTRIKE_MAX_ATTEMPTS == 3
    assert bp.PERSIST_RESTRIKE_BASE_SECONDS == 0.25
    assert bp.PERSIST_RESTRIKE_MAX_SECONDS == 2.0


def test_code_gate_is_exported():
    from config.batch_pipeline import persist_restrike_enabled as gate

    assert callable(gate)


def test_worker_method_docstring_carries_the_failure_class():
    import inspect

    source = inspect.getsource(bp.PipelineWorker._persist_with_restrike)
    # The method's own trailer names this delta's class; the transport arm's
    # class stays pinned at file level (NORMALIZED) and on the classifier.
    assert 'Failure-Class: FC-persist-contention-exhaustion-discards-completed-gpu-results' in source
    assert 'Failure-Class: FC-persist-transport-loss-discards-completed-gpu-results' in NORMALIZED


def test_doc_doc_names_the_contention_arm():
    assert 'persist_loss_is_contention' in NORMALIZED


def test_doc_doc_names_the_storm_window():
    assert 'persist_restrike_storm_after' in NORMALIZED
    assert 'PERSIST_RESTRIKE_STORM_MAX_SECONDS' in NORMALIZED


def test_doc_doc_names_the_prod_evidence():
    assert 'error_class=Aborted stage=persist' in NORMALIZED


def test_code_contention_arm_matches_the_doc_family():
    from database.firestore_transaction_retry import FirestoreContentionExhausted
    from utils.batch_pipeline.audio import StagedAudioInvalid as _StagedAudioInvalid

    assert bp.persist_loss_is_contention(FirestoreContentionExhausted('budget')) is True
    assert bp.persist_loss_is_contention(Aborted('read-time abort')) is True
    expired = InvalidArgument('The referenced transaction has expired or is no longer valid.')
    assert bp.persist_loss_is_contention(expired) is True
    assert bp.persist_loss_is_contention(_StagedAudioInvalid('pinned bytes')) is False
    assert bp.persist_loss_is_contention(PermissionError('policy')) is False
    assert bp.persist_loss_is_contention(None) is False


def test_code_storm_alignment_matches_the_doc():
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    stamped = FirestoreContentionExhausted('chain', retry_after=2.5)
    assert bp.persist_restrike_storm_after(stamped) == 2.5
    assert bp.persist_restrike_storm_after(FirestoreContentionExhausted('deep', retry_after=50.0)) == (
        bp.PERSIST_RESTRIKE_STORM_MAX_SECONDS
    )
    assert bp.persist_restrike_storm_after(InvalidArgument('transport')) == 0.0
    assert bp.persist_restrike_storm_after(None) == 0.0


def test_code_storm_cap_is_the_store_damper_ceiling():
    # The doc pins the lane cap to the damper's own window ceiling.
    from database.batch_pipeline_store import FirestoreStore

    assert bp.PERSIST_RESTRIKE_STORM_MAX_SECONDS == FirestoreStore.STORM_DAMPER_CAP_SECONDS


def test_classifier_docstring_explains_the_family():
    import inspect

    source = inspect.getsource(bp.persist_loss_is_restrikeable)
    assert 'Google API transport family' in source
    # The bare transport-timeout family is documented where the verdict is made.
    assert 'TimeoutError' in source and 'socket.timeout' in source


def test_delay_docstring_documents_the_schedule():
    import inspect

    source = inspect.getsource(bp.persist_restrike_delay)
    assert '0.25s, 0.5s, 1.0s' in source and '2.0s' in source


def test_worker_module_imports_error_site_field():
    import inspect

    assert 'error_site_field' in inspect.getsource(bp)


def test_worker_module_imports_the_google_family():
    import inspect

    assert 'GoogleAPIError' in inspect.getsource(bp)
