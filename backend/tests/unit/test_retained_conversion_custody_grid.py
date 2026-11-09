"""Generated grid: scheduler custody for every closed worker diagnosis.

Each closed (stage, reason) pair is driven through the REAL Scheduler on the
MemoryStore and pins the durable row, the terminal log channel (the demotion
families leave the ERROR quarantine channel to faults) and the ladder economics
the anonymous cohort still pays.

Failure-Class: FC-permanent-retained-decode-failure-burns-retry-ladder
"""

import logging
import time

import pytest

from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from tests.unit.test_batch_pipeline_worker import item
from utils.batch_pipeline.scheduler import Scheduler


def test_custody_asr_recovery_decoded_duration_mismatch():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail(
        'a', lease.token, time.time(), worker_failure={'stage': 'asr_recovery', 'reason': 'decoded_duration_mismatch'}
    )
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'asr_recovery', 'reason': 'decoded_duration_mismatch'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_asr_recovery_empty_asr():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'asr_recovery', 'reason': 'empty_asr'})
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'asr_recovery', 'reason': 'empty_asr'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_asr_recovery_no_owned_words():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail(
        'a', lease.token, time.time(), worker_failure={'stage': 'asr_recovery', 'reason': 'no_owned_words'}
    )
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'asr_recovery', 'reason': 'no_owned_words'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_asr_recovery_outside_admitted_source():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail(
        'a', lease.token, time.time(), worker_failure={'stage': 'asr_recovery', 'reason': 'outside_admitted_source'}
    )
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'asr_recovery', 'reason': 'outside_admitted_source'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_asr_recovery_retained_audio_invalid():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail(
        'a', lease.token, time.time(), worker_failure={'stage': 'asr_recovery', 'reason': 'retained_audio_invalid'}
    )
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'asr_recovery', 'reason': 'retained_audio_invalid'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_asr_recovery_staged_audio_invalid():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail(
        'a', lease.token, time.time(), worker_failure={'stage': 'asr_recovery', 'reason': 'staged_audio_invalid'}
    )
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'asr_recovery', 'reason': 'staged_audio_invalid'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_asr_recovery_unsupported_language():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail(
        'a', lease.token, time.time(), worker_failure={'stage': 'asr_recovery', 'reason': 'unsupported_language'}
    )
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'asr_recovery', 'reason': 'unsupported_language'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_asr_recovery_vad_bounds():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'asr_recovery', 'reason': 'vad_bounds'})
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'asr_recovery', 'reason': 'vad_bounds'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_asr_recovery_vad_nonfinite():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail(
        'a', lease.token, time.time(), worker_failure={'stage': 'asr_recovery', 'reason': 'vad_nonfinite'}
    )
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'asr_recovery', 'reason': 'vad_nonfinite'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_asr_recovery_vad_order():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'asr_recovery', 'reason': 'vad_order'})
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'asr_recovery', 'reason': 'vad_order'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_asr_recovery_word_clock():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'asr_recovery', 'reason': 'word_clock'})
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'asr_recovery', 'reason': 'word_clock'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_asr_recovery_word_sequence():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail(
        'a', lease.token, time.time(), worker_failure={'stage': 'asr_recovery', 'reason': 'word_sequence'}
    )
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'asr_recovery', 'reason': 'word_sequence'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_asr_recovery_word_shape():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'asr_recovery', 'reason': 'word_shape'})
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'asr_recovery', 'reason': 'word_shape'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_assemble_words_decoded_duration_mismatch():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail(
        'a', lease.token, time.time(), worker_failure={'stage': 'assemble_words', 'reason': 'decoded_duration_mismatch'}
    )
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'assemble_words', 'reason': 'decoded_duration_mismatch'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_assemble_words_empty_asr():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'assemble_words', 'reason': 'empty_asr'})
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'assemble_words', 'reason': 'empty_asr'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_assemble_words_no_owned_words():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail(
        'a', lease.token, time.time(), worker_failure={'stage': 'assemble_words', 'reason': 'no_owned_words'}
    )
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'assemble_words', 'reason': 'no_owned_words'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_assemble_words_outside_admitted_source():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail(
        'a', lease.token, time.time(), worker_failure={'stage': 'assemble_words', 'reason': 'outside_admitted_source'}
    )
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'assemble_words', 'reason': 'outside_admitted_source'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_assemble_words_retained_audio_invalid():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail(
        'a', lease.token, time.time(), worker_failure={'stage': 'assemble_words', 'reason': 'retained_audio_invalid'}
    )
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'assemble_words', 'reason': 'retained_audio_invalid'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_assemble_words_staged_audio_invalid():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail(
        'a', lease.token, time.time(), worker_failure={'stage': 'assemble_words', 'reason': 'staged_audio_invalid'}
    )
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'assemble_words', 'reason': 'staged_audio_invalid'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_assemble_words_unsupported_language():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail(
        'a', lease.token, time.time(), worker_failure={'stage': 'assemble_words', 'reason': 'unsupported_language'}
    )
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'assemble_words', 'reason': 'unsupported_language'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_assemble_words_vad_bounds():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'assemble_words', 'reason': 'vad_bounds'})
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'assemble_words', 'reason': 'vad_bounds'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_assemble_words_vad_nonfinite():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail(
        'a', lease.token, time.time(), worker_failure={'stage': 'assemble_words', 'reason': 'vad_nonfinite'}
    )
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'assemble_words', 'reason': 'vad_nonfinite'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_assemble_words_vad_order():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'assemble_words', 'reason': 'vad_order'})
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'assemble_words', 'reason': 'vad_order'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_assemble_words_word_clock():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'assemble_words', 'reason': 'word_clock'})
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'assemble_words', 'reason': 'word_clock'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_assemble_words_word_sequence():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail(
        'a', lease.token, time.time(), worker_failure={'stage': 'assemble_words', 'reason': 'word_sequence'}
    )
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'assemble_words', 'reason': 'word_sequence'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_assemble_words_word_shape():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'assemble_words', 'reason': 'word_shape'})
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'assemble_words', 'reason': 'word_shape'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_fetch_decode_decoded_duration_mismatch():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail(
        'a', lease.token, time.time(), worker_failure={'stage': 'fetch_decode', 'reason': 'decoded_duration_mismatch'}
    )
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'fetch_decode', 'reason': 'decoded_duration_mismatch'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_fetch_decode_empty_asr():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'fetch_decode', 'reason': 'empty_asr'})
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'fetch_decode', 'reason': 'empty_asr'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_fetch_decode_no_owned_words():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail(
        'a', lease.token, time.time(), worker_failure={'stage': 'fetch_decode', 'reason': 'no_owned_words'}
    )
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'fetch_decode', 'reason': 'no_owned_words'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_fetch_decode_outside_admitted_source():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail(
        'a', lease.token, time.time(), worker_failure={'stage': 'fetch_decode', 'reason': 'outside_admitted_source'}
    )
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'fetch_decode', 'reason': 'outside_admitted_source'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_fetch_decode_retained_audio_invalid():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail(
        'a', lease.token, time.time(), worker_failure={'stage': 'fetch_decode', 'reason': 'retained_audio_invalid'}
    )
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'fetch_decode', 'reason': 'retained_audio_invalid'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_fetch_decode_staged_audio_invalid():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail(
        'a', lease.token, time.time(), worker_failure={'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}
    )
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_fetch_decode_unsupported_language():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail(
        'a', lease.token, time.time(), worker_failure={'stage': 'fetch_decode', 'reason': 'unsupported_language'}
    )
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'fetch_decode', 'reason': 'unsupported_language'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_fetch_decode_vad_bounds():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'fetch_decode', 'reason': 'vad_bounds'})
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'fetch_decode', 'reason': 'vad_bounds'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_fetch_decode_vad_nonfinite():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail(
        'a', lease.token, time.time(), worker_failure={'stage': 'fetch_decode', 'reason': 'vad_nonfinite'}
    )
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'fetch_decode', 'reason': 'vad_nonfinite'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_fetch_decode_vad_order():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'fetch_decode', 'reason': 'vad_order'})
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'fetch_decode', 'reason': 'vad_order'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_fetch_decode_word_clock():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'fetch_decode', 'reason': 'word_clock'})
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'fetch_decode', 'reason': 'word_clock'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_fetch_decode_word_sequence():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail(
        'a', lease.token, time.time(), worker_failure={'stage': 'fetch_decode', 'reason': 'word_sequence'}
    )
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'fetch_decode', 'reason': 'word_sequence'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_fetch_decode_word_shape():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'fetch_decode', 'reason': 'word_shape'})
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'fetch_decode', 'reason': 'word_shape'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_vad_windows_decoded_duration_mismatch():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail(
        'a', lease.token, time.time(), worker_failure={'stage': 'vad_windows', 'reason': 'decoded_duration_mismatch'}
    )
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'vad_windows', 'reason': 'decoded_duration_mismatch'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_vad_windows_empty_asr():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'vad_windows', 'reason': 'empty_asr'})
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'vad_windows', 'reason': 'empty_asr'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_vad_windows_no_owned_words():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail(
        'a', lease.token, time.time(), worker_failure={'stage': 'vad_windows', 'reason': 'no_owned_words'}
    )
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'vad_windows', 'reason': 'no_owned_words'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_vad_windows_outside_admitted_source():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail(
        'a', lease.token, time.time(), worker_failure={'stage': 'vad_windows', 'reason': 'outside_admitted_source'}
    )
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'vad_windows', 'reason': 'outside_admitted_source'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_vad_windows_retained_audio_invalid():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail(
        'a', lease.token, time.time(), worker_failure={'stage': 'vad_windows', 'reason': 'retained_audio_invalid'}
    )
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'vad_windows', 'reason': 'retained_audio_invalid'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_vad_windows_staged_audio_invalid():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail(
        'a', lease.token, time.time(), worker_failure={'stage': 'vad_windows', 'reason': 'staged_audio_invalid'}
    )
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'vad_windows', 'reason': 'staged_audio_invalid'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_vad_windows_unsupported_language():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail(
        'a', lease.token, time.time(), worker_failure={'stage': 'vad_windows', 'reason': 'unsupported_language'}
    )
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'vad_windows', 'reason': 'unsupported_language'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_vad_windows_vad_bounds():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'vad_windows', 'reason': 'vad_bounds'})
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'vad_windows', 'reason': 'vad_bounds'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_vad_windows_vad_nonfinite():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'vad_windows', 'reason': 'vad_nonfinite'})
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'vad_windows', 'reason': 'vad_nonfinite'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_vad_windows_vad_order():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'vad_windows', 'reason': 'vad_order'})
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'vad_windows', 'reason': 'vad_order'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_vad_windows_word_clock():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'vad_windows', 'reason': 'word_clock'})
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'vad_windows', 'reason': 'word_clock'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_vad_windows_word_sequence():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'vad_windows', 'reason': 'word_sequence'})
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'vad_windows', 'reason': 'word_sequence'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_vad_windows_word_shape():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'vad_windows', 'reason': 'word_shape'})
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'vad_windows', 'reason': 'word_shape'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_word_clocks_decoded_duration_mismatch():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail(
        'a', lease.token, time.time(), worker_failure={'stage': 'word_clocks', 'reason': 'decoded_duration_mismatch'}
    )
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'word_clocks', 'reason': 'decoded_duration_mismatch'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_word_clocks_empty_asr():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'word_clocks', 'reason': 'empty_asr'})
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'word_clocks', 'reason': 'empty_asr'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_word_clocks_no_owned_words():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail(
        'a', lease.token, time.time(), worker_failure={'stage': 'word_clocks', 'reason': 'no_owned_words'}
    )
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'word_clocks', 'reason': 'no_owned_words'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_word_clocks_outside_admitted_source():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail(
        'a', lease.token, time.time(), worker_failure={'stage': 'word_clocks', 'reason': 'outside_admitted_source'}
    )
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'word_clocks', 'reason': 'outside_admitted_source'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_word_clocks_retained_audio_invalid():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail(
        'a', lease.token, time.time(), worker_failure={'stage': 'word_clocks', 'reason': 'retained_audio_invalid'}
    )
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'word_clocks', 'reason': 'retained_audio_invalid'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_word_clocks_staged_audio_invalid():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail(
        'a', lease.token, time.time(), worker_failure={'stage': 'word_clocks', 'reason': 'staged_audio_invalid'}
    )
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'word_clocks', 'reason': 'staged_audio_invalid'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_word_clocks_unsupported_language():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail(
        'a', lease.token, time.time(), worker_failure={'stage': 'word_clocks', 'reason': 'unsupported_language'}
    )
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'word_clocks', 'reason': 'unsupported_language'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_word_clocks_vad_bounds():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'word_clocks', 'reason': 'vad_bounds'})
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'word_clocks', 'reason': 'vad_bounds'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_word_clocks_vad_nonfinite():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'word_clocks', 'reason': 'vad_nonfinite'})
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'word_clocks', 'reason': 'vad_nonfinite'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_word_clocks_vad_order():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'word_clocks', 'reason': 'vad_order'})
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'word_clocks', 'reason': 'vad_order'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_word_clocks_word_clock():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'word_clocks', 'reason': 'word_clock'})
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'word_clocks', 'reason': 'word_clock'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_word_clocks_word_sequence():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'word_clocks', 'reason': 'word_sequence'})
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'word_clocks', 'reason': 'word_sequence'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_custody_word_clocks_word_shape():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'word_clocks', 'reason': 'word_shape'})
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['attempt'] == 1
    assert row['worker_failure'] == {'stage': 'word_clocks', 'reason': 'word_shape'}
    assert row['recovery_state'] == 'held' and not row['merge_pending']
    assert queue.pull(time.time() + 600) == []


