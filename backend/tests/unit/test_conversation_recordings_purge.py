"""Regression test: an unconfigured recordings bucket must not deadlock the account-deletion wipe.

BUCKET_MEMORIES_RECORDINGS was never wired into the backend charts, so `memories_recordings_bucket`
resolved to None in prod and `.bucket(None)` raised ValueError("Cannot determine path without bucket
name"). delete_all_conversation_recordings is a *required* purge step, so that raise aborted
background_wipe_user_data before users_db.delete_user_data(): every account-deletion request failed,
was marked wipe_failed, and was re-enqueued forever with the user's data still in Firestore.

An unconfigured bucket now means "nothing to purge" — uploads resolve the same name, so a deployment
without it cannot have stored recordings. A *real* GCS failure must still block the irreversible
Firestore wipe (test_delete_account_purge_storage.py::test_gcs_failure_blocks_firestore_wipe).

The purge itself runs through the shared owner-purge verifier
(``_delete_owner_bucket_prefix``), so the legacy MagicMock fixture (the same static blob on every
listing) cannot stand in for the bucket any more: the verifier requires a stateful listing and
would raise on it. The stateful fixture below also pins this boundary's verdict contract: the
sweep's own read-after-write echo (a versioned re-list answering a just-deleted generation) does
not fail the wipe, a 404-answered delete (a concurrent purge won the race) is settled by a fresh
re-attack, and only residue the deletes never removed still fails closed.
"""

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from google.cloud.exceptions import NotFound

from utils.other import storage as storage_mod


class _StatefulBlob:
    def __init__(self, bucket: "_RecordingsBucket", name: str, generation: int) -> None:
        self.bucket = bucket
        self.name = name
        self.generation = generation

    def delete(self) -> None:
        self.bucket.apply_delete(self.name, self.generation)


class _RecordingsBucket:
    """Versioned in-memory bucket with a configurable read-after-write echo.

    ``echo_rounds`` answers every successful delete with one more read of the
    deleted identity — the versioned-listing propagation window. ``gone`` is
    the set of names whose deletes answer 404 (a concurrent purge won the
    race; the object is where this delete wanted it). ``late_arrivals``
    become visible to listings from ``late_after_calls`` onward — an upload
    admitted mid-sweep, which the settle pass must pick up and delete.
    """

    module = "not-unittest-mock"

    def __init__(
        self,
        live: dict[str, int],
        *,
        echo_rounds: int = 0,
        gone: set[str] | None = None,
        late_arrivals: dict[str, int] | None = None,
        late_after_calls: int = 2,
    ) -> None:
        self.live = live
        self.echo_rounds = echo_rounds
        self.gone = gone or set()
        self.late_arrivals = late_arrivals or {}
        self.late_after_calls = late_after_calls
        self.list_calls = 0
        self.delete_calls = 0

    def apply_delete(self, name: str, generation: int) -> None:
        self.delete_calls += 1
        if name in self.gone:
            # A concurrent purge won the race: it already removed the object
            # and this delete answers 404.
            self.live.pop(name, None)
            raise NotFound(f"No such object: {name}")
        self.live.pop(name, None)
        if self.echo_rounds > 0:
            self.echo_rounds -= 1
            self.live[name] = generation

    def blob(self, name: str, generation: int | None = None) -> _StatefulBlob:
        return _StatefulBlob(self, name, self.live.get(name, 1) if generation is None else generation)

    def list_blobs(self, *, prefix: str, **kwargs: Any) -> list[_StatefulBlob]:
        self.list_calls += 1
        entries = {name: gen for name, gen in self.live.items() if name.startswith(prefix)}
        if self.list_calls >= self.late_after_calls:
            # A concurrent upload admitted in the delete loop's blind spot:
            # the listing only answers it from ``late_after_calls`` onward,
            # and its deletes never stick (the writer outraces them).
            entries.update({name: gen for name, gen in self.late_arrivals.items() if name.startswith(prefix)})
        return [_StatefulBlob(self, name, generation) for name, generation in sorted(entries.items())]


class _RecordingsClient:
    def __init__(self, recordings: _RecordingsBucket) -> None:
        self._recordings = recordings

    def bucket(self, name: str) -> _RecordingsBucket:
        assert name == "memories-recordings"
        return self._recordings


def _recordings_bucket(monkeypatch: pytest.MonkeyPatch, bucket: _RecordingsBucket) -> None:
    monkeypatch.setattr(storage_mod, "memories_recordings_bucket", "memories-recordings")
    monkeypatch.setattr(storage_mod, "_get_storage_client", lambda: _RecordingsClient(bucket))


