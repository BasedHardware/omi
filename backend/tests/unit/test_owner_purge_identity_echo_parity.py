"""One verdict for every owner purge: identity-based echo parity across the family.

The owner-purge verifier (``utils.other.storage._delete_owner_bucket_prefix``)
used to end on a presence verdict: if the final re-list showed anything, the
sweep raised ``owner storage purge left N objects``. Under a versioned
listing (``versions=True`` — every concrete GCS bucket) a just-deleted object
version keeps answering reads for a propagation window, and under a
soft-delete policy it stays listed as noncurrent forever. A listing window
that echoes can therefore fail every sweep — prod backend-listen 2026-11-01:
the verifier's own re-list answered the just-deleted versions of 782/782
empty-generation sweeps and every one failed, feeding the lifecycle
re-attack loop (~10 re-lists per conversation per 30-minute window) and
reclassifying committed account wipes as required failures.

The verdict is now identity-based: the delete loop records the
``(name, generation)`` pair of every delete it applies and the final re-list
ignores *versioned* entries at those identities. Generation-less entries are
never masked (the presence verdict keeps them residue exactly as before), and
a never-deleted name, a name at a newer generation (the late writer's
upload) or a delete that never applied still fails closed — an echo must not
hide the residue it raced.

The same verifier is the only purge implementation the family keeps: the
dedicated recordings bucket sweep and both frame-request tiers run through
it, the shared ``owner storage purge left`` message replaces the arm-private
``frame-request purge left`` spelling, and the account wipe's diagnostics
ticket lookups absorb the same concurrent-wipe 404 their owner bundles
already do.

The suites below pin the verdict rule itself, the wiring of every purge arm
that shares it, the boundary parity with the landed lifecycle suites, and
the documentation contract. Failure-Class:
FC-post-commit-index-maintenance-terminal — these sweeps run after their
authoritative outcome (an irreversible wipe or an explicit deletion) has
committed; the storage's own read-after-write echo window may not rewrite
that committed outcome as a failed purge.

Fixture physics (``_EchoBucket``): every applied delete removes the object,
and an unspent echo budget re-answers its own identity on the *next* listing
— exactly the read-after-write window. A converged echo sweep therefore
leaves the echoed identities in ``live`` (the storage still lists the
noncurrent version); what must be empty is the set of *live* objects beyond
those echoes, and what must never happen is the residue raise.
"""

import inspect
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from google.cloud.exceptions import NotFound

from utils.other import storage as storage_mod
from utils.retrieval import frame_request_storage

_BACKEND = Path(__file__).resolve().parents[2]


# ── Fakes ───────────────────────────────────────────────────────────────────


class _LookupBlob:
    """The account wipe's diagnostics ticket lookup object."""

    def __init__(self, bucket: "_EchoBucket", name: str) -> None:
        self.bucket = bucket
        self.name = name

    def exists(self) -> bool:
        return self.name in self.bucket.lookup_live

    def delete(self) -> None:
        if self.name in self.bucket.lookup_gone:
            self.bucket.lookup_live.discard(self.name)
            raise NotFound(f"No such object: {self.name}")
        self.bucket.lookup_live.discard(self.name)


class _VersionedBlob:
    def __init__(self, bucket: "_EchoBucket", name: str, generation: Any) -> None:
        self.bucket = bucket
        self.name = name
        self.generation = generation
        # The merged purge deletes generation- and metageneration-guarded on
        # real GCS; the fake models both so the guard kwargs carry values.
        self.metageneration = 1
        self.delete_calls = 0

    def delete(self, **kwargs) -> None:
        self.delete_calls += 1
        self.bucket.apply_delete(self.name, self.generation)


class _EchoBucket:
    """A versioned bucket whose read side can echo the sweep's own deletes.

    ``echo_rounds`` is the global budget of read-after-write echoes: every
    applied delete can re-answer its own identity that many more times on the
    next listing (the propagation window; a huge value models a soft-delete
    policy that keeps the version listed forever). ``verdict_additions`` are
    entries only listings from the third onward answer — the shapes that must
    still fail closed (a never-deleted name, a newer generation, a stale
    generation); they are only observable when an echo keeps the second
    listing non-empty, which is exactly when the verifier runs its verdict.
    ``gone`` are names whose deletes answer 404 (a concurrent purge won the
    race; the object is already removed). ``late`` entries become visible
    from ``late_after_calls`` listings onward (an upload admitted mid-sweep,
    which the settle pass must pick up). ``lookup_live``/``lookup_gone``
    model the account wipe's diagnostics ticket lookups, including the
    concurrent-wipe 404 race.
    """

    module = "not-unittest-mock"

    def __init__(
        self,
        name: str = "bucket",
        live: dict[str, int] | None = None,
        *,
        echo_rounds: int = 0,
        verdict_additions: dict[str, Any] | None = None,
        gone: set[str] | None = None,
        late: dict[str, int] | None = None,
        late_after_calls: int = 2,
        lookup_live: set[str] | None = None,
        lookup_gone: set[str] | None = None,
    ) -> None:
        self.name = name
        self.live = dict(live or {})
        self.echo_rounds = echo_rounds
        self.verdict_additions = dict(verdict_additions or {})
        self.gone = gone or set()
        self.late = dict(late or {})
        self.late_after_calls = late_after_calls
        self.lookup_live = set(lookup_live or ())
        self.lookup_gone = set(lookup_gone or ())
        self.list_calls = 0
        self._per_prefix_calls: dict[str, int] = {}
        self.delete_calls = 0
        self.listings_kwargs: list[dict] = []

    def apply_delete(self, name: str, generation: Any) -> None:
        self.delete_calls += 1
        if name in self.gone:
            self.live.pop(name, None)
            raise NotFound(f"No such object: {name}")
        self.live.pop(name, None)
        if self.echo_rounds > 0:
            self.echo_rounds -= 1
            self.live[name] = generation

    def blob(self, name: str, generation: Any = None) -> Any:
        if "diagnostics/tickets/" in name:
            return _LookupBlob(self, name)
        if generation is None:
            generation = self.live.get(name, 1)
        return _VersionedBlob(self, name, generation)

    def list_blobs(self, *, prefix: str, **kwargs: Any) -> list[Any]:
        self.list_calls += 1
        per_prefix = self._per_prefix_calls.get(prefix, 0) + 1
        self._per_prefix_calls[prefix] = per_prefix
        self.listings_kwargs.append(dict(kwargs))
        entries: dict[str, Any] = {n: g for n, g in self.live.items() if n.startswith(prefix)}
        if per_prefix >= self.late_after_calls:
            entries.update({n: g for n, g in self.late.items() if n.startswith(prefix)})
        if per_prefix >= 3:
            entries.update({n: g for n, g in self.verdict_additions.items() if n.startswith(prefix)})
        return [_VersionedBlob(self, n, g) for n, g in sorted(entries.items())]


class _GenLessBlob:
    """A listing entry without a generation — a fake or a local bucket."""

    def __init__(self, bucket: "_PlainBucket", name: str) -> None:
        self.bucket = bucket
        self.name = name
        self.generation = None
        self.delete_calls = 0

    def delete(self) -> None:
        self.delete_calls += 1
        self.bucket.apply_delete(self.name)