def test_rejects_unknown_reason_asr_recovery():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    with pytest.raises(ValueError):
        queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'asr_recovery', 'reason': 'unknown'})


def test_rejects_unknown_reason_assemble_words():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    with pytest.raises(ValueError):
        queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'assemble_words', 'reason': 'unknown'})


def test_rejects_unknown_reason_fetch_decode():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    with pytest.raises(ValueError):
        queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'fetch_decode', 'reason': 'unknown'})


def test_rejects_unknown_reason_vad_windows():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    with pytest.raises(ValueError):
        queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'vad_windows', 'reason': 'unknown'})


def test_rejects_unknown_reason_word_clocks():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    with pytest.raises(ValueError):
        queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'word_clocks', 'reason': 'unknown'})


def test_rejects_unknown_stage_decoded_duration_mismatch():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    with pytest.raises(ValueError):
        queue.fail(
            'a', lease.token, time.time(), worker_failure={'stage': 'unknown', 'reason': 'decoded_duration_mismatch'}
        )


def test_rejects_unknown_stage_empty_asr():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    with pytest.raises(ValueError):
        queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'unknown', 'reason': 'empty_asr'})


def test_rejects_unknown_stage_no_owned_words():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    with pytest.raises(ValueError):
        queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'unknown', 'reason': 'no_owned_words'})


