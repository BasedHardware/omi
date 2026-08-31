"""Regression test: create_audio_files_from_chunks must be able to call its chunk listing.

Production loop sensor (pusher, 30-min windows) recorded ~127 occurrences of:

    ERROR:routers.pusher:Error updating audio files: name 'list_audio_chunks'
    is not defined <uid> <conversation_id>

plus the same NameError swallowed by three other callers (process_conversation,
merge_conversations, sync pipeline finalization). The private-cloud-sync import
in database/conversations.py was accidentally replaced by the list-budget import
in #11858 instead of being added beside it, so the module-level name
``list_audio_chunks`` no longer existed while ``create_audio_files_from_chunks``
still called it at module scope. Every invocation raised NameError before doing
any work: no AudioFile records were created, no audio_files field was ever
persisted on any conversation, and each caller's broad except merely logged.

The existing suite never noticed because every test of the four callers mocks
``conversations_db.create_audio_files_from_chunks`` wholesale — the function
body itself had zero behavioral coverage, and the repo has no undefined-name
linter in the test path.

These tests call the real function and only stub the production seam the
function itself uses (``utils.other.storage._get_storage_client``), so the
module-level name binding is exercised for real:

1. with the import present, chunk listing flows through
   ``utils.other.storage.list_audio_chunks`` — real filename parsing, gap
   grouping, and AudioFile construction — and returns the records the callers
   persist;
2. the 90s gap rule (adjacent chunks split into separate AudioFiles) still
   holds, proving the function's own contract, not just name resolution;
3. an empty listing still returns [] (the documented no-chunks path).

Failure-Class: new — the violated contract is the module's own import surface:
a function must be able to resolve every name it calls. The regression was an
edit-time import replacement (#11858), invisible to a suite that mocks this
function at every call site.
"""

from types import SimpleNamespace
from unittest.mock import patch

import database.conversations as conversations_db
from utils.other import storage as storage_mod


def _fake_client(blobs_by_prefix):
    """GCS client double: bucket().list_blobs(prefix=...) serves canned blobs."""

    class _Bucket:
        def list_blobs(self, prefix=None):
            return blobs_by_prefix.get(prefix, [])

    class _Client:
        def bucket(self, name):
            return _Bucket()

    return _Client()


def _blob(path, size):
    # list_audio_chunks reads .name and .size off each blob
    return SimpleNamespace(name=path, size=size)


class TestCreateAudioFilesFromChunks:
    def test_chunk_listing_resolves_and_builds_audio_files(self):
        """Before the fix this raised NameError("list_audio_chunks is not defined")."""
        blobs = {
            'chunks/uid-a/conv-1/': [
                _blob('chunks/uid-a/conv-1/1000.000.opus', 32000),
                _blob('chunks/uid-a/conv-1/1010.000.opus', 32000),
            ],
        }
        with patch.object(storage_mod, '_get_storage_client', return_value=_fake_client(blobs)):
            files = conversations_db.create_audio_files_from_chunks('uid-a', 'conv-1')

        assert len(files) == 1
        audio_file = files[0]
        assert audio_file.uid == 'uid-a'
        assert audio_file.conversation_id == 'conv-1'
        assert audio_file.chunk_timestamps == [1000.0, 1010.0]
        # duration spans first chunk start to last chunk start plus its estimated
        # length from blob size (PCM16 mono 16kHz: 32000 bytes => 1.0s)
        assert audio_file.duration == 11.0
        assert audio_file.started_at is not None

    def test_gap_rule_splits_groups(self):
        """A >90s gap between adjacent chunks must produce two AudioFiles."""
        blobs = {
            'chunks/uid-a/conv-2/': [
                _blob('chunks/uid-a/conv-2/2000.000.opus', 32000),
                _blob('chunks/uid-a/conv-2/2100.000.opus', 32000),
            ],
        }
        with patch.object(storage_mod, '_get_storage_client', return_value=_fake_client(blobs)):
            files = conversations_db.create_audio_files_from_chunks('uid-a', 'conv-2')

        assert len(files) == 2
        assert files[0].chunk_timestamps == [2000.0]
        assert files[1].chunk_timestamps == [2100.0]
        assert files[0].chunk_timestamps[0] < files[1].chunk_timestamps[0]

    def test_no_chunks_returns_empty_list(self):
        with patch.object(storage_mod, '_get_storage_client', return_value=_fake_client({})):
            assert conversations_db.create_audio_files_from_chunks('uid-a', 'conv-3') == []

    def test_batch_blob_timestamps_use_range_start(self):
        """The pusher flush (the site logging the prod NameError) uploads batch
        blobs named '<first>-<last>.batch.bin'. Listing must attribute the batch
        to the range's first timestamp so grouping matches live flush order."""
        blobs = {
            'chunks/uid-a/conv-4/': [
                _blob('chunks/uid-a/conv-4/3000.000-3010.000.batch.bin', 320000),
                _blob('chunks/uid-a/conv-4/3020.000-3030.000.batch.enc', 320000),
            ],
        }
        with patch.object(storage_mod, '_get_storage_client', return_value=_fake_client(blobs)):
            files = conversations_db.create_audio_files_from_chunks('uid-a', 'conv-4')

        assert len(files) == 1
        assert files[0].chunk_timestamps == [3000.0, 3020.0]

    def test_corrupt_timestamp_blob_is_skipped_not_fatal(self):
        """A blob whose name is not parseable as a timestamp must be skipped,
        not break the listing for the whole conversation."""
        blobs = {
            'chunks/uid-a/conv-5/': [
                _blob('chunks/uid-a/conv-5/corrupt.opus', 32000),
                _blob('chunks/uid-a/conv-5/4000.000.opus', 32000),
            ],
        }
        with patch.object(storage_mod, '_get_storage_client', return_value=_fake_client(blobs)):
            files = conversations_db.create_audio_files_from_chunks('uid-a', 'conv-5')

        assert len(files) == 1
        assert files[0].chunk_timestamps == [4000.0]

    def test_non_audio_blob_in_prefix_is_ignored(self):
        """Only private-cloud audio extensions count; anything else sharing the
        prefix must not produce chunk records."""
        blobs = {
            'chunks/uid-a/conv-6/': [
                _blob('chunks/uid-a/conv-6/5000.000.opus', 32000),
                _blob('chunks/uid-a/conv-6/metadata.json', 100),
                _blob('chunks/uid-a/conv-6/notes.txt', 100),
            ],
        }
        with patch.object(storage_mod, '_get_storage_client', return_value=_fake_client(blobs)):
            files = conversations_db.create_audio_files_from_chunks('uid-a', 'conv-6')

        assert len(files) == 1
        assert files[0].chunk_timestamps == [5000.0]


class TestModuleImportSurface:
    def test_list_audio_chunks_is_module_level_name(self):
        """The production call site resolves the name at call time from module globals.

        This pins the binding the NameError removed — cheap, explicit, and
        stable against future import-block reorganization.
        """
        assert callable(conversations_db.list_audio_chunks)
        assert conversations_db.list_audio_chunks is storage_mod.list_audio_chunks