class TestDeleteAllConversationRecordings:
    def test_unconfigured_bucket_is_a_no_op(self):
        """Before the fix this raised ValueError and blocked the whole account wipe."""
        with patch.object(storage_mod, "memories_recordings_bucket", None), patch.object(
            storage_mod, "_get_storage_client"
        ) as get_client:
            assert storage_mod.delete_all_conversation_recordings("uid1") == 0
        get_client.assert_not_called()

    def test_configured_bucket_purges_the_uid_prefix(self, monkeypatch):
        bucket = _RecordingsBucket({"uid1/conv1.wav": 100})
        _recordings_bucket(monkeypatch, bucket)

        assert storage_mod.delete_all_conversation_recordings("uid1") == 1
        assert bucket.live == {}

    def test_configured_bucket_purges_every_object_under_the_owner_prefix(self, monkeypatch):
        bucket = _RecordingsBucket({"uid1/a.wav": 1, "uid1/b.wav": 2, "uid1x/keep.wav": 3})
        _recordings_bucket(monkeypatch, bucket)

        deleted = storage_mod.delete_all_conversation_recordings("uid1")

        assert deleted == 2
        assert bucket.live == {"uid1x/keep.wav": 3}

    def test_real_gcs_failure_still_raises(self):
        """The purge is required: a genuine GCS error must keep blocking the irreversible wipe."""
        client = SimpleNamespace(bucket=lambda name: (_ for _ in ()).throw(RuntimeError("gcs down")))
        with patch.object(storage_mod, "memories_recordings_bucket", "memories-recordings"), patch.object(
            storage_mod, "_get_storage_client", return_value=client
        ):
            with pytest.raises(RuntimeError):
                storage_mod.delete_all_conversation_recordings("uid1")

    def test_echo_of_own_deletes_does_not_fail_the_wipe(self, monkeypatch):
        """The versioned re-list answers the just-deleted generation once more; the settle
        pass removes it again and the verdict must not fail the wipe on the echo."""
        bucket = _RecordingsBucket({"uid1/conv1.wav": 100}, echo_rounds=1)
        _recordings_bucket(monkeypatch, bucket)

        assert storage_mod.delete_all_conversation_recordings("uid1") == 2
        assert bucket.live == {}

    def test_continuous_echo_converges_through_the_identity_verdict(self, monkeypatch):
        """Every listing in the window echoes the just-deleted identity — the pre-identity
        presence verdict failed wipes like this (prod backend-listen 2026-11-01). The
        identity verdict recognizes the echo as this call's own deletes and converges;
        under a soft-delete policy the echoed version simply stays listed."""
        bucket = _RecordingsBucket({"uid1/conv1.wav": 100}, echo_rounds=99)
        _recordings_bucket(monkeypatch, bucket)

        assert storage_mod.delete_all_conversation_recordings("uid1") == 2
        assert bucket.live["uid1/conv1.wav"] == 100

    def test_404_answered_delete_is_absorbed_and_settled(self, monkeypatch):
        """A concurrent purge won the race: the 404 is absorbed, the settle pass's fresh
        listing shows nothing, and the wipe proceeds instead of failing required."""
        bucket = _RecordingsBucket({"uid1/conv1.wav": 100}, gone={"uid1/conv1.wav"})
        _recordings_bucket(monkeypatch, bucket)

        assert storage_mod.delete_all_conversation_recordings("uid1") == 0
        assert bucket.live == {}

    def test_mid_sweep_arrival_is_picked_up_by_the_settle_pass(self, monkeypatch):
        """An upload admitted while the sweep is running becomes visible to the settle
        pass's fresh listing, which deletes it; the wipe proceeds."""
        bucket = _RecordingsBucket(
            {"uid1/conv1.wav": 100},
            late_arrivals={"uid1/late-writer.wav": 200},
            late_after_calls=2,
        )
        _recordings_bucket(monkeypatch, bucket)

        assert storage_mod.delete_all_conversation_recordings("uid1") == 2
        assert bucket.live == {}

    def test_newer_generation_at_the_verdict_still_fails_closed(self, monkeypatch):
        """The late writer's re-upload answers the verdict listing at a generation this
        sweep never deleted: the echo rule must not mask it (t228 contract — an echo
        never hides a newer generation), so the wipe still fails closed."""
        bucket = _RecordingsBucket(
            {"uid1/conv1.wav": 100},
            echo_rounds=99,
            late_arrivals={"uid1/conv1.wav": 300},
            late_after_calls=3,
        )
        _recordings_bucket(monkeypatch, bucket)

        with pytest.raises(RuntimeError, match="owner storage purge left 1 objects"):
            storage_mod.delete_all_conversation_recordings("uid1")