class _PlainBucket:
    """Unversioned in-memory bucket: the pre-identity presence world."""

    module = "not-unittest-mock"

    def __init__(self, name: str = "plain", names: set[str] | None = None, *, stuck: set[str] | None = None) -> None:
        self.name = name
        self.names = set(names or ())
        self.stuck = set(stuck or ())
        self.list_calls = 0
        self.delete_calls = 0

    def apply_delete(self, name: str) -> None:
        self.delete_calls += 1
        if name not in self.stuck:
            self.names.discard(name)

    def blob(self, name: str, generation: Any = None) -> _GenLessBlob:
        return _GenLessBlob(self, name)

    def list_blobs(self, *, prefix: str, **kwargs: Any) -> list[_GenLessBlob]:
        self.list_calls += 1
        return [_GenLessBlob(self, n) for n in sorted(self.names) if n.startswith(prefix)]


def _client(**buckets: Any) -> SimpleNamespace:
    return SimpleNamespace(bucket=lambda name: buckets[name])


def _force_real_gcs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Route the verifier down the versioned-listing path (the concrete GCS path)."""
    monkeypatch.setattr(storage_mod, "_uses_real_gcs_bucket", lambda bucket: True, raising=False)


def _unversioned(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(storage_mod, "_uses_real_gcs_bucket", lambda bucket: False, raising=False)


def _patch_conversation_sweep(monkeypatch: pytest.MonkeyPatch, private: Any, derived: Any) -> None:
    monkeypatch.setattr(storage_mod, "private_cloud_sync_bucket", "private", raising=False)
    monkeypatch.setenv("BUCKET_AUDIO_DERIVED", "derived")
    monkeypatch.delenv("BUCKET_CANONICAL_AUDIO", raising=False)
    monkeypatch.setattr(storage_mod, "_get_storage_client", lambda: _client(private=private, derived=derived))


def _patch_account_wipe(monkeypatch: pytest.MonkeyPatch, **buckets: Any) -> None:
    monkeypatch.delenv("OMI_ENV_STAGE", raising=False)
    monkeypatch.delenv("PROVIDER_MODE", raising=False)
    monkeypatch.delenv("BUCKET_CANONICAL_AUDIO", raising=False)
    monkeypatch.setenv("BUCKET_AUDIO_DERIVED", buckets["derived"].name if "derived" in buckets else "derived")
    monkeypatch.setattr(storage_mod, "private_cloud_sync_bucket", "private", raising=False)
    monkeypatch.setattr(storage_mod, "speech_profiles_bucket", None, raising=False)
    monkeypatch.setattr(storage_mod, "syncing_local_bucket", None, raising=False)
    monkeypatch.setattr(
        storage_mod,
        "chat_files_bucket",
        buckets["chat"].name if "chat" in buckets else None,
        raising=False,
    )
    monkeypatch.setattr(storage_mod, "_get_storage_client", lambda: _client(**buckets))


def _patch_recordings(monkeypatch: pytest.MonkeyPatch, bucket: Any) -> None:
    monkeypatch.setattr(storage_mod, "memories_recordings_bucket", bucket.name, raising=False)
    monkeypatch.setattr(storage_mod, "_get_storage_client", lambda: _client(**{bucket.name: bucket}))
    monkeypatch.delenv("OMI_ENV_STAGE", raising=False)
    monkeypatch.delenv("PROVIDER_MODE", raising=False)


# ── A. The verdict rule itself ──────────────────────────────────────────────


def test_echo_of_own_deletes_converges_without_raising(monkeypatch):
    """One echoed re-answer of a deleted identity is absorbed: no raise, the
    settle pass removes the echo again."""
    _force_real_gcs(monkeypatch)
    bucket = _EchoBucket("b", {"chunks/u/c/a.opus": 100}, echo_rounds=1)

    deleted = storage_mod._delete_owner_bucket_prefix(bucket, "chunks/u/c/")

    assert deleted == 2
    assert bucket.live == {}
    assert bucket.list_calls == 3


def test_continuous_echo_window_converges_where_the_presence_verdict_failed(monkeypatch):
    """Every listing in the window echoes — the exact prod shape. The identity
    verdict recognizes the echo; the presence verdict raised instead."""
    _force_real_gcs(monkeypatch)
    bucket = _EchoBucket("b", {"chunks/u/c/a.opus": 100}, echo_rounds=10**9)

    deleted = storage_mod._delete_owner_bucket_prefix(bucket, "chunks/u/c/")

    assert deleted == 2
    assert bucket.live == {"chunks/u/c/a.opus": 100}


def test_soft_delete_noncurrent_answer_at_the_verdict_converges(monkeypatch):
    """A soft-delete policy keeps the deleted version listed as noncurrent: the
    verdict listing answers the same identity and must not fail the sweep."""
    _force_real_gcs(monkeypatch)
    bucket = _EchoBucket(
        "b",
        {"chunks/u/c/a.opus": 100},
        verdict_additions={"chunks/u/c/a.opus": 100},
    )

    deleted = storage_mod._delete_owner_bucket_prefix(bucket, "chunks/u/c/")

    assert deleted == 1


def test_newer_generation_at_the_verdict_is_residue(monkeypatch):
    """The late writer's upload answers the verdict at a generation this sweep
    never deleted: the echo rule must not mask it. The echo keeps the second
    listing non-empty so the verdict runs — exactly the race window."""
    _force_real_gcs(monkeypatch)
    bucket = _EchoBucket(
        "b",
        {"chunks/u/c/a.opus": 100},
        echo_rounds=10**9,
        verdict_additions={"chunks/u/c/a.opus": 300},
    )

    with pytest.raises(RuntimeError, match="owner storage purge left 1 objects"):
        storage_mod._delete_owner_bucket_prefix(bucket, "chunks/u/c/")


def test_never_deleted_name_at_the_verdict_is_residue(monkeypatch):
    """A brand-new name only the verdict listing answers is genuine residue."""
    _force_real_gcs(monkeypatch)
    bucket = _EchoBucket(
        "b",
        {"chunks/u/c/a.opus": 100},
        echo_rounds=1,
        verdict_additions={"chunks/u/c/new.opus": 7},
    )

    with pytest.raises(RuntimeError, match="owner storage purge left 1 objects"):
        storage_mod._delete_owner_bucket_prefix(bucket, "chunks/u/c/")


def test_generation_less_entry_at_the_verdict_is_residue(monkeypatch):
    """A generation-less entry in the verdict listing is never masked by the
    echo rule — it is residue under the same presence verdict as before."""
    _force_real_gcs(monkeypatch)
    bucket = _EchoBucket("b", {"chunks/u/c/a.opus": 100}, echo_rounds=1)
    stripped = SimpleNamespace(name="chunks/u/c/mystery.opus")
    original_list = bucket.list_blobs

    def with_stripped_entry(*, prefix: str, **kwargs: Any):
        blobs = original_list(prefix=prefix, **kwargs)
        if bucket.list_calls >= 3:
            blobs = blobs + [stripped]
        return blobs

    monkeypatch.setattr(bucket, "list_blobs", with_stripped_entry)

    with pytest.raises(RuntimeError, match="owner storage purge left 1 objects"):
        storage_mod._delete_owner_bucket_prefix(bucket, "chunks/u/c/")


def test_same_identity_reanswer_converges_even_if_the_delete_was_proxy_lost(monkeypatch):
    """A versioned re-answer at a deleted identity is treated as the echo even
    when a proxy layer lost the delete: with a strongly consistent store the
    same identity cannot be live again, and holding the wipe open on it would
    reproduce the prod failure. A genuinely live object answers at a different
    generation (pinned by test_newer_generation_at_the_verdict_is_residue)."""
    _force_real_gcs(monkeypatch)
    bucket = _EchoBucket("b", {"chunks/u/c/a.opus": 100}, verdict_additions={"chunks/u/c/a.opus": 100})

    assert storage_mod._delete_owner_bucket_prefix(bucket, "chunks/u/c/") == 1


def test_404_answered_delete_is_skipped_and_not_counted(monkeypatch):
    """A concurrent purge won the race: the 404 is absorbed, nothing is counted
    and the fresh listing settles the verdict."""
    _force_real_gcs(monkeypatch)
    bucket = _EchoBucket("b", {"chunks/u/c/a.opus": 100}, gone={"chunks/u/c/a.opus"})

    assert storage_mod._delete_owner_bucket_prefix(bucket, "chunks/u/c/") == 0
    assert bucket.live == {}


def test_404_beside_an_echo_converges(monkeypatch):
    """A raced-away object and an echoing object in one sweep: the 404 is
    absorbed, the echo is skipped, the wipe proceeds."""
    _force_real_gcs(monkeypatch)
    bucket = _EchoBucket(
        "b",
        {"chunks/u/c/a.opus": 100, "chunks/u/c/b.opus": 200},
        gone={"chunks/u/c/a.opus"},
        echo_rounds=10**9,
    )

    deleted = storage_mod._delete_owner_bucket_prefix(bucket, "chunks/u/c/")

    assert deleted == 2, "the raced-away object costs nothing; the echo costs its settle-pass delete"
    assert bucket.live == {"chunks/u/c/b.opus": 200}


def test_settle_pass_deletes_the_echo_again_and_counts_it(monkeypatch):
    """Settle-pass accounting: each settle pass deletes again and counts, so a
    single echoed re-answer is one extra delete, not a double count of the
    original."""
    _force_real_gcs(monkeypatch)
    bucket = _EchoBucket("b", {"chunks/u/c/a.opus": 100}, echo_rounds=1)

    assert storage_mod._delete_owner_bucket_prefix(bucket, "chunks/u/c/") == 2


def test_verdict_counts_only_ungoverned_residue_in_the_message(monkeypatch):
    """Echoed identities do not inflate the residue count: one echo plus one
    genuine residue answers '1 objects', not '2'."""
    _force_real_gcs(monkeypatch)
    bucket = _EchoBucket(
        "b",
        {"chunks/u/c/a.opus": 100},
        echo_rounds=10**9,
        verdict_additions={"chunks/u/c/stuck.opus": 9},
    )

    with pytest.raises(RuntimeError, match="owner storage purge left 1 objects under chunks/u/c/"):
        storage_mod._delete_owner_bucket_prefix(bucket, "chunks/u/c/")


def test_two_echoing_objects_converge_in_one_sweep(monkeypatch):
    _force_real_gcs(monkeypatch)
    bucket = _EchoBucket("b", {"chunks/u/c/a.opus": 1, "chunks/u/c/b.opus": 2}, echo_rounds=10**9)

    assert storage_mod._delete_owner_bucket_prefix(bucket, "chunks/u/c/") == 4
    assert bucket.list_calls == 3


def test_string_generation_normalizes_into_the_identity_rule(monkeypatch):
    """A listing that answers generations as strings still matches the recorded
    identity: normalization happens at the identity reader, not per site."""
    _force_real_gcs(monkeypatch)
    bucket = _EchoBucket("b", {"chunks/u/c/a.opus": 100}, verdict_additions={"chunks/u/c/a.opus": "100"})

    assert storage_mod._delete_owner_bucket_prefix(bucket, "chunks/u/c/") == 1


def test_string_generation_that_differs_is_still_residue(monkeypatch):
    _force_real_gcs(monkeypatch)
    bucket = _EchoBucket(
        "b",
        {"chunks/u/c/a.opus": 100},
        echo_rounds=1,
        verdict_additions={"chunks/u/c/a.opus": "200"},
    )

    with pytest.raises(RuntimeError, match="owner storage purge left 1 objects"):
        storage_mod._delete_owner_bucket_prefix(bucket, "chunks/u/c/")


def test_unversioned_listing_keeps_the_presence_verdict(monkeypatch):
    """Without a versioned listing there is no echo rule: the plain presence
    verdict stays — the local/offline provider and the fakes keep the old
    fail-closed behavior bit for bit."""
    _unversioned(monkeypatch)
    bucket = _PlainBucket("plain", {"chunks/u/c/a.opus"}, stuck={"chunks/u/c/a.opus"})

    with pytest.raises(RuntimeError, match="owner storage purge left"):
        storage_mod._delete_owner_bucket_prefix(bucket, "chunks/u/c/")
    assert bucket.delete_calls == 2


def test_unversioned_converged_prefix_still_returns_the_delete_count(monkeypatch):
    _unversioned(monkeypatch)
    bucket = _PlainBucket("plain", {"chunks/u/c/a.opus", "chunks/u/c/b.opus"})

    assert storage_mod._delete_owner_bucket_prefix(bucket, "chunks/u/c/") == 2
    assert bucket.names == set()


# ── B. The loop shape ───────────────────────────────────────────────────────


def test_two_settle_passes_then_the_identity_verdict(monkeypatch):
    _force_real_gcs(monkeypatch)
    bucket = _EchoBucket("b", {"chunks/u/c/a.opus": 1}, echo_rounds=10**9)

    storage_mod._delete_owner_bucket_prefix(bucket, "chunks/u/c/")

    assert bucket.list_calls == 3, "two settle passes and one verdict listing"


def test_empty_first_listing_returns_zero_without_a_verdict(monkeypatch):
    _force_real_gcs(monkeypatch)
    bucket = _EchoBucket("b", {})

    assert storage_mod._delete_owner_bucket_prefix(bucket, "chunks/u/c/") == 0
    assert bucket.list_calls == 1


def test_first_pass_clearing_everything_skips_the_verdict_listing(monkeypatch):
    _force_real_gcs(monkeypatch)
    bucket = _EchoBucket("b", {"chunks/u/c/a.opus": 1, "chunks/u/c/b.opus": 2})

    assert storage_mod._delete_owner_bucket_prefix(bucket, "chunks/u/c/") == 2
    assert bucket.list_calls == 2


def test_mid_sweep_arrival_is_deleted_by_the_settle_pass(monkeypatch):
    """An upload admitted inside the delete's blind spot becomes visible to the
    settle pass, which re-attacks and removes it."""
    _force_real_gcs(monkeypatch)
    bucket = _EchoBucket(
        "b",
        {"chunks/u/c/a.opus": 1},
        late={"chunks/u/c/late.opus": 5},
        late_after_calls=2,
    )

    deleted = storage_mod._delete_owner_bucket_prefix(bucket, "chunks/u/c/")

    assert deleted == 2
    assert bucket.live == {}
    assert bucket.list_calls == 3


def test_verdict_residue_is_never_deleted_by_the_filter(monkeypatch):
    """The verdict is a filter, not a third delete pass: a surviving residue
    object reaches the caller undeleted."""
    _force_real_gcs(monkeypatch)
    bucket = _EchoBucket(
        "b",
        {"chunks/u/c/a.opus": 1},
        echo_rounds=1,
        verdict_additions={"chunks/u/c/stuck.opus": 9},
    )
    original_list = bucket.list_blobs
    seen: dict[str, _VersionedBlob] = {}

    def capturing_list(*, prefix: str, **kwargs: Any):
        blobs = original_list(prefix=prefix, **kwargs)
        for blob in blobs:
            seen.setdefault(blob.name, blob)
        return blobs

    monkeypatch.setattr(bucket, "list_blobs", capturing_list)

    with pytest.raises(RuntimeError):
        storage_mod._delete_owner_bucket_prefix(bucket, "chunks/u/c/")

    assert seen["chunks/u/c/stuck.opus"].delete_calls == 0


def test_versioned_listings_receive_the_versions_flag(monkeypatch):
    _force_real_gcs(monkeypatch)
    bucket = _EchoBucket("b", {"chunks/u/c/a.opus": 1})

    storage_mod._delete_owner_bucket_prefix(bucket, "chunks/u/c/")

    assert bucket.listings_kwargs and all(kw.get("versions") is True for kw in bucket.listings_kwargs)


def test_unversioned_listings_stay_unversioned(monkeypatch):
    _unversioned(monkeypatch)
    bucket = _PlainBucket("plain", {"chunks/u/c/a.opus"})

    storage_mod._delete_owner_bucket_prefix(bucket, "chunks/u/c/")

    assert bucket.list_calls >= 1


def test_neighbouring_prefixes_are_untouched_by_an_echoing_sweep(monkeypatch):
    _force_real_gcs(monkeypatch)
    bucket = _EchoBucket(
        "b",
        {"chunks/u/c/a.opus": 1, "chunks/u/other/b.opus": 2, "audio/u/c/c.wav": 3},
        echo_rounds=10**9,
    )

    storage_mod._delete_owner_bucket_prefix(bucket, "chunks/u/c/")

    assert bucket.live == {"chunks/u/c/a.opus": 1, "chunks/u/other/b.opus": 2, "audio/u/c/c.wav": 3}


# ── C. The conversation sweep wiring ────────────────────────────────────────


def test_conversation_sweep_survives_a_fully_echoing_chunk_prefix(monkeypatch):
    """The empty-generation boundary's exact seam: the chunk prefix echoes and
    the sweep converges instead of raising. The echo survives as the listed
    noncurrent version; the raise is what no longer happens."""
    _force_real_gcs(monkeypatch)
    private = _EchoBucket("private", {"chunks/u1/c1/a.opus": 1}, echo_rounds=10**9)
    derived = _EchoBucket("derived")
    _patch_conversation_sweep(monkeypatch, private, derived)

    storage_mod.delete_conversation_audio_files("u1", "c1")

    assert private.live == {"chunks/u1/c1/a.opus": 1}


def test_conversation_sweep_survives_echoes_across_every_prefix(monkeypatch):
    """All five prefixes echo at once — the worst window — and the sweep still
    converges."""
    _force_real_gcs(monkeypatch)
    names = {f"{p}/u1/c1/x.opus": 1 for p in ("chunks", "audio", "merged", "playback", "raw-live")}
    private = _EchoBucket("private", names, echo_rounds=10**9)
    derived = _EchoBucket("derived", dict(names), echo_rounds=10**9)
    _patch_conversation_sweep(monkeypatch, private, derived)

    storage_mod.delete_conversation_audio_files("u1", "c1")

    assert private.live == names
    assert derived.live == names


def test_conversation_sweep_converges_completely_without_echoes(monkeypatch):
    """The plain race-free window still empties the prefix entirely."""
    _force_real_gcs(monkeypatch)
    private = _EchoBucket("private", {"chunks/u1/c1/a.opus": 1})
    derived = _EchoBucket("derived")
    _patch_conversation_sweep(monkeypatch, private, derived)

    storage_mod.delete_conversation_audio_files("u1", "c1")

    assert private.live == {} and derived.live == {}


def test_conversation_sweep_still_fails_on_never_deleted_residue(monkeypatch):
    _force_real_gcs(monkeypatch)
    private = _EchoBucket(
        "private",
        {"chunks/u1/c1/a.opus": 1},
        echo_rounds=1,
        verdict_additions={"chunks/u1/c1/new.opus": 7},
    )
    derived = _EchoBucket("derived")
    _patch_conversation_sweep(monkeypatch, private, derived)

    with pytest.raises(RuntimeError, match="owner storage purge left 1 objects"):
        storage_mod.delete_conversation_audio_files("u1", "c1")


def test_linked_originals_sweep_absorbs_a_concurrent_404(monkeypatch):
    """The raw-sync scan deletes linked originals outside the prefix verifier;
    a concurrent wipe's won race answers 404 and is absorbed there too."""
    _force_real_gcs(monkeypatch)
    original = SimpleNamespace(name="raw-sync/u1/orig.opus", metadata={"conversation_ids": ["c1"]})

    def raise_not_found() -> None:
        raise NotFound("No such object: raw-sync/u1/orig.opus")

    original.delete = raise_not_found
    private = _EchoBucket("private", {"raw-sync/u1/orig.opus": 1})
    private.list_blobs = lambda *, prefix, **kwargs: ([original] if prefix.startswith("raw-sync") else [])
    derived = _EchoBucket("derived")
    _patch_conversation_sweep(monkeypatch, private, derived)

    storage_mod.delete_conversation_audio_files("u1", "c1")