def test_terminal_line_asr_recovery_decoded_duration_mismatch(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail(
        'a', lease.token, time.time(), worker_failure={'stage': 'asr_recovery', 'reason': 'decoded_duration_mismatch'}
    )
    assert 'event=batch_quarantined reason=worker_failed' in caplog.text
    assert any(
        record.levelno == logging.ERROR and 'batch_quarantined' in record.getMessage() for record in caplog.records
    )


def test_terminal_line_asr_recovery_empty_asr(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'asr_recovery', 'reason': 'empty_asr'})
    assert 'event=batch_quarantined reason=worker_failed' in caplog.text
    assert any(
        record.levelno == logging.ERROR and 'batch_quarantined' in record.getMessage() for record in caplog.records
    )


def test_terminal_line_asr_recovery_no_owned_words(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'asr_recovery', 'reason': 'no_owned_words'})
    assert 'event=batch_quarantined reason=worker_failed' in caplog.text
    assert any(
        record.levelno == logging.ERROR and 'batch_quarantined' in record.getMessage() for record in caplog.records
    )


def test_terminal_line_asr_recovery_outside_admitted_source(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail(
        'a', lease.token, time.time(), worker_failure={'stage': 'asr_recovery', 'reason': 'outside_admitted_source'}
    )
    assert 'event=batch_quarantined reason=worker_failed' in caplog.text
    assert any(
        record.levelno == logging.ERROR and 'batch_quarantined' in record.getMessage() for record in caplog.records
    )


def test_terminal_line_asr_recovery_retained_audio_invalid(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail(
        'a', lease.token, time.time(), worker_failure={'stage': 'asr_recovery', 'reason': 'retained_audio_invalid'}
    )
    assert 'event=batch_quarantined reason=worker_failed' in caplog.text
    assert any(
        record.levelno == logging.ERROR and 'batch_quarantined' in record.getMessage() for record in caplog.records
    )


def test_terminal_line_asr_recovery_staged_audio_invalid(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail(
        'a', lease.token, time.time(), worker_failure={'stage': 'asr_recovery', 'reason': 'staged_audio_invalid'}
    )
    assert 'event=batch_quarantined reason=worker_failed' in caplog.text
    assert any(
        record.levelno == logging.ERROR and 'batch_quarantined' in record.getMessage() for record in caplog.records
    )


def test_terminal_line_asr_recovery_unsupported_language(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail(
        'a', lease.token, time.time(), worker_failure={'stage': 'asr_recovery', 'reason': 'unsupported_language'}
    )
    assert 'event=batch_language_guard outcome=held_for_redrive' in caplog.text
    assert 'event=batch_quarantined' not in caplog.text


def test_terminal_line_asr_recovery_vad_bounds(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'asr_recovery', 'reason': 'vad_bounds'})
    assert 'event=batch_validation_disposition outcome=held_for_disposition' in caplog.text
    assert 'event=batch_quarantined' not in caplog.text


def test_terminal_line_asr_recovery_vad_nonfinite(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'asr_recovery', 'reason': 'vad_nonfinite'})
    assert 'event=batch_validation_disposition outcome=held_for_disposition' in caplog.text
    assert 'event=batch_quarantined' not in caplog.text


def test_terminal_line_asr_recovery_vad_order(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'asr_recovery', 'reason': 'vad_order'})
    assert 'event=batch_validation_disposition outcome=held_for_disposition' in caplog.text
    assert 'event=batch_quarantined' not in caplog.text


def test_terminal_line_asr_recovery_word_clock(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'asr_recovery', 'reason': 'word_clock'})
    assert 'event=batch_validation_disposition outcome=held_for_disposition' in caplog.text
    assert 'event=batch_quarantined' not in caplog.text


