"""The classification gate discovers new raw readers, including imported aliases."""

import importlib.util
from pathlib import Path

GUARD = Path(__file__).resolve().parents[2] / 'scripts' / 'check_conversation_readers.py'


def load():
    spec = importlib.util.spec_from_file_location('conversation_reader_guard', GUARD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_new_collection_reader_is_detected(tmp_path):
    path = tmp_path / 'backend/routers/unclassified.py'
    path.parent.mkdir(parents=True)
    path.write_text("def read(db):\n    return db.collection('conversations').stream()\n")
    assert list(load().references(tmp_path)) == [('backend/routers/unclassified.py', 'collection', 2)]
    assert load().check({}, root=tmp_path) == 1
    assert (
        load().check(
            {
                'backend/routers/unclassified.py:collection': {
                    'policy': 'conversations',
                    'reason': 'Synthetic product boundary',
                }
            },
            root=tmp_path,
        )
        == 0
    )


def test_alias_and_document_path_readers_are_detected(tmp_path):
    path = tmp_path / 'backend/utils/new_reader.py'
    path.parent.mkdir(parents=True)
    path.write_text(
        "from database.conversations import get_conversation as read_one\ndef read(db, uid, cid):\n    read_one(uid, cid)\n    return db.document(f'users/{uid}/conversations/{cid}').get()\n"
    )
    assert {operation for _, operation, _ in load().references(tmp_path)} == {'read_one', 'document_path'}


def test_attribute_collection_constant_is_detected(tmp_path):
    path = tmp_path / 'backend/database/recovery.py'
    path.parent.mkdir(parents=True)
    path.write_text('def read(db):\n    return db.collection(jobs.CONVERSATIONS_COLLECTION).stream()\n')
    assert list(load().references(tmp_path)) == [('backend/database/recovery.py', 'collection', 2)]
