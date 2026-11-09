#!/usr/bin/env python3
"""Registry shape and doc round-two grid.

The flag-budget entry matches its publication-restrike sibling (owner, review date,
entry shape, count arithmetic) and the production scope scan reads the gate exactly once;
the doc grid pins the remaining factual sentences and the loop-jargon-free guarantees.

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


def flat(s):
    return ' '.join(s.split())


NORMALIZED = flat(open(DOC_PATH).read())


@pytest.fixture(autouse=True)
def _lane_env(monkeypatch):
    pin_full_gpu_stages(monkeypatch)


def test_registry_names_matches_count():
    budget = json.load(open(BUDGET_PATH))
    assert budget['count'] == len(budget['names'])


def test_registry_budget_matches_seeded_slots():
    budget = json.load(open(BUDGET_PATH))
    slots = sum(1 for entry in budget['names'].values() if 'seeded' in entry or 'replaces' in entry)
    assert slots == budget['budget']


def test_registry_both_restrike_flags_share_the_owner():
    budget = json.load(open(BUDGET_PATH))
    assert budget['names']['BATCH_PIPELINE_PERSIST_RESTRIKE_ENABLED']['owner'] == (
        budget['names']['BATCH_PIPELINE_PUBLICATION_RESTRIKE_ENABLED']['owner']
    )


def test_registry_both_restrike_flags_share_the_review_date():
    budget = json.load(open(BUDGET_PATH))
    assert budget['names']['BATCH_PIPELINE_PERSIST_RESTRIKE_ENABLED']['review_by'] == (
        budget['names']['BATCH_PIPELINE_PUBLICATION_RESTRIKE_ENABLED']['review_by']
    )


def test_registry_gate_is_not_retired():
    budget = json.load(open(BUDGET_PATH))
    assert GATE not in budget.get('retired', {})


def test_registry_entry_shape_matches_sibling_owner_entries():
    budget = json.load(open(BUDGET_PATH))
    entry = budget['names'][GATE]
    assert set(entry) == {'owner', 'review_by'}


def test_scan_reads_the_gate_exactly_once_in_scope():
    from tests.unit import test_flag_budget

    found = test_flag_budget.scan()
    assert found.get(GATE) == ['config/batch_pipeline.py']


def test_scope_covers_the_worker_module():
    from tests.unit import test_flag_budget

    assert 'diarizer/batch_pipeline*.py' in test_flag_budget.SCOPE


def test_doc_doc_never_names_asyncio_sleep():
    assert 'asyncio.sleep' not in open(DOC_PATH).read()


def test_doc_doc_never_names_monkeypatch():
    assert 'monkeypatch' not in open(DOC_PATH).read()


def test_doc_doc_never_names_the_word_candidate():
    assert 'candidate' not in open(DOC_PATH).read()


def test_doc_doc_never_names_the_word_objective():
    assert 'objective' not in open(DOC_PATH).read()


def test_doc_doc_never_names_the_word_scorer():
    assert 'scorer' not in open(DOC_PATH).read()


def test_doc_doc_never_names_the_word_tick():
    assert ' tick' not in open(DOC_PATH).read()


def test_doc_doc_never_promises_a_review_sla():
    assert 'within 24 hours' not in open(DOC_PATH).read()


def test_doc_doc_never_names_the_old_flag():
    assert 'PUBLICATION_RESTRIKE_ENABLED=false' not in open(DOC_PATH).read()


def test_doc_round2_doc_intro_names_the_worker_persist_stage():
    assert 'worker persist stage' in NORMALIZED


def test_doc_round2_doc_pins_the_burst_shape():
    assert 'tight bursts on distinct units' in NORMALIZED


def test_doc_round2_doc_pins_the_silent_window():
    assert '29-hour window' in NORMALIZED


def test_doc_round2_doc_pins_the_verbatim_first_call():
    assert 'first call is the legacy persist byte-for-byte' in NORMALIZED


def test_doc_round2_doc_pins_the_io_thread_occupancy():
    assert 'one IO' in NORMALIZED


def test_doc_round2_doc_pins_the_outbox_order():
    assert 'registers every attempt before its upload' in NORMALIZED


def test_doc_round2_doc_pins_the_generation_pinned_uri():
    assert 'generation-pinned URI' in NORMALIZED


def test_doc_round2_doc_pins_the_fresh_stream():
    assert 'fresh sealed' in NORMALIZED


def test_doc_round2_doc_names_the_sensor_family():
    assert 'InvalidArgument stage=persist' in NORMALIZED


def test_doc_round2_doc_says_fewer_lines_mean_fewer_losses():
    assert 'fewer actual discarded results' in NORMALIZED


def test_doc_round2_doc_names_the_drain_and_damper_composition():
    assert 'storm damper' in NORMALIZED


def test_doc_round2_doc_names_the_fetch_decode_trio_as_unchanged():
    assert 'typed custody trio' in NORMALIZED


def test_doc_round2_doc_says_ladder_unchanged():
    assert 'bounded retry ladder are unchanged' in NORMALIZED


def test_doc_round2_doc_rollback_says_recovery_owns_the_item():
    assert 'lease-expiry recovery owns the' in NORMALIZED


def test_doc_round2_doc_rollback_says_substring_matches_safe():
    assert 'prefix-based and unaffected' in NORMALIZED


def test_doc_round2_doc_header_titled_after_the_lane():
    assert '# Persist re-strike lane:' in NORMALIZED


def test_doc_round2_doc_names_the_two_call_sites():
    assert 'serial chain and the IO-executor overlap path' in NORMALIZED


def test_doc_round2_doc_says_the_vocabulary_stays_closed():
    assert 'vocabulary stays closed' in NORMALIZED


def test_doc_round2_doc_says_scheduling_untouched():
    assert 'lease-fenced single-document transactions' in NORMALIZED or 'publication re-strike lane' in NORMALIZED


def test_doc_round2_doc_names_the_restrike_schedule_source():
    assert 'same schedule' in NORMALIZED


def test_doc_round2_normalized_helper_covers_the_whole_file():
    NORMALIZED  # noqa: B018
    assert NORMALIZED


def test_every_new_lane_file_carries_the_failure_class():
    here = os.path.dirname(__file__)
    names = [n for n in sorted(os.listdir(here)) if n.startswith('test_persist_restrike') and n.endswith('.py')]
    assert names
    for name in names:
        assert (
            'Failure-Class: FC-persist-transport-loss-discards-completed-gpu-results'
            in open(os.path.join(here, name)).read()
        ), name