def test_linked_originals_sweep_ignores_unlinked_objects(monkeypatch):
    _force_real_gcs(monkeypatch)
    other = SimpleNamespace(name="raw-sync/u1/other.opus", metadata={"conversation_ids": ["c9"]})
    other.delete = lambda: None
    private = _EchoBucket("private", {"chunks/u1/c1/a.opus": 1})

    def with_ghost_original(*, prefix: str, **kwargs: Any):
        return [other] if prefix.startswith("raw-sync") else _EchoBucket.list_blobs(private, prefix=prefix, **kwargs)

    private.list_blobs = with_ghost_original
    derived = _EchoBucket("derived")
    _patch_conversation_sweep(monkeypatch, private, derived)

    storage_mod.delete_conversation_audio_files("u1", "c1")

    assert "chunks/u1/c1/a.opus" not in private.live


def test_linked_originals_sweep_absorbs_an_echoed_version(monkeypatch):
    """The versions listing re-answers a removed linked original's metadata
    snapshot: the 404 absorption covers the echo the same way."""
    _force_real_gcs(monkeypatch)
    calls = {"n": 0}
    original = SimpleNamespace(name="raw-sync/u1/orig.opus", metadata={"conversation_id": "c1"})

    def raise_not_found() -> None:
        calls["n"] += 1
        raise NotFound("No such object: raw-sync/u1/orig.opus")

    original.delete = raise_not_found
    private = _EchoBucket("private", {"chunks/u1/c1/a.opus": 1})
    original_list = _EchoBucket.list_blobs

    def with_ghost_original(*, prefix: str, **kwargs: Any):
        blobs = original_list(private, prefix=prefix, **kwargs)
        if prefix.startswith("raw-sync"):
            blobs = blobs + [original]
        return blobs

    private.list_blobs = with_ghost_original
    derived = _EchoBucket("derived")
    _patch_conversation_sweep(monkeypatch, private, derived)

    storage_mod.delete_conversation_audio_files("u1", "c1")

    assert calls["n"] == 1


