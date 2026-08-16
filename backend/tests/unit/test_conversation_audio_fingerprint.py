"""Fingerprint + staleness invalidation for the conversation playback artifact.

Runs against the REAL utils.other.storage functions (no module stubbing — the
GCS client is lazy, so importing storage is safe). Kept separate from
test_conversation_playback_artifact.py, whose module-scoped fixture stubs
utils.other.storage for the playback module load.
"""

from utils.other import storage as storage_mod


def test_fingerprint_determinism_and_order_insensitivity():
    a = [{'id': 'A', 'chunk_timestamps': [1.0, 2.0]}, {'id': 'B', 'chunk_timestamps': [9.0]}]
    b = [{'id': 'B', 'chunk_timestamps': [9.0]}, {'id': 'A', 'chunk_timestamps': [2.0, 1.0]}]
    assert storage_mod.compute_audio_files_fingerprint(a) == storage_mod.compute_audio_files_fingerprint(b)


def test_fingerprint_sensitivity_to_chunk_count_and_last_timestamp():
    a = [{'id': 'A', 'chunk_timestamps': [1.0, 2.0]}, {'id': 'B', 'chunk_timestamps': [9.0]}]

    more_chunks = [{'id': 'A', 'chunk_timestamps': [1.0, 2.0, 3.0]}, {'id': 'B', 'chunk_timestamps': [9.0]}]
    assert storage_mod.compute_audio_files_fingerprint(a) != storage_mod.compute_audio_files_fingerprint(more_chunks)

    later_last = [{'id': 'A', 'chunk_timestamps': [1.0, 2.5]}, {'id': 'B', 'chunk_timestamps': [9.0]}]
    assert storage_mod.compute_audio_files_fingerprint(a) != storage_mod.compute_audio_files_fingerprint(later_last)


def test_fingerprint_ignores_parts_without_id_or_chunks():
    a = [{'id': 'A', 'chunk_timestamps': [1.0, 2.0]}, {'id': 'B', 'chunk_timestamps': [9.0]}]
    with_junk = a + [{'id': None}, {'chunk_timestamps': []}, {'id': 'C'}]
    assert storage_mod.compute_audio_files_fingerprint(with_junk) == storage_mod.compute_audio_files_fingerprint(a)


def test_maybe_invalidate_no_stamp_is_noop(monkeypatch):
    enqueues = []
    monkeypatch.setattr(storage_mod, 'enqueue_conversation_artifact_build', lambda *a, **k: enqueues.append(a))
    files = [{'id': 'A', 'chunk_timestamps': [1.0]}]

    storage_mod.maybe_invalidate_conversation_playback('u', 'c', None, files, 'test')
    storage_mod.maybe_invalidate_conversation_playback('u', 'c', {}, files, 'test')
    storage_mod.maybe_invalidate_conversation_playback('u', 'c', {'conversation_audio': {}}, files, 'test')
    assert enqueues == []


def test_maybe_invalidate_enqueues_only_on_fingerprint_change(monkeypatch):
    enqueues = []
    monkeypatch.setattr(
        storage_mod,
        'enqueue_conversation_artifact_build',
        lambda uid, cid, fingerprint, caller: enqueues.append((uid, cid, fingerprint, caller)),
    )
    files = [{'id': 'A', 'chunk_timestamps': [1.0]}]
    current_fp = storage_mod.compute_audio_files_fingerprint(files)

    stamped = {'conversation_audio': {'audio_files_fingerprint': current_fp}}
    storage_mod.maybe_invalidate_conversation_playback('u', 'c', stamped, files, 'test')
    assert enqueues == []

    stale = {'conversation_audio': {'audio_files_fingerprint': 'fp-old'}}
    storage_mod.maybe_invalidate_conversation_playback('u', 'c', stale, files, 'test')
    assert enqueues == [('u', 'c', current_fp, 'test')]
