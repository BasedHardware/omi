#!/usr/bin/env python3
"""Production-grounded nightly macOS Beta fault harness (SCA-48).

This is the checked-in deterministic debugging tool born from the SCA-44
read-only simulation. Where that simulation was a parallel state-machine model,
this harness imports the ACTUAL production decision logic for the nightly Beta
promotion chain and drives it with injected boundary doubles. Nothing here
reimplements a production rule: every assertion runs against the real planner
(``.github/scripts/plan-desktop-release.py``), the real qualification-admission
gate (``backend/desktop_qualification_admission.py``), the real server-owned
manifest builder (``backend/utils/qualified_beta_promotion.py``), and the real
atomic admission transaction (``backend/database/desktop_update_channels.py``).

Boundary mocking policy (mandated by SCA-48): only the GitHub, Codemagic,
Firestore, Redis, and HTTP boundaries are stubbed -- never the logic. The real
Firestore transaction *serialization* (concurrency, stale-generation conflict
resolution) is proven separately by the
``desktop-beta-admission-firestore-contention`` check against a live emulator;
this harness proves the *decision* logic and, critically, that every failure
path mutates no Beta pointer (zero writes).

Run directly: ``python3 .github/scripts/test_desktop_beta_fault_harness.py``.
Exits non-zero if any scenario fails. Registered in ``checks-manifest.yaml``
on the local and ci lanes so production changes to the chain re-run it.
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import hashlib
import importlib.util
import io
import json
import sys
import types
import zipfile
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

# ---------------------------------------------------------------------------
# Boundary stubs: mock ONLY GitHub / Firestore / Redis / HTTP, never the logic.
# ---------------------------------------------------------------------------
# google.cloud.firestore: the @transactional decorator only adds Firestore
# retry/serialization around the production decision logic. That serialization
# is already proven by desktop-beta-admission-firestore-contention; here we run
# the raw decision function with a recording fake transaction so the zero-write
# invariant is observable directly.
_g = types.ModuleType("google")
_gc = types.ModuleType("google.cloud")
_gc.__path__ = []  # type: ignore[attr-defined]
_gfs = types.ModuleType("google.cloud.firestore")


def _transactional(fn):  # identity: expose the undecorated decision function
    fn.to_wrap = fn
    return fn


_gfs.transactional = _transactional
sys.modules.update({"google": _g, "google.cloud": _gc, "google.cloud.firestore": _gfs})

# Firestore client factory + Redis/HTTP/exec helpers are imported only so the
# production modules load; the client is injected per-call via firestore_client=
# and the GitHub reader is injected per-call via reader=, so none of these run.
_dbc = types.ModuleType("database._client")
_dbc.get_firestore_client = lambda *a, **k: None
_rdb = types.ModuleType("database.redis_db")
_rdb.get_generic_cache = lambda *a, **k: None
_rdb.set_generic_cache = lambda *a, **k: None
_exe = types.ModuleType("utils.executors")
_exe.db_executor = lambda f: f
_exe.run_blocking = lambda *a, **k: None
_http = types.ModuleType("utils.http_client")
_http.get_web_fetch_client = lambda *a, **k: None
sys.modules.update(
    {"database._client": _dbc, "database.redis_db": _rdb, "utils.executors": _exe, "utils.http_client": _http}
)

# Production decision logic -- imported for real, exercised for real.
from database.desktop_update_channels import (  # noqa: E402
    _admit_qualified_beta_transaction,
    _build_pointer,
    _canonical_beta_tag,
)
from desktop_qualification_admission import validate_qualification_run  # noqa: E402
from utils.qualified_beta_promotion import (  # noqa: E402
    QualifiedBetaAdmissionError,
    build_qualified_beta_manifest,
)

# The planner ships as a hyphen-named script; load it the way the repo's own
# test_plan_desktop_release.py does.
_spec = importlib.util.spec_from_file_location(
    "plan_desktop_release", REPO / ".github/scripts/plan-desktop-release.py"
)
assert _spec and _spec.loader
planner = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(planner)

REPOSITORY = "BasedHardware/omi"
QUALIFICATION_WORKFLOW = ".github/workflows/desktop_qualify_beta.yml"

# ---------------------------------------------------------------------------
# GitHub boundary double: serves internally-consistent canned responses.
# ---------------------------------------------------------------------------


def _sha(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def github_state(
    tag: str,
    sha: str,
    now: _dt.datetime,
    *,
    run_id: int = 777,
    signature: str = "SIG-DEADBEEF",
    zip_blob: bytes = b"omi-zip-bytes",
    dmg_blob: bytes = b"omi-dmg-bytes",
    merged: bool = True,
) -> dict[str, Any]:
    """Build a fully self-consistent GitHub view that the manifest builder accepts."""
    published = now.isoformat(timespec="seconds").replace("+00:00", "Z")
    base = f"https://github.com/{REPOSITORY}/releases/download/{tag}"
    zip_url, dmg_url = f"{base}/Omi.zip", f"{base}/omi.dmg"
    evidence_name = f"qualification-evidence-{tag}.json"

    def asset(name: str, blob: bytes) -> dict[str, Any]:
        return {"name": name, "browser_download_url": f"{base}/{name}", "digest": "sha256:" + _sha(blob)}

    evidence = {
        "schema_version": 1,
        "qualification_run_id": run_id,
        "release_id": tag,
        "source_sha": sha,
        "source_qualification": {"passed": True, "tier": "T2"},
        "signed_artifact_verification": {"passed": True, "subject": "exact signed ZIP/DMG bytes"},
        "artifacts": {
            "Omi.zip": {"sha256": _sha(zip_blob), "url": zip_url, "signature": signature},
            "omi.dmg": {"sha256": _sha(dmg_blob), "url": dmg_url},
        },
    }
    evidence_blob = json.dumps(evidence, separators=(",", ":")).encode()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("qualification-evidence.json", evidence_blob)

    body = (
        f"<!-- KEY_VALUE_START\nedSignature: {signature}\nchangelog: nightly beta|fix a\nKEY_VALUE_END -->"
    )
    return {
        "release": {
            "tag_name": tag,
            "draft": False,
            "prerelease": False,
            "published_at": published,
            "body": body,
            "assets": [asset("Omi.zip", zip_blob), asset("omi.dmg", dmg_blob), asset(evidence_name, evidence_blob)],
        },
        "tag_sha": sha,
        "merged": merged,
        "runs": [
            {
                "id": run_id,
                "status": "completed",
                "conclusion": "success",
                "event": "workflow_dispatch",
                "path": QUALIFICATION_WORKFLOW,
                "head_branch": tag,
                "head_sha": sha,
                "name": "Qualify Desktop Beta Candidate",
                "updated_at": published,
                "repository": {"full_name": REPOSITORY},
                "head_repository": {"full_name": REPOSITORY},
            }
        ],
        "artifacts": [
            {
                "id": 9001,
                "name": f"desktop-qualification-evidence-{tag}",
                "expired": False,
                "size_in_bytes": len(buf.getvalue()),
                "archive_download_url": f"https://api.github.com/repos/{REPOSITORY}/actions/artifacts/9001/zip",
            }
        ],
        "blobs": {"Omi.zip": zip_blob, "omi.dmg": dmg_blob, evidence_name: evidence_blob},
        "artifact_zip": buf.getvalue(),
    }


class _Unavailable(Exception):
    """Raised by the reader to model a GitHub read failure (fail-closed)."""


class FakeReader:
    """Async read-only GitHub view; mutates are scoped per scenario via `state`."""

    def __init__(self, state: dict[str, Any]):
        self.s = state

    def _check(self, key: str) -> Any:
        value = self.s.get(key, _Unavailable)
        if value is _Unavailable:
            raise _Unavailable(f"github view has no {key}")
        return value

    async def release(self, tag: str) -> dict[str, Any]:
        return self._check("release")

    async def tag_sha(self, tag: str) -> str:
        return self._check("tag_sha")

    async def is_merged_source(self, source_sha: str) -> bool:
        return self._check("merged")

    async def runs(self) -> list[dict[str, Any]]:
        return self._check("runs")

    async def artifacts(self, run_id: int) -> list[dict[str, Any]]:
        return self._check("artifacts")

    async def download(self, url: str) -> bytes:
        name = url.rsplit("/", 1)[-1]
        blobs = self._check("blobs")
        if name not in blobs:
            raise _Unavailable(f"no blob for {name}")
        return blobs[name]

    async def download_artifact(self, artifact_id: int) -> bytes:
        return self._check("artifact_zip")


# ---------------------------------------------------------------------------
# Firestore boundary double: a recording transaction over an in-memory store.
# ---------------------------------------------------------------------------


class FakeSnap:
    def __init__(self, data: Any, exists: bool):
        self._d = data
        self.exists = exists

    def to_dict(self) -> Any:
        return self._d


class FakeRef:
    def __init__(self, store: dict[str, Any], key: str):
        self._s = store
        self._k = key

    def get(self, *, transaction: Any = None) -> FakeSnap:
        return FakeSnap(self._s.get(self._k), self._k in self._s)


class FakeTx:
    """Records every create/set. Writes apply on call (commit-on-call) so a
    second transaction in the same scenario observes committed state; reads
    always precede writes in the production function, so this is faithful."""

    def __init__(self, store: dict[str, Any]):
        self._s = store
        self.writes: list[tuple[str, str]] = []

    def get(self, ref: FakeRef, *, transaction: Any = None) -> FakeSnap:
        return ref.get(transaction=transaction)

    def create(self, ref: FakeRef, data: dict[str, Any]) -> None:
        self.writes.append(("create", ref._k))
        self._s[ref._k] = data

    def set(self, ref: FakeRef, data: dict[str, Any]) -> None:
        self.writes.append(("set", ref._k))
        self._s[ref._k] = data


def _control(tag: str, build: int, *, generation: int = 5, enabled: bool = True) -> dict[str, Any]:
    now = _dt.datetime(2026, 7, 22, 12, 0, 0, tzinfo=_dt.timezone.utc)
    return {
        "schema_version": 1,
        "promotion_enabled": enabled,
        "latest_reserved_tag": tag,
        "latest_reserved_build_number": build,
        "control_generation": generation,
        "latest_reserved_at": now,
        "admission_updated_at": now,
    }


def _run_txn(store: dict[str, Any], manifest: dict[str, Any], generation: int) -> tuple[Any, FakeTx]:
    tx = FakeTx(store)
    refs = (
        FakeRef(store, "control"),
        FakeRef(store, "macos-beta"),
        FakeRef(store, manifest["release_id"]),
    )
    result = _admit_qualified_beta_transaction(tx, refs[0], refs[1], refs[2], manifest, generation)
    return result, tx


# ---------------------------------------------------------------------------
# Scenario registry.
# ---------------------------------------------------------------------------

_results: list[tuple[str, bool, str]] = []


def scenario(name: str) -> Any:
    def deco(fn):
        def wrapped() -> None:
            try:
                fn()
                _results.append((name, True, ""))
            except AssertionError as exc:
                _results.append((name, False, str(exc) or "assertion failed"))
                raise
            except Exception as exc:  # noqa: BLE001 -- surface any failure
                _results.append((name, False, f"{type(exc).__name__}: {exc}"))
                raise

        wrapped.__name__ = fn.__name__
        wrapped._scenario = name  # type: ignore[attr-defined]
        return wrapped

    return deco


NOW = _dt.datetime(2026, 7, 22, 12, 0, 0, tzinfo=_dt.timezone.utc)
SCENARIOS: list = []


def register(fn):
    SCENARIOS.append(fn)
    return fn


def _build_manifest(state=None, **kw):
    state = state or github_state("v0.12.64+100001-macos", "a" * 40, NOW, **kw)
    return asyncio.run(build_qualified_beta_manifest(state["release"]["tag_name"], reader=FakeReader(state), now=NOW)), state


# === Planner layer: real plan-desktop-release.py decision helpers ===========


@register
@scenario("planner: canceled exact-SHA CI blocks the candidate gate")
def _planner_canceled_ci():
    orig = planner.github_check_status
    # The gate short-circuits on the first non-passing check; make one canceled.
    blocker = planner.REQUIRED_SOURCE_CHECK_NAMES[1]
    planner.github_check_status = lambda repo, sha, name: (
        ("completed", "canceled", None) if name == blocker else ("completed", "success", None)
    )
    try:
        reason = planner.required_source_checks_reason(REPOSITORY, "a" * 40)
    finally:
        planner.github_check_status = orig
    assert reason is not None and "canceled" in reason, f"canceled CI must block; got {reason!r}"


@register
@scenario("planner: missing exact-SHA CI blocks the candidate gate")
def _planner_missing_ci():
    orig = planner.github_check_status
    planner.github_check_status = lambda *a: (None, None, None)
    try:
        reason = planner.required_source_checks_reason(REPOSITORY, "a" * 40)
    finally:
        planner.github_check_status = orig
    assert reason is not None and "missing" in reason, f"missing CI must block; got {reason!r}"


@register
@scenario("planner: failed CI conclusion blocks the candidate gate")
def _planner_failed_ci():
    orig = planner.github_check_status
    planner.github_check_status = lambda *a: ("completed", "failure", None)
    try:
        reason = planner.required_source_checks_reason(REPOSITORY, "a" * 40)
    finally:
        planner.github_check_status = orig
    assert reason is not None and "failure" in reason, f"failed CI must block; got {reason!r}"


@register
@scenario("planner: in-progress build blocks a duplicate scheduler tick")
def _planner_duplicate_tick():
    # A tag created seconds ago whose Codemagic build is still running must
    # block a second hourly tick from re-tagging (active-release fence).
    orig_sha, orig_age, orig_chk = planner.tag_sha, planner.tag_age_seconds, planner.github_check_status
    planner.tag_sha = lambda tag: "c" * 40
    planner.tag_age_seconds = lambda tag: 30
    planner.github_check_status = lambda *a: ("in_progress", None, None)
    try:
        reason = planner.active_release_reason(REPOSITORY, "v0.12.64+100000-macos")
    finally:
        planner.tag_sha, planner.tag_age_seconds, planner.github_check_status = orig_sha, orig_age, orig_chk
    assert reason is not None and "in_progress" in reason, f"in-progress build must block; got {reason!r}"


@register
@scenario("planner: completed-failure build retries stranded latest tag (SCA-44 B1)")
def _planner_failed_build_retry():
    # A completed-FAILURE latest tag must not block a duplicate tick, but it also
    # must not strand the scheduler when no newer desktop paths changed.
    tag = "v0.12.64+100000-macos"
    sha = "c" * 40
    orig_sha, orig_chk, orig_changes = (
        planner.tag_sha,
        planner.github_check_status,
        planner.releasable_desktop_changes_since,
    )
    planner.tag_sha = lambda _tag: sha
    planner.github_check_status = lambda *a: ("completed", "failure", None)
    planner.releasable_desktop_changes_since = lambda _ref: []
    try:
        block_reason = planner.active_release_reason(REPOSITORY, tag)
        retry_sha = planner.failed_latest_tag_retry_source(REPOSITORY, tag)
    finally:
        planner.tag_sha, planner.github_check_status, planner.releasable_desktop_changes_since = (
            orig_sha,
            orig_chk,
            orig_changes,
        )
    assert block_reason is None, f"failed build must not block active release; got {block_reason!r}"
    assert retry_sha == sha, f"failed latest tag must retry its source SHA; got {retry_sha!r}"


# === Qualification admission layer: real validate_qualification_run =========


def _good_run(tag="v0.12.64+100001-macos", sha="a" * 40):
    return {
        "status": "completed",
        "conclusion": "success",
        "event": "workflow_dispatch",
        "path": QUALIFICATION_WORKFLOW,
        "head_branch": tag,
        "head_sha": sha,
        "name": "Qualify Desktop Beta Candidate",
        "repository": {"full_name": REPOSITORY},
        "head_repository": {"full_name": REPOSITORY},
    }


@register
@scenario("qualify: happy-path run is admitted")
def _qualify_happy():
    validate_qualification_run(_good_run(), REPOSITORY, "v0.12.64+100001-macos", "a" * 40)  # no raise


@register
@scenario("qualify: workflow_run head_branch != tag is rejected (SCA-44 B2)")
def _qualify_tag_mismatch():
    run = _good_run()
    run["head_branch"] = "main"
    try:
        validate_qualification_run(run, REPOSITORY, "v0.12.64+100001-macos", "a" * 40)
    except ValueError as exc:
        assert "tag" in str(exc).lower(), str(exc)
        return
    raise AssertionError("head_branch != tag must be rejected")


@register
@scenario("qualify: workflow_run head_sha != source is rejected")
def _qualify_sha_mismatch():
    run = _good_run()
    run["head_sha"] = "b" * 40
    try:
        validate_qualification_run(run, REPOSITORY, "v0.12.64+100001-macos", "a" * 40)
    except ValueError as exc:
        assert "source" in str(exc).lower(), str(exc)
        return
    raise AssertionError("head_sha != source must be rejected")


@register
@scenario("qualify: non-success conclusion / wrong event / wrong repo rejected")
def _qualify_other_rejections():
    for mutate, needle in (
        (lambda r: r.__setitem__("conclusion", "failure"), "conclusion"),
        (lambda r: r.__setitem__("event", "push"), "event"),
        (lambda r: r.__setitem__("head_repository", {"full_name": "evil/org"}), "repository"),
    ):
        run = _good_run()
        mutate(run)
        try:
            validate_qualification_run(run, REPOSITORY, "v0.12.64+100001-macos", "a" * 40)
        except ValueError as exc:
            assert needle in str(exc).lower() or "repository" in str(exc).lower(), str(exc)
            continue
        raise AssertionError(f"{needle} mismatch must be rejected")


# === Backend manifest builder: real build_qualified_beta_manifest ==========


@register
@scenario("manifest: happy path builds a canonical manifest")
def _manifest_happy():
    manifest, _ = _build_manifest()
    assert manifest["release_id"] == "v0.12.64+100001-macos"
    assert manifest["build_number"] == 100001
    assert manifest["qualification_tier"] == "T2" and manifest["qualification_passed"] is True
    assert manifest["ed_signature"] == "SIG-DEADBEEF"


@register
@scenario("manifest: absent release fails closed")
def _manifest_absent_release():
    state = github_state("v0.12.64+100001-macos", "a" * 40, NOW)
    del state["release"]
    with _expect_admission_error():
        asyncio.run(build_qualified_beta_manifest("v0.12.64+100001-macos", reader=FakeReader(state), now=NOW))


@register
@scenario("manifest: failed qualification leaves no fresh trusted run")
def _manifest_failed_qualification():
    state = github_state("v0.12.64+100001-macos", "a" * 40, NOW)
    state["runs"][0]["conclusion"] = "failure"
    with _expect_admission_error():
        asyncio.run(build_qualified_beta_manifest("v0.12.64+100001-macos", reader=FakeReader(state), now=NOW))


@register
@scenario("manifest: qualification retry selects the newest fresh trusted run")
def _manifest_qualification_retry():
    state = github_state("v0.12.64+100001-macos", "a" * 40, NOW, run_id=778)
    older = json.loads(json.dumps(state["runs"][0]))
    older["id"] = 777
    older["conclusion"] = "failure"  # an earlier failed attempt...
    older["updated_at"] = (NOW - _dt.timedelta(minutes=5)).isoformat(timespec="seconds").replace("+00:00", "Z")
    state["runs"].insert(0, older)  # ...superseded by the newer successful retry
    manifest = asyncio.run(build_qualified_beta_manifest("v0.12.64+100001-macos", reader=FakeReader(state), now=NOW))
    assert manifest["release_id"] == "v0.12.64+100001-macos"


@register
@scenario("manifest: unmerged changelog/source is rejected (SCA-44 B3)")
def _manifest_unmerged_source():
    state = github_state("v0.12.64+100001-macos", "a" * 40, NOW, merged=False)
    with _expect_admission_error():
        asyncio.run(build_qualified_beta_manifest("v0.12.64+100001-macos", reader=FakeReader(state), now=NOW))


@register
@scenario("manifest: >7-day-old release is stale and rejected (SCA-44 B5)")
def _manifest_stale():
    state = github_state("v0.12.64+100001-macos", "a" * 40, NOW)
    old = (NOW - _dt.timedelta(days=8)).isoformat(timespec="seconds").replace("+00:00", "Z")
    state["release"]["published_at"] = old
    state["runs"][0]["updated_at"] = old
    with _expect_admission_error():
        asyncio.run(build_qualified_beta_manifest("v0.12.64+100001-macos", reader=FakeReader(state), now=NOW))


@register
@scenario("manifest: digest mismatch between release metadata and bytes is rejected")
def _manifest_digest_mismatch():
    state = github_state("v0.12.64+100001-macos", "a" * 40, NOW)
    # Tamper the served bytes so the re-derived digest no longer matches metadata.
    state["blobs"]["Omi.zip"] = b"tampered"
    with _expect_admission_error():
        asyncio.run(build_qualified_beta_manifest("v0.12.64+100001-macos", reader=FakeReader(state), now=NOW))


@register
@scenario("manifest: draft/prerelease release is rejected")
def _manifest_draft_release():
    state = github_state("v0.12.64+100001-macos", "a" * 40, NOW)
    state["release"]["draft"] = True
    with _expect_admission_error():
        asyncio.run(build_qualified_beta_manifest("v0.12.64+100001-macos", reader=FakeReader(state), now=NOW))


@register
@scenario("manifest: missing qualification artifact is rejected")
def _manifest_missing_artifact():
    state = github_state("v0.12.64+100001-macos", "a" * 40, NOW)
    state["artifacts"] = []  # no evidence artifact for this tag
    with _expect_admission_error():
        asyncio.run(build_qualified_beta_manifest("v0.12.64+100001-macos", reader=FakeReader(state), now=NOW))


# === Backend admission transaction: real _admit_qualified_beta_transaction ==


@register
@scenario("admission: happy path promotes with manifest create + beta pointer set")
def _admit_happy():
    manifest, _ = _build_manifest()
    store = {"control": _control(manifest["release_id"], manifest["build_number"])}
    result, tx = _run_txn(store, manifest, 5)
    assert ("create", manifest["release_id"]) in tx.writes, tx.writes
    assert ("set", "macos-beta") in tx.writes, tx.writes
    assert result["pointer"]["generation"] == 1, result["pointer"]
    assert result["pointer"]["build_number"] == 100001


@register
@scenario("admission: duplicate tick is idempotent (zero writes)")
def _admit_idempotent():
    manifest, _ = _build_manifest()
    store = {"control": _control(manifest["release_id"], manifest["build_number"])}
    _, first = _run_txn(store, manifest, 5)  # commit once
    assert ("set", "macos-beta") in first.writes
    # Second tick: manifest already retained, pointer already current -> no writes.
    _, second = _run_txn(store, manifest, 5)
    assert second.writes == [], f"duplicate tick must be zero-write; got {second.writes}"


@register
@scenario("admission: stale generation is rejected with zero writes (SCA-44 B2/stale)")
def _admit_stale_generation():
    manifest, _ = _build_manifest()
    store = {"control": _control(manifest["release_id"], manifest["build_number"], generation=6)}
    tx = _reject_txn(store, manifest, 5)
    assert tx.writes == [], f"stale generation must not mutate; got {tx.writes}"


@register
@scenario("admission: disabled promotion is rejected with zero writes")
def _admit_disabled():
    manifest, _ = _build_manifest()
    store = {"control": _control(manifest["release_id"], manifest["build_number"], enabled=False)}
    tx = _reject_txn(store, manifest, 5)
    assert tx.writes == [], f"disabled promotion must not mutate; got {tx.writes}"


@register
@scenario("admission: reservation mismatch is rejected with zero writes")
def _admit_reservation_mismatch():
    manifest, _ = _build_manifest()
    # Control reserved a different tag/build than the candidate manifest.
    store = {"control": _control("v0.12.64+199999-macos", 199999)}
    tx = _reject_txn(store, manifest, 5)
    assert tx.writes == [], f"reservation mismatch must not mutate; got {tx.writes}"


@register
@scenario("admission: differing existing manifest metadata is rejected with zero writes")
def _admit_manifest_conflict():
    manifest, _ = _build_manifest()
    conflict = json.loads(json.dumps(manifest))
    conflict["ed_signature"] = "DIFFERENT"
    store = {"control": _control(manifest["release_id"], manifest["build_number"]), manifest["release_id"]: conflict}
    tx = _reject_txn(store, manifest, 5)
    assert tx.writes == [], f"manifest conflict must not mutate; got {tx.writes}"


@register
@scenario("admission: missing control document is rejected with zero writes")
def _admit_missing_control():
    manifest, _ = _build_manifest()
    store: dict[str, Any] = {}
    tx = _reject_txn(store, manifest, 5)
    assert tx.writes == [], f"missing control must not mutate; got {tx.writes}"


@register
@scenario("pointer: roll-forward-only rejects same/lower build (concurrent/rollback)")
def _pointer_rollforward():
    manifest, _ = _build_manifest()
    current_higher = {"release_id": "v0.12.64+100002-macos", "build_number": 100002, "generation": 3}
    rejected = False
    try:
        _build_pointer(current_higher, manifest, transition="promote", platform="macos", channel="beta",
                       release_id=manifest["release_id"], expected_generation=None)
    except ValueError as exc:
        rejected = "roll-forward" in str(exc).lower()
    assert rejected, "promoting build <= current must be rejected as roll-forward-only"


@register
@scenario("pointer: generation mismatch is rejected (concurrent promotion fence)")
def _pointer_generation_fence():
    manifest, _ = _build_manifest()
    current = {"release_id": "v0.12.64+100000-macos", "build_number": 100000, "generation": 9}
    rejected = False
    try:
        _build_pointer(current, manifest, transition="promote", platform="macos", channel="beta",
                       release_id=manifest["release_id"], expected_generation=4)
    except ValueError as exc:
        rejected = "generation" in str(exc).lower()
    assert rejected, "generation mismatch must be rejected"


@register
@scenario("pointer: promotion advances generation by exactly one")
def _pointer_generation_advance():
    manifest, _ = _build_manifest()
    current = {"release_id": "v0.12.64+100000-macos", "build_number": 100000, "generation": 7}
    pointer = _build_pointer(current, manifest, transition="promote", platform="macos", channel="beta",
                             release_id=manifest["release_id"], expected_generation=7)
    assert pointer["generation"] == 8 and pointer["build_number"] == 100001


@register
@scenario("pointer: unqualified manifest cannot be promoted")
def _pointer_requires_qualified():
    manifest, _ = _build_manifest()
    manifest["qualification_passed"] = False
    rejected = False
    try:
        _build_pointer({"build_number": 100000, "generation": 1}, manifest, transition="promote", platform="macos",
                       channel="beta", release_id=manifest["release_id"], expected_generation=None)
    except ValueError as exc:
        rejected = "qualification" in str(exc).lower() or "t2" in str(exc).lower()
    assert rejected, "unqualified manifest must be rejected"


# ---------------------------------------------------------------------------
# Helpers + runner.
# ---------------------------------------------------------------------------


class _expect_admission_error:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            raise AssertionError("expected QualifiedBetaAdmissionError but the call succeeded")
        return issubclass(exc_type, QualifiedBetaAdmissionError) or issubclass(exc_type, ValueError)


def _reject_txn(store: dict[str, Any], manifest: dict[str, Any], generation: int) -> FakeTx:
    """Run the real transaction expecting rejection; return the recording tx."""
    tx = FakeTx(store)
    refs = (FakeRef(store, "control"), FakeRef(store, "macos-beta"), FakeRef(store, manifest["release_id"]))
    try:
        _admit_qualified_beta_transaction(tx, refs[0], refs[1], refs[2], manifest, generation)
    except ValueError:
        return tx
    raise AssertionError("expected the transaction to reject, but it committed")


def main() -> int:
    failures = 0
    for fn in SCENARIOS:
        try:
            fn()
            print(f"  PASS  {fn._scenario}")  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            failures += 1
            print(f"  FAIL  {fn._scenario}")  # type: ignore[attr-defined]
    passed = len(SCENARIOS) - failures
    print(f"\n{passed}/{len(SCENARIOS)} scenarios passed.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