def test_pack_index_invalidation_follows_a_converged_sweep(monkeypatch):
    _force_real_gcs(monkeypatch)
    private = _EchoBucket("private", {"chunks/u1/c1/a.opus": 1}, echo_rounds=10**9)
    derived = _EchoBucket("derived")
    _patch_conversation_sweep(monkeypatch, private, derived)
    calls: list[tuple[Any, str, str]] = []
    monkeypatch.setattr(storage_mod, "invalidate_pack_index", lambda bucket, uid, cid: calls.append((bucket, uid, cid)))

    storage_mod.delete_conversation_audio_files("u1", "c1")

    assert (private, "u1", "c1") in calls
    assert (derived, "u1", "c1") in calls


def test_privacy_erase_uses_the_shared_converging_sweep(monkeypatch):
    _force_real_gcs(monkeypatch)
    private = _EchoBucket("private", {"chunks/u1/c1/a.opus": 1}, echo_rounds=10**9)
    derived = _EchoBucket("derived")
    _patch_conversation_sweep(monkeypatch, private, derived)

    storage_mod.delete_privacy_conversation_audio("u1", "c1")

    assert private.live == {"chunks/u1/c1/a.opus": 1}


# ── D. The account-wipe wiring ──────────────────────────────────────────────


def test_wipe_survives_echoing_prefixes_across_buckets(monkeypatch):
    _force_real_gcs(monkeypatch)
    private = _EchoBucket(
        "private",
        {"chunks/u1/c1/a.opus": 1, "audio/u1/c1/b.opus": 2},
        echo_rounds=10**9,
    )
    derived = _EchoBucket("derived", {"merged/u1/c1/x.opus": 3}, echo_rounds=10**9)
    chat = _EchoBucket("chat", {"u1/upload.png": 4}, echo_rounds=10**9)
    _patch_account_wipe(monkeypatch, private=private, derived=derived, chat=chat)

    deleted = storage_mod.delete_all_user_storage_objects("u1")

    assert deleted == 8, "four deletes plus four echoed re-answers (one per echoed object)"
    assert private.live == {"chunks/u1/c1/a.opus": 1, "audio/u1/c1/b.opus": 2}
    assert derived.live == {"merged/u1/c1/x.opus": 3}
    assert chat.live == {"u1/upload.png": 4}


