"""save_x_posts and mark_memory_extraction_completed built one Firestore WriteBatch
per call and committed it with no chunking, so a page of more than 500 posts crashed
the whole sync with "A maximum of 500 operations are allowed on a commit" instead of
storing the page. Neither writer validated uid, so a blank id reached Firestore as an
empty document id, and a non-dict entry in a connector page raised mid-write and
aborted the batch. The readers crashed on the same invalid uid instead of returning
safe default empties ([] / 0 / None).
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import database.x_posts as x_posts_db

UID = "user-x-posts"


class _RecordingBatch:
    def __init__(self, commits, writes):
        self._commits = commits
        self._writes = writes

    def set(self, ref, data, merge=False):
        self._writes.append(ref.id)

    def commit(self):
        self._commits.append(len(self._writes))


def _install_fake_db(monkeypatch):
    commits = []
    writes = []

    posts_collection = MagicMock()
    posts_collection.document.side_effect = lambda doc_id: SimpleNamespace(id=doc_id)

    user_doc = MagicMock()
    user_doc.collection.return_value = posts_collection
    users = MagicMock()
    users.document.return_value = user_doc

    fake_db = MagicMock()
    fake_db.collection.return_value = users
    fake_db.get_all.return_value = []
    fake_db.batch.side_effect = lambda: _RecordingBatch(commits, writes)

    monkeypatch.setattr(x_posts_db, "db", fake_db)
    return commits, writes


def _posts(n):
    return [{"id": str(i), "text": f"t{i}", "kind": "tweet"} for i in range(n)]


def test_save_x_posts_chunks_past_499(monkeypatch):
    commits, writes = _install_fake_db(monkeypatch)

    saved = x_posts_db.save_x_posts(UID, _posts(1200))

    assert saved == 1200
    assert len(writes) == 1200
    # 1200 writes chunked at the 500-op Firestore limit -> commits after 500, 1000, 1200.
    assert commits == [500, 1000, 1200]


def test_save_x_posts_under_limit_single_commit(monkeypatch):
    commits, writes = _install_fake_db(monkeypatch)

    saved = x_posts_db.save_x_posts(UID, _posts(10))

    assert saved == 10
    assert commits == [10]


def test_save_x_posts_skips_malformed_entries(monkeypatch):
    commits, writes = _install_fake_db(monkeypatch)

    saved = x_posts_db.save_x_posts(
        UID, [{"id": "1"}, "not-a-dict", {"id": ""}, {"id": None}, {"id": " 2 "}]
    )

    assert saved == 2
    assert writes == ["1", "2"]
    assert commits == [2]


def test_save_x_posts_rejects_blank_uid(monkeypatch):
    _install_fake_db(monkeypatch)

    try:
        x_posts_db.save_x_posts("   ", _posts(1))
    except ValueError as exc:
        assert "uid" in str(exc)
    else:
        raise AssertionError("blank uid should raise ValueError")


def test_mark_memory_extraction_completed_chunks_past_499(monkeypatch):
    commits, writes = _install_fake_db(monkeypatch)

    x_posts_db.mark_memory_extraction_completed(UID, [str(i) for i in range(1200)])

    assert len(writes) == 1200
    assert commits == [500, 1000, 1200]


def test_mark_memory_extraction_completed_rejects_blank_uid(monkeypatch):
    _install_fake_db(monkeypatch)

    try:
        x_posts_db.mark_memory_extraction_completed("", ["1"])
    except ValueError:
        pass
    else:
        raise AssertionError("blank uid should raise ValueError")


def test_readers_return_safe_defaults_for_invalid_uid(monkeypatch):
    _install_fake_db(monkeypatch)

    assert x_posts_db.get_pending_memory_extraction_posts("") == []
    assert x_posts_db.get_x_posts("  ") == []
    assert x_posts_db.get_x_posts_by_ids("", ["1"]) == []
    assert x_posts_db.count_x_posts("") == 0
    assert x_posts_db.get_newest_tweet_id("") is None


def test_get_x_posts_by_ids_skips_unusable_ids(monkeypatch):
    _install_fake_db(monkeypatch)

    assert x_posts_db.get_x_posts_by_ids(UID, ["", "  ", None]) == []
