"""Episode finalization fence read sites split account-marker and tombstone reads.

Counters only: account hit/miss is the marked/unmarked state at decision time,
and the tombstone read has its own site. Decisions are unchanged.
"""

from types import SimpleNamespace

import pytest

from database import episode_finalization_fence as fence
from database.firestore_read_metrics import FirestoreReadOutcome as Outcome, FirestoreReadSite as Site


class _Doc:
    def __init__(self, exists, data=None):
        self.exists = exists
        self._data = data or {}

    def get(self, transaction=None):
        return self

    def to_dict(self):
        return dict(self._data) if self.exists else None


class _Client:
    def __init__(self, tombstone):
        self._tombstone = tombstone

    def collection(self, _name):
        return self

    def document(self, _id):
        return self

    def get(self, transaction=None):
        return self._tombstone


def _run(monkeypatch, *, marker, tombstone, site=Site.EPISODE_FINALIZATION_UPDATE_FENCE):
    recorded = []
    monkeypatch.setattr(fence, 'record_document_read', lambda s, o, count=1: recorded.append((s, o)))
    monkeypatch.setattr(fence, 'account_deletion_document', lambda uid, firestore_client=None: marker)
    client = _Client(tombstone)
    try:
        fence.require_not_deleted(SimpleNamespace(), client, 'uid', 'cid', site)
        allowed = True
    except fence.EpisodeFinalizationDeleted:
        allowed = False
    return allowed, recorded


@pytest.mark.parametrize(
    'site',
    [
        Site.EPISODE_FINALIZATION_UPDATE_FENCE,
        Site.EPISODE_FINALIZATION_MOMENT_FENCE,
        Site.EPISODE_FINALIZATION_CLOSE_FENCE,
        Site.EPISODE_FINALIZATION_MEMO_FENCE,
    ],
)
def test_unmarked_allowed_records_account_miss_and_tombstone_miss(monkeypatch, site):
    allowed, recorded = _run(monkeypatch, marker=_Doc(False), tombstone=_Doc(False), site=site)
    assert allowed
    assert recorded == [
        (Site(f'{site.value}_account'), Outcome.MISS),
        (Site(f'{site.value}_tombstone'), Outcome.MISS),
    ]


def test_unmarked_tombstone_refusal_is_attributed_to_the_tombstone_site(monkeypatch):
    allowed, recorded = _run(monkeypatch, marker=_Doc(False), tombstone=_Doc(True))
    assert not allowed
    assert recorded == [
        (Site.EPISODE_FINALIZATION_UPDATE_FENCE_ACCOUNT, Outcome.MISS),
        (Site.EPISODE_FINALIZATION_UPDATE_FENCE_TOMBSTONE, Outcome.HIT),
    ]


def test_marked_account_refusal_records_only_the_account_hit(monkeypatch):
    allowed, recorded = _run(monkeypatch, marker=_Doc(True, {'wipe_status': 'pending'}), tombstone=_Doc(False))
    assert not allowed
    assert recorded == [(Site.EPISODE_FINALIZATION_UPDATE_FENCE_ACCOUNT, Outcome.HIT)]


def test_allowed_marker_status_still_counts_as_marked(monkeypatch):
    allowed, recorded = _run(monkeypatch, marker=_Doc(True, {'wipe_status': 'cancelled'}), tombstone=_Doc(False))
    assert allowed
    assert recorded == [
        (Site.EPISODE_FINALIZATION_UPDATE_FENCE_ACCOUNT, Outcome.HIT),
        (Site.EPISODE_FINALIZATION_UPDATE_FENCE_TOMBSTONE, Outcome.MISS),
    ]


def test_unsplit_site_keeps_its_single_label(monkeypatch):
    allowed, recorded = _run(monkeypatch, marker=_Doc(False), tombstone=_Doc(False), site=Site.UNATTRIBUTED)
    assert allowed
    assert recorded == [(Site.UNATTRIBUTED, Outcome.MISS), (Site.UNATTRIBUTED, Outcome.MISS)]