def test_terminal_line_asr_recovery_word_sequence(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'asr_recovery', 'reason': 'word_sequence'})
    assert 'event=batch_validation_disposition outcome=held_for_disposition' in caplog.text
    assert 'event=batch_quarantined' not in caplog.text


def test_terminal_line_asr_recovery_word_shape(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'asr_recovery', 'reason': 'word_shape'})
    assert 'event=batch_validation_disposition outcome=held_for_disposition' in caplog.text
    assert 'event=batch_quarantined' not in caplog.text


def test_terminal_line_assemble_words_decoded_duration_mismatch(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail(
        'a', lease.token, time.time(), worker_failure={'stage': 'assemble_words', 'reason': 'decoded_duration_mismatch'}
    )
    assert 'event=batch_quarantined reason=worker_failed' in caplog.text
    assert any(
        record.levelno == logging.ERROR and 'batch_quarantined' in record.getMessage() for record in caplog.records
    )


def test_terminal_line_assemble_words_empty_asr(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'assemble_words', 'reason': 'empty_asr'})
    assert 'event=batch_empty_ladder outcome=held_for_recovery' in caplog.text
    assert 'event=batch_quarantined' not in caplog.text


def test_terminal_line_assemble_words_no_owned_words(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'assemble_words', 'reason': 'no_owned_words'})
    assert 'event=batch_empty_ladder outcome=held_for_recovery' in caplog.text
    assert 'event=batch_quarantined' not in caplog.text


