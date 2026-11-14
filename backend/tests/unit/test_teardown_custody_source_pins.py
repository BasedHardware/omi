"""Source pins: the teardown wiring reads the family, the fault lines are gone.

The four flight-teardown exits must drive ``replay_teardown_refund`` with
their closed site rows, the raw per-site fault lines must be gone from the
pump's source, the shared helpers must live in the family module, and the
pull lane's losing-store-label helper must be the family's one authority.
These pins are pure source-text asserts, so they fail at assert level on a
parent that lacks the change.

Failure-Class: FC-flight-custody-contention-losses-booked-as-production-faults
"""

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
PUMP_SRC = (ROOT / 'utils' / 'batch_pipeline' / 'pump.py').read_text(encoding='utf-8')
SCHEDULER_SRC = (ROOT / 'utils' / 'batch_pipeline' / 'scheduler.py').read_text(encoding='utf-8')
FAMILY_SRC = (ROOT / 'utils' / 'batch_pipeline' / 'teardown_custody.py').read_text(encoding='utf-8')
STORE_SRC = (ROOT / 'database' / 'batch_pipeline_store.py').read_text(encoding='utf-8')

FC = 'FC-flight-custody-contention-losses-booked-as-production-faults'


def test_the_raw_fault_lines_left_the_pump_source():
    assert 'event=batch_flight outcome=lease_recovery exception_type' not in PUMP_SRC
    assert 'event=batch_flight outcome=lease_release exception_type' not in PUMP_SRC
    assert 'event=batch_gpu_restart outcome=lease_recovery exception_type' not in PUMP_SRC


def test_pump_imports_the_family_from_the_teardown_custody_module():
    assert 'from utils.batch_pipeline.teardown_custody import TEARDOWN_SITES, replay_teardown_refund' in PUMP_SRC


def test_each_teardown_exit_drives_its_closed_site_row():
    assert "site=TEARDOWN_SITES['stop_refund']" in PUMP_SRC
    assert "site=TEARDOWN_SITES['gpu_restart_refund']" in PUMP_SRC
    assert "site=TEARDOWN_SITES['skipped_refund']" in PUMP_SRC
    assert "site=TEARDOWN_SITES['release']" in PUMP_SRC
    assert PUMP_SRC.count('replay_teardown_refund,') == 4


def test_the_site_table_lives_in_the_family_module_not_the_pump():
    assert 'TEARDOWN_SITES = {' in FAMILY_SRC
    assert 'TEARDOWN_SITES = {' not in PUMP_SRC


def test_the_family_carries_the_failure_class():
    assert f'Failure-Class: {FC}' in FAMILY_SRC


def test_the_shared_classifier_lives_once():
    assert 'def teardown_loss_is_contention' in FAMILY_SRC
    assert 'def teardown_loss_is_contention' not in PUMP_SRC
    assert 'def teardown_loss_is_contention' not in SCHEDULER_SRC


def test_the_losing_store_label_moved_to_the_family_and_scheduler_reexports():
    assert 'def contention_operation_field' in FAMILY_SRC
    assert 'def contention_operation_field' not in SCHEDULER_SRC
    assert (
        'from utils.batch_pipeline.teardown_custody import contention_operation_field' in SCHEDULER_SRC
    ), 'the pull lane and the parity tests read the moved helper from scheduler'


def test_pump_still_reads_the_moved_label_helper_through_scheduler():
    assert 'from utils.batch_pipeline.scheduler import Scheduler, contention_operation_field' in PUMP_SRC


def test_the_family_storm_cap_is_the_store_damper_window_cap():
    assert 'TEARDOWN_REPLAY_STORM_MAX_SECONDS = 4.0' in FAMILY_SRC
    assert 'STORM_DAMPER_CAP_SECONDS = 4.0' in STORE_SRC


def test_the_family_is_storm_aligned_through_the_stamped_attribute():
    assert (
        'stamped = error.retry_after' in FAMILY_SRC
    ), 'the replay wait must consume the stamped window the scanner reads'


def test_the_replay_sleeps_on_the_measured_maximum():
    assert 'sleep(max(teardown_replay_delay(attempts), teardown_storm_after(error)))' in FAMILY_SRC


def test_the_docs_carry_the_contract():
    docs = (ROOT / 'docs' / 'lease-teardown-custody-contention.md').read_text(encoding='utf-8')
    assert f'Failure-Class: {FC}' in docs
    assert 'TEARDOWN_SITES' in docs