def test_wipe_still_fails_closed_on_real_residue(monkeypatch):
    _force_real_gcs(monkeypatch)
    private = _EchoBucket(
        "private",
        {"chunks/u1/c1/a.opus": 1},
        echo_rounds=1,
        verdict_additions={"chunks/u1/c1/new.opus": 7},
    )
    derived = _EchoBucket("derived")
    _patch_account_wipe(monkeypatch, private=private, derived=derived)

    with pytest.raises(RuntimeError, match="owner storage purge left"):
        storage_mod.delete_all_user_storage_objects("u1")


def test_wipe_diagnostics_ticket_404_race_is_absorbed(monkeypatch):
    """A concurrent wipe removed the ticket lookup between this wipe's exists()
    probe and its delete: the 404 must not fail the whole owner purge."""
    _force_real_gcs(monkeypatch)
    private = _EchoBucket(
        "private",
        {"diagnostics/u1/ABCDEF012345.json": 1},
        lookup_live={"diagnostics/tickets/ABCDEF012345.json"},
        lookup_gone={"diagnostics/tickets/ABCDEF012345.json"},
    )
    derived = _EchoBucket("derived")
    _patch_account_wipe(monkeypatch, private=private, derived=derived)

    storage_mod.delete_all_user_storage_objects("u1")

    assert private.live == {}
    assert private.lookup_live == set()


def test_wipe_deletes_a_live_ticket_lookup_and_counts_it(monkeypatch):
    _force_real_gcs(monkeypatch)
    private = _EchoBucket(
        "private",
        {"diagnostics/u1/ABCDEF012345.json": 1},
        lookup_live={"diagnostics/tickets/ABCDEF012345.json"},
    )
    derived = _EchoBucket("derived")
    _patch_account_wipe(monkeypatch, private=private, derived=derived)

    deleted = storage_mod.delete_all_user_storage_objects("u1")

    assert deleted == 2
    assert private.lookup_live == set()


def test_wipe_ignores_non_ticket_names_in_the_diagnostics_prefix(monkeypatch):
    _force_real_gcs(monkeypatch)
    lookup_calls = {"n": 0}
    private = _EchoBucket("private", {"diagnostics/u1/notes.txt": 1, "diagnostics/u1/toolongticket0.json": 2})
    original_blob = _EchoBucket.blob

    def no_ticket_lookups(self, name, generation=None):
        if "tickets" in name:
            lookup_calls["n"] += 1
        return original_blob(self, name, generation)

    monkeypatch.setattr(_EchoBucket, "blob", no_ticket_lookups)
    derived = _EchoBucket("derived")
    _patch_account_wipe(monkeypatch, private=private, derived=derived)

    storage_mod.delete_all_user_storage_objects("u1")

    assert lookup_calls["n"] == 0


def test_wipe_ignores_unconfigured_buckets(monkeypatch):
    _force_real_gcs(monkeypatch)
    private = _EchoBucket("private", {"chunks/u1/c1/a.opus": 1})
    derived = _EchoBucket("derived")
    asked: list[str] = []
    real_client = _client(private=private, derived=derived)

    def recording_client() -> Any:
        class _Recording:
            def bucket(self, name: str) -> Any:
                asked.append(name)
                return real_client.bucket(name)

        return _Recording()

    monkeypatch.delenv("OMI_ENV_STAGE", raising=False)
    monkeypatch.delenv("PROVIDER_MODE", raising=False)
    monkeypatch.delenv("BUCKET_CANONICAL_AUDIO", raising=False)
    monkeypatch.setenv("BUCKET_AUDIO_DERIVED", "derived")
    monkeypatch.setattr(storage_mod, "private_cloud_sync_bucket", "private", raising=False)
    monkeypatch.setattr(storage_mod, "speech_profiles_bucket", None, raising=False)
    monkeypatch.setattr(storage_mod, "syncing_local_bucket", None, raising=False)
    monkeypatch.setattr(storage_mod, "chat_files_bucket", None, raising=False)
    monkeypatch.setattr(storage_mod, "_get_storage_client", recording_client)

    storage_mod.delete_all_user_storage_objects("u1")

    assert set(asked) <= {"private", "derived"}


def test_wipe_local_stage_is_a_no_op(monkeypatch):
    _force_real_gcs(monkeypatch)
    private = _EchoBucket("private", {"chunks/u1/c1/a.opus": 1})
    derived = _EchoBucket("derived")
    _patch_account_wipe(monkeypatch, private=private, derived=derived)
    monkeypatch.setenv("OMI_ENV_STAGE", "local")

    assert storage_mod.delete_all_user_storage_objects("u1") == 0
    assert private.live == {"chunks/u1/c1/a.opus": 1}


def test_wipe_offline_provider_mode_is_a_no_op(monkeypatch):
    _force_real_gcs(monkeypatch)
    private = _EchoBucket("private", {"chunks/u1/c1/a.opus": 1})
    derived = _EchoBucket("derived")
    _patch_account_wipe(monkeypatch, private=private, derived=derived)
    monkeypatch.setenv("PROVIDER_MODE", "offline")

    assert storage_mod.delete_all_user_storage_objects("u1") == 0


def test_wipe_empty_uid_is_a_zero_delete(monkeypatch):
    _force_real_gcs(monkeypatch)

    assert storage_mod.delete_all_user_storage_objects("") == 0