def test_terminal_line_assemble_words_outside_admitted_source(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail(
        'a', lease.token, time.time(), worker_failure={'stage': 'assemble_words', 'reason': 'outside_admitted_source'}
    )
    assert 'event=batch_quarantined reason=worker_failed' in caplog.text
    assert any(
        record.levelno == logging.ERROR and 'batch_quarantined' in record.getMessage() for record in caplog.records
    )


def test_terminal_line_assemble_words_retained_audio_invalid(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail(
        'a', lease.token, time.time(), worker_failure={'stage': 'assemble_words', 'reason': 'retained_audio_invalid'}
    )
    assert 'event=batch_quarantined reason=worker_failed' in caplog.text
    assert any(
        record.levelno == logging.ERROR and 'batch_quarantined' in record.getMessage() for record in caplog.records
    )


def test_terminal_line_assemble_words_staged_audio_invalid(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail(
        'a', lease.token, time.time(), worker_failure={'stage': 'assemble_words', 'reason': 'staged_audio_invalid'}
    )
    assert 'event=batch_quarantined reason=worker_failed' in caplog.text
    assert any(
        record.levelno == logging.ERROR and 'batch_quarantined' in record.getMessage() for record in caplog.records
    )


def test_terminal_line_assemble_words_unsupported_language(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail(
        'a', lease.token, time.time(), worker_failure={'stage': 'assemble_words', 'reason': 'unsupported_language'}
    )
    assert 'event=batch_language_guard outcome=held_for_redrive' in caplog.text
    assert 'event=batch_quarantined' not in caplog.text


def test_terminal_line_assemble_words_vad_bounds(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'assemble_words', 'reason': 'vad_bounds'})
    assert 'event=batch_validation_disposition outcome=held_for_disposition' in caplog.text
    assert 'event=batch_quarantined' not in caplog.text


def test_terminal_line_assemble_words_vad_nonfinite(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'assemble_words', 'reason': 'vad_nonfinite'})
    assert 'event=batch_validation_disposition outcome=held_for_disposition' in caplog.text
    assert 'event=batch_quarantined' not in caplog.text


def test_terminal_line_assemble_words_vad_order(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'assemble_words', 'reason': 'vad_order'})
    assert 'event=batch_validation_disposition outcome=held_for_disposition' in caplog.text
    assert 'event=batch_quarantined' not in caplog.text


def test_terminal_line_assemble_words_word_clock(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'assemble_words', 'reason': 'word_clock'})
    assert 'event=batch_validation_disposition outcome=held_for_disposition' in caplog.text
    assert 'event=batch_quarantined' not in caplog.text


def test_terminal_line_assemble_words_word_sequence(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'assemble_words', 'reason': 'word_sequence'})
    assert 'event=batch_validation_disposition outcome=held_for_disposition' in caplog.text
    assert 'event=batch_quarantined' not in caplog.text


def test_terminal_line_assemble_words_word_shape(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'assemble_words', 'reason': 'word_shape'})
    assert 'event=batch_validation_disposition outcome=held_for_disposition' in caplog.text
    assert 'event=batch_quarantined' not in caplog.text


def test_terminal_line_fetch_decode_decoded_duration_mismatch(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail(
        'a', lease.token, time.time(), worker_failure={'stage': 'fetch_decode', 'reason': 'decoded_duration_mismatch'}
    )
    assert 'event=batch_validation_disposition outcome=held_for_disposition' in caplog.text
    assert 'event=batch_quarantined' not in caplog.text


def test_terminal_line_fetch_decode_empty_asr(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'fetch_decode', 'reason': 'empty_asr'})
    assert 'event=batch_quarantined reason=worker_failed' in caplog.text
    assert any(
        record.levelno == logging.ERROR and 'batch_quarantined' in record.getMessage() for record in caplog.records
    )


def test_terminal_line_fetch_decode_no_owned_words(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'fetch_decode', 'reason': 'no_owned_words'})
    assert 'event=batch_quarantined reason=worker_failed' in caplog.text
    assert any(
        record.levelno == logging.ERROR and 'batch_quarantined' in record.getMessage() for record in caplog.records
    )


def test_terminal_line_fetch_decode_outside_admitted_source(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail(
        'a', lease.token, time.time(), worker_failure={'stage': 'fetch_decode', 'reason': 'outside_admitted_source'}
    )
    assert 'event=batch_quarantined reason=worker_failed' in caplog.text
    assert any(
        record.levelno == logging.ERROR and 'batch_quarantined' in record.getMessage() for record in caplog.records
    )


def test_terminal_line_fetch_decode_retained_audio_invalid(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail(
        'a', lease.token, time.time(), worker_failure={'stage': 'fetch_decode', 'reason': 'retained_audio_invalid'}
    )
    assert 'event=batch_validation_disposition outcome=held_for_disposition' in caplog.text
    assert 'event=batch_quarantined' not in caplog.text


def test_terminal_line_fetch_decode_staged_audio_invalid(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail(
        'a', lease.token, time.time(), worker_failure={'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}
    )
    assert 'event=batch_validation_disposition outcome=held_for_disposition' in caplog.text
    assert 'event=batch_quarantined' not in caplog.text


def test_terminal_line_fetch_decode_unsupported_language(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail(
        'a', lease.token, time.time(), worker_failure={'stage': 'fetch_decode', 'reason': 'unsupported_language'}
    )
    assert 'event=batch_language_guard outcome=held_for_redrive' in caplog.text
    assert 'event=batch_quarantined' not in caplog.text


def test_terminal_line_fetch_decode_vad_bounds(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'fetch_decode', 'reason': 'vad_bounds'})
    assert 'event=batch_validation_disposition outcome=held_for_disposition' in caplog.text
    assert 'event=batch_quarantined' not in caplog.text


def test_terminal_line_fetch_decode_vad_nonfinite(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'fetch_decode', 'reason': 'vad_nonfinite'})
    assert 'event=batch_validation_disposition outcome=held_for_disposition' in caplog.text
    assert 'event=batch_quarantined' not in caplog.text


def test_terminal_line_fetch_decode_vad_order(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'fetch_decode', 'reason': 'vad_order'})
    assert 'event=batch_validation_disposition outcome=held_for_disposition' in caplog.text
    assert 'event=batch_quarantined' not in caplog.text


def test_terminal_line_fetch_decode_word_clock(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'fetch_decode', 'reason': 'word_clock'})
    assert 'event=batch_validation_disposition outcome=held_for_disposition' in caplog.text
    assert 'event=batch_quarantined' not in caplog.text


def test_terminal_line_fetch_decode_word_sequence(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'fetch_decode', 'reason': 'word_sequence'})
    assert 'event=batch_validation_disposition outcome=held_for_disposition' in caplog.text
    assert 'event=batch_quarantined' not in caplog.text


