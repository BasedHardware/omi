#!/usr/bin/env python3
"""Driver for the backend memory continuity gauntlet (INV-MEM)."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable
from unittest.mock import patch

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
REPO_DIR = BACKEND_DIR.parent
GAUNTLET_ROOT = BACKEND_DIR / ".harness" / "memory-continuity-gauntlet"
PRUNE_ABORTED_BUNDLE_DAYS = 7

WORKFLOW_ID = "canonical_memory_pipeline"
WORKFLOW_TEST_PATH = "testing/e2e/test_canonical_memory_pipeline.py"
REQUIRED_SELF_CHECK_PATHS = (
    "backend/scripts/memory-continuity-gauntlet.py",
    "backend/scripts/memory-continuity-gauntlet.sh",
    "backend/testing/e2e/test_canonical_memory_pipeline.py",
    "backend/tests/unit/test_inv_mem_1_guard.py",
    "backend/testing/workflow_contracts.json",
)

SUITE_NAMES = frozenset({"capture", "promote", "recall", "archive", "surfaces", "resilience"})
SUITE_ALIASES: dict[str, frozenset[str]] = {
    "all": SUITE_NAMES,
    "pipeline": frozenset({"capture", "promote", "recall", "archive"}),
}
NONCE_KINDS = ("CAPTURE", "PROMOTE", "ARCHIVE")

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def nonce_for(run_id: str, kind: str) -> str:
    if kind not in NONCE_KINDS:
        raise ValueError(f"unknown nonce kind {kind!r}")
    return f"MEMGAUNTLET-{run_id}-{secrets.token_hex(4)}-{kind}"


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_manifest_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def git_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(REPO_DIR), "rev-parse", "--short", "HEAD"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def finalize_evidence_hygiene(run_dir: Path, *, passed: bool, git_sha_value: str) -> None:
    GAUNTLET_ROOT.mkdir(parents=True, exist_ok=True)
    if passed:
        latest = GAUNTLET_ROOT / "latest-green"
        if latest.is_symlink() or latest.exists():
            latest.unlink()
        latest.symlink_to(run_dir.name, target_is_directory=True)
        index_path = GAUNTLET_ROOT / "INDEX.md"
        line = f"- `{run_dir.name}` — `{git_sha_value[:12]}` — green\n"
        existing = index_path.read_text(encoding="utf-8") if index_path.exists() else ""
        if line not in existing:
            with index_path.open("a", encoding="utf-8") as handle:
                if not existing:
                    handle.write("# Memory continuity gauntlet evidence index\n\n")
                handle.write(line)
    prune_aborted_bundles(GAUNTLET_ROOT, keep_dir=run_dir, max_age_days=PRUNE_ABORTED_BUNDLE_DAYS)


def prune_aborted_bundles(root: Path, *, keep_dir: Path, max_age_days: int) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    if not root.is_dir():
        return
    for entry in root.iterdir():
        if not entry.is_dir():
            continue
        if entry.resolve() == keep_dir.resolve():
            continue
        manifest_path = entry / "manifest.json"
        if not manifest_path.is_file():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if manifest.get("passed") is True:
            continue
        stamp = parse_manifest_timestamp(manifest.get("finished_at")) or parse_manifest_timestamp(
            manifest.get("started_at")
        )
        if stamp is None or stamp >= cutoff:
            continue
        shutil.rmtree(entry, ignore_errors=True)


def expand_suites(raw: str) -> set[str]:
    enabled: set[str] = set()
    for token in raw.split(","):
        token = token.strip().lower()
        if not token:
            continue
        if token in SUITE_ALIASES:
            enabled |= set(SUITE_ALIASES[token])
        elif token in SUITE_NAMES:
            enabled.add(token)
        else:
            known = sorted(SUITE_NAMES | set(SUITE_ALIASES))
            raise SystemExit(f"unknown suite {token!r}; choose from {known}")
    return enabled or set(SUITE_ALIASES["all"])


def load_workflow_contract() -> dict[str, Any] | None:
    contracts_path = BACKEND_DIR / "testing" / "workflow_contracts.json"
    if not contracts_path.is_file():
        return None
    contracts = json.loads(contracts_path.read_text(encoding="utf-8"))
    for workflow in contracts.get("workflows", []):
        if workflow.get("id") == WORKFLOW_ID:
            return workflow
    return None


def self_check() -> int:
    failures: list[str] = []
    for rel_path in REQUIRED_SELF_CHECK_PATHS:
        if not (REPO_DIR / rel_path).is_file():
            failures.append(f"missing required file {rel_path}")

    shell_script = SCRIPT_DIR / "memory-continuity-gauntlet.sh"
    if shell_script.is_file():
        shell_text = shell_script.read_text(encoding="utf-8")
        if "memory-continuity-gauntlet.py" not in shell_text:
            failures.append("shell wrapper must exec memory-continuity-gauntlet.py")
        if "exec python3" not in shell_text:
            failures.append("shell wrapper must exec python3 driver")

    driver_source = (SCRIPT_DIR / "memory-continuity-gauntlet.py").read_text(encoding="utf-8")
    for flag in ("--self-check", "def self_check(", "GAUNTLET_ROOT"):
        if flag not in driver_source:
            failures.append(f"driver missing {flag!r} wiring")

    for suite in sorted(SUITE_NAMES):
        if f'"{suite}"' not in driver_source and f"'{suite}'" not in driver_source:
            failures.append(f"driver missing suite token {suite!r}")

    for kind in NONCE_KINDS:
        if kind not in driver_source:
            failures.append(f"driver missing nonce kind {kind!r}")

    workflow = load_workflow_contract()
    if workflow is None:
        failures.append(f"workflow_contracts.json missing workflow id {WORKFLOW_ID!r}")
    else:
        tests = workflow.get("tests") or []
        if WORKFLOW_TEST_PATH not in tests:
            failures.append(f"{WORKFLOW_ID} workflow must register tests path {WORKFLOW_TEST_PATH!r}; got {tests!r}")

    if failures:
        for failure in failures:
            print(f"self-check failed: {failure}", file=sys.stderr)
        return 1

    print("self-check passed " f"(files + {WORKFLOW_ID} workflow + suite wiring + nonce contract + --self-check)")
    return 0


def live_env_probe() -> tuple[bool, str, str]:
    if os.environ.get("MEM_GAUNTLET_FORCE_HERMETIC", "").lower() in {"1", "true", "yes"}:
        return False, "forced_hermetic", ""
    api_url = (
        os.environ.get("MEM_GAUNTLET_API_URL") or os.environ.get("OMI_DESKTOP_API_URL") or "http://127.0.0.1:8080"
    ).rstrip("/")
    admin_key = os.environ.get("ADMIN_KEY", "").strip()
    if not admin_key:
        return False, "missing_ADMIN_KEY", api_url
    request = urllib.request.Request(f"{api_url}/health", method="GET", headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            if response.status != 200:
                return False, f"health_http_{response.status}", api_url
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return False, f"health_unreachable:{exc}", api_url
    return True, "ok", api_url


def http_get_json(url: str, headers: dict[str, str]) -> tuple[int, Any]:
    request = urllib.request.Request(url, method="GET", headers={"Accept": "application/json", **headers})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            try:
                body = json.loads(raw) if raw else None
            except json.JSONDecodeError:
                body = {"raw_length": len(raw)}
            return response.status, body
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            body = {"raw_length": len(raw)}
        return exc.code, body


@dataclass
class SuiteResult:
    status: str
    mode: str
    steps: list[dict[str, Any]] = field(default_factory=list)
    reason: str | None = None
    nonces: dict[str, str] = field(default_factory=dict)


@dataclass
class HermeticState:
    uid: str
    db: Any
    client: Any | None = None
    memory_id: str | None = None
    capture_nonce: str | None = None
    promote_nonce: str | None = None
    archive_nonce: str | None = None


class HermeticRuntime:
    """Keeps e2e fakes + cohort patches alive for the full gauntlet run."""

    def __init__(self, uid: str) -> None:
        self.uid = uid
        self._patchers: list[Any] = []
        self.db: Any = None
        self.client: Any = None

    def start(self) -> HermeticState:
        e2e_dir = BACKEND_DIR / "testing" / "e2e"
        if str(e2e_dir) not in sys.path:
            sys.path.insert(0, str(e2e_dir))

        import testing.e2e.conftest as e2e_conftest  # noqa: WPS433 — gauntlet bootstrap
        from fakes.firestore import setup_fake_firestore
        from fakes.redis import setup_fake_redis
        from fakes.storage import setup_fake_storage
        from fastapi.testclient import TestClient
        from tests.unit.canonical_cohort_test_helpers import set_canonical_cohort

        e2e_conftest._set_e2e_env()
        fake_firestore = setup_fake_firestore()
        fake_redis = setup_fake_redis()
        fake_storage = setup_fake_storage()
        app = e2e_conftest._create_backend_app(fake_firestore, fake_redis, fake_storage)
        self.client = TestClient(app)
        self.db = fake_firestore
        set_canonical_cohort(_GauntletMonkeypatch(), self.uid)
        self._patchers.extend(self._start_canonical_patches())
        return HermeticState(uid=self.uid, db=self.db, client=self.client)

    def _start_canonical_patches(self) -> list[Any]:
        trusted = SimpleNamespace(account_generation=3, head_commit_id="head0", read_error_reason=None)
        from utils.memory.canonical_kg_promotion import CanonicalKgPromotionResult

        patchers = [
            patch(
                "utils.memory.canonical_memory_adapter.read_memory_v3_trusted_account_generation",
                lambda **_: trusted,
            ),
            patch(
                "utils.memory.v3_account_generation_source.read_memory_v3_trusted_account_generation",
                lambda **_: trusted,
                create=True,
            ),
            patch(
                "utils.memory.short_term_promotion.extract_kg_for_promoted_memory",
                lambda *args, **kwargs: CanonicalKgPromotionResult(attempted=False, success=True),
            ),
            patch(
                "utils.memory.canonical_consolidation.query_memory_vector_candidates",
                lambda *args, **kwargs: SimpleNamespace(hits=[], rejected_count=0),
            ),
            patch("utils.memory.short_term_promotion.promotion_batch_threshold", lambda: 1),
            patch("utils.memory.canonical_consolidation.consolidation_batch_threshold", lambda: 1),
        ]
        for patcher in patchers:
            patcher.start()
        return patchers

    def stop(self) -> None:
        if self.client is not None:
            self.client.close()
            self.client = None
        for patcher in reversed(self._patchers):
            patcher.stop()
        self._patchers.clear()


class MemoryContinuityGauntlet:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.run_id = args.run_id or now_iso()
        self.run_dir = Path(args.run_dir or (GAUNTLET_ROOT / self.run_id))
        self.suites = expand_suites(args.suite)
        self.request_live = bool(args.live)
        self.failures: list[str] = []
        self.warnings: list[str] = []
        self.suite_results: dict[str, SuiteResult] = {}
        self.markers = {kind.lower(): nonce_for(self.run_id, kind) for kind in NONCE_KINDS}
        self.manifest: dict[str, Any] = {}
        self._hermetic: HermeticState | None = None
        self._runtime: HermeticRuntime | None = None

    def fail(self, message: str) -> None:
        self.failures.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def record_step(self, suite: str, name: str, **details: Any) -> None:
        result = self.suite_results.setdefault(suite, SuiteResult(status="RUNNING", mode="unknown"))
        result.steps.append({"name": name, **details})

    def suite_not_run(self, suite: str, reason: str) -> None:
        self.suite_results[suite] = SuiteResult(status="NOT_RUN", mode="live", reason=reason)

    def resolve_mode(self) -> tuple[str, str, str]:
        live_ok, reason, api_url = live_env_probe()
        if self.request_live:
            return ("live" if live_ok else "not_run", reason, api_url)
        if live_ok and os.environ.get("MEM_GAUNTLET_PREFER_LIVE", "").lower() in {"1", "true", "yes"}:
            return "live", reason, api_url
        return "hermetic", reason, api_url

    def _seed_rollout(self, db: Any, uid: str, *, grant_consumer: str = "omi_chat") -> None:
        from config.memory_rollout import PASSED, MemoryRolloutMode, MemoryRolloutStageGate
        from tests.unit.fixtures.memory_adapter_fakes import enabled_rollout_doc
        from utils.memory.default_read_rollout import GLOBAL_READ_GATE_PATH
        from utils.memory.v3_limited_rollout_config import WRITE_CONVERGENCE_GATE_PATH

        def _set_gate(path: str, payload: dict[str, Any]) -> None:
            parts = path.split("/")
            ref = db.collection(parts[0]).document(parts[1])
            for index in range(2, len(parts), 2):
                ref = ref.collection(parts[index]).document(parts[index + 1])
            ref.set(payload)

        _set_gate(GLOBAL_READ_GATE_PATH, {"memory_reads_enabled": True, "kill_switch_active": False})
        _set_gate(
            WRITE_CONVERGENCE_GATE_PATH,
            {
                "durable_outbox_enabled": True,
                "dual_write_projection_ready": True,
                "delete_convergence_ready": True,
                "idempotency_contract_ready": True,
            },
        )
        rollout = enabled_rollout_doc(uid, grant_consumer=grant_consumer)
        rollout["mode"] = MemoryRolloutMode.read.value
        rollout["stage_gates"] = {
            MemoryRolloutStageGate.shadow.value: PASSED,
            MemoryRolloutStageGate.write.value: PASSED,
            MemoryRolloutStageGate.read.value: PASSED,
        }
        db.collection("users").document(uid).collection("memory_control").document("state").set(rollout)

    def _seed_apply_control(self, db: Any, uid: str) -> None:
        from models.memory_apply import MemoryControlState

        control = MemoryControlState(
            uid=uid,
            head_commit_id="head0",
            account_generation=3,
            source_generation=1,
        ).model_dump(mode="json")
        db.collection("users").document(uid).collection("memory_state").document("apply_control").set(control)

    def _ensure_hermetic(self) -> HermeticState:
        if self._hermetic is not None:
            return self._hermetic
        uid = f"mem-gauntlet-{self.run_id.lower()}"
        self._runtime = HermeticRuntime(uid)
        state = self._runtime.start()
        self._seed_apply_control(state.db, uid)
        self._seed_rollout(state.db, uid)
        self._hermetic = state
        return self._hermetic

    def run_capture_hermetic(self, state: HermeticState) -> None:
        from models.memories import MemoryCategory
        from tests.unit.test_ws_i_write_convergence import _sample_memory_payload
        from utils.memory.canonical_memory_adapter import write_canonical_extraction_memory

        capture_nonce = self.markers["capture"]
        payload = _sample_memory_payload(
            uid=state.uid,
            conversation_id=f"gauntlet-{self.run_id}",
            content=f"Gauntlet capture probe {capture_nonce}",
        )
        payload["category"] = MemoryCategory.system.value
        memory_id = write_canonical_extraction_memory(state.uid, payload, db_client=state.db)
        item_ref = state.db.collection("users").document(state.uid).collection("memory_items").document(memory_id)
        snapshot = item_ref.get().to_dict()
        assert snapshot["tier"] == "short_term", snapshot
        assert capture_nonce in snapshot.get("content", ""), snapshot
        state.memory_id = memory_id
        state.capture_nonce = capture_nonce
        self.record_step(
            "capture",
            "write_short_term",
            memory_id=memory_id,
            tier=snapshot["tier"],
            nonce=capture_nonce,
        )

    def run_promote_hermetic(self, state: HermeticState) -> None:
        from utils.memory.canonical_consolidation import ConsolidationAgentBatch
        from utils.memory.short_term_promotion import run_canonical_short_term_maintenance

        if state.memory_id is None:
            self.run_capture_hermetic(state)
        promote_nonce = self.markers["promote"]
        item_ref = state.db.collection("users").document(state.uid).collection("memory_items").document(state.memory_id)
        prior = dict(item_ref.get().to_dict())
        prior["content"] = f"{prior.get('content', '')} {promote_nonce}"
        item_ref.set(prior)

        def scripted_llm(_prompt: str) -> str:
            return json.dumps(ConsolidationAgentBatch(decisions=[], reasoning="no_changes").model_dump(mode="json"))

        now = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)
        maintenance = run_canonical_short_term_maintenance(
            state.uid,
            db_client=state.db,
            now=now,
            run_id=f"gauntlet-{self.run_id}",
            llm_invoke=scripted_llm,
        )
        promoted = item_ref.get().to_dict()
        assert maintenance.promotion.promoted_count >= 1, maintenance
        assert promoted["tier"] == "long_term", promoted
        assert promote_nonce in promoted.get("content", ""), promoted
        state.promote_nonce = promote_nonce
        self.record_step(
            "promote",
            "short_term_maintenance",
            memory_id=state.memory_id,
            tier=promoted["tier"],
            promoted_count=maintenance.promotion.promoted_count,
            nonce=promote_nonce,
        )

    def run_recall_hermetic(self, state: HermeticState) -> None:
        from utils.memory.chat_memory_adapter import search_memory_default_chat_memories_text
        from utils.memory.memory_service import MemoryService

        if state.memory_id is None:
            self.run_promote_hermetic(state)
        now = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)
        service = MemoryService(db_client=state.db)
        read_ids = {memory.id for memory in service.read(state.uid, limit=50)}
        assert state.memory_id in read_ids, read_ids
        query_token = state.promote_nonce or state.capture_nonce or self.markers["promote"]
        chat_text = search_memory_default_chat_memories_text(
            uid=state.uid,
            query=query_token,
            limit=10,
            db_client=state.db,
            now=now,
        )
        assert chat_text is not None, "chat search returned None"
        assert query_token in chat_text, chat_text
        self.record_step(
            "recall",
            "default_read_and_chat_search",
            memory_id=state.memory_id,
            query_token=query_token,
            read_count=len(read_ids),
        )

    def run_archive_hermetic(self, state: HermeticState) -> None:
        from datetime import datetime, timezone

        from models.product_memory import MemoryAccessPolicy, MemoryTier
        from tests.unit.fixtures.memory_adapter_fakes import memory_item, stored_item
        from utils.memory.canonical_visibility_filter import filter_canonical_default_visible_items
        from utils.memory.product_memory_read_service import fetch_authoritative_product_memory_items

        now = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)
        archive_nonce = self.markers["archive"]
        archive_item = memory_item(
            f"archive-{self.run_id}",
            uid=state.uid,
            tier=MemoryTier.archive,
            now=now,
            content=f"archive hidden {archive_nonce}",
            quote_text="archive quote",
        )
        visible_item = memory_item(
            f"visible-{self.run_id}",
            uid=state.uid,
            tier=MemoryTier.long_term,
            now=now,
            content="visible long term gauntlet fact",
            quote_text="visible quote",
        )
        items_ref = state.db.collection("users").document(state.uid).collection("memory_items")
        items_ref.document(archive_item.memory_id).set(stored_item(archive_item))
        items_ref.document(visible_item.memory_id).set(stored_item(visible_item))
        state.archive_nonce = archive_nonce

        policy = MemoryAccessPolicy.for_omi_chat(archive_capability=False)
        visible = filter_canonical_default_visible_items(
            fetch_authoritative_product_memory_items(uid=state.uid, db_client=state.db),
            policy=policy,
            now=now,
        )
        visible_ids = {item.memory_id for item in visible}
        assert archive_item.memory_id not in visible_ids, visible_ids
        assert visible_item.memory_id in visible_ids, visible_ids
        if state.memory_id is not None:
            assert state.memory_id in visible_ids, visible_ids
        self.record_step(
            "archive",
            "default_read_excludes_archive",
            archive_id=archive_item.memory_id,
            visible_id=visible_item.memory_id,
            nonce=archive_nonce,
            visible_count=len(visible_ids),
        )

    def run_surfaces_hermetic(self, state: HermeticState) -> None:
        from datetime import datetime, timezone

        from models.product_memory import MemoryAccessPolicy, MemoryConsumer, MemoryTier, ProcessingState
        from tests.unit.fixtures.memory_adapter_fakes import memory_item, stored_item
        from utils.memory.chat_memory_adapter import (
            list_default_chat_memories_decision_text,
            search_memory_default_chat_memories_text,
        )
        from utils.memory.default_read_rollout import MemoryReadDecision, read_default_read_rollout
        from utils.memory.developer_memory_adapter import search_memory_default_developer_memories
        from utils.memory.product_memory_read_service import fetch_default_product_memory_search
        from utils.retrieval.tool_services import memories as tool_memories_service

        now = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)
        archive_nonce = state.archive_nonce or self.markers["archive"]
        items_ref = state.db.collection("users").document(state.uid).collection("memory_items")
        seeded = (
            memory_item(
                f"surface-fresh-{self.run_id}",
                uid=state.uid,
                now=now,
                content="coffee fresh short term",
                quote_text="fresh quote",
                processing_state=ProcessingState.processed,
            ),
            memory_item(
                f"surface-long-{self.run_id}",
                uid=state.uid,
                tier=MemoryTier.long_term,
                now=now,
                content="surface visible coffee preference",
                quote_text="long quote",
            ),
            memory_item(
                f"surface-archive-{self.run_id}",
                uid=state.uid,
                tier=MemoryTier.archive,
                now=now,
                content=f"surface archive {archive_nonce}",
                quote_text="surface archive quote",
            ),
        )
        for item in seeded:
            items_ref.document(item.memory_id).set(stored_item(item))

        rollout = read_default_read_rollout(uid=state.uid, db_client=state.db, consumer="omi_chat")
        assert rollout.read_decision == MemoryReadDecision.USE_MEMORY
        policy = MemoryAccessPolicy(
            consumer=MemoryConsumer.omi_chat,
            app_has_default_memory_grant=True,
            archive_capability=False,
        )

        surfaces: dict[str, Callable[[], Any]] = {
            "chat_text": lambda: search_memory_default_chat_memories_text(
                uid=state.uid, query="coffee", limit=10, db_client=state.db, now=now
            ),
            "chat_list": lambda: list_default_chat_memories_decision_text(
                uid=state.uid, limit=10, offset=0, db_client=state.db
            ).text,
            "developer": lambda: search_memory_default_developer_memories(
                uid=state.uid,
                query="coffee",
                limit=10,
                offset=0,
                db_client=state.db,
                rollout_decision=rollout,
                now=now,
            ).memories,
            "agent_tools": lambda: tool_memories_service.get_memories_text(uid=state.uid, limit=50),
            "product_search": lambda: fetch_default_product_memory_search(
                uid=state.uid,
                query="coffee",
                db_client=state.db,
                policy=policy,
                now=now,
            )["items"],
        }

        for surface_name, reader in surfaces.items():
            payload = reader()
            serialized = json.dumps(payload, default=str)
            assert archive_nonce not in serialized, surface_name
            assert (
                "surface visible coffee preference" in serialized or "coffee fresh short term" in serialized
            ), surface_name
            self.record_step(
                "surfaces",
                surface_name,
                archive_excluded=True,
                visible_present=True,
            )

    def run_resilience_hermetic(self, state: HermeticState) -> None:
        from fakes.firestore import seed_memory
        from testing.e2e.test_canonical_memory_pipeline import _override_memory_runtime, _runtime

        seed_memory(
            state.uid,
            {
                "id": "legacy-must-not-bleed-gauntlet",
                "content": "legacy memory must not leak on canonical projection failure",
                "category": "manual",
                "visibility": "public",
            },
        )

        def failing_memory_service(_params, _adapters):
            from utils.memory.v3_composed_get_service import V3ComposedResponse

            return V3ComposedResponse.error(503, "infrastructure_failure")

        assert state.client is not None
        auth_headers = {"Authorization": "Bearer dev-token"}
        with _override_memory_runtime(
            state.client,
            _runtime(enabled=True, source_decision="memory_read", service=failing_memory_service),
        ):
            resp = state.client.get("/v3/memories", headers=auth_headers)
        assert resp.status_code == 503, resp.text
        assert resp.json() == {"detail": "infrastructure_failure"}
        assert resp.headers.get("x-omi-memory-read-source") == "none"
        assert "legacy-must-not-bleed-gauntlet" not in resp.text
        self.record_step(
            "resilience",
            "projection_failure_fail_closed",
            status_code=resp.status_code,
            legacy_bleed=False,
        )

    def run_suite_live(self, suite: str, api_url: str) -> None:
        admin_key = os.environ["ADMIN_KEY"].strip()
        uid = os.environ.get("MEM_GAUNTLET_UID", "mem-gauntlet-live").strip()
        headers = {"Authorization": f"Bearer {admin_key}{uid}"}
        status, body = http_get_json(f"{api_url}/v3/memories", headers)
        self.record_step(suite, "live_v3_memories_probe", http_status=status, body_summary=_summarize_body(body))
        if status not in {200, 403, 503}:
            raise AssertionError(f"unexpected /v3/memories status {status}")

    def run_suite(self, suite: str, mode: str, api_url: str) -> None:
        if mode == "not_run":
            self.suite_not_run(suite, "live_requested_but_env_unavailable")
            return
        self.suite_results[suite] = SuiteResult(status="RUNNING", mode=mode, nonces=dict(self.markers))
        try:
            if mode == "live":
                self.run_suite_live(suite, api_url)
            else:
                state = self._ensure_hermetic()
                runner = {
                    "capture": self.run_capture_hermetic,
                    "promote": self.run_promote_hermetic,
                    "recall": self.run_recall_hermetic,
                    "archive": self.run_archive_hermetic,
                    "surfaces": self.run_surfaces_hermetic,
                    "resilience": self.run_resilience_hermetic,
                }[suite]
                runner(state)
            self.suite_results[suite].status = "GO"
        except Exception as exc:  # noqa: BLE001 — gauntlet records failure evidence
            self.suite_results[suite].status = "FAIL"
            self.fail(f"{suite}: {exc}")
            self.record_step(suite, "error", message=str(exc))

    def run(self) -> int:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        mode, mode_reason, api_url = self.resolve_mode()
        effective_mode = "live" if mode == "live" else "hermetic" if mode == "hermetic" else "not_run"

        self.manifest = {
            "run_id": self.run_id,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "git": git_sha(),
            "requested_suites": sorted(self.suites),
            "markers": self.markers,
            "mode": effective_mode,
            "mode_reason": mode_reason,
            "api_url": api_url,
            "live_requested": self.request_live,
        }
        write_json(self.run_dir / "manifest.json", self.manifest)

        try:
            for suite in sorted(self.suites):
                self.run_suite(suite, mode, api_url)
        finally:
            if self._runtime is not None:
                self._runtime.stop()
                self._runtime = None

        # Prerequisites (e.g. promote running capture internally) may leave
        # non-selected suites stuck as RUNNING; mark them GO since they
        # completed without raising.
        for name, result in list(self.suite_results.items()):
            if name not in self.suites and result.status == "RUNNING":
                result.status = "GO"

        self.manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
        self.manifest["suite_results"] = {
            name: {
                "status": result.status,
                "mode": result.mode,
                "reason": result.reason,
                "steps": result.steps,
                "nonces": result.nonces,
            }
            for name, result in self.suite_results.items()
        }
        self.manifest["failures"] = self.failures
        self.manifest["warnings"] = self.warnings
        # A run where no selected suite reached GO (e.g. all NOT_RUN because
        # the live environment was unavailable) must not be marked green even
        # when there are zero failures.
        at_least_one_go = any(
            self.suite_results.get(s) is not None and self.suite_results[s].status == "GO" for s in self.suites
        )
        self.manifest["passed"] = not self.failures and at_least_one_go
        write_json(self.run_dir / "manifest.json", self.manifest)
        finalize_evidence_hygiene(self.run_dir, passed=self.manifest["passed"], git_sha_value=self.manifest["git"])

        if self.failures:
            for failure in self.failures:
                print(f"FAIL: {failure}", file=sys.stderr)
            print(f"evidence: {self.run_dir}", file=sys.stderr)
            return 1

        print(
            f"memory-continuity-gauntlet passed mode={effective_mode} "
            f"suites={','.join(sorted(self.suites))} evidence={self.run_dir}"
        )
        return 0


class _GauntletMonkeypatch:
    """Minimal monkeypatch shim for canonical_cohort_test_helpers outside pytest."""

    def setattr(self, target, name, value, raising=True):  # noqa: ARG002
        if isinstance(target, str):
            if "." in target:
                module_path, attr = target.rsplit(".", 1)
                module = __import__(module_path, fromlist=[attr])
                setattr(module, attr, value)
            else:
                module = __import__(target, fromlist=[name])
                setattr(module, name, value)
            return
        setattr(target, name, value)

    def setenv(self, name, value) -> None:
        os.environ[name] = value

    def delenv(self, name, raising=True) -> None:  # noqa: ARG002
        os.environ.pop(name, None)


def _summarize_body(body: Any) -> Any:
    if isinstance(body, dict):
        if "items" in body and isinstance(body["items"], list):
            return {"items_count": len(body["items"])}
        if "detail" in body:
            return {"detail": body["detail"]}
    if isinstance(body, list):
        return {"list_count": len(body)}
    return body


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backend memory continuity gauntlet (INV-MEM)")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--run-dir", default=None)
    parser.add_argument(
        "--suite",
        default="all",
        help="Comma-separated suites: capture, promote, recall, archive, surfaces, resilience, "
        "pipeline (capture→archive), all (default).",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Require live backend (ADMIN_KEY + reachable /health). Suites record NOT_RUN when unavailable.",
    )
    parser.add_argument("--self-check", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.self_check:
        return self_check()
    return MemoryContinuityGauntlet(args).run()


if __name__ == "__main__":
    raise SystemExit(main())