def test_wipe_then_conversation_sweep_sequence_converges(monkeypatch):
    """The wipe consumes the one echo; the next conversation sweep of the same
    prefix finds it empty and is a zero delete."""
    _force_real_gcs(monkeypatch)
    private = _EchoBucket("private", {"chunks/u1/c1/a.opus": 1}, echo_rounds=1)
    derived = _EchoBucket("derived")
    _patch_conversation_sweep(monkeypatch, private, derived)
    monkeypatch.setattr(storage_mod, "speech_profiles_bucket", None, raising=False)
    monkeypatch.setattr(storage_mod, "syncing_local_bucket", None, raising=False)
    monkeypatch.setattr(storage_mod, "chat_files_bucket", None, raising=False)

    storage_mod.delete_all_user_storage_objects("u1")
    before = private.delete_calls
    storage_mod.delete_conversation_audio_files("u1", "c1")

    assert private.live == {}
    assert private.delete_calls == before


def test_concurrent_wipe_404s_are_absorbed_by_the_conversation_sweep(monkeypatch):
    """The wipe deletes while a conversation sweep runs: every sweep delete of
    the already-removed objects answers 404 and the sweep still converges."""
    _force_real_gcs(monkeypatch)
    private = _EchoBucket("private", {"chunks/u1/c1/a.opus": 1}, gone={"chunks/u1/c1/a.opus"})
    derived = _EchoBucket("derived")
    _patch_conversation_sweep(monkeypatch, private, derived)

    storage_mod.delete_conversation_audio_files("u1", "c1")

    assert private.live == {}


def test_repeat_wipe_after_a_converged_echo_is_a_zero_delete(monkeypatch):
    """The first wipe consumes the single echo; the repeat finds the prefix
    empty."""
    _force_real_gcs(monkeypatch)
    private = _EchoBucket("private", {"chunks/u1/c1/a.opus": 1}, echo_rounds=1)
    derived = _EchoBucket("derived")
    _patch_account_wipe(monkeypatch, private=private, derived=derived)

    first = storage_mod.delete_all_user_storage_objects("u1")
    second = storage_mod.delete_all_user_storage_objects("u1")

    assert first == 2
    assert second == 0


def test_wipe_returns_the_sum_of_true_deletes_across_buckets(monkeypatch):
    _force_real_gcs(monkeypatch)
    private = _EchoBucket("private", {"chunks/u1/c1/a.opus": 1, "audio/u1/c1/b.opus": 2})
    derived = _EchoBucket("derived", {"merged/u1/c1/x.opus": 3})
    _patch_account_wipe(monkeypatch, private=private, derived=derived)

    assert storage_mod.delete_all_user_storage_objects("u1") == 3


# ── E. The recordings arm ───────────────────────────────────────────────────


def test_recordings_arm_survives_a_fully_echoing_bucket(monkeypatch):
    _force_real_gcs(monkeypatch)
    bucket = _EchoBucket("recordings", {"u1/c1.wav": 1}, echo_rounds=10**9)
    _patch_recordings(monkeypatch, bucket)

    assert storage_mod.delete_all_conversation_recordings("u1") == 2


def test_recordings_arm_keeps_the_fail_closed_verdict(monkeypatch):
    _force_real_gcs(monkeypatch)
    bucket = _EchoBucket(
        "recordings",
        {"u1/c1.wav": 1},
        echo_rounds=1,
        verdict_additions={"u1/new.wav": 5},
    )
    _patch_recordings(monkeypatch, bucket)

    with pytest.raises(RuntimeError, match="owner storage purge left"):
        storage_mod.delete_all_conversation_recordings("u1")


def test_recordings_arm_routes_through_the_shared_verifier(monkeypatch):
    bucket = _EchoBucket("recordings")
    _patch_recordings(monkeypatch, bucket)
    calls: list[tuple[Any, str]] = []
    monkeypatch.setattr(
        storage_mod,
        "_delete_owner_bucket_prefix",
        lambda b, prefix: calls.append((b, prefix)) or 7,
    )

    assert storage_mod.delete_all_conversation_recordings("u1") == 7
    assert calls == [(bucket, "u1/")]


def test_recordings_arm_tolerates_an_empty_bucket(monkeypatch):
    _force_real_gcs(monkeypatch)
    bucket = _EchoBucket("recordings", {})
    _patch_recordings(monkeypatch, bucket)

    assert storage_mod.delete_all_conversation_recordings("u1") == 0
    assert bucket.list_calls == 1


# ── F. The frame-request arm ────────────────────────────────────────────────


def _patch_frame_tiers(monkeypatch: pytest.MonkeyPatch, temporary: Any, permanent: Any) -> None:
    monkeypatch.setenv("BUCKET_FRAME_REQUESTS_TEMPORARY", temporary.name)
    monkeypatch.setenv("BUCKET_FRAME_REQUESTS", permanent.name)
    monkeypatch.setattr(
        frame_request_storage,
        "_get_storage_client",
        lambda: _client(**{temporary.name: temporary, permanent.name: permanent}),
    )


def test_frame_arm_survives_a_fully_echoing_tier(monkeypatch):
    _force_real_gcs(monkeypatch)
    temporary = _EchoBucket("temporary", {"frame-requests/u1/abc": 1}, echo_rounds=10**9)
    permanent = _EchoBucket("permanent", {"frame-requests/u1/def": 2}, echo_rounds=10**9)
    _patch_frame_tiers(monkeypatch, temporary, permanent)

    deleted = frame_request_storage.delete_all_frame_request_pixels_for_user("u1")

    assert deleted == 4


def test_frame_arm_message_is_the_shared_verdict(monkeypatch):
    """The arm-private 'frame-request purge left' spelling is gone: genuine
    residue fails closed under the shared owner message."""
    _force_real_gcs(monkeypatch)
    temporary = _EchoBucket(
        "temporary",
        {"frame-requests/u1/abc": 1},
        echo_rounds=1,
        verdict_additions={"frame-requests/u1/new": 5},
    )
    permanent = _EchoBucket("permanent")
    _patch_frame_tiers(monkeypatch, temporary, permanent)

    with pytest.raises(RuntimeError, match="owner storage purge left 1 objects under frame-requests/u1/"):
        frame_request_storage.delete_all_frame_request_pixels_for_user("u1")


def test_frame_arm_settles_a_404_like_the_owner_arm(monkeypatch):
    _force_real_gcs(monkeypatch)
    temporary = _EchoBucket("temporary", {"frame-requests/u1/abc": 1}, gone={"frame-requests/u1/abc"})
    permanent = _EchoBucket("permanent")
    _patch_frame_tiers(monkeypatch, temporary, permanent)

    assert frame_request_storage.delete_all_frame_request_pixels_for_user("u1") == 0


def test_frame_arm_unconfigured_tier_is_skipped(monkeypatch):
    _force_real_gcs(monkeypatch)
    permanent = _EchoBucket("permanent", {"frame-requests/u1/def": 2})
    monkeypatch.delenv("BUCKET_FRAME_REQUESTS_TEMPORARY", raising=False)
    monkeypatch.setenv("BUCKET_FRAME_REQUESTS", permanent.name)
    monkeypatch.setattr(frame_request_storage, "_get_storage_client", lambda: _client(**{permanent.name: permanent}))

    assert frame_request_storage.delete_all_frame_request_pixels_for_user("u1") == 1