def test_terminal_line_fetch_decode_word_shape(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'fetch_decode', 'reason': 'word_shape'})
    assert 'event=batch_validation_disposition outcome=held_for_disposition' in caplog.text
    assert 'event=batch_quarantined' not in caplog.text


def test_terminal_line_vad_windows_decoded_duration_mismatch(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail(
        'a', lease.token, time.time(), worker_failure={'stage': 'vad_windows', 'reason': 'decoded_duration_mismatch'}
    )
    assert 'event=batch_quarantined reason=worker_failed' in caplog.text
    assert any(
        record.levelno == logging.ERROR and 'batch_quarantined' in record.getMessage() for record in caplog.records
    )


def test_terminal_line_vad_windows_empty_asr(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'vad_windows', 'reason': 'empty_asr'})
    assert 'event=batch_quarantined reason=worker_failed' in caplog.text
    assert any(
        record.levelno == logging.ERROR and 'batch_quarantined' in record.getMessage() for record in caplog.records
    )


def test_terminal_line_vad_windows_no_owned_words(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'vad_windows', 'reason': 'no_owned_words'})
    assert 'event=batch_quarantined reason=worker_failed' in caplog.text
    assert any(
        record.levelno == logging.ERROR and 'batch_quarantined' in record.getMessage() for record in caplog.records
    )


def test_terminal_line_vad_windows_outside_admitted_source(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail(
        'a', lease.token, time.time(), worker_failure={'stage': 'vad_windows', 'reason': 'outside_admitted_source'}
    )
    assert 'event=batch_quarantined reason=worker_failed' in caplog.text
    assert any(
        record.levelno == logging.ERROR and 'batch_quarantined' in record.getMessage() for record in caplog.records
    )


def test_terminal_line_vad_windows_retained_audio_invalid(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail(
        'a', lease.token, time.time(), worker_failure={'stage': 'vad_windows', 'reason': 'retained_audio_invalid'}
    )
    assert 'event=batch_quarantined reason=worker_failed' in caplog.text
    assert any(
        record.levelno == logging.ERROR and 'batch_quarantined' in record.getMessage() for record in caplog.records
    )


def test_terminal_line_vad_windows_staged_audio_invalid(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'vad_windows', 'reason': 'staged_audio_invalid'})
    assert 'event=batch_quarantined reason=worker_failed' in caplog.text
    assert any(
        record.levelno == logging.ERROR and 'batch_quarantined' in record.getMessage() for record in caplog.records
    )


def test_terminal_line_vad_windows_unsupported_language(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'vad_windows', 'reason': 'unsupported_language'})
    assert 'event=batch_language_guard outcome=held_for_redrive' in caplog.text
    assert 'event=batch_quarantined' not in caplog.text


def test_terminal_line_vad_windows_vad_bounds(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'vad_windows', 'reason': 'vad_bounds'})
    assert 'event=batch_validation_disposition outcome=held_for_disposition' in caplog.text
    assert 'event=batch_quarantined' not in caplog.text


def test_terminal_line_vad_windows_vad_nonfinite(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'vad_windows', 'reason': 'vad_nonfinite'})
    assert 'event=batch_validation_disposition outcome=held_for_disposition' in caplog.text
    assert 'event=batch_quarantined' not in caplog.text


def test_terminal_line_vad_windows_vad_order(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'vad_windows', 'reason': 'vad_order'})
    assert 'event=batch_validation_disposition outcome=held_for_disposition' in caplog.text
    assert 'event=batch_quarantined' not in caplog.text


def test_terminal_line_vad_windows_word_clock(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'vad_windows', 'reason': 'word_clock'})
    assert 'event=batch_validation_disposition outcome=held_for_disposition' in caplog.text
    assert 'event=batch_quarantined' not in caplog.text


def test_terminal_line_vad_windows_word_sequence(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'vad_windows', 'reason': 'word_sequence'})
    assert 'event=batch_validation_disposition outcome=held_for_disposition' in caplog.text
    assert 'event=batch_quarantined' not in caplog.text


def test_terminal_line_vad_windows_word_shape(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'vad_windows', 'reason': 'word_shape'})
    assert 'event=batch_validation_disposition outcome=held_for_disposition' in caplog.text
    assert 'event=batch_quarantined' not in caplog.text


def test_terminal_line_word_clocks_decoded_duration_mismatch(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail(
        'a', lease.token, time.time(), worker_failure={'stage': 'word_clocks', 'reason': 'decoded_duration_mismatch'}
    )
    assert 'event=batch_quarantined reason=worker_failed' in caplog.text
    assert any(
        record.levelno == logging.ERROR and 'batch_quarantined' in record.getMessage() for record in caplog.records
    )


def test_terminal_line_word_clocks_empty_asr(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'word_clocks', 'reason': 'empty_asr'})
    assert 'event=batch_quarantined reason=worker_failed' in caplog.text
    assert any(
        record.levelno == logging.ERROR and 'batch_quarantined' in record.getMessage() for record in caplog.records
    )


