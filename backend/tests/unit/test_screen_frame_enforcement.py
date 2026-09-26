"""Tests for utils/screen_frames/enforcement.py (contract §7).

Covers: the cap is actually applied (not merely requested), a banner below
the 0.35 suitability threshold yields banner=None, and the strip is sorted
by capture order rather than model/insertion order.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from models.screen_frame import ScreenFrameGround
from utils.screen_frames import enforcement as enforcement_mod
from utils.screen_frames.enforcement import NewPersistedFrame, _apply_cap_and_roles

UID = "user-1"
CONVERSATION_ID = "conv-1"

_GROUND = ScreenFrameGround(stops=["#111111", "#222222"], is_neutral=True)


def _t(offset_seconds: float) -> datetime:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return base + timedelta(seconds=offset_seconds)


def _new_frame(frame_id: str, captured_at_offset: float, banner_suitability: float) -> NewPersistedFrame:
    return NewPersistedFrame(
        frame_id=frame_id,
        captured_at=_t(captured_at_offset),
        caption=f"frame {frame_id}",
        labels=[],
        source_badge=None,
        banner_suitability=banner_suitability,
        width=800,
        height=600,
        canonical_sha256="a" * 64,
        ground=_GROUND,
    )


class TestCapIsApplied:
    def test_more_candidates_than_max_persisted_are_capped(self):
        frames = [_new_frame(f"f{i}", i, 0.1) for i in range(10)]
        docs = [enforcement_mod._frame_doc(f) for f in frames]
        survivors, evicted = _apply_cap_and_roles([], docs, max_persisted=7)
        assert len(survivors) == 7
        assert len(evicted) == 3

    def test_eviction_keeps_the_most_recently_captured(self):
        frames = [_new_frame(f"f{i}", i, 0.1) for i in range(10)]
        docs = [enforcement_mod._frame_doc(f) for f in frames]
        survivors, evicted = _apply_cap_and_roles([], docs, max_persisted=7)
        survivor_ids = {d["id"] for d in survivors}
        evicted_ids = {d["id"] for d in evicted}
        # f0..f2 are the oldest three (offsets 0,1,2) — evicted.
        assert evicted_ids == {"f0", "f1", "f2"}
        assert survivor_ids == {"f3", "f4", "f5", "f6", "f7", "f8", "f9"}

    def test_existing_plus_new_are_capped_together(self):
        existing_frames = [_new_frame(f"old{i}", i, 0.1) for i in range(5)]
        existing_docs = [enforcement_mod._frame_doc(f) for f in existing_frames]
        for doc in existing_docs:
            doc["role"] = "strip"
            doc["rank"] = 0

        new_frames = [_new_frame(f"new{i}", 100 + i, 0.1) for i in range(5)]
        new_docs = [enforcement_mod._frame_doc(f) for f in new_frames]

        survivors, evicted = _apply_cap_and_roles(existing_docs, new_docs, max_persisted=7)
        assert len(survivors) == 7
        assert len(evicted) == 3
        # All 5 new frames are newer than all 5 old frames, so the 3 oldest
        # overall (old0, old1, old2) are the ones evicted.
        assert {d["id"] for d in evicted} == {"old0", "old1", "old2"}


class TestBannerThreshold:
    def test_banner_below_threshold_yields_none(self):
        frames = [_new_frame("f0", 0, 0.10), _new_frame("f1", 1, 0.20), _new_frame("f2", 2, 0.34)]
        docs = [enforcement_mod._frame_doc(f) for f in frames]
        survivors, _evicted = _apply_cap_and_roles([], docs, max_persisted=7)
        banner_docs = [d for d in survivors if d["role"] == "banner"]
        assert banner_docs == []
        assert all(d["role"] == "strip" for d in survivors)

    def test_banner_at_or_above_threshold_is_selected(self):
        frames = [_new_frame("f0", 0, 0.10), _new_frame("f1", 1, 0.35), _new_frame("f2", 2, 0.20)]
        docs = [enforcement_mod._frame_doc(f) for f in frames]
        survivors, _evicted = _apply_cap_and_roles([], docs, max_persisted=7)
        banner_docs = [d for d in survivors if d["role"] == "banner"]
        assert len(banner_docs) == 1
        assert banner_docs[0]["id"] == "f1"

    def test_highest_suitability_among_survivors_wins(self):
        frames = [_new_frame("f0", 0, 0.40), _new_frame("f1", 1, 0.90), _new_frame("f2", 2, 0.50)]
        docs = [enforcement_mod._frame_doc(f) for f in frames]
        survivors, _evicted = _apply_cap_and_roles([], docs, max_persisted=7)
        banner_docs = [d for d in survivors if d["role"] == "banner"]
        assert banner_docs[0]["id"] == "f1"


class TestCaptureOrderSort:
    def test_strip_is_sorted_by_captured_at_not_insertion_order(self):
        # Insert out of chronological order.
        frames = [_new_frame("late", 100, 0.1), _new_frame("early", 1, 0.1), _new_frame("mid", 50, 0.1)]
        docs = [enforcement_mod._frame_doc(f) for f in frames]
        survivors, _evicted = _apply_cap_and_roles([], docs, max_persisted=7)
        strip_sorted = sorted((d for d in survivors if d["role"] == "strip"), key=lambda d: d["rank"])
        assert [d["id"] for d in strip_sorted] == ["early", "mid", "late"]

    def test_ranks_are_0_indexed_and_contiguous(self):
        frames = [_new_frame(f"f{i}", i, 0.1) for i in range(5)]
        docs = [enforcement_mod._frame_doc(f) for f in frames]
        survivors, _evicted = _apply_cap_and_roles([], docs, max_persisted=7)
        ranks = sorted(d["rank"] for d in survivors if d["role"] == "strip")
        assert ranks == list(range(5))


class TestBuildFrameSetResponse:
    def test_builds_banner_and_sorted_strip_with_fresh_signed_urls(self, monkeypatch):
        fake_screen_frames_db = MagicMock()
        fake_screen_frames_db.get_conversation_screen_frames.return_value = [
            {
                "id": "banner-frame",
                "captured_at": _t(5),
                "role": "banner",
                "rank": 0,
                "caption": "banner",
                "labels": [],
                "source_badge": None,
                "width": 800,
                "height": 600,
                "ground": {"stops": ["#111111", "#222222"], "is_neutral": True},
            },
            {
                "id": "strip-late",
                "captured_at": _t(20),
                "role": "strip",
                "rank": 1,
                "caption": "late",
                "labels": [],
                "source_badge": None,
                "width": 800,
                "height": 600,
                "ground": {"stops": ["#333333", "#444444"], "is_neutral": False},
            },
            {
                "id": "strip-early",
                "captured_at": _t(1),
                "role": "strip",
                "rank": 0,
                "caption": "early",
                "labels": [],
                "source_badge": None,
                "width": 800,
                "height": 600,
                "ground": {"stops": ["#555555", "#666666"], "is_neutral": False},
            },
        ]
        fake_screen_frames_db.get_conversation_screen_frames_revision.return_value = 3
        monkeypatch.setattr(enforcement_mod, "screen_frames_db", fake_screen_frames_db)

        fake_storage = MagicMock()
        fake_storage.get_screen_frame_signed_url.side_effect = lambda uid, cid, fid: f"https://signed/{fid}"
        fake_storage.get_screen_frame_thumbnail_signed_url.side_effect = (
            lambda uid, cid, fid: f"https://signed/{fid}/thumb"
        )
        fake_storage.SCREEN_FRAME_SIGNED_URL_MINUTES = 60
        monkeypatch.setattr(enforcement_mod, "storage", fake_storage)

        frame_set = enforcement_mod.build_frame_set_response(UID, CONVERSATION_ID)

        assert frame_set.revision == 3
        assert frame_set.banner is not None
        assert frame_set.banner.id == "banner-frame"
        assert [f.id for f in frame_set.strip] == ["strip-early", "strip-late"]
        assert frame_set.banner.content_url == "https://signed/banner-frame"


class TestAnAllRejectedPassIsStillRecorded:
    """The privacy gate must not become a repeating egress of what it refused.

    `revision` only moves when a frame is approved, so a pass that rejected every candidate
    leaves it at 0 — indistinguishable from never having tried. A client keying off `revision`
    therefore re-selects and re-uploads on every reopen, and what it re-uploads is precisely what
    the judge refused: the credentials, the DM window, the inbox.

    `adjudicated_at` is stamped whatever the outcome, so "we asked, and the answer was no" is
    representable and the client can stop asking.
    """

    def test_adjudicated_at_is_carried_even_when_nothing_survived(self, monkeypatch):
        fake_screen_frames_db = MagicMock()
        fake_screen_frames_db.get_conversation_screen_frames.return_value = []
        fake_screen_frames_db.get_conversation_screen_frames_revision.return_value = 0
        fake_screen_frames_db.get_conversation_screen_frames_adjudicated_at.return_value = datetime(
            2026, 8, 24, 12, 0, tzinfo=timezone.utc
        )
        monkeypatch.setattr(enforcement_mod, "screen_frames_db", fake_screen_frames_db)

        frame_set = enforcement_mod.build_frame_set_response(UID, CONVERSATION_ID)

        assert frame_set.banner is None
        assert frame_set.strip == []
        # revision alone cannot express the attempt...
        assert frame_set.revision == 0
        # ...but the attempt is on the record, so the client will not re-offer these frames.
        assert frame_set.adjudicated_at == datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)

    def test_a_conversation_never_attempted_has_no_stamp(self, monkeypatch):
        fake_screen_frames_db = MagicMock()
        fake_screen_frames_db.get_conversation_screen_frames.return_value = []
        fake_screen_frames_db.get_conversation_screen_frames_revision.return_value = 0
        fake_screen_frames_db.get_conversation_screen_frames_adjudicated_at.return_value = None
        monkeypatch.setattr(enforcement_mod, "screen_frames_db", fake_screen_frames_db)

        frame_set = enforcement_mod.build_frame_set_response(UID, CONVERSATION_ID)

        assert frame_set.adjudicated_at is None


def test_one_unrepresentable_stored_frame_does_not_break_the_whole_read(monkeypatch):
    """A stored doc that violates the wire contract costs that frame, not the note.

    ConversationScreenFrame still enforces caption length, label count and the
    two-stop gradient. Before this, a doc that violated any of them raised straight
    out of build_frame_set_response and 500'd the entire screenshots read for the
    conversation — so one bad record hid every good one.
    """
    from utils.screen_frames import enforcement as enf

    good = {**enforcement_mod._frame_doc(_new_frame("ok", 0, 0.9)), "role": "banner", "rank": 0}
    bad = {
        **enforcement_mod._frame_doc(_new_frame("bad", 1, 0.2)),
        "role": "strip",
        "rank": 1,
        "caption": "x" * 400,  # violates ConversationScreenFrame's 160-char contract
    }

    monkeypatch.setattr(enf.screen_frames_db, "get_conversation_screen_frames", lambda *_: [good, bad])
    monkeypatch.setattr(enf.screen_frames_db, "get_conversation_screen_frames_revision", lambda *_: 3)
    monkeypatch.setattr(enf.screen_frames_db, "get_conversation_screen_frames_adjudicated_at", lambda *_: None)
    monkeypatch.setattr(enf.storage, "get_screen_frame_signed_url", lambda *_: "https://example/c")
    monkeypatch.setattr(enf.storage, "get_screen_frame_thumbnail_signed_url", lambda *_: "https://example/t")

    frame_set = enf.build_frame_set_response("uid", "cid")

    assert frame_set.banner is not None and frame_set.banner.id == "ok"
    assert [f.id for f in frame_set.strip] == []
