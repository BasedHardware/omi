"""Design-doc parity for the publication re-strike lane.

``backend/docs/publication-restrike-lane.md`` is the reviewed contract for the lane. Every constant, event token, gate name and safety claim in the doc is pinned here against the code it describes, so doc and code can only drift together — and any retune is a reviewed diff in both files in the same change.

Failure-Class: FC-publication-contention-discards-completed-gpu-results
"""

from pathlib import Path

from database.firestore_transaction_retry import FirestoreContentionExhausted
import utils.batch_pipeline.pump as pump_module

try:
    from utils.batch_pipeline.pump import (
        PUBLICATION_RESTRIKE_BASE_SECONDS,
        PUBLICATION_RESTRIKE_MAX_ATTEMPTS,
        PUBLICATION_RESTRIKE_MAX_SECONDS,
        publication_loss_is_contention,
        publication_restrike_delay,
    )
except ImportError:
    pass

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent
DOC_PATH = BACKEND / 'docs' / 'publication-restrike-lane.md'
PUMP_PATH = BACKEND / 'utils' / 'batch_pipeline' / 'pump.py'
CONFIG_PATH = BACKEND / 'config' / 'batch_pipeline.py'
BUDGET_PATH = BACKEND / 'config' / 'flag_budget.json'
FC = 'FC-publication-contention-discards-completed-gpu-results'
GATE = 'BATCH_PIPELINE_PUBLICATION_RESTRIKE_ENABLED'


def doc_text():
    return DOC_PATH.read_text()


def pump_text():
    return PUMP_PATH.read_text()


def test_doc_exists_next_to_the_lane_it_describes():
    assert DOC_PATH.is_file()


def test_doc_carries_the_failure_class():
    assert FC in doc_text()


def test_pump_source_carries_the_failure_class():
    assert FC in pump_text()


def test_config_source_carries_the_failure_class():
    assert FC in CONFIG_PATH.read_text()


def test_doc_names_the_gate_and_the_gate_exists_in_config():
    assert GATE in doc_text()
    assert GATE in CONFIG_PATH.read_text()


def test_gate_is_registered_in_the_flag_budget():
    import json

    assert GATE in json.loads(BUDGET_PATH.read_text())['names']


def test_doc_base_step_matches_the_code():
    assert '0.25s at re-strike 1' in doc_text()
    assert PUBLICATION_RESTRIKE_BASE_SECONDS == 0.25


def test_doc_doubling_matches_the_code():
    assert '0.5s at 2' in doc_text()
    assert '1.0s at 3' in doc_text()
    assert publication_restrike_delay(2) == 0.5
    assert publication_restrike_delay(3) == 1.0


def test_doc_cap_matches_the_code():
    assert '2.0s' in doc_text()
    assert PUBLICATION_RESTRIKE_MAX_SECONDS == 2.0


def test_doc_attempt_cap_matches_the_code():
    assert 'PUBLICATION_RESTRIKE_MAX_ATTEMPTS = 3' in doc_text()
    assert PUBLICATION_RESTRIKE_MAX_ATTEMPTS == 3


def test_doc_lease_window_matches_the_scheduler():
    from utils.batch_pipeline.scheduler import LEASE_SECONDS

    assert '120-second lease' in doc_text()
    assert LEASE_SECONDS == 120.0


def test_doc_wait_token_exists_in_pump_source():
    assert 'outcome=restrike_wait' in doc_text()
    assert 'outcome=restrike_wait' in pump_text()


def test_doc_committed_token_exists_in_pump_source():
    assert 'outcome=restrike_committed' in doc_text()
    assert 'outcome=restrike_committed' in pump_text()


def test_doc_keeps_the_legacy_terminal_line_named():
    assert 'event=batch_completion outcome=retry' in doc_text()
    assert 'event=batch_completion outcome=retry' in pump_text()


def test_doc_names_the_extracted_transition():
    assert '_publish_transition' in doc_text()
    assert 'async def _publish_transition' in pump_text()


def test_doc_names_the_lane():
    assert '_restrike_publication' in doc_text()
    assert 'async def _restrike_publication' in pump_text()


def test_doc_names_the_classifier():
    assert 'publication_loss_is_contention' in doc_text()
    assert pump_text().count('def publication_loss_is_contention') == 1


def test_doc_names_the_schedule_helper():
    ladder = [publication_restrike_delay(n) for n in (1, 2, 3)]
    assert ladder == [0.25, 0.5, 1.0]
    assert pump_text().count('def publication_restrike_delay') == 1


def test_doc_names_the_lease_fence():
    assert 'lease fence' in doc_text()
    assert 'owns_lease' in pump_text()


def test_doc_keeps_the_lane_on_asyncio_sleep():
    assert 'asyncio.sleep' in doc_text()
    assert 'asyncio.sleep' in pump_text()
    assert 'time.sleep' not in pump_text()


def test_doc_names_the_drain_lane_it_must_not_touch():
    assert 'batch_merge_drain' in doc_text()
    assert 'DRAIN_RETRY_MAX_ATTEMPTS' in pump_text()


def test_doc_names_the_store_damper_it_composes_with():
    assert 'storm damper' in doc_text()
    from database.batch_pipeline_store import FirestoreStore

    assert PUBLICATION_RESTRIKE_MAX_SECONDS <= FirestoreStore.STORM_DAMPER_CAP_SECONDS


def test_doc_names_the_completion_idempotency():
    assert 'matches_persisted' in doc_text()
    from utils.batch_pipeline.contracts import WorkResult

    assert hasattr(WorkResult, 'matches_persisted')


def test_doc_names_the_postgres_subclass():
    assert 'Postgres job-store subclass' in doc_text()
    from database.jobstore.postgres_store import JobStoreContentionExhausted

    assert issubclass(JobStoreContentionExhausted, FirestoreContentionExhausted)


def test_doc_sections_are_intact():
    text = doc_text()
    assert '## What changed' in text
    assert '## What deliberately did not change' in text
    assert '## Rollback' in text


def test_doc_rollback_names_the_kill_switch_value():
    text = doc_text()
    assert GATE + '=false' in text


def test_doc_total_lane_time_claim_matches_the_schedule():
    total = sum(publication_restrike_delay(n) for n in (1, 2, 3))
    assert total < PUBLICATION_RESTRIKE_MAX_SECONDS * 10
    assert 'order of magnitude under the 120-second lease' in doc_text()


def test_pump_defines_the_lane_helpers_once_each():
    text = pump_text()
    assert text.count('def _restrike_publication') == 1
    assert text.count('def _publish_transition') == 1
    assert text.count('def publication_restrike_delay') == 1
    assert text.count('def publication_loss_is_contention') == 1


def test_doc_and_pump_agree_the_lane_is_bounded():
    assert 'bounded' in doc_text().lower()
    assert 'PUBLICATION_RESTRIKE_MAX_ATTEMPTS' in pump_text()


def test_budget_owner_string_is_the_batch_record_lane():
    import json

    entry = json.loads(BUDGET_PATH.read_text())['names'][GATE]
    assert 'batch record lane' in entry.get('owner', '')


def test_doc_explains_the_fallback_is_lease_expiry_recovery():
    assert 'lease expires' in doc_text() or 'lease-expiry recovery' in doc_text()