def test_terminal_line_word_clocks_no_owned_words(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'word_clocks', 'reason': 'no_owned_words'})
    assert 'event=batch_quarantined reason=worker_failed' in caplog.text
    assert any(
        record.levelno == logging.ERROR and 'batch_quarantined' in record.getMessage() for record in caplog.records
    )


def test_terminal_line_word_clocks_outside_admitted_source(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail(
        'a', lease.token, time.time(), worker_failure={'stage': 'word_clocks', 'reason': 'outside_admitted_source'}
    )
    assert 'event=batch_quarantined reason=worker_failed' in caplog.text
    assert any(
        record.levelno == logging.ERROR and 'batch_quarantined' in record.getMessage() for record in caplog.records
    )


def test_terminal_line_word_clocks_retained_audio_invalid(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail(
        'a', lease.token, time.time(), worker_failure={'stage': 'word_clocks', 'reason': 'retained_audio_invalid'}
    )
    assert 'event=batch_quarantined reason=worker_failed' in caplog.text
    assert any(
        record.levelno == logging.ERROR and 'batch_quarantined' in record.getMessage() for record in caplog.records
    )


def test_terminal_line_word_clocks_staged_audio_invalid(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'word_clocks', 'reason': 'staged_audio_invalid'})
    assert 'event=batch_quarantined reason=worker_failed' in caplog.text
    assert any(
        record.levelno == logging.ERROR and 'batch_quarantined' in record.getMessage() for record in caplog.records
    )


def test_terminal_line_word_clocks_unsupported_language(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'word_clocks', 'reason': 'unsupported_language'})
    assert 'event=batch_language_guard outcome=held_for_redrive' in caplog.text
    assert 'event=batch_quarantined' not in caplog.text


def test_terminal_line_word_clocks_vad_bounds(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'word_clocks', 'reason': 'vad_bounds'})
    assert 'event=batch_validation_disposition outcome=held_for_disposition' in caplog.text
    assert 'event=batch_quarantined' not in caplog.text


def test_terminal_line_word_clocks_vad_nonfinite(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'word_clocks', 'reason': 'vad_nonfinite'})
    assert 'event=batch_validation_disposition outcome=held_for_disposition' in caplog.text
    assert 'event=batch_quarantined' not in caplog.text


def test_terminal_line_word_clocks_vad_order(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'word_clocks', 'reason': 'vad_order'})
    assert 'event=batch_validation_disposition outcome=held_for_disposition' in caplog.text
    assert 'event=batch_quarantined' not in caplog.text


def test_terminal_line_word_clocks_word_clock(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'word_clocks', 'reason': 'word_clock'})
    assert 'event=batch_validation_disposition outcome=held_for_disposition' in caplog.text
    assert 'event=batch_quarantined' not in caplog.text


def test_terminal_line_word_clocks_word_sequence(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'word_clocks', 'reason': 'word_sequence'})
    assert 'event=batch_validation_disposition outcome=held_for_disposition' in caplog.text
    assert 'event=batch_quarantined' not in caplog.text


def test_terminal_line_word_clocks_word_shape(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'word_clocks', 'reason': 'word_shape'})
    assert 'event=batch_validation_disposition outcome=held_for_disposition' in caplog.text
    assert 'event=batch_quarantined' not in caplog.text


def test_flagged_keeps_error_when_disposition_off_vad_windows_vad_nonfinite(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'vad_windows', 'reason': 'vad_nonfinite'})
    assert 'event=batch_quarantined reason=worker_failed' in caplog.text
    assert 'event=batch_validation_disposition' not in caplog.text


def test_flagged_keeps_error_when_disposition_off_word_clocks_vad_nonfinite(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'word_clocks', 'reason': 'vad_nonfinite'})
    assert 'event=batch_quarantined reason=worker_failed' in caplog.text
    assert 'event=batch_validation_disposition' not in caplog.text


def test_flagged_keeps_error_when_disposition_off_vad_windows_vad_order(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'vad_windows', 'reason': 'vad_order'})
    assert 'event=batch_quarantined reason=worker_failed' in caplog.text
    assert 'event=batch_validation_disposition' not in caplog.text


def test_flagged_keeps_error_when_disposition_off_word_clocks_vad_order(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'word_clocks', 'reason': 'vad_order'})
    assert 'event=batch_quarantined reason=worker_failed' in caplog.text
    assert 'event=batch_validation_disposition' not in caplog.text


def test_flagged_keeps_error_when_disposition_off_vad_windows_vad_bounds(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'vad_windows', 'reason': 'vad_bounds'})
    assert 'event=batch_quarantined reason=worker_failed' in caplog.text
    assert 'event=batch_validation_disposition' not in caplog.text


def test_flagged_keeps_error_when_disposition_off_word_clocks_vad_bounds(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'word_clocks', 'reason': 'vad_bounds'})
    assert 'event=batch_quarantined reason=worker_failed' in caplog.text
    assert 'event=batch_validation_disposition' not in caplog.text


def test_flagged_keeps_error_when_disposition_off_vad_windows_word_shape(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'vad_windows', 'reason': 'word_shape'})
    assert 'event=batch_quarantined reason=worker_failed' in caplog.text
    assert 'event=batch_validation_disposition' not in caplog.text