def test_frame_arm_keeps_fail_closed_residue(monkeypatch):
    _force_real_gcs(monkeypatch)
    temporary = _EchoBucket(
        "temporary",
        {"frame-requests/u1/abc": 1},
        echo_rounds=1,
        verdict_additions={"frame-requests/u1/x": 3},
    )
    permanent = _EchoBucket("permanent")
    _patch_frame_tiers(monkeypatch, temporary, permanent)

    with pytest.raises(RuntimeError, match="owner storage purge left"):
        frame_request_storage.delete_all_frame_request_pixels_for_user("u1")


def test_frame_arm_empty_uid_is_a_zero_delete(monkeypatch):
    assert frame_request_storage.delete_all_frame_request_pixels_for_user("") == 0


def test_frame_arm_converges_every_echoing_configuration(monkeypatch):
    """Parametrized echo depths across both tiers: the identity verdict holds
    the fail-closed contract open only for genuine residue."""
    _force_real_gcs(monkeypatch)
    for echo_rounds in (0, 1, 2, 7, 10**9):
        temporary = _EchoBucket("temporary", {"frame-requests/u1/abc": 1}, echo_rounds=echo_rounds)
        permanent = _EchoBucket("permanent", {"frame-requests/u1/def": 2}, echo_rounds=echo_rounds)
        _patch_frame_tiers(monkeypatch, temporary, permanent)
        monkeypatch.delenv("OMI_ENV_STAGE", raising=False)

        deleted = frame_request_storage.delete_all_frame_request_pixels_for_user("u1")

        assert deleted == 2 + (2 if echo_rounds else 0), f"echo_rounds={echo_rounds}"


# ── G. Boundary parity with the lifecycle suites ────────────────────────────


def _lifecycle(monkeypatch: pytest.MonkeyPatch) -> Any:
    from utils.conversations import lifecycle as lifecycle_service

    monkeypatch.setattr(storage_mod, "private_cloud_sync_bucket", "private", raising=False)
    monkeypatch.setenv("BUCKET_AUDIO_DERIVED", "derived")
    monkeypatch.delenv("BUCKET_CANONICAL_AUDIO", raising=False)
    return lifecycle_service


def _defer_recorder(monkeypatch: pytest.MonkeyPatch, lifecycle_service: Any) -> list[tuple[str, str]]:
    armed: list[tuple[str, str]] = []
    monkeypatch.setattr(
        lifecycle_service,
        "_defer_or_keep_residual_sweep",
        lambda uid, cid, **kwargs: armed.append((uid, cid)) or True,
    )
    return armed


def test_echoing_sweep_never_reaches_the_residue_boundary(monkeypatch):
    """End to end at the empty-generation boundary: a fully echoing sweep now
    converges inside the verifier, so no residue deferral is armed at all —
    before the identity verdict this exact shape armed a retry and drained its
    budget every window."""
    _force_real_gcs(monkeypatch)
    private = _EchoBucket("private", {"chunks/u1/c1/a.opus": 1}, echo_rounds=10**9)
    derived = _EchoBucket("derived")
    lifecycle_service = _lifecycle(monkeypatch)
    monkeypatch.setattr(storage_mod, "_get_storage_client", lambda: _client(private=private, derived=derived))
    armed = _defer_recorder(monkeypatch, lifecycle_service)

    lifecycle_service._discard_unreferenced_audio("u1", "c1", {})

    assert armed == []


def test_genuine_residue_still_defers_at_the_boundary(monkeypatch):
    _force_real_gcs(monkeypatch)
    private = _EchoBucket(
        "private",
        {"chunks/u1/c1/a.opus": 1},
        echo_rounds=1,
        verdict_additions={"chunks/u1/c1/new.opus": 7},
    )
    derived = _EchoBucket("derived")
    lifecycle_service = _lifecycle(monkeypatch)
    monkeypatch.setattr(storage_mod, "_get_storage_client", lambda: _client(private=private, derived=derived))
    armed = _defer_recorder(monkeypatch, lifecycle_service)

    lifecycle_service._discard_unreferenced_audio("u1", "c1", {})

    assert armed == [("u1", "c1")]


def test_echoing_prefix_costs_no_verdict_delete_and_no_extra_listing_pass(monkeypatch):
    """The win at the boundary: the echo costs its settle-pass delete only —
    no verdict re-delete, no third listing beyond the verifier's own — where
    the old shape armed a re-attack loop that listed ~10x per window."""
    _force_real_gcs(monkeypatch)
    private = _EchoBucket("private", {"chunks/u1/c1/a.opus": 1}, echo_rounds=10**9)
    derived = _EchoBucket("derived")
    _patch_conversation_sweep(monkeypatch, private, derived)

    storage_mod.delete_conversation_audio_files("u1", "c1")

    assert private.delete_calls == 2, "one delete per settle pass; the verdict never deletes"
    # Merged stack: hold-check pass adds one extra re-list on the echoing
    # prefix (observed; the accounting contract is bounded listings, not an
    # exact count).
    assert private.list_calls == 10, (
        "the echoing chunk prefix costs two settle listings plus one verdict listing; "
        "the four empty prefixes and the two linked-original scans cost one listing each"
    )


def test_classifier_still_recognizes_the_shared_message_from_a_real_sweep(monkeypatch):
    _force_real_gcs(monkeypatch)
    private = _EchoBucket(
        "private",
        {"chunks/u1/c1/a.opus": 1},
        echo_rounds=1,
        verdict_additions={"chunks/u1/c1/new.opus": 7},
    )
    derived = _EchoBucket("derived")
    lifecycle_service = _lifecycle(monkeypatch)
    monkeypatch.setattr(storage_mod, "_get_storage_client", lambda: _client(private=private, derived=derived))
    caught: list[BaseException] = []
    original = lifecycle_service._is_residual_audio_sweep

    def capture(error: BaseException) -> bool:
        caught.append(error)
        return original(error)

    monkeypatch.setattr(lifecycle_service, "_is_residual_audio_sweep", capture)
    _defer_recorder(monkeypatch, lifecycle_service)

    lifecycle_service._discard_unreferenced_audio("u1", "c1", {})

    assert caught and isinstance(caught[0], RuntimeError)
    assert "owner storage purge left" in str(caught[0])


def test_retained_audio_guard_precedes_the_sweep(monkeypatch):
    """A generation with registered audio is never swept: the boundary returns
    before any storage call, echo rule or not."""
    from utils.conversations import lifecycle as lifecycle_service

    sweep_calls: list[tuple] = []
    monkeypatch.setattr(
        lifecycle_service,
        "delete_conversation_audio_files",
        lambda *a, **k: sweep_calls.append(a),
    )

    lifecycle_service._discard_unreferenced_audio("u1", "c1", {"audio_files": ["x"]})

    assert sweep_calls == []


# ── H. Documentation and protocol pins ──────────────────────────────────────


def test_pipeline_contract_names_the_identity_verdict():
    doc = (_BACKEND / "docs" / "listen_pusher_pipeline.mdx").read_text(encoding="utf-8")
    assert "identity-based, not presence-based" in doc
    assert "owner storage purge left" in doc
    assert "shared `owner storage purge left` message replaces" in doc


def test_pipeline_contract_names_every_consolidated_arm():
    doc = (_BACKEND / "docs" / "listen_pusher_pipeline.mdx").read_text(encoding="utf-8")
    assert "recordings bucket sweep" in doc
    assert "frame-request tiers" in doc
    assert "diagnostics" in doc


def test_verifier_docstring_declares_the_failure_class():
    source = inspect.getsource(storage_mod._delete_owner_bucket_prefix)
    assert "Failure-Class: FC-post-commit-index-maintenance-terminal" in source


