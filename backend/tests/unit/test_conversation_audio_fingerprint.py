"""Fingerprint versioning and identity for the conversation playback artifact.

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


def test_source_identity_ignores_audio_file_order(monkeypatch):
    monkeypatch.setenv('PLAYBACK_ON_DEMAND_ENABLED', 'false')
    files = [dict(id='B', chunk_timestamps=[9.0]), dict(id='A', chunk_timestamps=[1.0, 2.0])]
    key = storage_mod.compute_audio_files_fingerprint(files, origin=0, source_identity=True)
    assert key == storage_mod.compute_audio_files_fingerprint(files[::-1], origin=0, source_identity=True)


def test_conversation_build_format_bump_changes_artifact_key(monkeypatch):
    files = [dict(id='A', chunk_timestamps=[1.0])]
    key = storage_mod.compute_audio_files_fingerprint(files, origin=0, source_identity=True)
    monkeypatch.setattr(storage_mod, 'CONVERSATION_BUILD_FORMAT', 'test-next-assembly-format')
    assert key != storage_mod.compute_audio_files_fingerprint(files, origin=0, source_identity=True)