def test_flagged_keeps_error_when_disposition_off_word_clocks_word_shape(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'word_clocks', 'reason': 'word_shape'})
    assert 'event=batch_quarantined reason=worker_failed' in caplog.text
    assert 'event=batch_validation_disposition' not in caplog.text


def test_flagged_keeps_error_when_disposition_off_vad_windows_word_clock(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'vad_windows', 'reason': 'word_clock'})
    assert 'event=batch_quarantined reason=worker_failed' in caplog.text
    assert 'event=batch_validation_disposition' not in caplog.text


def test_flagged_keeps_error_when_disposition_off_word_clocks_word_clock(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'word_clocks', 'reason': 'word_clock'})
    assert 'event=batch_quarantined reason=worker_failed' in caplog.text
    assert 'event=batch_validation_disposition' not in caplog.text


def test_flagged_keeps_error_when_disposition_off_vad_windows_word_sequence(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'vad_windows', 'reason': 'word_sequence'})
    assert 'event=batch_quarantined reason=worker_failed' in caplog.text
    assert 'event=batch_validation_disposition' not in caplog.text


def test_flagged_keeps_error_when_disposition_off_word_clocks_word_sequence(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'word_clocks', 'reason': 'word_sequence'})
    assert 'event=batch_quarantined reason=worker_failed' in caplog.text
    assert 'event=batch_validation_disposition' not in caplog.text


def test_awaiting_fenced_recovery_warning_disposition(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail(
        'a', lease.token, time.time(), worker_failure={'stage': 'fetch_decode', 'reason': 'retained_audio_invalid'}
    )
    assert 'event=batch_recovery outcome=held reason=awaiting_fenced_recovery' in caplog.text


def test_awaiting_fenced_recovery_warning_empty_ladder(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'assemble_words', 'reason': 'empty_asr'})
    assert 'event=batch_recovery outcome=held reason=awaiting_fenced_recovery' in caplog.text


def test_awaiting_fenced_recovery_warning_language_guard(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'vad_windows', 'reason': 'unsupported_language'})
    assert 'event=batch_recovery outcome=held reason=awaiting_fenced_recovery' in caplog.text


def test_awaiting_fenced_recovery_warning_fault_family(monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    caplog.set_level(logging.INFO)
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail('a', lease.token, time.time(), worker_failure={'stage': 'word_clocks', 'reason': 'word_shape'})
    assert 'event=batch_recovery outcome=held reason=awaiting_fenced_recovery' in caplog.text


def test_ladder_first_defers_with_future_available_at():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    assert queue.fail('a', lease.token, time.time()) is True
    row = store.rows['jobs', 'a']
    assert row['state'] == 'retry' and row['attempt'] == 1
    assert row['available_at'] > time.time()
    assert 'worker_failure' not in row


def test_ladder_quarantines_at_the_attempt_cap():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    now = time.time()
    pulls = 0
    while pulls < 8:
        leases = queue.pull(now)
        if not leases:
            now += 30
            queue.recover(now)
            continue
        pulls += 1
        assert queue.fail('a', leases[0].token, now) is True
        if store.rows['jobs', 'a']['state'] == 'quarantined':
            break
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined'
    assert pulls == 5


def test_ladder_held_rows_never_reenter_the_pull_ring():
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail(
        'a', lease.token, time.time(), worker_failure={'stage': 'fetch_decode', 'reason': 'retained_audio_invalid'}
    )
    assert queue.recover(time.time() + 3600) == 0
    assert queue.pull(time.time() + 3600) == []


def test_ladder_metrics_record_quarantine_and_recovery_held():
    class FakeMetrics:
        def __init__(self):
            self.recorded = []

        def record(self, name):
            self.recorded.append(name)

    store = MemoryStore()
    metrics = FakeMetrics()
    queue = Scheduler(store, metrics=metrics)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    queue.fail(
        'a', lease.token, time.time(), worker_failure={'stage': 'fetch_decode', 'reason': 'retained_audio_invalid'}
    )
    assert metrics.recorded == ['quarantined', 'recovery_held']


async def test_pump_publishes_terminal_diagnosis_to_fail(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    from utils.batch_pipeline.contracts import ValidationFailureWork
    from utils.batch_pipeline.pump import Pump

    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    fail = __import__("unittest.mock", fromlist=["Mock"]).Mock(wraps=queue.fail)
    __import__("unittest.mock", fromlist=["patch"]).patch.object(queue, "fail", fail).__enter__()
    result = ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')
    assert await Pump(queue, None)._publish(lease, {"a": result}, set())
    assert fail.call_args.kwargs['worker_failure'] == {'stage': 'fetch_decode', 'reason': 'retained_audio_invalid'}
    row = store.rows['jobs', 'a']
    assert row['state'] == 'quarantined' and row['recovery_state'] == 'held'


async def test_pump_publishes_anonymous_fault_to_the_retry_ladder(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    from utils.batch_pipeline.contracts import FailedWork
    from utils.batch_pipeline.pump import Pump

    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    lease = queue.pull(time.time())[0]
    result = FailedWork('a', None, None)
    assert await Pump(queue, None)._publish(lease, {"a": result}, set())
    row = store.rows['jobs', 'a']
    assert row['state'] == 'retry' and 'worker_failure' not in row