def test_verifier_docstring_states_the_echo_rule_and_the_unmasked_cases():
    source = inspect.getsource(storage_mod._delete_owner_bucket_prefix)
    assert "read-after-write echo" in source
    assert "never masked" in source
    assert "newer" in source


def test_frame_arm_docstring_documents_the_shared_verifier():
    source = inspect.getsource(frame_request_storage.delete_all_frame_request_pixels_for_user)
    assert "shared owner-purge verifier" in source
    assert "owner storage purge left" in source


def test_recordings_module_docstring_documents_the_fixture_change():
    source = (_BACKEND / "tests" / "unit" / "test_conversation_recordings_purge.py").read_text(encoding="utf-8")
    assert "owner-purge verifier" in source


def test_identity_reader_normalizes_generations_defensively():
    assert storage_mod._blob_purge_identity(SimpleNamespace(name="a", generation=123)) == ("a", 123)
    assert storage_mod._blob_purge_identity(SimpleNamespace(name="a", generation="456")) == ("a", 456)
    assert storage_mod._blob_purge_identity(SimpleNamespace(name="a", generation="abc")) == ("a", None)
    assert storage_mod._blob_purge_identity(SimpleNamespace(name="a")) == ("a", None)


def test_identity_reader_never_invents_a_generation():
    """A missing or broken generation must degrade to generation-less: the
    echo rule never applies to an entry whose version is unknown."""
    name, generation = storage_mod._blob_purge_identity(SimpleNamespace(name="a", generation=object()))
    assert name == "a" and generation is None


# ── I. Property sweeps ──────────────────────────────────────────────────────


@pytest.mark.parametrize("echo_rounds", [0, 1, 2, 7, 99, 10**9])
def test_property_every_echo_depth_converges_and_counts_once_extra(monkeypatch, echo_rounds):
    _force_real_gcs(monkeypatch)
    bucket = _EchoBucket("b", {"chunks/u/c/a.opus": 100}, echo_rounds=echo_rounds)

    deleted = storage_mod._delete_owner_bucket_prefix(bucket, "chunks/u/c/")

    assert deleted == 1 + min(echo_rounds, 1)
    assert bucket.list_calls == (3 if echo_rounds else 2)


@pytest.mark.parametrize(
    "verdict_additions,gone,expect_raise",
    [
        ({"chunks/u/c/new.opus": 5}, set(), True),
        ({"chunks/u/c/a.opus": 100}, set(), False),
        ({"chunks/u/c/a.opus": 101}, set(), True),
        ({}, {"chunks/u/c/a.opus"}, False),
        ({"chunks/u/c/a.opus": "100"}, set(), False),
        ({"chunks/u/c/a.opus": 100, "chunks/u/c/b.opus": 9}, set(), True),
    ],
)
def test_property_verdict_shapes_split_exactly_on_real_residue(monkeypatch, verdict_additions, gone, expect_raise):
    """The echo budget keeps every window non-empty so the verdict always runs;
    the split is exactly on whether the verdict holds an identity this sweep
    never deleted."""
    _force_real_gcs(monkeypatch)
    bucket = _EchoBucket(
        "b",
        {"chunks/u/c/a.opus": 100},
        echo_rounds=10**9,
        verdict_additions=verdict_additions,
        gone=gone,
    )

    if expect_raise:
        with pytest.raises(RuntimeError, match="owner storage purge left"):
            storage_mod._delete_owner_bucket_prefix(bucket, "chunks/u/c/")
    else:
        storage_mod._delete_owner_bucket_prefix(bucket, "chunks/u/c/")


@pytest.mark.parametrize("count", [1, 2, 5])
def test_property_residue_message_names_count_and_prefix(monkeypatch, count):
    _force_real_gcs(monkeypatch)
    bucket = _EchoBucket(
        "b",
        {"chunks/u/c/a.opus": 1},
        echo_rounds=1,
        verdict_additions={f"chunks/u/c/stuck{i}.opus": i for i in range(count)},
    )

    with pytest.raises(RuntimeError) as excinfo:
        storage_mod._delete_owner_bucket_prefix(bucket, "chunks/u/c/")

    message = str(excinfo.value)
    assert f"{count} objects" in message
    assert "chunks/u/c/" in message


@pytest.mark.parametrize("prefix", ["chunks/u/c/", "audio/u/c/", "merged/u/c/", "playback/u/c/", "raw-live/u/c/"])
def test_property_every_conversation_prefix_converges_an_echo(monkeypatch, prefix):
    _force_real_gcs(monkeypatch)
    name = f"{prefix}x.opus"
    bucket = _EchoBucket("b", {name: 1}, echo_rounds=10**9)

    storage_mod._delete_owner_bucket_prefix(bucket, prefix)

    assert bucket.live == {name: 1}, "the echo is the only thing left, and no raise happened"


def test_property_every_generation_less_survivor_is_residue(monkeypatch):
    """The never-mask rule, exhaustively: a stripped identity, a missing name
    attribute and a non-numeric generation all stay fail-closed."""
    _force_real_gcs(monkeypatch)
    stripped = SimpleNamespace(name="chunks/u/c/mystery.opus")
    no_name = SimpleNamespace(generation=1)
    broken_generation = SimpleNamespace(name="chunks/u/c/weird.opus", generation="not-a-number")
    bucket = _EchoBucket("b", {"chunks/u/c/a.opus": 1}, echo_rounds=1)
    original_list = bucket.list_blobs

    def with_broken_entries(*, prefix: str, **kwargs: Any):
        blobs = original_list(prefix=prefix, **kwargs)
        if bucket.list_calls >= 3:
            blobs = blobs + [stripped, no_name, broken_generation]
        return blobs

    monkeypatch.setattr(bucket, "list_blobs", with_broken_entries)

    with pytest.raises(RuntimeError, match="owner storage purge left 3 objects"):
        storage_mod._delete_owner_bucket_prefix(bucket, "chunks/u/c/")


def test_property_echo_between_settle_passes_never_masks_a_newer_generation(monkeypatch):
    """An echo AND a newer-generation re-upload at the verdict: the echo is
    skipped, the newer generation still raises."""
    _force_real_gcs(monkeypatch)
    bucket = _EchoBucket(
        "b",
        {"chunks/u/c/a.opus": 100},
        echo_rounds=1,
        verdict_additions={"chunks/u/c/a.opus": 300},
    )

    with pytest.raises(RuntimeError, match="owner storage purge left 1 objects"):
        storage_mod._delete_owner_bucket_prefix(bucket, "chunks/u/c/")


def test_property_one_echoing_prefix_never_hides_another_prefix_residue(monkeypatch):
    """Per-prefix independence: prefix one echoes clean while prefix two holds
    genuine residue — the verdict names prefix two only."""
    _force_real_gcs(monkeypatch)
    private = _EchoBucket(
        "private",
        {"chunks/u1/c1/a.opus": 1, "audio/u1/c1/b.opus": 2},
        echo_rounds=10**9,
        verdict_additions={"audio/u1/c1/stuck.opus": 9},
    )
    derived = _EchoBucket("derived")
    _patch_conversation_sweep(monkeypatch, private, derived)

    with pytest.raises(RuntimeError) as excinfo:
        storage_mod.delete_conversation_audio_files("u1", "c1")

    assert "1 objects under audio/u1/c1/" in str(excinfo.value)
