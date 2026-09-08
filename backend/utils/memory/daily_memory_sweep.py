"""Dark, bounded once-per-local-day automatic memory sweep.

This module is an authority seam, not a scheduler.  It accepts a server-built
daily input, writes through the canonical ledger boundary, and stays completely
inert until an explicit backend authority opens it.  The completed-day producer
reads the day's finished conversation SUMMARIES as one bounded spine and runs a
single two-phase agent pass over them (the agent may pull a bounded number of
raw transcript excerpts to verify specifics before finalizing), all under an
explicit cost budget.  The onboarding cold-start channel still reads bounded
finished transcript text per conversation.

The contract is deliberately small:

* one completed user-local day per input, with at most three missed days per run;
* at most 32 candidates and 16 durable writes per day;
* stable source keys and receipts make retry after a crash an exact no-op;
* direct user statements outrank reusable agent conclusions, which outrank
  sweep inferences;
* fact candidates may be added/amended automatically, while triggers may only
  repair an existing trigger; passive behavior never creates standing intent;
* source references are metadata-only; raw pixels and image payloads are
  rejected before any canonical write;
* account-deletion, owner, canonical-generation, and cursor CAS fences fail
  closed; disabling the authority never deletes already-written user data.

The maintenance job may import the closed scheduler seam, but no current writer
is changed and every runtime call remains inert until backend authority opens.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from enum import Enum
from dataclasses import dataclass, field
import atexit
import importlib
import logging
import os
import re
import threading
from typing import Any, Dict, Iterable, List, Literal, Mapping, Optional, Sequence, Tuple, cast
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger(__name__)

from google.cloud.firestore_v1 import FieldFilter
from google.cloud import firestore
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from database.account_deletion_policy import account_deletion_blocks_access, normalize_account_deletion_status
from database.account_deletion_projection_fence import read_account_deletion_projection_fence
from database.firestore_index_registry import (
    DAILY_SWEEP_ACTIVE_FACT_ENTITY_SLOT_QUERY,
    DAILY_SWEEP_ACTIVE_FACT_ENTITY_CONTENT_QUERY,
    DAILY_SWEEP_ACTIVE_FACT_ENTITY_QUERY,
    DAILY_SWEEP_ACTIVE_FACT_SUBJECT_CONTENT_QUERY,
    DAILY_SWEEP_ACTIVE_FACT_SUBJECT_QUERY,
    DAILY_SWEEP_ACTIVE_FACT_SLOT_QUERY,
    DAILY_SWEEP_ONBOARDING_CONVERSATIONS_QUERY,
)
from database.memory_collections import MemoryCollections
from database.memory_apply_store import cleanup_expired_memory_deletion_receipts
from models.memory_apply import MemoryControlState, WriterMode
from models.memory_contracts import deterministic_contract_id
from models.product_memory import (
    LedgerWriteReason,
    MemoryItem,
    MemoryItemStatus,
    MemoryKind,
    MemorySubjectScope,
    normalized_memory_content_key,
)
from utils.free_tier_memory_policy import (
    free_tier_memory_suppression_enabled,
    memory_formation_verdict,
)
from utils.managed_compute import authorize_managed_compute
from utils.memory.canonical_memory_adapter import read_canonical_memory_item
from utils.memory.daily_memory_sweep_queue import ProcessOutcome, drain_sweep_uids
from utils.memory.knowledge_ledger import (
    LedgerProvenance,
    LedgerWrite,
    amend_fact,
    evidence_id_for_ledger_provenance,
    save_ledger_write,
)
from utils.memory.memory_system import ensure_canonical_apply_control_state
from utils.memory.memory_authority import validate_uid_for_memory_path
from utils.memory.jit_trigger_contract import compile_trigger_condition
from utils.llm.usage_tracker import Features, track_usage

# These budgets are deliberately separate from the canonical write budget.  A
# completed-day producer must prove that it read the whole bounded source
# window before the cursor can advance; it may never turn an unavailable read
# into an empty day.
MAX_COMPLETED_DAY_CONVERSATIONS = 32
MAX_COMPLETED_DAY_INPUT_CHARACTERS = 48_000
# The summary spine bounds the whole-day agent pass.  Summaries are two orders
# of magnitude smaller than transcripts, so these ceilings are effectively
# unreachable for real days; they exist so an over-budget page is still a
# provable incomplete source rather than a silent truncation.
MAX_COMPLETED_DAY_SUMMARY_CONVERSATIONS = 200
MAX_COMPLETED_DAY_SUMMARY_INPUT_CHARACTERS = 120_000
MAX_DAILY_TRANSCRIPT_FETCHES = 8
MAX_DAILY_TRANSCRIPT_FETCH_CHARACTERS = 8_000
MAX_DAILY_MEMORY_LOOKUPS = 4
MAX_SUMMARY_FALLBACK_TRANSCRIPT_CHARACTERS = 1_200
# Rows whose "summary" is a raw transcript head (no structured summary exists)
# carry this marker so the agent prompt can refuse to source standing-profile
# slots from unstructured third-party speech without transcript verification.
UNSTRUCTURED_SUMMARY_MARKER = "(unstructured transcript excerpt)"
MAX_ONBOARDING_CONVERSATIONS = 8
MAX_ONBOARDING_SCAN_PAGES = 16
MAX_ONBOARDING_INPUT_CHARACTERS = 24_000
MAX_ONBOARDING_RECEIPT_KEYS = 4_096
MAX_LEGACY_COMPAT_OCCUPANTS = 64
# The compatibility occupant proof pages through the complete cohort; a real
# long-tenured account holds hundreds of active unslotted facts per subject,
# so completeness must come from draining a cursor, not from one bounded page.
# The ceiling still fails closed on a pathological cohort.
LEGACY_COMPAT_OCCUPANT_PAGE_SIZE = 300
MAX_LEGACY_COMPAT_OCCUPANT_SCAN = 5000
MODEL_COST_PER_1K_INPUT_CHARACTERS_USD = 0.002
ONBOARDING_CONSUMED_STATE_PATH = "memory_control/daily_memory_sweep_onboarding"
ONBOARDING_PERMANENT_RECEIPT_PREFIX = "onboarding_source_"
ONBOARDING_SOURCE_RECEIPT_PATH = "daily_memory_sweep_onboarding_sources"
ONBOARDING_STAGED_CANDIDATE_PATH = "daily_memory_sweep_onboarding_staged"
DAILY_SUMMARY_STAGED_CANDIDATE_PATH = "daily_memory_sweep_daily_summary_staged"
DAILY_SUMMARY_STAGE_SCHEMA_VERSION = "daily_memory_sweep_daily_summary_stage.v2"
MODEL_INVOCATION_PATH = "daily_memory_sweep_model_invocations"
# This collection is intentionally outside ``users/{uid}``.  Account deletion
# recursively removes every user subcollection, but an in-flight provider call
# must retain a content-free identity fence so a source retry cannot charge the
# same logical invocation again.
MODEL_INVOCATION_FENCE_COLLECTION = "daily_memory_sweep_model_invocation_fences"
MODEL_INVOCATION_SCHEMA_VERSION = "daily_memory_sweep_model_invocation.v1"

SCHEMA_VERSION = "daily_memory_sweep.v1"
CURSOR_SCHEMA_VERSION = "daily_memory_sweep_cursor.v1"
RECEIPT_SCHEMA_VERSION = "daily_memory_sweep_receipt.v1"

MAX_CATCH_UP_DAYS = 3
MAX_CANDIDATES_PER_DAY = 32
MAX_ONBOARDING_SOURCE_KEYS_PER_PACKET = MAX_CANDIDATES_PER_DAY
MAX_ONBOARDING_STAGED_CANDIDATES = MAX_CANDIDATES_PER_DAY
MAX_WRITES_PER_DAY = 16
MAX_CONTENT_CHARACTERS = 1_200
MAX_SOURCE_ID_CHARACTERS = 256
MAX_SOURCE_REFS = 8
MAX_SOURCE_REF_CHARACTERS = 256
MAX_TRIGGER_CONDITION_KEYS = 12
DAILY_MEMORY_SWEEP_ENABLED_ENV = "MEMORY_DAILY_MEMORY_SWEEP_ENABLED"
DAILY_MEMORY_SWEEP_KILL_SWITCH_ENV = "MEMORY_DAILY_MEMORY_SWEEP_KILL_SWITCH"
DAILY_MEMORY_SWEEP_MODEL_ENABLED_ENV = "MEMORY_DAILY_MEMORY_SWEEP_MODEL_ENABLED"
DAILY_MEMORY_SWEEP_MODEL_NAME_ENV = "MEMORY_DAILY_MEMORY_SWEEP_MODEL_NAME"
DAILY_MEMORY_SWEEP_MAX_MODEL_CANDIDATES_ENV = "MEMORY_DAILY_MEMORY_SWEEP_MAX_MODEL_CANDIDATES"
DAILY_MEMORY_SWEEP_MAX_MODEL_COST_USD_ENV = "MEMORY_DAILY_MEMORY_SWEEP_MAX_MODEL_COST_USD"
DAILY_MEMORY_SWEEP_COHORT_ENABLED_ENV = "MEMORY_DAILY_MEMORY_SWEEP_COHORT_ENABLED"
DAILY_MEMORY_SWEEP_COHORT_NAME_ENV = "MEMORY_DAILY_MEMORY_SWEEP_COHORT_NAME"
DAILY_MEMORY_SWEEP_COHORT_FLAG_ENV = "MEMORY_DAILY_MEMORY_SWEEP_COHORT_FLAG"
DAILY_MEMORY_SWEEP_COHORT_TIMEOUT_ENV = "MEMORY_DAILY_MEMORY_SWEEP_COHORT_TIMEOUT_SECONDS"
DAILY_MEMORY_SWEEP_TIMEZONE_RECONCILIATION_ENV = "MEMORY_DAILY_MEMORY_SWEEP_TIMEZONE_RECONCILIATION_ENABLED"

# The QA run seam is intentionally separate from the ordinary scheduler
# controls.  A caller must provide every QA-only gate below; setting a run id
# alone can never open the production sweep or its cohort.
QA_SWEEP_RUN_ID_ENV = "OMI_JIT_QA_SWEEP_RUN_ID"
QA_SWEEP_ADMISSION_ENV = "OMI_JIT_QA_SWEEP_ADMISSION"
QA_SWEEP_PROJECT = "based-hardware-dev"
QA_SWEEP_DATABASE = "jit-qa"
QA_SWEEP_UID = "vi7SA9ckQCe4ccobWNxlbdcNdC23"
QA_SWEEP_COHORT = "jit-qa-sweep-v1"
QA_SWEEP_MODEL_NAME = "gpt-5.6-luna"
QA_SWEEP_MAX_MODEL_CANDIDATES = 1
QA_SWEEP_MAX_MODEL_COST_USD = 0.05
# Qualification uses the same completed-day producer with an explicit tighter
# envelope.  Zero phase-B requests/lookups makes one provider call the real
# maximum for one completed day, instead of pricing the production envelope as
# if it were a cheap single call.
QA_SWEEP_MAX_CATCH_UP_DAYS = 1
QA_SWEEP_MAX_SUMMARY_CONVERSATIONS = 1
QA_SWEEP_MAX_SUMMARY_INPUT_CHARACTERS = 2_000
QA_SWEEP_MAX_TRANSCRIPT_FETCHES = 0
QA_SWEEP_MAX_TRANSCRIPT_FETCH_CHARACTERS = 0
QA_SWEEP_MAX_MEMORY_LOOKUPS = 0
QA_SWEEP_MAX_SDK_RETRIES = 0
QA_SWEEP_MAX_GATEWAY_ATTEMPTS = 1
QA_SWEEP_MAX_PROVIDER_CALLS = 1
# The deployed memories route is gpt-5.6-luna at $0.20/M input and $1.20/M
# output.  The parser instructions alone are about 9.6K UTF-8 bytes, so an
# 8K input cap would reject every real QA request.  12K input + 256 output
# reserves about $0.0028, below the $0.05 run envelope; the gateway enforces
# these same headers against the provider request and settles actual usage.
QA_SWEEP_MAX_INPUT_TOKENS = 12_288
QA_SWEEP_MAX_OUTPUT_TOKENS = 256
QA_SWEEP_MAX_SPEND_MICRO_USD = 50_000
QA_SWEEP_JIT_CONTRACT_VERSION = "jit-cloud-qa-v1"
QA_SWEEP_RECEIPT_SCHEMA_VERSION = "omi.jit.qa.daily-memory-sweep-run.v1"
QA_SWEEP_OUTPUT_SCHEMA_VERSION = "omi.jit.qa.daily-memory-sweep-output.v1"
QA_SWEEP_RUN_COLLECTION = "jit_qa_sweep_runs"
QA_SWEEP_OUTPUT_SUBCOLLECTION = "outputs"
QA_SWEEP_RUN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,47}$")

RECEIPT_LEASE = timedelta(minutes=10)
MODEL_INVOCATION_LEASE = timedelta(minutes=15)
STAGED_CANDIDATE_RETENTION = timedelta(days=7)
MAX_AUTHORITATIVE_OCCUPANTS = 2

# Cohort assignment is a read-only control-plane operation, but creating a
# PostHog SDK client for every UID leaks transports and turns a bounded sweep
# into an unbounded client factory.  Keep one client per (key, host, timeout)
# and close each transport when the worker exits.
_POSTHOG_CLIENTS: Dict[Tuple[str, str, float], Any] = {}
_POSTHOG_CLIENTS_LOCK = threading.RLock()
_MODEL_INVOCATION_LOCK = threading.RLock()

_ID_RE = re.compile(r"[a-z0-9][a-z0-9._:-]{0,127}")
_FORBIDDEN_SOURCE_MARKERS = (
    "base64",
    "data:image",
    "pixel",
    "raw_image",
    "raw-image",
    "screenshot_bytes",
    "image_bytes",
)
_FORBIDDEN_PAYLOAD_MARKERS = (
    "base64",
    "data:image",
    "image_bytes",
    "raw_image",
    "raw-image",
    "pixel",
    "screenshot",
    "bytes",
    "image",
    "raw",
)
_ALLOWED_SOURCE_TYPES = frozenset(
    {
        "conversation",
        "daily_summary",
        "explicit_user_statement",
        "onboarding",
        "agent_conclusion",
        "screen_metadata",
    }
)


def _reject_payload(value: Any, *, depth: int = 0, nodes: int = 0) -> None:
    """Reject image/raw/base64-shaped values recursively before compilation.

    Trigger conditions are metadata selectors, never a transport for pixels or
    opaque model payloads.  The recursive walk is intentionally stricter than
    the canonical model's JSON check and bounded to keep validation cheap.
    """

    if depth > 8 or nodes > 128:
        raise ValueError("trigger condition nesting exceeds the daily sweep budget")
    if isinstance(value, (bytes, bytearray, memoryview)):
        raise ValueError("raw image/pixel payloads are not valid trigger metadata")
    if isinstance(value, str):
        lowered = value.casefold()
        if any(marker in lowered for marker in _FORBIDDEN_PAYLOAD_MARKERS):
            raise ValueError("raw image/base64 payloads are not valid trigger metadata")
        if len(value) > 300:
            raise ValueError("trigger condition values are oversized")
        return
    if isinstance(value, Mapping):
        if len(value) > MAX_TRIGGER_CONDITION_KEYS:
            raise ValueError("trigger condition exceeds the daily sweep budget")
        for key, item in value.items():
            if not isinstance(key, str) or not key.strip() or len(key) > 64:
                raise ValueError("trigger condition keys must be bounded strings")
            lowered_key = key.casefold()
            if any(marker in lowered_key for marker in _FORBIDDEN_PAYLOAD_MARKERS):
                raise ValueError("raw image/base64 fields are not valid trigger metadata")
            _reject_payload(item, depth=depth + 1, nodes=nodes + 1)
        return
    if isinstance(value, (list, tuple, set, frozenset)):
        if len(value) > 128:
            raise ValueError("trigger condition has too many nested values")
        for item in value:
            _reject_payload(item, depth=depth + 1, nodes=nodes + 1)
        return
    if value is not None and not isinstance(value, (bool, int, float)):
        raise ValueError("trigger condition contains an unsupported value")


class SweepAuthorityState(BaseModel):
    """Backend-owned activation and kill-switch state.

    A client or candidate cannot set either field.  Both must be true to write;
    the separate kill switch is intentionally checked on every invocation.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = False
    kill_switch_active: bool = False
    authority_version: str = Field(default="v1", min_length=1, max_length=32)

    @property
    def may_write(self) -> bool:
        return self.enabled and not self.kill_switch_active


class DailySweepCohortAuthority(BaseModel):
    """Read-only per-user rollout seam (for example a PostHog flag read).

    The sweep never writes PostHog.  A deployment may inject a resolver that
    reads the cohort assignment; when the seam is enabled without a resolver,
    the scheduler fails closed for every user.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = False
    cohort_name: str = ""


class DailySweepCohortDecision(str, Enum):
    """Tri-state result for the read-only cohort control-plane lookup."""

    enabled = "enabled"
    disabled = "disabled"
    unavailable = "unavailable"

    def __bool__(self) -> bool:
        # Preserve the old truthiness seam for small adapters while keeping
        # outage distinct from a definite false assignment.
        return self is DailySweepCohortDecision.enabled


def daily_memory_sweep_cohort_authority_from_environment() -> DailySweepCohortAuthority:
    truthy = {"1", "true", "yes", "on"}
    return DailySweepCohortAuthority(
        enabled=os.getenv(DAILY_MEMORY_SWEEP_COHORT_ENABLED_ENV, "false").casefold() in truthy,
        # The feature-flag binding is intentionally the only deployment input;
        # a legacy free-form cohort-name alias could reopen an unrestricted
        # rollout under a different name.
        cohort_name=os.getenv(DAILY_MEMORY_SWEEP_COHORT_FLAG_ENV, "").strip(),
    )


def read_daily_memory_sweep_cohort_assignment(
    uid: str,
    cohort_name: str,
    *,
    resolver: Optional[Any] = None,
) -> DailySweepCohortDecision:
    """Read-only per-user cohort seam used by the maintenance entrypoint.

    The default is deliberately fail-closed.  A deployment may inject a
    read-only PostHog resolver at this function boundary; this code never
    creates flags, identifies users, or mutates PostHog state.
    """

    normalized_uid = (uid or "").strip()
    normalized_flag = (cohort_name or "").strip()
    if not normalized_uid or not normalized_flag:
        return DailySweepCohortDecision.unavailable
    # Tests and the maintenance adaptor inject a read-only resolver.  The
    # production fallback is lazy so importing this module never constructs a
    # client or performs network I/O.  No identify/capture call is made and
    # the user id comes only from the server-side inventory.
    reader = resolver
    if reader is None:
        api_key = (os.getenv("POSTHOG_PROJECT_API_KEY") or os.getenv("POSTHOG_API_KEY") or "").strip()
        host = (os.getenv("POSTHOG_HOST") or "https://app.posthog.com").strip()
        if not api_key or not host:
            return DailySweepCohortDecision.unavailable
        try:
            posthog_module = importlib.import_module("posthog")
            client_type = getattr(posthog_module, "Posthog")
            timeout = float(os.getenv(DAILY_MEMORY_SWEEP_COHORT_TIMEOUT_ENV, "3"))
            if timeout <= 0 or timeout > 10:
                return DailySweepCohortDecision.unavailable
            client_key = (api_key, host, timeout)
            with _POSTHOG_CLIENTS_LOCK:
                reader = _POSTHOG_CLIENTS.get(client_key)
                if reader is None:
                    reader = client_type(
                        project_api_key=api_key,
                        host=host,
                        feature_flags_request_timeout_seconds=timeout,
                    )
                    _POSTHOG_CLIENTS[client_key] = reader
        except Exception:
            return DailySweepCohortDecision.unavailable
    try:
        get_flag = getattr(reader, "get_feature_flag", None)
        if callable(get_flag):
            result = get_flag(
                normalized_flag,
                normalized_uid,
                only_evaluate_locally=False,
                send_feature_flag_events=False,
            )
        elif callable(reader):
            result = reader(normalized_uid, normalized_flag)
        else:
            return DailySweepCohortDecision.unavailable
    except Exception:
        return DailySweepCohortDecision.unavailable
    # A boolean true is the only accepted assignment.  String variants are
    # deliberately not treated as enrollment: a flag configured with a named
    # variant must use a server-side boolean rollout or stay closed.
    if result is True:
        return DailySweepCohortDecision.enabled
    if result is False:
        return DailySweepCohortDecision.disabled
    return DailySweepCohortDecision.unavailable


def close_daily_memory_sweep_cohort_clients() -> None:
    """Close cached PostHog transports at worker shutdown.

    The SDK has used both ``shutdown`` and ``close`` across released versions;
    invoke whichever lifecycle method the installed client exposes. Closing is
    best effort and never changes the fail-closed assignment result.
    """

    with _POSTHOG_CLIENTS_LOCK:
        clients = tuple(_POSTHOG_CLIENTS.values())
        _POSTHOG_CLIENTS.clear()
    for client in clients:
        for method_name in ("shutdown", "close"):
            method = getattr(client, method_name, None)
            if callable(method):
                try:
                    method()
                except Exception:
                    pass
                break


atexit.register(close_daily_memory_sweep_cohort_clients)


class DailySweepModelAuthority(BaseModel):
    """Explicit authority for the bounded completed-day candidate producer.

    ``model_name`` is checked against the configured ``memories`` route before
    the built-in extractor is called.  The optional extractor injection is for
    deterministic emulator/unit tests; production uses the same existing
    memory model route and never accepts a client-selected model.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = False
    model_name: str = "disabled"
    max_candidates: int = Field(default=8, ge=0, le=MAX_CANDIDATES_PER_DAY)
    max_cost_usd: float = Field(default=0.0, ge=0.0, le=10.0)

    @property
    def route_is_budgeted(self) -> bool:
        return self.enabled and self.model_name not in {"", "disabled"} and self.max_cost_usd > 0


def daily_memory_sweep_model_authority_from_environment() -> DailySweepModelAuthority:
    truthy = {"1", "true", "yes", "on"}
    raw_candidates = os.getenv(DAILY_MEMORY_SWEEP_MAX_MODEL_CANDIDATES_ENV, "8")
    raw_cost = os.getenv(DAILY_MEMORY_SWEEP_MAX_MODEL_COST_USD_ENV, "0")
    try:
        max_candidates = int(raw_candidates)
        max_cost = float(raw_cost)
    except ValueError as exc:
        raise ValueError("daily sweep model budget environment is malformed") from exc
    return DailySweepModelAuthority(
        enabled=os.getenv(DAILY_MEMORY_SWEEP_MODEL_ENABLED_ENV, "false").casefold() in truthy,
        model_name=os.getenv(DAILY_MEMORY_SWEEP_MODEL_NAME_ENV, "disabled").strip() or "disabled",
        max_candidates=max_candidates,
        max_cost_usd=max_cost,
    )


def validate_qa_sweep_run_id(run_id: str) -> str:
    normalized = (run_id or "").strip()
    if not QA_SWEEP_RUN_ID_RE.fullmatch(normalized):
        raise ValueError("QA sweep run id must match [a-z0-9][a-z0-9_-]{0,47}")
    return normalized


def qa_sweep_run_id_from_environment(environ: Optional[Mapping[str, str]] = None) -> Optional[str]:
    env = environ if environ is not None else os.environ
    raw = env.get(QA_SWEEP_RUN_ID_ENV, "").strip()
    return validate_qa_sweep_run_id(raw) if raw else None


def validate_qa_sweep_environment(environ: Optional[Mapping[str, str]] = None) -> str:
    """Require the complete, closed-world override set for one QA sweep run."""

    env = environ if environ is not None else os.environ
    run_id = qa_sweep_run_id_from_environment(env)
    if not run_id:
        raise ValueError(f"{QA_SWEEP_RUN_ID_ENV} is required for a QA sweep run")
    required = {
        "OMI_ENV_STAGE": "dev",
        "GOOGLE_CLOUD_PROJECT": QA_SWEEP_PROJECT,
        "GCLOUD_PROJECT": QA_SWEEP_PROJECT,
        "OMI_FIRESTORE_DATA_PLANE_PROJECT": QA_SWEEP_PROJECT,
        "FIRESTORE_DATABASE_ID": QA_SWEEP_DATABASE,
        "FIREBASE_AUTH_PROJECT_ID": "based-hardware",
        "MEMORY_ENABLED": "on",
        "OMI_JIT_QA_AUTH_ONLY": "true",
        "OMI_JIT_QA_UID_ALLOWLIST": QA_SWEEP_UID,
        QA_SWEEP_ADMISSION_ENV: "true",
        DAILY_MEMORY_SWEEP_ENABLED_ENV: "true",
        DAILY_MEMORY_SWEEP_KILL_SWITCH_ENV: "false",
        DAILY_MEMORY_SWEEP_MODEL_ENABLED_ENV: "true",
        DAILY_MEMORY_SWEEP_MODEL_NAME_ENV: QA_SWEEP_MODEL_NAME,
        DAILY_MEMORY_SWEEP_MAX_MODEL_CANDIDATES_ENV: str(QA_SWEEP_MAX_MODEL_CANDIDATES),
        DAILY_MEMORY_SWEEP_MAX_MODEL_COST_USD_ENV: f"{QA_SWEEP_MAX_MODEL_COST_USD:g}",
        DAILY_MEMORY_SWEEP_COHORT_ENABLED_ENV: "true",
        DAILY_MEMORY_SWEEP_COHORT_FLAG_ENV: QA_SWEEP_COHORT,
        DAILY_MEMORY_SWEEP_TIMEZONE_RECONCILIATION_ENV: "false",
    }
    for name, expected in required.items():
        if env.get(name, "").strip().casefold() != expected.casefold():
            raise ValueError(f"QA sweep requires {name}={expected!r}")
    if env.get("FIRESTORE_EMULATOR_HOST", "").strip():
        raise ValueError("QA sweep proof must use named Cloud Firestore")
    if env.get("SERVICE_ACCOUNT_JSON", "").strip() or env.get("FIREBASE_AUTH_CREDENTIALS_PATH", "").strip():
        raise ValueError("QA sweep proof cannot select customer Firebase credentials")
    return run_id


def qa_sweep_cohort_authorizer(uid: str, cohort_name: str = "") -> DailySweepCohortDecision:
    """Admit only the fixed QA account under the explicit QA capability gate."""

    try:
        validate_qa_sweep_environment()
    except ValueError:
        return DailySweepCohortDecision.unavailable
    if uid != QA_SWEEP_UID or cohort_name != QA_SWEEP_COHORT:
        return DailySweepCohortDecision.unavailable
    return DailySweepCohortDecision.enabled


class SweepFenceBlocked(RuntimeError):
    """A durable deletion or generation fence closed during a transaction."""


class SweepAuthoritativeQueryUnavailable(RuntimeError):
    """A bounded canonical query could not prove the occupant set."""


class SweepAuthority(str, Enum):
    direct_user_statement = "direct_user_statement"
    agent_reusable_conclusion = "agent_reusable_conclusion"
    sweep_inference = "sweep_inference"

    @property
    def rank(self) -> int:
        return {
            SweepAuthority.sweep_inference: 1,
            SweepAuthority.agent_reusable_conclusion: 2,
            SweepAuthority.direct_user_statement: 3,
        }[self]

    @property
    def ledger_reason(self) -> LedgerWriteReason:
        return {
            SweepAuthority.direct_user_statement: LedgerWriteReason.direct_user_statement,
            SweepAuthority.agent_reusable_conclusion: LedgerWriteReason.agent_reusable_conclusion,
            SweepAuthority.sweep_inference: LedgerWriteReason.daily_reconciliation,
        }[self]


class DailySweepCandidate(BaseModel):
    """One server-built, bounded candidate from a completed local day."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_id: str
    kind: Literal["fact", "trigger"]
    operation: Literal["add", "amend", "repair"] = "add"
    content: str
    source_id: str
    source_type: str
    source_version: str = "v1"
    source_refs: Tuple[str, ...] = ()
    authority: SweepAuthority = SweepAuthority.sweep_inference
    target_memory_id: Optional[str] = None
    slot: Optional[str] = None
    subject_scope: MemorySubjectScope = MemorySubjectScope.primary_user
    subject_entity_id: Optional[str] = None
    trigger_condition: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("candidate_id", "target_memory_id", "subject_entity_id")
    @classmethod
    def validate_ids(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized or not _ID_RE.fullmatch(normalized.casefold()):
            raise ValueError("candidate identifiers must be bounded canonical ids")
        return normalized

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        normalized = " ".join((value or "").split())
        if not normalized:
            raise ValueError("candidate content is required")
        if len(normalized) > MAX_CONTENT_CHARACTERS:
            raise ValueError("candidate content exceeds the daily sweep budget")
        if any(marker in normalized.casefold() for marker in _FORBIDDEN_SOURCE_MARKERS):
            raise ValueError("raw image/pixel payloads are not valid sweep content")
        return normalized

    @field_validator("source_id", "source_type", "source_version")
    @classmethod
    def validate_source_identity(cls, value: str, info) -> str:
        normalized = (value or "").strip()
        limit = MAX_SOURCE_ID_CHARACTERS if info.field_name == "source_id" else 64
        if not normalized or len(normalized) > limit:
            raise ValueError("source identity is missing or oversized")
        lowered = normalized.casefold()
        if any(marker in lowered for marker in _FORBIDDEN_SOURCE_MARKERS):
            raise ValueError("raw image/pixel payloads are not valid sweep sources")
        if info.field_name == "source_type" and normalized not in _ALLOWED_SOURCE_TYPES:
            raise ValueError("unsupported sweep source type")
        return normalized

    @field_validator("source_refs")
    @classmethod
    def validate_source_refs(cls, value: Tuple[str, ...]) -> Tuple[str, ...]:
        normalized = tuple(sorted({ref.strip() for ref in value if ref and ref.strip()}))
        if len(normalized) > MAX_SOURCE_REFS:
            raise ValueError("source_refs exceed the daily sweep budget")
        for ref in normalized:
            lowered = ref.casefold()
            if len(ref) > MAX_SOURCE_REF_CHARACTERS or any(marker in lowered for marker in _FORBIDDEN_SOURCE_MARKERS):
                raise ValueError("source_refs must be bounded metadata-only references")
        return normalized

    @field_validator("slot")
    @classmethod
    def validate_slot(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = "_".join(value.strip().lower().replace("-", "_").split())
        if not normalized or len(normalized) > 64:
            raise ValueError("slot must be a bounded non-empty name")
        return normalized

    @field_validator("trigger_condition")
    @classmethod
    def validate_trigger_condition(cls, value: Dict[str, Any]) -> Dict[str, Any]:
        _reject_payload(value)
        if len(value) > MAX_TRIGGER_CONDITION_KEYS:
            raise ValueError("trigger condition exceeds the daily sweep budget")
        return value

    @model_validator(mode="after")
    def validate_semantics(self) -> "DailySweepCandidate":
        if self.subject_scope == MemorySubjectScope.third_party and not self.subject_entity_id:
            raise ValueError("third-party sweep facts require subject_entity_id")
        if self.kind == "fact" and self.trigger_condition:
            raise ValueError("fact candidates cannot carry trigger conditions")
        if self.kind == "trigger" and self.operation != "repair":
            raise ValueError("the daily sweep may repair existing triggers but never invent them")
        if self.operation in {"amend", "repair"} and not self.target_memory_id:
            raise ValueError("amend/repair candidates require target_memory_id")
        if self.authority == SweepAuthority.direct_user_statement and self.source_type not in {
            "explicit_user_statement",
            "onboarding",
        }:
            raise ValueError("direct authority requires an explicit-user-statement or onboarding source")
        if self.kind == "trigger":
            # Compile at the boundary, then persist the normalized strict schema
            # so a future evaluator never receives an unvalidated ad-hoc map.
            object.__setattr__(
                self, "trigger_condition", compile_trigger_condition(self.trigger_condition).as_condition()
            )
        return self

    @property
    def source_key(self) -> str:
        return f"{self.source_type}:{self.source_id}:{self.candidate_id}"

    def digest(self) -> str:
        return deterministic_contract_id("daily-memory-sweep-candidate", self.model_dump(mode="json"))


class DailySweepInput(BaseModel):
    """Immutable input packet for one completed user-local date."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = SCHEMA_VERSION
    uid: str
    local_date: date
    account_generation: int
    source_generation: int
    # Sweep-owned receipt namespace.  ``source_generation`` remains the live
    # canonical fence; this generation must not be advanced by a timezone
    # preference change in the global canonical control document.
    sweep_generation: int = 1
    timezone_name: str
    window_id: str
    window_start_utc: datetime
    window_end_utc: datetime
    window_kind: Literal["local_day", "timezone_transition"] = "local_day"
    complete: bool
    candidates: Tuple[DailySweepCandidate, ...] = ()
    # The producer attests the onboarding sources represented by this packet,
    # including sources that yielded zero candidates.  Consumption is done
    # after all candidate receipts commit, never once per candidate.
    onboarding_source_keys: Tuple[str, ...] = ()
    onboarding_source_progress: Dict[str, int] = Field(default_factory=dict)
    eligibility_proof: Literal["completed_transcript_v1", "none"] = "none"

    @field_validator("uid")
    @classmethod
    def validate_uid(cls, value: str) -> str:
        normalized = (value or "").strip()
        if not normalized:
            raise ValueError("uid is required")
        return normalized

    @field_validator("account_generation", "source_generation", "sweep_generation")
    @classmethod
    def validate_generations(cls, value: int) -> int:
        if value < 0:
            raise ValueError("generation must be nonnegative")
        return value

    @field_validator("window_start_utc", "window_end_utc")
    @classmethod
    def validate_window_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("input window timestamps must be timezone-aware")
        return value.astimezone(timezone.utc)

    @field_validator("candidates")
    @classmethod
    def validate_candidate_count(cls, value: Tuple[DailySweepCandidate, ...]) -> Tuple[DailySweepCandidate, ...]:
        if len(value) > MAX_CANDIDATES_PER_DAY:
            raise ValueError("daily sweep candidate window exceeded")
        return value

    @field_validator("onboarding_source_keys")
    @classmethod
    def validate_onboarding_source_keys(cls, value: Tuple[str, ...]) -> Tuple[str, ...]:
        normalized = tuple(sorted({item.strip() for item in value if item.strip()}))
        if len(normalized) > MAX_CANDIDATES_PER_DAY:
            raise ValueError("daily sweep onboarding source budget exceeded")
        if any(not item.startswith("onboarding:") or len(item) > MAX_SOURCE_ID_CHARACTERS for item in normalized):
            raise ValueError("invalid onboarding source key")
        return normalized

    @field_validator("onboarding_source_progress")
    @classmethod
    def validate_onboarding_source_progress(cls, value: Dict[str, int]) -> Dict[str, int]:
        normalized = {str(key).strip(): int(offset) for key, offset in value.items()}
        if len(normalized) > MAX_CANDIDATES_PER_DAY or any(
            not key.startswith("onboarding:") or offset < 0 for key, offset in normalized.items()
        ):
            raise ValueError("invalid onboarding source progress")
        return normalized

    @model_validator(mode="after")
    def validate_schema(self) -> "DailySweepInput":
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("unsupported daily sweep input schema")
        try:
            ZoneInfo(self.timezone_name)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("input timezone must be an installed IANA timezone") from exc
        expected = completed_local_day_window(self.local_date, self.timezone_name)
        exact_window = (
            self.window_id == expected.window_id
            and self.window_start_utc == expected.start_utc
            and self.window_end_utc == expected.end_utc
        )
        transition_window = False
        if self.window_kind == "timezone_transition" and self.window_start_utc < self.window_end_utc:
            try:
                transition = timezone_transition_window(
                    self.local_date,
                    self.timezone_name,
                    coverage_start_utc=self.window_start_utc,
                )
                transition_window = self.window_id == transition.window_id and self.window_end_utc == transition.end_utc
            except ValueError:
                transition_window = False
        if not self.complete or not (exact_window if self.window_kind == "local_day" else transition_window):
            raise ValueError("input must be an immutable complete exact local-day packet")
        return self


class DailySweepSkip(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_id: str
    reason: Literal[
        "duplicate_candidate",
        "lower_authority",
        "missing_target",
        "target_not_active",
        "target_kind_mismatch",
        "target_not_explicit_trigger",
        "source_key_conflict",
        "invalid_candidate",
        "existing_active_slot",
        "existing_active_subject",
    ]


class DailySweepPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = SCHEMA_VERSION
    uid: str
    local_date: date
    idempotency_key: str
    candidates: Tuple[DailySweepCandidate, ...] = ()
    skipped: Tuple[DailySweepSkip, ...] = ()


class DailySweepCursor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = CURSOR_SCHEMA_VERSION
    uid: str
    account_generation: int
    source_generation: int
    sweep_generation: int = 1
    generation: int = 0
    timezone_name: Optional[str] = None
    last_completed_local_date: Optional[date] = None
    last_completed_window_id: Optional[str] = None
    last_completed_window_start_utc: Optional[datetime] = None
    last_completed_window_end_utc: Optional[datetime] = None
    pending_transition_local_date: Optional[date] = None
    pending_transition_window_id: Optional[str] = None
    pending_transition_start_utc: Optional[datetime] = None
    pending_transition_end_utc: Optional[datetime] = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator(
        "updated_at",
        "last_completed_window_start_utc",
        "last_completed_window_end_utc",
        "pending_transition_start_utc",
        "pending_transition_end_utc",
    )
    @classmethod
    def validate_timestamp(cls, value: Optional[datetime]) -> Optional[datetime]:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("cursor timestamps must be timezone-aware")
        return value.astimezone(timezone.utc)

    @field_validator("timezone_name")
    @classmethod
    def validate_timezone_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("cursor timezone must be an installed IANA timezone") from exc
        return value

    @model_validator(mode="after")
    def validate_window_identity(self) -> "DailySweepCursor":
        if self.last_completed_local_date is None:
            if any(
                (
                    self.last_completed_window_id,
                    self.last_completed_window_start_utc,
                    self.last_completed_window_end_utc,
                )
            ):
                raise ValueError("cursor window identity requires a completed local date")
        elif not (
            self.timezone_name
            and self.last_completed_window_id
            and self.last_completed_window_start_utc
            and self.last_completed_window_end_utc
        ):
            raise ValueError("completed cursor rows require an exact UTC window identity")
        transition_values = (
            self.pending_transition_local_date,
            self.pending_transition_window_id,
            self.pending_transition_start_utc,
            self.pending_transition_end_utc,
        )
        if any(value is not None for value in transition_values) and not all(
            value is not None for value in transition_values
        ):
            raise ValueError("timezone transition cursor rows require an exact pending window identity")
        if (
            self.pending_transition_start_utc is not None
            and self.pending_transition_end_utc is not None
            and self.pending_transition_end_utc <= self.pending_transition_start_utc
        ):
            raise ValueError("timezone transition window must advance in UTC")
        if any(value is not None for value in transition_values):
            if self.last_completed_window_end_utc is None:
                raise ValueError("timezone transition requires a completed UTC coverage anchor")
            if self.pending_transition_start_utc != self.last_completed_window_end_utc:
                raise ValueError("timezone transition must begin at the completed UTC coverage end")
            pending_local_date = self.pending_transition_local_date
            pending_start_utc = self.pending_transition_start_utc
            if pending_local_date is None or pending_start_utc is None or self.timezone_name is None:
                raise ValueError("timezone transition cursor window is incomplete")
            try:
                expected_transition = timezone_transition_window(
                    pending_local_date,
                    self.timezone_name,
                    coverage_start_utc=pending_start_utc,
                )
            except (TypeError, ValueError) as exc:
                raise ValueError("timezone transition cursor window is invalid") from exc
            if (
                self.pending_transition_window_id != expected_transition.window_id
                or self.pending_transition_end_utc != expected_transition.end_utc
            ):
                raise ValueError("timezone transition cursor window identity mismatch")
        return self


class DailySweepOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = SCHEMA_VERSION
    uid: str
    status: Literal["disabled", "not_due", "blocked", "committed"]
    completed_local_dates: Tuple[date, ...] = ()
    committed_count: int = 0
    idempotent_count: int = 0
    skipped_count: int = 0
    blocked_reason: Optional[str] = None
    telemetry: Dict[str, int | str] = Field(default_factory=dict)


@dataclass(frozen=True)
class CompletedLocalDayWindow:
    start_utc: datetime
    end_utc: datetime
    window_id: str


def completed_local_day_window(local_date: date, timezone_name: str) -> CompletedLocalDayWindow:
    """Return the exact UTC half-open window for one local calendar day.

    ZoneInfo conversion intentionally preserves 23-hour spring-forward and
    25-hour fall-back days.  A timezone change while a cursor is non-empty is
    fail-closed by the runner: an operator must reconcile/reset the cursor, so
    overlap is never double-processed and a gap is never silently skipped.
    """

    try:
        zone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("timezone_name must be a valid IANA timezone") from exc
    start = datetime.combine(local_date, time.min, tzinfo=zone).astimezone(timezone.utc)
    end = datetime.combine(local_date + timedelta(days=1), time.min, tzinfo=zone).astimezone(timezone.utc)
    if end <= start:
        raise ValueError("local-day window must advance in UTC")
    window_id = deterministic_contract_id(
        "daily-memory-sweep-window",
        {
            "local_date": local_date.isoformat(),
            "timezone": timezone_name,
            "start_utc": start.isoformat(),
            "end_utc": end.isoformat(),
        },
    )
    return CompletedLocalDayWindow(start_utc=start, end_utc=end, window_id=window_id)


def timezone_transition_window(
    local_date: date,
    timezone_name: str,
    *,
    coverage_start_utc: datetime,
) -> CompletedLocalDayWindow:
    """Build the one bounded bridge window after a timezone preference change.

    The new zone's local day ending at ``local_date + 1 midnight`` can begin
    before or after the prior zone's UTC coverage end.  Clipping its start to
    that prior end gives the first post-change packet a half-open interval
    contiguous with the already completed history; subsequent new-zone days
    use ordinary exact local-day windows.
    """

    expected = completed_local_day_window(local_date, timezone_name)
    if coverage_start_utc.tzinfo is None or coverage_start_utc.utcoffset() is None:
        raise ValueError("coverage_start_utc must be timezone-aware")
    start = coverage_start_utc.astimezone(timezone.utc)
    if start >= expected.end_utc:
        raise ValueError("timezone transition bridge must end after its coverage start")
    window_id = deterministic_contract_id(
        "daily-memory-sweep-timezone-transition-window",
        {
            "local_date": local_date.isoformat(),
            "timezone": timezone_name,
            "start_utc": start.isoformat(),
            "end_utc": expected.end_utc.isoformat(),
        },
    )
    return CompletedLocalDayWindow(start_utc=start, end_utc=expected.end_utc, window_id=window_id)


def _plan_id(uid: str, local_date: date) -> str:
    return "daily-memory-sweep:" + deterministic_contract_id(
        "daily-memory-sweep", {"uid": uid, "local_date": local_date.isoformat()}
    )


def _semantic_key(candidate: DailySweepCandidate) -> Tuple[str, str, str, str]:
    return (
        candidate.kind,
        candidate.subject_scope.value,
        candidate.subject_entity_id or "",
        candidate.target_memory_id or candidate.slot or candidate.content.casefold(),
    )


def plan_daily_memory_sweep(packet: DailySweepInput) -> DailySweepPlan:
    """Deterministically deduplicate candidates and apply authority ordering."""

    uid = packet.uid.strip()
    if not uid:
        raise ValueError("uid is required")
    by_source: Dict[str, DailySweepCandidate] = {}
    skipped: List[DailySweepSkip] = []
    # Sort before reducing so equal-authority input order cannot change the
    # selected winner (including malformed producer retries with one source key).
    for candidate in sorted(packet.candidates, key=lambda item: (item.source_key, item.digest())):
        key = candidate.source_key
        if key in by_source:
            prior = by_source[key]
            if candidate.digest() == prior.digest():
                skipped.append(DailySweepSkip(candidate_id=candidate.candidate_id, reason="duplicate_candidate"))
            elif candidate.digest() > prior.digest():
                by_source[key] = candidate
                skipped.append(DailySweepSkip(candidate_id=prior.candidate_id, reason="source_key_conflict"))
            else:
                skipped.append(DailySweepSkip(candidate_id=candidate.candidate_id, reason="source_key_conflict"))
            continue
        by_source[key] = candidate

    selected: Dict[Tuple[str, str, str, str], DailySweepCandidate] = {}
    for candidate in sorted(by_source.values(), key=lambda item: (item.source_key, item.digest())):
        semantic = _semantic_key(candidate)
        prior = selected.get(semantic)
        if prior is None:
            selected[semantic] = candidate
            continue
        candidate_order = (candidate.authority.rank, candidate.digest(), candidate.source_key)
        prior_order = (prior.authority.rank, prior.digest(), prior.source_key)
        if candidate_order > prior_order:
            skipped.append(DailySweepSkip(candidate_id=prior.candidate_id, reason="lower_authority"))
            selected[semantic] = candidate
        else:
            skipped.append(DailySweepSkip(candidate_id=candidate.candidate_id, reason="lower_authority"))

    candidates = tuple(sorted(selected.values(), key=lambda item: (item.kind, item.source_key)))
    skipped.sort(key=lambda item: (item.reason, item.candidate_id))
    return DailySweepPlan(
        uid=uid,
        local_date=packet.local_date,
        idempotency_key=_plan_id(uid, packet.local_date),
        candidates=candidates,
        skipped=tuple(skipped),
    )


def _cursor_ref(db_client: Any, uid: str) -> Any:
    return db_client.document(f"{MemoryCollections(uid=uid).user_root}/memory_control/daily_memory_sweep")


def _receipt_ref(db_client: Any, uid: str, receipt_id: str) -> Any:
    return db_client.document(f"{MemoryCollections(uid=uid).daily_memory_sweep_receipts}/{receipt_id}")


def _onboarding_source_receipt_ref(
    db_client: Any,
    uid: str,
    local_date: date,
    source_key: str,
    *,
    account_generation: int,
    source_generation: int,
    sweep_generation: int = 1,
) -> Any:
    source_receipt_id = (
        "source_"
        + deterministic_contract_id(
            "daily-memory-sweep-onboarding-source-receipt",
            {
                "uid": uid,
                "local_date": local_date.isoformat(),
                "source_key": source_key,
                "account_generation": account_generation,
                "source_generation": source_generation,
                "sweep_generation": sweep_generation,
            },
        )[:40]
    )
    return _receipt_ref(db_client, uid, source_receipt_id)


def _onboarding_permanent_receipt_ref(db_client: Any, uid: str, source_key: str) -> Any:
    """Return the once-only receipt keyed solely by the source identity.

    Candidate receipts are generation and local-window scoped because they
    protect a particular canonical write.  Onboarding source consumption is a
    different invariant: a source must never re-enter merely because the
    cursor or source generation rolled.  Keep that proof in its own bounded,
    exhaustive document namespace.
    """

    receipt_id = (
        ONBOARDING_PERMANENT_RECEIPT_PREFIX
        + deterministic_contract_id(
            "daily-memory-sweep-onboarding-permanent-source", {"uid": uid, "source_key": source_key}
        )[:48]
    )
    return db_client.document(f"users/{uid}/{ONBOARDING_SOURCE_RECEIPT_PATH}/{receipt_id}")


def _onboarding_staged_candidates_ref(
    db_client: Any,
    uid: str,
    source_key: str,
    *,
    account_generation: Optional[int] = None,
    source_generation: Optional[int] = None,
    sweep_generation: int = 1,
    window_id: Optional[str] = None,
) -> Any:
    stage_id = (
        ONBOARDING_PERMANENT_RECEIPT_PREFIX
        + deterministic_contract_id(
            "daily-memory-sweep-onboarding-staged-candidates",
            {
                "uid": uid,
                "source_key": source_key,
                "account_generation": account_generation,
                "source_generation": source_generation,
                "sweep_generation": sweep_generation,
                "window_id": window_id,
            },
        )[:48]
    )
    return db_client.document(f"users/{uid}/{ONBOARDING_STAGED_CANDIDATE_PATH}/{stage_id}")


def _daily_summary_staged_candidates_ref(
    db_client: Any,
    uid: str,
    local_date: date,
    *,
    account_generation: int,
    source_generation: int,
    window_id: str,
    sweep_generation: int = 1,
) -> Any:
    stage_id = deterministic_contract_id(
        "daily-memory-sweep-daily-summary-staged-candidates",
        {
            "uid": uid,
            "local_date": local_date.isoformat(),
            "account_generation": account_generation,
            "source_generation": source_generation,
            "sweep_generation": sweep_generation,
            "window_id": window_id,
        },
    )[:96]
    return db_client.document(f"users/{uid}/{DAILY_SUMMARY_STAGED_CANDIDATE_PATH}/{stage_id}")


def _model_invocation_ref(db_client: Any, uid: str, invocation_id: str) -> Any:
    """Return the durable model-invocation record for one source digest.

    The invocation record is deliberately separate from the candidate stage.
    A provider can return successfully and the process can die before the
    stage write; the pending record then remains an indeterminate outcome and
    a retry is refused rather than charging the provider a second time.
    """

    return db_client.document(f"users/{uid}/{MODEL_INVOCATION_PATH}/{invocation_id}")


def _model_invocation_fence_ref(db_client: Any, invocation_id: str) -> Any:
    """Return the non-expiring, content-free invocation identity fence."""

    return db_client.document(f"{MODEL_INVOCATION_FENCE_COLLECTION}/{invocation_id}")


def cleanup_expired_daily_memory_sweep_stages(
    uid: str,
    *,
    db_client: Any,
    now: Optional[datetime] = None,
    limit: int = 128,
) -> int:
    """Delete bounded, expired model stages while retaining invocation tombstones.

    Candidate pages are user data.  Their expiry is enforced both by this
    sweep-time janitor and by the read paths (which refuse an expired page),
    so a crash or permanently skipped account cannot retain model output
    indefinitely.  Invocation identity is a different kind of data: it is a
    content-free at-most-once tombstone and must never be deleted merely
    because its returned payload expired.  Otherwise a retry could recreate
    the same invocation and charge the provider twice.  The account-deletion
    recursive walk remains the final backstop for all rows under
    ``users/{uid}``.
    """

    cutoff = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    bounded_limit = max(1, min(256, int(limit)))
    deleted = 0
    collection_factory = getattr(db_client, "collection", None)
    if not callable(collection_factory):
        return 0
    for collection_path in (
        f"users/{uid}/{DAILY_SUMMARY_STAGED_CANDIDATE_PATH}",
        f"users/{uid}/{ONBOARDING_STAGED_CANDIDATE_PATH}",
        f"users/{uid}/{MODEL_INVOCATION_PATH}",
    ):
        try:
            collection_ref = cast(Any, collection_factory(collection_path))
            # Query by expiry first.  Permanent invocation tombstones do not
            # carry an expiry, so they must never consume the janitor's page
            # budget and starve returned user payloads behind them.
            where = getattr(collection_ref, "where", None)
            if not callable(where):
                # Tiny unit fakes from older callers have no query surface;
                # production Firestore always takes the queryable branch.  A
                # full stream here keeps that compatibility path privacy-safe
                # without imposing a hard first-page cap.
                rows = list(collection_ref.stream())
            else:
                try:
                    query: Any = where(filter=FieldFilter("expires_at", "<=", cutoff))
                except TypeError:
                    query = where("expires_at", "<=", cutoff)
                try:
                    query = query.order_by("expires_at")
                except (AttributeError, TypeError):
                    # Filtering remains useful even when an emulator fake
                    # does not model explicit ordering.
                    pass
                rows = []
                cursor = None
                while True:
                    page_query: Any = query
                    if cursor is not None:
                        start_after = getattr(page_query, "start_after", None)
                        if not callable(start_after):
                            break
                        page_query = start_after(cursor)
                    page = list(page_query.limit(bounded_limit).stream())
                    if not page:
                        break
                    rows.extend(page)
                    if len(page) < bounded_limit:
                        break
                    next_cursor = page[-1]
                    if next_cursor is cursor:
                        break
                    cursor = next_cursor
        except Exception:
            continue
        for row in rows:
            payload = row.to_dict() if hasattr(row, "to_dict") else None
            if not isinstance(payload, dict):
                continue
            is_invocation = collection_path.endswith(MODEL_INVOCATION_PATH)
            if is_invocation:
                state = payload.get("state")
                # Every invocation row is an at-most-once identity fence. A
                # pending lease can expire, and an indeterminate provider
                # outcome can be old, but neither proves that no paid call
                # happened. Never delete either row or allow it to be
                # recreated. They contain no candidate payload by design.
                if state in {"pending", "indeterminate", "payload_expired"}:
                    # Be defensive if a malformed/legacy indeterminate row
                    # accidentally carries user output: remove only that
                    # payload, retaining the identity fence.
                    if state == "indeterminate" and "candidate_page" in payload:
                        reference = getattr(row, "reference", None)
                        setter = getattr(reference, "set", None)
                        if callable(setter):
                            try:
                                setter(
                                    {
                                        "candidate_page": firestore.DELETE_FIELD,
                                        "candidate_digest": firestore.DELETE_FIELD,
                                        "returned_at": firestore.DELETE_FIELD,
                                        "expires_at": firestore.DELETE_FIELD,
                                    },
                                    merge=True,
                                )
                            except Exception:
                                pass
                    continue
                # Unknown invocation states fail closed too. Only a returned
                # payload has an expiry that can be compacted; no invocation
                # identity is safe to garbage-collect automatically.
                if state != "returned":
                    continue
            # Queryable collections have already proved the expiry condition;
            # the fallback path still checks both fields for legacy rows.
            expires_raw = payload.get("expires_at") or payload.get("lease_expires_at")
            expired = False
            try:
                expires_at = (
                    expires_raw
                    if isinstance(expires_raw, datetime)
                    else datetime.fromisoformat(str(expires_raw).replace("Z", "+00:00"))
                )
                expired = expires_at.tzinfo is None or expires_at.astimezone(timezone.utc) <= cutoff
            except (TypeError, ValueError):
                # Malformed expiry is treated as expired by the janitor. The
                # read path already fails closed on malformed stages.
                expired = True
            if not expired:
                continue
            reference = getattr(row, "reference", None)
            if is_invocation:
                # Delete user/model output but preserve a durable, content-free
                # fence. Firestore's field-delete sentinel removes the fields
                # from the document while ``merge=True`` retains identity and
                # state. A missing setter is fail-closed: retain the whole row
                # rather than deleting the only at-most-once proof.
                setter = getattr(reference, "set", None)
                if not callable(setter):
                    continue
                try:
                    setter(
                        {
                            "schema_version": MODEL_INVOCATION_SCHEMA_VERSION,
                            "uid": uid,
                            "invocation_id": payload.get("invocation_id", getattr(row, "id", "")),
                            "state": "payload_expired",
                            "at_most_once_tombstone": True,
                            "payload_expired_at": cutoff,
                            "candidate_page": firestore.DELETE_FIELD,
                            "candidate_digest": firestore.DELETE_FIELD,
                            "returned_at": firestore.DELETE_FIELD,
                            "expires_at": firestore.DELETE_FIELD,
                            "lease_expires_at": firestore.DELETE_FIELD,
                        },
                        merge=True,
                    )
                    deleted += 1
                except Exception:
                    continue
                continue
            delete = getattr(reference, "delete", None)
            if callable(delete):
                try:
                    delete()
                    deleted += 1
                except Exception:
                    continue
    return deleted


def _invoke_model_once_legacy(
    db_client: Any,
    uid: str,
    invocation_id: str,
    *,
    candidate_builder: Any,
    now: Optional[datetime] = None,
) -> Optional[Tuple[dict[str, Any], ...]]:
    """Claim and durably record one model invocation before returning output.

    Firestore ``create`` is the cross-process first-writer fence.  The local
    lock also makes the tiny in-memory fakes used by adversarial thread tests
    behave like the production atomic create path.  Pending and indeterminate
    records are fail-closed forever: their provider outcome cannot be proven,
    so they must be repaired by an explicit operator path instead of being
    retried implicitly.
    """

    invocation_ref = _model_invocation_ref(db_client, uid, invocation_id)
    claim_now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)

    def validated_output(invocation_payload: Any) -> Optional[Tuple[dict[str, Any], ...]]:
        if not isinstance(invocation_payload, dict):
            return None
        # A returned page is user payload, not the durable receipt. Once its
        # bounded retention has elapsed, fail closed even if the janitor has
        # not compacted the payload yet.
        expires_raw = invocation_payload.get("expires_at")
        try:
            expires_at = (
                expires_raw
                if isinstance(expires_raw, datetime)
                else datetime.fromisoformat(str(expires_raw).replace("Z", "+00:00"))
            )
            if expires_at.tzinfo is None or expires_at.astimezone(timezone.utc) <= claim_now:
                return None
        except (TypeError, ValueError):
            return None
        output = invocation_payload.get("candidate_page")
        if not isinstance(output, list) or any(not isinstance(item, dict) for item in output):
            return None
        expected_digest = deterministic_contract_id("daily-sweep-model-invocation-output", {"candidate_page": output})
        if invocation_payload.get("candidate_digest") != expected_digest:
            return None
        return tuple(output)

    with _MODEL_INVOCATION_LOCK:
        try:
            snapshot = invocation_ref.get()
        except Exception:
            return None
        if getattr(snapshot, "exists", False):
            payload = snapshot.to_dict() or {}
            if not isinstance(payload, dict) or payload.get("schema_version") != MODEL_INVOCATION_SCHEMA_VERSION:
                return None
            state = payload.get("state")
            if state == "returned":
                return validated_output(payload)
            # ``pending`` includes a lease that has expired. Expiry is not
            # evidence that the provider did not return; reclaiming it would
            # violate the at-most-once cost boundary.
            return None

        pending_payload = {
            "schema_version": MODEL_INVOCATION_SCHEMA_VERSION,
            "uid": uid,
            "invocation_id": invocation_id,
            "state": "pending",
            "at_most_once_tombstone": True,
            "claimed_at": claim_now,
            "lease_expires_at": claim_now + MODEL_INVOCATION_LEASE,
        }
        create = getattr(invocation_ref, "create", None)
        if callable(create):
            try:
                create(pending_payload)
            except Exception:
                # Another process won the create race. Read the winner's
                # durable result; a pending winner is intentionally blocked.
                try:
                    winner = invocation_ref.get()
                    winner_payload = winner.to_dict() or {}
                    if (
                        getattr(winner, "exists", False)
                        and isinstance(winner_payload, dict)
                        and winner_payload.get("schema_version") == MODEL_INVOCATION_SCHEMA_VERSION
                        and winner_payload.get("state") == "returned"
                    ):
                        return validated_output(winner_payload)
                except Exception:
                    pass
                return None
        else:
            # Non-production fakes do not expose create. Keep this fallback
            # deterministic; real Firestore always takes the atomic branch.
            try:
                invocation_ref.set(pending_payload)
            except Exception:
                return None

        try:
            built = tuple(candidate_builder())
            if any(not isinstance(item, dict) for item in built):
                raise ValueError("model invocation candidate output is malformed")
            returned_payload = {
                "state": "returned",
                "at_most_once_tombstone": True,
                "candidate_page": list(built),
                "candidate_digest": deterministic_contract_id(
                    "daily-sweep-model-invocation-output", {"candidate_page": list(built)}
                ),
                "returned_at": claim_now,
                "expires_at": claim_now + STAGED_CANDIDATE_RETENTION,
            }
            invocation_ref.set(returned_payload, merge=True)
            return built
        except Exception:
            # Preserve the pending marker as an indeterminate outcome. The
            # only safe retry is an explicit repair that proves what the
            # provider did, never an automatic second charge.
            try:
                invocation_ref.set(
                    {
                        "state": "indeterminate",
                        "at_most_once_tombstone": True,
                        "indeterminate_at": claim_now,
                    },
                    merge=True,
                )
            except Exception:
                pass
            return None


def _invoke_model_once(
    db_client: Any,
    uid: str,
    invocation_id: str,
    *,
    candidate_builder: Any,
    account_generation: Optional[int] = None,
    source_generation: Optional[int] = None,
    sweep_generation: Optional[int] = None,
    window_id: Optional[str] = None,
    now: Optional[datetime] = None,
) -> Optional[Tuple[dict[str, Any], ...]]:
    """Run one fenced provider call with a durable cross-account-delete claim.

    The user subcollection stores only bounded model output and may be
    recursively deleted.  The top-level fence is content-free and survives
    that deletion, so a worker that loses its payload after a provider call
    cannot recreate the logical invocation and pay twice.  ``pending`` and
    ``indeterminate`` are manual-repair-only states; lease expiry never
    reopens them.

    The optional identity arguments exist solely for old hermetic unit callers
    that predate generation fencing. Every production scheduler path supplies
    all four values and therefore takes the transactional branch below.
    """

    fenced = (
        account_generation is not None
        and source_generation is not None
        and sweep_generation is not None
        and isinstance(window_id, str)
        and bool(window_id)
    )
    if not fenced:
        return _invoke_model_once_legacy(
            db_client,
            uid,
            invocation_id,
            candidate_builder=candidate_builder,
            now=now,
        )

    account_generation = int(cast(int, account_generation))
    source_generation = int(cast(int, source_generation))
    sweep_generation = int(cast(int, sweep_generation))
    claim_now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    invocation_ref = _model_invocation_ref(db_client, uid, invocation_id)
    fence_ref = _model_invocation_fence_ref(db_client, invocation_id)
    deletion_ref, control_ref = _live_fence_refs(db_client, uid)
    identity = {
        "uid": uid,
        "invocation_id": invocation_id,
        "account_generation": account_generation,
        "source_generation": source_generation,
        "sweep_generation": sweep_generation,
        "window_id": window_id,
    }

    def _identity_matches(payload: Any) -> bool:
        return isinstance(payload, dict) and all(payload.get(key) == value for key, value in identity.items())

    def _validated_output(payload: Any) -> Optional[Tuple[dict[str, Any], ...]]:
        if not isinstance(payload, dict) or payload.get("state") != "returned" or not _identity_matches(payload):
            return None
        expires_raw = payload.get("expires_at")
        try:
            expires_at = (
                expires_raw
                if isinstance(expires_raw, datetime)
                else datetime.fromisoformat(str(expires_raw).replace("Z", "+00:00"))
            )
            if expires_at.tzinfo is None or expires_at.astimezone(timezone.utc) <= claim_now:
                return None
        except (TypeError, ValueError):
            return None
        output = payload.get("candidate_page")
        if not isinstance(output, list) or any(not isinstance(item, dict) for item in output):
            return None
        expected_digest = deterministic_contract_id("daily-sweep-model-invocation-output", {"candidate_page": output})
        if payload.get("candidate_digest") != expected_digest:
            return None
        return tuple(output)

    def _read(ref: Any, transaction: Any) -> Any:
        return ref.get(transaction=transaction)

    def _create_or_set(transaction: Any, ref: Any, payload: dict[str, Any]) -> None:
        # Firestore Transaction.create is atomic. Small test doubles lack it,
        # so their transaction.set fallback remains deterministic under the
        # module lock used by the adversarial unit tests.
        create = getattr(transaction, "create", None)
        if callable(create):
            create(ref, payload)
        else:
            transaction.set(ref, payload)

    def claim(transaction: Any) -> Tuple[str, Optional[Tuple[dict[str, Any], ...]]]:
        if not _transaction_fence_open(
            transaction,
            deletion_ref,
            control_ref,
            uid=uid,
            account_generation=account_generation,
            source_generation=source_generation,
        ):
            return "blocked", None
        fence_snapshot = _read(fence_ref, transaction)
        user_snapshot = _read(invocation_ref, transaction)
        fence_payload = fence_snapshot.to_dict() if getattr(fence_snapshot, "exists", False) else None
        user_payload = user_snapshot.to_dict() if getattr(user_snapshot, "exists", False) else None
        if fence_payload is not None:
            if not _identity_matches(fence_payload):
                return "blocked", None
            if fence_payload.get("state") == "returned":
                return "returned", _validated_output(user_payload)
            # Existing pending, indeterminate, and payload-expired fences are
            # deliberately closed forever without an explicit repair receipt.
            return "blocked", None
        # A user payload without its top-level identity fence is an orphan,
        # usually the result of an interrupted account wipe. Never recreate it.
        if user_payload is not None:
            return "blocked", None
        pending = {
            **identity,
            "schema_version": MODEL_INVOCATION_SCHEMA_VERSION,
            "state": "pending",
            "at_most_once_tombstone": True,
            "claimed_at": claim_now,
        }
        _create_or_set(transaction, fence_ref, pending)
        transaction.set(
            invocation_ref,
            {**pending, "lease_expires_at": claim_now + MODEL_INVOCATION_LEASE},
        )
        return "claimed", None

    def run_transaction(callback: Any) -> Any:
        transaction = db_client.transaction()
        return firestore.transactional(callback)(transaction)

    with _MODEL_INVOCATION_LOCK:
        try:
            claim_state, existing_output = run_transaction(claim)
        except Exception:
            return None
        if claim_state == "returned":
            return existing_output
        if claim_state != "claimed":
            return None

        try:
            built = tuple(candidate_builder())
            if any(not isinstance(item, dict) for item in built):
                raise ValueError("model invocation candidate output is malformed")
        except Exception:
            # The fence is top-level and therefore still writable after a
            # recursive account wipe. Do not recreate the user payload.
            def mark_indeterminate(transaction: Any) -> bool:
                snapshot = _read(fence_ref, transaction)
                payload = snapshot.to_dict() if getattr(snapshot, "exists", False) else None
                if not _identity_matches(payload):
                    return False
                assert isinstance(payload, dict)
                if payload.get("state") != "pending":
                    return False
                transaction.set(
                    fence_ref,
                    {
                        **identity,
                        "schema_version": MODEL_INVOCATION_SCHEMA_VERSION,
                        "state": "indeterminate",
                        "at_most_once_tombstone": True,
                        "indeterminate_at": claim_now,
                    },
                    merge=True,
                )
                user_snapshot = _read(invocation_ref, transaction)
                if getattr(user_snapshot, "exists", False):
                    transaction.set(
                        invocation_ref,
                        {"state": "indeterminate", "at_most_once_tombstone": True, "indeterminate_at": claim_now},
                        merge=True,
                    )
                return True

            try:
                run_transaction(mark_indeterminate)
            except Exception:
                pass
            return None

        returned_payload = {
            **identity,
            "schema_version": MODEL_INVOCATION_SCHEMA_VERSION,
            "state": "returned",
            "at_most_once_tombstone": True,
            "candidate_page": list(built),
            "candidate_digest": deterministic_contract_id(
                "daily-sweep-model-invocation-output", {"candidate_page": list(built)}
            ),
            "returned_at": claim_now,
            "expires_at": claim_now + STAGED_CANDIDATE_RETENTION,
        }

        def finalize(transaction: Any) -> bool:
            if not _transaction_fence_open(
                transaction,
                deletion_ref,
                control_ref,
                uid=uid,
                account_generation=account_generation,
                source_generation=source_generation,
            ):
                return False
            fence_snapshot = _read(fence_ref, transaction)
            fence_payload = fence_snapshot.to_dict() if getattr(fence_snapshot, "exists", False) else None
            user_snapshot = _read(invocation_ref, transaction)
            user_payload = user_snapshot.to_dict() if getattr(user_snapshot, "exists", False) else None
            # Never recreate a user payload after recursive deletion, even if
            # the deletion marker is briefly unavailable to this transaction.
            if not _identity_matches(fence_payload):
                return False
            if not isinstance(fence_payload, dict) or fence_payload.get("state") != "pending":
                return False
            if not _identity_matches(user_payload):
                return False
            if not isinstance(user_payload, dict) or user_payload.get("state") != "pending":
                return False
            transaction.set(
                fence_ref,
                {key: value for key, value in returned_payload.items() if key not in {"candidate_page", "expires_at"}},
                merge=True,
            )
            transaction.set(invocation_ref, returned_payload)
            return True

        try:
            if not run_transaction(finalize):
                # A closed generation/account is an indeterminate provider
                # outcome. Mark only the durable fence; never recreate user
                # payload, stage, receipt, canonical item, or cursor state.
                def mark_closed(transaction: Any) -> bool:
                    snapshot = _read(fence_ref, transaction)
                    payload = snapshot.to_dict() if getattr(snapshot, "exists", False) else None
                    if not _identity_matches(payload):
                        return False
                    if not isinstance(payload, dict) or payload.get("state") != "pending":
                        return False
                    transaction.set(
                        fence_ref,
                        {
                            **identity,
                            "schema_version": MODEL_INVOCATION_SCHEMA_VERSION,
                            "state": "indeterminate",
                            "at_most_once_tombstone": True,
                            "indeterminate_at": claim_now,
                        },
                        merge=True,
                    )
                    return True

                try:
                    run_transaction(mark_closed)
                except Exception:
                    pass
                return None
        except Exception:
            return None
        return built


def _receipt_id(
    uid: str,
    local_date: date,
    candidate: DailySweepCandidate,
    *,
    account_generation: int,
    source_generation: int,
    sweep_generation: int = 1,
) -> str:
    return (
        "receipt_"
        + deterministic_contract_id(
            "daily-memory-sweep-receipt",
            {
                "uid": uid,
                "local_date": local_date.isoformat(),
                "source_key": candidate.source_key,
                "account_generation": account_generation,
                "source_generation": source_generation,
                "sweep_generation": sweep_generation,
            },
        )[:40]
    )


def _read_cursor(db_client: Any, uid: str, control: MemoryControlState) -> DailySweepCursor:
    snapshot = _cursor_ref(db_client, uid).get()
    if not getattr(snapshot, "exists", False):
        return DailySweepCursor(
            uid=uid,
            account_generation=control.account_generation,
            source_generation=control.source_generation,
        )
    try:
        cursor = DailySweepCursor.model_validate(snapshot.to_dict() or {})
    except Exception as exc:
        raise RuntimeError("daily sweep cursor is malformed") from exc
    if cursor.uid != uid or cursor.account_generation != control.account_generation:
        raise RuntimeError("daily sweep cursor owner or generation mismatch")
    if cursor.source_generation != control.source_generation:
        if cursor.source_generation > control.source_generation:
            raise RuntimeError("daily sweep cursor source generation is ahead of canonical control")
        if not _rollover_cursor_source_generation(
            db_client,
            uid,
            cursor,
            control,
        ):
            raise RuntimeError("daily sweep cursor source-generation rollover conflict")
        snapshot = _cursor_ref(db_client, uid).get()
        try:
            cursor = DailySweepCursor.model_validate(snapshot.to_dict() or {})
        except Exception as exc:
            raise RuntimeError("daily sweep cursor is malformed after source-generation rollover") from exc
        if cursor.source_generation != control.source_generation:
            raise RuntimeError("daily sweep cursor source-generation rollover did not commit")
    return cursor


def _rollover_cursor_source_generation(
    db_client: Any,
    uid: str,
    prior: DailySweepCursor,
    control: MemoryControlState,
) -> bool:
    """CAS source generation while preserving the exact completed-day identity.

    A source refresh must not replay a completed local day or silently skip a
    pending one. Receipts are generation-namespaced, so stale packets/receipts
    cannot be reused after this transaction.
    """

    ref = _cursor_ref(db_client, uid)

    def rollover(transaction: Any) -> bool:
        deletion_ref, control_ref = _live_fence_refs(db_client, uid)
        if not _transaction_fence_open(
            transaction,
            deletion_ref,
            control_ref,
            uid=uid,
            account_generation=control.account_generation,
            source_generation=control.source_generation,
        ):
            return False
        snapshot = ref.get(transaction=transaction)
        if not getattr(snapshot, "exists", False):
            return prior.source_generation == control.source_generation
        payload = snapshot.to_dict() or {}
        if (
            payload.get("uid") != uid
            or int(payload.get("account_generation", -1)) != control.account_generation
            or int(payload.get("source_generation", -1)) != prior.source_generation
            or int(payload.get("generation", -1)) != prior.generation
        ):
            return False
        transaction.set(
            ref,
            {
                **payload,
                "source_generation": control.source_generation,
                "generation": prior.generation + 1,
                "updated_at": datetime.now(timezone.utc),
            },
        )
        return True

    transaction = db_client.transaction()
    return bool(firestore.transactional(rollover)(transaction))


def reconcile_daily_memory_sweep_timezone(
    uid: str,
    timezone_name: str,
    *,
    db_client: Any,
    reconciliation_authorized: bool = False,
) -> bool:
    """Explicitly re-anchor a cursor after a user timezone change.

    A timezone change can create a 23/25-hour overlap or gap.  The scheduler
    therefore blocks automatically; this separate server-only operation rolls
    the sweep-owned receipt namespace while preserving the completed-day
    anchor.  The global canonical source generation is never mutated here.
    """

    if not reconciliation_authorized:
        return False
    try:
        ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("timezone_name must be a valid IANA timezone") from exc
    # Ensure the control document exists before entering the transaction; the
    # transaction below still re-reads the live value and fences the cursor
    # namespace atomically.
    ensure_canonical_apply_control_state(uid, db_client=db_client)
    ref = _cursor_ref(db_client, uid)

    def reconcile(transaction: Any) -> bool:
        deletion_ref, control_ref = _live_fence_refs(db_client, uid)
        deletion_snapshot = deletion_ref.get(transaction=transaction)
        deletion_payload = deletion_snapshot.to_dict() if getattr(deletion_snapshot, "exists", False) else {}
        if account_deletion_blocks_access(
            normalize_account_deletion_status(
                marker_exists=bool(getattr(deletion_snapshot, "exists", False)),
                raw_status=deletion_payload.get("wipe_status") if isinstance(deletion_payload, dict) else None,
            )
        ):
            return False
        control_snapshot = control_ref.get(transaction=transaction)
        if not getattr(control_snapshot, "exists", False):
            return False
        control_payload = control_snapshot.to_dict() or {}
        try:
            live_control = MemoryControlState.model_validate(control_payload)
        except Exception:
            return False
        if live_control.uid != uid:
            return False
        snapshot = ref.get(transaction=transaction)
        if not getattr(snapshot, "exists", False):
            transaction.set(
                ref,
                DailySweepCursor(
                    uid=uid,
                    account_generation=live_control.account_generation,
                    source_generation=live_control.source_generation,
                    sweep_generation=1,
                    timezone_name=timezone_name,
                ).model_dump(mode="json"),
            )
            return True
        try:
            cursor = DailySweepCursor.model_validate(snapshot.to_dict() or {})
        except Exception:
            return False
        if (
            cursor.uid != uid
            or cursor.account_generation != live_control.account_generation
            or cursor.source_generation != live_control.source_generation
        ):
            return False
        if cursor.timezone_name == timezone_name:
            return True
        if cursor.last_completed_window_end_utc is None:
            return False
        # Receipt IDs include the sweep-owned generation. Roll that namespace
        # in the same transaction as the timezone anchor. The first new-zone
        # packet is a clipped bridge ending at that zone's next midnight; this
        # preserves half-open UTC coverage even when NY -> LA/London shifts
        # the boundary backwards or forwards.
        transition_local_date = cursor.last_completed_window_end_utc.astimezone(ZoneInfo(timezone_name)).date()
        try:
            transition = timezone_transition_window(
                transition_local_date,
                timezone_name,
                coverage_start_utc=cursor.last_completed_window_end_utc,
            )
        except ValueError:
            return False
        now = datetime.now(timezone.utc)
        transaction.set(
            ref,
            {
                "schema_version": CURSOR_SCHEMA_VERSION,
                "uid": uid,
                "account_generation": live_control.account_generation,
                "source_generation": live_control.source_generation,
                "sweep_generation": cursor.sweep_generation + 1,
                "generation": cursor.generation + 1,
                "timezone_name": timezone_name,
                "last_completed_local_date": (
                    cursor.last_completed_local_date.isoformat() if cursor.last_completed_local_date else None
                ),
                "last_completed_window_id": cursor.last_completed_window_id,
                "last_completed_window_start_utc": cursor.last_completed_window_start_utc,
                "last_completed_window_end_utc": cursor.last_completed_window_end_utc,
                "pending_transition_local_date": transition_local_date.isoformat(),
                "pending_transition_window_id": transition.window_id,
                "pending_transition_start_utc": transition.start_utc,
                "pending_transition_end_utc": transition.end_utc,
                "updated_at": now,
            },
        )
        return True

    return bool(firestore.transactional(reconcile)(db_client.transaction()))


def reconcile_daily_memory_sweep_timezones_for_maintenance(
    uid_inventory: Iterable[str],
    *,
    timezone_resolver: Any,
    db_client: Any,
    authorized: bool = False,
    max_users: int = 400,
) -> Tuple[str, ...]:
    """Bounded operator/runtime entrypoint for explicit timezone reconciliation."""

    if not authorized:
        return ()
    reconciled: List[str] = []
    for uid in tuple(sorted({str(item).strip() for item in uid_inventory if str(item).strip()}))[:max_users]:
        try:
            timezone_name = str(timezone_resolver(uid) or "UTC")
            if reconcile_daily_memory_sweep_timezone(
                uid,
                timezone_name,
                db_client=db_client,
                reconciliation_authorized=True,
            ):
                reconciled.append(uid)
        except Exception:
            # A malformed profile or a contention failure must not turn this
            # bounded auxiliary pass into a cursor-advancing fallback.
            continue
    return tuple(reconciled)


def _pending_receipt_dates(
    db_client: Any,
    uid: str,
    *,
    through: date,
    account_generation: int,
    source_generation: int,
    sweep_generation: int = 1,
) -> Tuple[date, ...]:
    """Recover bounded incomplete dates when a crash occurred before cursor CAS."""

    try:
        snapshots = list(
            db_client.collection(MemoryCollections(uid=uid).daily_memory_sweep_receipts)
            .where(filter=FieldFilter("receipt_state", "==", "pending"))
            .limit(MAX_CANDIDATES_PER_DAY * MAX_CATCH_UP_DAYS)
            .stream()
        )
    except Exception:
        # A missing index/query support is not evidence that there are no
        # pending dates. The regular cursor path remains safe and the caller
        # will block on missing input rather than advance.
        return ()
    dates: set[date] = set()
    for snapshot in snapshots:
        payload = snapshot.to_dict() or {}
        if (
            not isinstance(payload, dict)
            or int(payload.get("account_generation", -1)) != account_generation
            or int(payload.get("source_generation", -1)) != source_generation
            or int(payload.get("sweep_generation", 1)) != sweep_generation
        ):
            continue
        raw = payload.get("local_date")
        try:
            local_date = date.fromisoformat(str(raw))
        except (TypeError, ValueError):
            continue
        if local_date <= through:
            dates.add(local_date)
    return tuple(sorted(dates))


def _live_fence_refs(db_client: Any, uid: str) -> Tuple[Any, Any]:
    return (
        db_client.document(f"account_deletions/{uid}"),
        db_client.document(MemoryCollections(uid=uid).memory_apply_control_state),
    )


def _transaction_fence_open(
    transaction: Any,
    deletion_ref: Any,
    control_ref: Any,
    *,
    uid: str,
    account_generation: int,
    source_generation: int,
) -> bool:
    """Read deletion and live control state in the same transaction as writes."""

    deletion_snapshot = deletion_ref.get(transaction=transaction)
    deletion_payload = deletion_snapshot.to_dict() if getattr(deletion_snapshot, "exists", False) else {}
    deletion_status = normalize_account_deletion_status(
        marker_exists=bool(getattr(deletion_snapshot, "exists", False)),
        raw_status=deletion_payload.get("wipe_status") if isinstance(deletion_payload, dict) else None,
    )
    if account_deletion_blocks_access(deletion_status):
        return False
    control_snapshot = control_ref.get(transaction=transaction)
    if not getattr(control_snapshot, "exists", False):
        return False
    control_payload = control_snapshot.to_dict() or {}
    return (
        isinstance(control_payload, dict)
        and control_payload.get("uid") == uid
        and int(control_payload.get("account_generation", -1)) == account_generation
        and int(control_payload.get("source_generation", -1)) == source_generation
    )


def _advance_cursor_txn(
    transaction: Any,
    ref: Any,
    uid: str,
    account_generation: int,
    source_generation: int,
    sweep_generation: int,
    expected_generation: int,
    local_date: date,
    timezone_name: str,
    window_start_utc: datetime,
    window_end_utc: datetime,
    window_id: str,
    window_kind: str,
    deletion_ref: Any,
    control_ref: Any,
    now: datetime,
) -> bool:
    if not _transaction_fence_open(
        transaction,
        deletion_ref,
        control_ref,
        uid=uid,
        account_generation=account_generation,
        source_generation=source_generation,
    ):
        return False
    snapshot = ref.get(transaction=transaction)
    payload = snapshot.to_dict() if getattr(snapshot, "exists", False) else {}
    if payload:
        if (
            payload.get("uid") != uid
            or int(payload.get("account_generation", -1)) != account_generation
            or int(payload.get("source_generation", -1)) != source_generation
        ):
            return False
        if int(payload.get("sweep_generation", 1)) != sweep_generation:
            return False
        if int(payload.get("generation", -1)) != expected_generation:
            return False
        if payload.get("timezone_name") not in {None, timezone_name}:
            return False
        prior = payload.get("last_completed_local_date")
        if isinstance(prior, str) and prior == local_date.isoformat():
            if window_kind != "timezone_transition":
                return payload.get("last_completed_window_id") == window_id
        if window_kind == "timezone_transition" and (
            payload.get("pending_transition_local_date") not in {local_date, local_date.isoformat()}
            or payload.get("pending_transition_window_id") != window_id
            or payload.get("pending_transition_start_utc") != window_start_utc
            or payload.get("pending_transition_end_utc") != window_end_utc
        ):
            return False
        if isinstance(prior, str) and prior > local_date.isoformat():
            return False
    elif expected_generation != 0:
        return False
    transaction.set(
        ref,
        {
            "schema_version": CURSOR_SCHEMA_VERSION,
            "uid": uid,
            "account_generation": account_generation,
            "source_generation": source_generation,
            "sweep_generation": sweep_generation,
            "generation": expected_generation + 1,
            "timezone_name": timezone_name,
            "last_completed_local_date": local_date.isoformat(),
            "last_completed_window_id": window_id,
            "last_completed_window_start_utc": window_start_utc,
            "last_completed_window_end_utc": window_end_utc,
            "pending_transition_local_date": None,
            "pending_transition_window_id": None,
            "pending_transition_start_utc": None,
            "pending_transition_end_utc": None,
            "updated_at": now,
        },
    )
    return True


def _advance_cursor(
    db_client: Any,
    uid: str,
    control: MemoryControlState,
    cursor: DailySweepCursor,
    local_date: date,
    timezone_name: str,
    window_start_utc: datetime,
    window_end_utc: datetime,
    window_id: str,
    *,
    sweep_generation: Optional[int] = None,
    window_kind: str = "local_day",
) -> bool:
    transaction = db_client.transaction()
    transactional = firestore.transactional(_advance_cursor_txn)
    deletion_ref, control_ref = _live_fence_refs(db_client, uid)
    return bool(
        transactional(
            transaction,
            _cursor_ref(db_client, uid),
            uid,
            control.account_generation,
            control.source_generation,
            sweep_generation if sweep_generation is not None else cursor.sweep_generation,
            cursor.generation,
            local_date,
            timezone_name,
            window_start_utc,
            window_end_utc,
            window_id,
            window_kind,
            deletion_ref,
            control_ref,
            datetime.now(timezone.utc),
        )
    )


def _claim_receipt(
    db_client: Any,
    uid: str,
    local_date: date,
    candidate: DailySweepCandidate,
    *,
    account_generation: int,
    source_generation: int,
    claimant: str,
    claim_now: datetime,
    window: CompletedLocalDayWindow,
    sweep_generation: int = 1,
    qa_run_id: Optional[str] = None,
) -> Literal["claimed", "idempotent", "conflict"]:
    receipt_ref = _receipt_ref(
        db_client,
        uid,
        _receipt_id(
            uid,
            local_date,
            candidate,
            account_generation=account_generation,
            source_generation=source_generation,
            sweep_generation=sweep_generation,
        ),
    )
    digest = candidate.digest()
    normalized_now = claim_now.astimezone(timezone.utc)

    def claim(transaction: Any) -> Literal["claimed", "idempotent", "conflict"]:
        deletion_ref, control_ref = _live_fence_refs(db_client, uid)
        if not _transaction_fence_open(
            transaction,
            deletion_ref,
            control_ref,
            uid=uid,
            account_generation=account_generation,
            source_generation=source_generation,
        ):
            return "conflict"
        snapshot = receipt_ref.get(transaction=transaction)
        existing = snapshot.to_dict() if getattr(snapshot, "exists", False) else None
        if existing is not None:
            if (
                existing.get("uid") != uid
                or existing.get("source_key") != candidate.source_key
                or existing.get("candidate_digest") != digest
                or int(existing.get("account_generation", -1)) != account_generation
                or int(existing.get("source_generation", -1)) != source_generation
                or int(existing.get("sweep_generation", 1)) != sweep_generation
                or existing.get("qa_run_id") != qa_run_id
                or (
                    qa_run_id is not None
                    and (
                        existing.get("source_id") != candidate.source_id
                        or existing.get("source_type") != candidate.source_type
                        or existing.get("source_version") != candidate.source_version
                    )
                )
                or existing.get("local_timezone_window_id") != window.window_id
                or existing.get("window_start_utc") != window.start_utc
                or existing.get("window_end_utc") != window.end_utc
            ):
                return "conflict"
            if existing.get("receipt_state") == "committed":
                return "idempotent"
            prior_claimant = existing.get("claimant")
            if prior_claimant and prior_claimant != claimant:
                expires_raw = existing.get("claim_expires_at")
                try:
                    expires = (
                        expires_raw
                        if isinstance(expires_raw, datetime)
                        else datetime.fromisoformat(str(expires_raw).replace("Z", "+00:00"))
                    )
                    if (
                        expires.tzinfo is None
                        or expires.utcoffset() is None
                        or expires.astimezone(timezone.utc) > normalized_now
                    ):
                        return "conflict"
                except (TypeError, ValueError):
                    # An old or malformed pending claim is never guessed at or
                    # overwritten. The next retry must use an explicit repair.
                    return "conflict"
            transaction.set(
                receipt_ref,
                {
                    "claimant": claimant,
                    "claimed_at": normalized_now,
                    "claim_expires_at": normalized_now + RECEIPT_LEASE,
                },
                merge=True,
            )
            return "claimed"
        payload: dict[str, Any] = {
            "schema_version": RECEIPT_SCHEMA_VERSION,
            "uid": uid,
            "local_date": local_date.isoformat(),
            "source_key": candidate.source_key,
            "candidate_digest": digest,
            "account_generation": account_generation,
            "source_generation": source_generation,
            "sweep_generation": sweep_generation,
            "claimant": claimant,
            "receipt_state": "pending",
            "local_timezone_window_id": window.window_id,
            "window_start_utc": window.start_utc,
            "window_end_utc": window.end_utc,
            "claimed_at": normalized_now,
            "claim_expires_at": normalized_now + RECEIPT_LEASE,
        }
        if qa_run_id is not None:
            payload.update(
                {
                    "qa_run_id": qa_run_id,
                    "source_id": candidate.source_id,
                    "source_type": candidate.source_type,
                    "source_version": candidate.source_version,
                    "source_refs": list(candidate.source_refs),
                }
            )
        transaction.set(receipt_ref, payload)
        return "claimed"

    transaction = db_client.transaction()
    transactional = firestore.transactional(claim)
    return transactional(transaction)


def _finish_receipt(
    db_client: Any,
    uid: str,
    local_date: date,
    candidate: DailySweepCandidate,
    *,
    memory_id: Optional[str],
    outcome: Literal["committed", "skipped"] = "committed",
    skip_reason: Optional[str] = None,
    account_generation: int,
    source_generation: int,
    claimant: str,
    window: CompletedLocalDayWindow,
    sweep_generation: int = 1,
    qa_run_id: Optional[str] = None,
) -> None:
    receipt_ref = _receipt_ref(
        db_client,
        uid,
        _receipt_id(
            uid,
            local_date,
            candidate,
            account_generation=account_generation,
            source_generation=source_generation,
            sweep_generation=sweep_generation,
        ),
    )

    def finish(transaction: Any) -> None:
        deletion_ref, control_ref = _live_fence_refs(db_client, uid)
        if not _transaction_fence_open(
            transaction,
            deletion_ref,
            control_ref,
            uid=uid,
            account_generation=account_generation,
            source_generation=source_generation,
        ):
            raise SweepFenceBlocked("daily sweep receipt completion fence closed")
        snapshot = receipt_ref.get(transaction=transaction)
        if not getattr(snapshot, "exists", False):
            raise RuntimeError("daily sweep receipt disappeared before completion")
        existing = snapshot.to_dict() or {}
        if (
            existing.get("uid") != uid
            or existing.get("source_key") != candidate.source_key
            or existing.get("candidate_digest") != candidate.digest()
            or int(existing.get("account_generation", -1)) != account_generation
            or int(existing.get("source_generation", -1)) != source_generation
            or int(existing.get("sweep_generation", 1)) != sweep_generation
            or existing.get("qa_run_id") != qa_run_id
            or (
                qa_run_id is not None
                and (
                    existing.get("source_id") != candidate.source_id
                    or existing.get("source_type") != candidate.source_type
                    or existing.get("source_version") != candidate.source_version
                )
            )
            or existing.get("claimant") != claimant
            or existing.get("local_timezone_window_id") != window.window_id
            or existing.get("window_start_utc") != window.start_utc
            or existing.get("window_end_utc") != window.end_utc
        ):
            raise RuntimeError("daily sweep receipt changed while completing")
        payload: Dict[str, Any] = {
            "schema_version": RECEIPT_SCHEMA_VERSION,
            "receipt_state": "committed",
            "source_generation": source_generation,
            "sweep_generation": sweep_generation,
            "claimant": claimant,
            "outcome": outcome,
            "local_timezone_window_id": window.window_id,
            "window_start_utc": window.start_utc,
            "window_end_utc": window.end_utc,
            "completed_at": datetime.now(timezone.utc),
        }
        if qa_run_id is not None:
            payload.update(
                {
                    "source_id": candidate.source_id,
                    "source_type": candidate.source_type,
                    "source_version": candidate.source_version,
                    "source_refs": list(candidate.source_refs),
                }
            )
        if memory_id:
            payload["memory_id"] = memory_id
        if skip_reason:
            payload["skip_reason"] = skip_reason
        if qa_run_id is not None:
            payload["qa_run_id"] = qa_run_id
        transaction.set(receipt_ref, payload, merge=True)

    transaction = db_client.transaction()
    firestore.transactional(finish)(transaction)


def _finish_onboarding_sources(
    db_client: Any,
    uid: str,
    local_date: date,
    source_keys: Iterable[str],
    candidates: Iterable[DailySweepCandidate],
    *,
    account_generation: int,
    source_generation: int,
    window: CompletedLocalDayWindow,
    source_progress: Optional[Mapping[str, int]] = None,
    sweep_generation: int = 1,
) -> bool:
    """Atomically consume onboarding sources after every candidate is safe.

    A source receipt is separate from candidate receipts.  If the process dies
    after one canonical write, the source remains retryable; the next attempt
    sees the committed candidate receipt and finishes the remaining candidates
    before writing the source marker.  Empty model output still has a source
    receipt and is therefore not re-run forever.
    """

    normalized_keys = tuple(sorted(set(source_keys)))
    if not normalized_keys:
        return True
    if len(normalized_keys) > MAX_ONBOARDING_SOURCE_KEYS_PER_PACKET:
        # Never silently drop the prefix of a once-only receipt set.  The
        # source producer is bounded at the Firestore transaction-safe packet
        # limit; this guard is for malformed or manually forged packets.
        return False
    candidates_by_source: Dict[str, List[DailySweepCandidate]] = {key: [] for key in normalized_keys}
    for candidate in candidates:
        source_key = f"onboarding:{candidate.source_id.split(':', 1)[-1]}"
        if source_key in candidates_by_source:
            candidates_by_source[source_key].append(candidate)
    consumed_ref = db_client.document(f"users/{uid}/{ONBOARDING_CONSUMED_STATE_PATH}")

    def complete(transaction: Any) -> bool:
        deletion_ref, control_ref = _live_fence_refs(db_client, uid)
        if not _transaction_fence_open(
            transaction,
            deletion_ref,
            control_ref,
            uid=uid,
            account_generation=account_generation,
            source_generation=source_generation,
        ):
            return False
        consumed_snapshot = transaction.get(consumed_ref)
        consumed_payload = consumed_snapshot.to_dict() if getattr(consumed_snapshot, "exists", False) else {}
        raw_consumed = consumed_payload.get("consumed_source_keys", []) if isinstance(consumed_payload, dict) else []
        consumed_values = list(raw_consumed) if isinstance(raw_consumed, list) else []
        if len(consumed_values) > MAX_ONBOARDING_RECEIPT_KEYS:
            return False
        if any(
            not isinstance(value, str) or not value.startswith("onboarding:") or len(value) > MAX_SOURCE_ID_CHARACTERS
            for value in consumed_values
        ):
            return False
        raw_offsets = consumed_payload.get("candidate_offsets", {}) if isinstance(consumed_payload, dict) else {}
        offsets = {
            key: int(value)
            for key, value in raw_offsets.items()
            if isinstance(key, str) and isinstance(value, int) and value >= 0
        }
        source_receipts: List[Tuple[Any, str]] = []
        permanent_receipts: List[Tuple[Any, str]] = []
        candidate_receipts: List[Any] = []
        # Firestore requires all reads before writes.  Candidate receipts are
        # proof that canonical application completed for this whole source.
        for source_key in normalized_keys:
            permanent_receipts.append((_onboarding_permanent_receipt_ref(db_client, uid, source_key), source_key))
            if source_key not in (source_progress or {}):
                source_ref = _onboarding_source_receipt_ref(
                    db_client,
                    uid,
                    local_date,
                    source_key,
                    account_generation=account_generation,
                    source_generation=source_generation,
                    sweep_generation=sweep_generation,
                )
                source_receipts.append((source_ref, source_key))
            for candidate in candidates_by_source[source_key]:
                candidate_receipts.append(
                    _receipt_ref(
                        db_client,
                        uid,
                        _receipt_id(
                            uid,
                            local_date,
                            candidate,
                            account_generation=account_generation,
                            source_generation=source_generation,
                            sweep_generation=sweep_generation,
                        ),
                    )
                )
        source_snapshots = [transaction.get(ref) for ref, _ in source_receipts]
        permanent_snapshots = [transaction.get(ref) for ref, _ in permanent_receipts]
        candidate_snapshots = [transaction.get(ref) for ref in candidate_receipts]
        for snapshot in candidate_snapshots:
            if not getattr(snapshot, "exists", False) or (snapshot.to_dict() or {}).get("receipt_state") != "committed":
                return False
        next_consumed = list(consumed_values)
        permanent_by_key = {
            source_key: snapshot
            for (_permanent_ref, source_key), snapshot in zip(permanent_receipts, permanent_snapshots)
        }
        source_by_key = {source_key: snapshot for (_, source_key), snapshot in zip(source_receipts, source_snapshots)}
        for source_key in normalized_keys:
            # A progress row means only a bounded prefix was staged and
            # applied. Keep the source retryable until the tail is proven.
            if source_key in (source_progress or {}):
                continue
            permanent_snapshot = permanent_by_key[source_key]
            source_snapshot = source_by_key.get(source_key)
            permanent_payload = permanent_snapshot.to_dict() or {}
            try:
                permanent_generation = int(permanent_payload.get("account_generation", -1))
            except (TypeError, ValueError):
                permanent_generation = -1
            permanent_committed = (
                getattr(permanent_snapshot, "exists", False)
                and permanent_payload.get("receipt_state") == "committed"
                and permanent_generation == account_generation
            )
            source_committed = (
                source_snapshot is not None
                and getattr(source_snapshot, "exists", False)
                and (source_snapshot.to_dict() or {}).get("receipt_state") == "committed"
            )
            if not permanent_committed:
                transaction.set(
                    _onboarding_permanent_receipt_ref(db_client, uid, source_key),
                    {
                        "schema_version": "daily_memory_sweep_onboarding_permanent_source.v1",
                        "uid": uid,
                        "source_key": source_key,
                        "account_generation": account_generation,
                        "receipt_state": "committed",
                        "completed_at": datetime.now(timezone.utc),
                    },
                    merge=True,
                )
            if not source_committed and source_snapshot is not None:
                transaction.set(
                    source_receipts[[item[1] for item in source_receipts].index(source_key)][0],
                    {
                        "schema_version": "daily_memory_sweep_onboarding_source.v1",
                        "uid": uid,
                        "local_date": local_date.isoformat(),
                        "source_key": source_key,
                        "account_generation": account_generation,
                        "source_generation": source_generation,
                        "sweep_generation": sweep_generation,
                        "window_id": window.window_id,
                        "window_start_utc": window.start_utc,
                        "window_end_utc": window.end_utc,
                        "receipt_state": "committed",
                        "completed_at": datetime.now(timezone.utc),
                    },
                )
            if source_key not in next_consumed:
                next_consumed.append(source_key)
            offsets.pop(source_key, None)
        for source_key, offset in (source_progress or {}).items():
            if source_key not in normalized_keys or offset < 0:
                return False
            # A partial source has committed candidate receipts for exactly
            # this prefix.  Persisting the offset in the same transaction as
            # those proof reads makes retry/restart advance without dropping
            # the unprocessed tail.
            offsets[source_key] = offset
        if len(set(next_consumed)) > MAX_ONBOARDING_RECEIPT_KEYS or len(offsets) > MAX_ONBOARDING_RECEIPT_KEYS:
            return False
        transaction.set(
            consumed_ref,
            {
                "schema_version": "daily_memory_sweep_onboarding.v1",
                "consumed_source_keys": sorted(set(next_consumed)),
                "candidate_offsets": dict(sorted(offsets.items())),
                "account_generation": account_generation,
                "source_generation": source_generation,
                "sweep_generation": sweep_generation,
                "updated_at": datetime.now(timezone.utc),
            },
            merge=True,
        )
        return True

    return bool(firestore.transactional(complete)(db_client.transaction()))


def _target_for_candidate(uid: str, candidate: DailySweepCandidate, *, db_client: Any) -> Optional[MemoryItem]:
    if not candidate.target_memory_id:
        return None
    return read_canonical_memory_item(uid, candidate.target_memory_id, db_client=db_client)


def _target_authority(item: MemoryItem) -> int:
    reason = item.write_reason
    if reason in {
        LedgerWriteReason.direct_user_statement,
        LedgerWriteReason.explicit_remember,
        LedgerWriteReason.onboarding,
    }:
        return SweepAuthority.direct_user_statement.rank
    if reason == LedgerWriteReason.agent_reusable_conclusion:
        return SweepAuthority.agent_reusable_conclusion.rank
    return SweepAuthority.sweep_inference.rank


def _find_active_slot_or_subject(
    uid: str,
    candidate: DailySweepCandidate,
    *,
    db_client: Any,
) -> Optional[MemoryItem]:
    """Find one deterministic active canonical occupant using a targeted query.

    A broad collection scan is unsafe here: truncation could be mistaken for
    an empty slot and create a duplicate. The production query is narrowed by
    active fact + subject identity (+ slot when present), and a result page
    larger than the bounded proof fails closed.
    """

    if candidate.kind != "fact":
        return None
    collection = db_client.collection(MemoryCollections(uid=uid).memory_items)
    where = getattr(collection, "where", None)
    if not callable(where):
        raise SweepAuthoritativeQueryUnavailable("canonical occupant query is unavailable")
    values = {
        "status": MemoryItemStatus.active.value,
        "kind": MemoryKind.fact.value,
        "subject_scope": candidate.subject_scope.value,
    }
    snapshots: List[Any] = []
    used_legacy_compatibility = False
    try:
        if candidate.slot:
            query_spec = (
                DAILY_SWEEP_ACTIVE_FACT_ENTITY_SLOT_QUERY
                if candidate.subject_entity_id is not None
                else DAILY_SWEEP_ACTIVE_FACT_SLOT_QUERY
            )
        else:
            # Content equality is part of the Firestore predicate for the
            # unslotted path.  Do not bound a broad subject page and then
            # casefold/filter locally: the matching occupant could be row 4.
            query_spec = (
                DAILY_SWEEP_ACTIVE_FACT_ENTITY_CONTENT_QUERY
                if candidate.subject_entity_id is not None
                else DAILY_SWEEP_ACTIVE_FACT_SUBJECT_CONTENT_QUERY
            )
        query = query_spec.build(
            collection,
            {
                **values,
                **(
                    {"normalized_content_key": normalized_memory_content_key(candidate.content)}
                    if not candidate.slot
                    else {}
                ),
                **({"slot": candidate.slot} if candidate.slot else {}),
                **(
                    {"subject_entity_id": candidate.subject_entity_id}
                    if candidate.subject_entity_id is not None
                    else {}
                ),
            },
            field_filter_factory=FieldFilter,
        )
        snapshots = list(query.limit(MAX_AUTHORITATIVE_OCCUPANTS + 1).stream())
        if not candidate.slot and not snapshots:
            # Migration-safe fallback for rows written before the key was
            # introduced.  It remains a targeted subject/entity proof and
            # fails closed on truncation; it never scans an unbounded
            # collection or trusts a broad first page.
            legacy_spec = (
                DAILY_SWEEP_ACTIVE_FACT_ENTITY_QUERY
                if candidate.subject_entity_id is not None
                else DAILY_SWEEP_ACTIVE_FACT_SUBJECT_QUERY
            )
            used_legacy_compatibility = True
            legacy_query = legacy_spec.build(
                collection,
                {
                    **values,
                    **(
                        {"subject_entity_id": candidate.subject_entity_id}
                        if candidate.subject_entity_id is not None
                        else {}
                    ),
                },
                field_filter_factory=FieldFilter,
            )
            # Legacy rows predate ``normalized_content_key``.  Prove the
            # complete compatibility cohort before deciding that no duplicate
            # exists. One bounded page is not that proof: a long-tenured
            # account holds far more than 64 active unslotted facts per
            # subject, and the old single-page cap made every such account's
            # sweep day fail closed forever (dev, hourly, since 2026-08-30).
            # Drain the cursor in bounded pages instead; the scan ceiling
            # below still fails closed on a pathological cohort.
            snapshots = []
            cursor_query = legacy_query
            while True:
                page = list(cursor_query.limit(LEGACY_COMPAT_OCCUPANT_PAGE_SIZE).stream())
                snapshots.extend(page)
                if len(snapshots) > MAX_LEGACY_COMPAT_OCCUPANT_SCAN:
                    break
                if len(page) < LEGACY_COMPAT_OCCUPANT_PAGE_SIZE:
                    break
                cursor_query = legacy_query.start_after(page[-1])
    except Exception as exc:
        raise SweepAuthoritativeQueryUnavailable("canonical occupant query failed") from exc
    proof_limit = MAX_LEGACY_COMPAT_OCCUPANT_SCAN if used_legacy_compatibility else MAX_AUTHORITATIVE_OCCUPANTS
    if len(snapshots) > proof_limit:
        raise SweepAuthoritativeQueryUnavailable("canonical occupant query exceeded proof budget")
    items: List[MemoryItem] = []
    for snapshot in snapshots:
        raw = snapshot.to_dict()
        if not isinstance(raw, dict):
            raise SweepAuthoritativeQueryUnavailable("canonical occupant row is malformed")
        item = MemoryItem.model_validate(raw)
        if (
            item.uid != uid
            or item.status != MemoryItemStatus.active
            or item.kind != MemoryKind.fact
            or item.subject_scope != candidate.subject_scope
            or item.subject_entity_id != candidate.subject_entity_id
            or (candidate.slot and item.slot != candidate.slot)
            or (
                not candidate.slot
                and (item.normalized_content_key or normalized_memory_content_key(item.content))
                != normalized_memory_content_key(candidate.content)
            )
        ):
            continue
        items.append(item)
    return sorted(items, key=lambda item: item.memory_id)[0] if items else None


def _apply_candidate(
    uid: str,
    local_date: date,
    candidate: DailySweepCandidate,
    *,
    db_client: Any,
) -> Tuple[Optional[str], Optional[str]]:
    """Return ``(memory_id, skip_reason)``; all writes use canonical apply."""

    target = _target_for_candidate(uid, candidate, db_client=db_client)
    effective_operation = candidate.operation
    if candidate.operation == "add":
        occupant = _find_active_slot_or_subject(uid, candidate, db_client=db_client)
        if occupant is not None:
            # Crash-replay recognition: if the occupant already carries this
            # exact plan/candidate's evidence identity, the canonical write for
            # this receipt landed before a crash prevented receipt
            # finalization. Re-applying would supersede our own row with a
            # duplicate; recognize the landed effect and complete as a skip.
            # A next-day sweep derives a different ``_plan_id`` and therefore a
            # different evidence identity, so legitimate same-slot refreshes
            # are unaffected.
            replay_evidence_id = evidence_id_for_ledger_provenance(
                uid,
                LedgerProvenance(
                    source_id=candidate.source_id,
                    source_type=candidate.source_type,
                    source_version=candidate.source_version,
                    action_id=f"{_plan_id(uid, local_date)}:{candidate.source_key}",
                ),
            )
            # An occupant without readable evidence cannot be proven to be our
            # own replay, so fall through to the ordinary authority rules
            # rather than suppressing a write we cannot account for.
            occupant_evidence = getattr(occupant, "evidence", None) or ()
            if any(getattr(item, "evidence_id", None) == replay_evidence_id for item in occupant_evidence):
                return occupant.memory_id, "existing_active_slot" if candidate.slot else "existing_active_subject"
            occupant_rank = _target_authority(occupant)
            # A slot is a standing attribute the daily run maintains: a
            # sweep-authored occupant may be refreshed by an equal-rank sweep
            # candidate carrying the same slot (same-slot supersession).
            # Subject-matched occupants without a slot stay strictly ranked —
            # equal rank there is a duplicate observation, not an update — and
            # a higher-authority occupant (a direct user statement) is never
            # overwritten by sweep inference.
            sweep_slot_refresh = (
                bool(candidate.slot)
                and candidate.authority.rank == occupant_rank == SweepAuthority.sweep_inference.rank
            )
            if candidate.authority.rank <= occupant_rank and not sweep_slot_refresh:
                return occupant.memory_id, "existing_active_slot" if candidate.slot else "existing_active_subject"
            target = occupant
            effective_operation = "amend"
    if effective_operation in {"amend", "repair"}:
        if target is None:
            return None, "missing_target"
        if target.status != MemoryItemStatus.active:
            return None, "target_not_active"
        if candidate.authority.rank < _target_authority(target):
            return None, "lower_authority"
        if candidate.kind == "fact" and target.kind != MemoryKind.fact:
            return None, "target_kind_mismatch"
        if candidate.kind == "trigger" and target.kind != MemoryKind.trigger:
            return None, "target_kind_mismatch"
        if candidate.kind == "trigger" and target.write_reason != LedgerWriteReason.standing_trigger:
            return None, "target_not_explicit_trigger"

    provenance = LedgerProvenance(
        source_id=candidate.source_id,
        source_type=candidate.source_type,
        source_version=candidate.source_version,
        action_id=f"{_plan_id(uid, local_date)}:{candidate.source_key}",
        artifact_ref={
            "local_date": local_date.isoformat(),
            "source_refs": list(candidate.source_refs),
            # Repair provenance is deliberately separate from the durable
            # standing-trigger authority below.
            "sweep_repair": (
                {
                    "schema_version": SCHEMA_VERSION,
                    "authority": candidate.authority.value,
                    "operation": candidate.operation,
                }
                if candidate.kind == "trigger"
                else None
            ),
        },
        quote_refs=[{"source_ref": ref} for ref in candidate.source_refs],
    )
    if candidate.kind == "trigger":
        reason = LedgerWriteReason.standing_trigger
    elif candidate.source_type == "onboarding":
        reason = LedgerWriteReason.onboarding
    else:
        reason = candidate.authority.ledger_reason
    if effective_operation == "amend":
        assert target is not None
        try:
            memory_id = amend_fact(
                uid,
                target.memory_id,
                candidate.content,
                provenance=provenance,
                write_reason=reason,
                slot=candidate.slot,
                subject_scope=candidate.subject_scope,
                subject_entity_id=candidate.subject_entity_id,
                valid_from=datetime.combine(local_date, time.min, tzinfo=timezone.utc),
                db_client=db_client,
                required_source_item=target,
            )
        except ValueError as exc:
            if "unsupported knowledge ledger slot" not in str(exc):
                raise
            return None, "unknown_slot"
        return memory_id, None

    try:
        write = LedgerWrite(
            kind=MemoryKind.trigger if candidate.kind == "trigger" else MemoryKind.fact,
            content=candidate.content,
            provenance=provenance,
            write_reason=reason,
            subject_scope=candidate.subject_scope,
            subject_entity_id=candidate.subject_entity_id,
            slot=candidate.slot,
            trigger_condition=candidate.trigger_condition,
            # A completed-day replay must derive identical mutation metadata.  The
            # ledger otherwise defaults ``valid_from`` to wall-clock ``now`` and a
            # crash after canonical apply would produce a different operation ID.
            valid_from=datetime.combine(local_date, time.min, tzinfo=timezone.utc),
            # Inference-backed rows stay out of the user-asserted profile path.
            user_asserted=candidate.authority == SweepAuthority.direct_user_statement,
            supersedes=([target.memory_id] if effective_operation == "repair" and target is not None else []),
        )
        return save_ledger_write(uid, write, db_client=db_client, required_source_item=target), None
    except ValueError as exc:
        if "unsupported knowledge ledger slot" not in str(exc):
            raise
        return None, "unknown_slot"


def _blocked_output(
    uid: str, reason: str, *, status: Literal["blocked", "disabled", "not_due"] = "blocked"
) -> DailySweepOutput:
    return DailySweepOutput(
        uid=uid,
        status=status,
        blocked_reason=reason if status == "blocked" else None,
        telemetry={"status": status, "blocked_reason": reason if status == "blocked" else "none"},
    )


def run_daily_memory_sweep(
    uid: str,
    timezone_name: str,
    now: datetime,
    inputs_by_date: Mapping[date, DailySweepInput],
    *,
    db_client: Any,
    authority: SweepAuthorityState = SweepAuthorityState(),
    max_catch_up_days: int = MAX_CATCH_UP_DAYS,
    claimant: Optional[str] = None,
    qa_run_id: Optional[str] = None,
) -> DailySweepOutput:
    """Run bounded completed local days with durable cursor and source receipts.

    ``inputs_by_date`` is server-owned and must contain only complete local-day
    packets.  The function never consumes today's partial window.  It advances
    the cursor only after every candidate in a day is either committed,
    idempotently replayed, or explicitly skipped by a deterministic validation
    fence.  A canonical write failure leaves the cursor behind for retry.
    """

    normalized_uid = (uid or "").strip()
    validate_uid_for_memory_path(normalized_uid)
    if qa_run_id is not None:
        qa_run_id = validate_qa_sweep_run_id(qa_run_id)
    if not authority.may_write:
        return _blocked_output(normalized_uid, "authority_closed", status="disabled")
    if max_catch_up_days < 1 or max_catch_up_days > MAX_CATCH_UP_DAYS:
        raise ValueError("max_catch_up_days must be between 1 and the bounded maximum")
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    try:
        local_today = now.astimezone(ZoneInfo(timezone_name)).date()
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("timezone_name must be a valid IANA timezone") from exc
    if any(packet.uid != normalized_uid for packet in inputs_by_date.values()):
        return _blocked_output(normalized_uid, "input_owner_mismatch")

    try:
        deletion_fence = read_account_deletion_projection_fence(normalized_uid, db_client=db_client)
        if deletion_fence.blocks_projection_writes:
            return _blocked_output(normalized_uid, "account_deletion_fence")
        control = ensure_canonical_apply_control_state(normalized_uid, db_client=db_client)
        cursor = _read_cursor(db_client, normalized_uid, control)
    except Exception:
        return _blocked_output(normalized_uid, "authority_state_unavailable")
    if cursor.last_completed_local_date is not None and cursor.timezone_name != timezone_name:
        # Changing zones can make a previously completed local date overlap or
        # leave a gap in UTC.  Require an explicit server-side reconciliation;
        # never silently replay or skip data.
        return _blocked_output(normalized_uid, "timezone_changed_requires_reconciliation")
    eligible_through = local_today - timedelta(days=1)
    first_pending = (
        cursor.pending_transition_local_date
        if cursor.pending_transition_local_date is not None
        else (
            cursor.last_completed_local_date + timedelta(days=1)
            if cursor.last_completed_local_date is not None
            else eligible_through
        )
    )
    pending_receipt_dates = _pending_receipt_dates(
        db_client,
        normalized_uid,
        through=eligible_through,
        account_generation=control.account_generation,
        source_generation=control.source_generation,
        sweep_generation=cursor.sweep_generation,
    )
    if first_pending > eligible_through:
        return _blocked_output(normalized_uid, "no_completed_local_day", status="not_due")
    if cursor.pending_transition_local_date is not None:
        dates = [first_pending]
        dates.extend(
            day
            for day in (first_pending + timedelta(days=index) for index in range(1, max_catch_up_days))
            if day <= eligible_through
        )
    elif pending_receipt_dates:
        # A crash can leave a receipt for an older day while the wall clock
        # moves on. Recover that exact day first; do not demand a newer day's
        # source packet and accidentally turn a recoverable replay into a
        # cursor-advancing gap.
        dates = list(pending_receipt_dates[:max_catch_up_days])
    else:
        dates = [first_pending + timedelta(days=index) for index in range(max_catch_up_days)]
        dates = [item for item in dates if item <= eligible_through]

    completed: List[date] = []
    committed_count = 0
    idempotent_count = 0
    skipped_count = 0
    current_cursor = cursor
    # A production invocation owns a unique lease. Date-derived claimants made
    # two independent runners look like one worker and could strand pending
    # work across the next day.
    receipt_claimant = claimant or f"run:{uuid4().hex}"
    for local_date in dates:
        packet = inputs_by_date.get(local_date)
        if packet is None:
            return _blocked_output(normalized_uid, f"missing_input:{local_date.isoformat()}")
        if packet.local_date != local_date:
            return _blocked_output(normalized_uid, "input_date_mismatch")
        if (
            packet.account_generation != control.account_generation
            or packet.source_generation != control.source_generation
            or packet.sweep_generation != current_cursor.sweep_generation
        ):
            return _blocked_output(normalized_uid, "input_generation_mismatch")
        if packet.timezone_name != timezone_name:
            return _blocked_output(normalized_uid, "input_timezone_mismatch")
        expected_window = completed_local_day_window(local_date, timezone_name)
        if packet.window_kind == "timezone_transition":
            try:
                expected_window = timezone_transition_window(
                    local_date,
                    timezone_name,
                    coverage_start_utc=packet.window_start_utc,
                )
            except ValueError:
                return _blocked_output(normalized_uid, "incomplete_or_wrong_window")
        if (
            not packet.complete
            or packet.window_id != expected_window.window_id
            or packet.window_start_utc != expected_window.start_utc
            or packet.window_end_utc != expected_window.end_utc
        ):
            return _blocked_output(normalized_uid, "incomplete_or_wrong_window")
        try:
            plan = plan_daily_memory_sweep(packet)
        except Exception:
            return _blocked_output(normalized_uid, "invalid_input_packet")
        skipped_count += len(plan.skipped)
        if len(plan.candidates) > MAX_WRITES_PER_DAY:
            return _blocked_output(normalized_uid, "write_budget_exceeded")
        for candidate in plan.candidates:
            claim = _claim_receipt(
                db_client,
                normalized_uid,
                local_date,
                candidate,
                account_generation=control.account_generation,
                source_generation=control.source_generation,
                claimant=receipt_claimant,
                claim_now=now,
                window=expected_window,
                sweep_generation=current_cursor.sweep_generation,
                qa_run_id=qa_run_id,
            )
            if claim == "conflict":
                return _blocked_output(normalized_uid, "source_idempotency_conflict")
            if claim == "idempotent":
                idempotent_count += 1
                continue
            try:
                memory_id, skip_reason = _apply_candidate(
                    normalized_uid,
                    local_date,
                    candidate,
                    db_client=db_client,
                )
            except SweepAuthoritativeQueryUnavailable:
                return _blocked_output(normalized_uid, "canonical_occupant_query_unavailable")
            except ValueError as exc:
                if "unsupported knowledge ledger slot" not in str(exc):
                    raise
                memory_id, skip_reason = None, "unknown_slot"
            if skip_reason:
                skipped_count += 1
                try:
                    _finish_receipt(
                        db_client,
                        normalized_uid,
                        local_date,
                        candidate,
                        memory_id=memory_id,
                        outcome="skipped",
                        skip_reason=skip_reason,
                        account_generation=control.account_generation,
                        source_generation=control.source_generation,
                        claimant=receipt_claimant,
                        window=expected_window,
                        sweep_generation=current_cursor.sweep_generation,
                        qa_run_id=qa_run_id,
                    )
                except SweepFenceBlocked:
                    return _blocked_output(normalized_uid, "receipt_completion_fence_closed")
                continue
            if not memory_id:
                return _blocked_output(normalized_uid, "empty_canonical_write_result")
            try:
                _finish_receipt(
                    db_client,
                    normalized_uid,
                    local_date,
                    candidate,
                    memory_id=memory_id,
                    account_generation=control.account_generation,
                    source_generation=control.source_generation,
                    claimant=receipt_claimant,
                    window=expected_window,
                    sweep_generation=current_cursor.sweep_generation,
                    qa_run_id=qa_run_id,
                )
            except SweepFenceBlocked:
                return _blocked_output(normalized_uid, "receipt_completion_fence_closed")
            committed_count += 1
        if not _finish_onboarding_sources(
            db_client,
            normalized_uid,
            local_date,
            packet.onboarding_source_keys,
            plan.candidates,
            account_generation=control.account_generation,
            source_generation=control.source_generation,
            window=expected_window,
            source_progress=packet.onboarding_source_progress,
            sweep_generation=current_cursor.sweep_generation,
        ):
            return _blocked_output(normalized_uid, "onboarding_source_receipt_incomplete")
        window_start_utc, window_end_utc, window_id = (
            expected_window.start_utc,
            expected_window.end_utc,
            expected_window.window_id,
        )
        if not _advance_cursor(
            db_client,
            normalized_uid,
            control,
            current_cursor,
            local_date,
            timezone_name,
            window_start_utc,
            window_end_utc,
            window_id,
            sweep_generation=current_cursor.sweep_generation,
            window_kind=packet.window_kind,
        ):
            return _blocked_output(normalized_uid, "cursor_conflict")
        current_cursor = current_cursor.model_copy(
            update={
                "generation": current_cursor.generation + 1,
                "timezone_name": timezone_name,
                "last_completed_local_date": local_date,
                "last_completed_window_id": window_id,
                "last_completed_window_start_utc": window_start_utc,
                "last_completed_window_end_utc": window_end_utc,
                "pending_transition_local_date": None,
                "pending_transition_window_id": None,
                "pending_transition_start_utc": None,
                "pending_transition_end_utc": None,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        completed.append(local_date)

    status: Literal["committed"] = "committed"
    return DailySweepOutput(
        uid=normalized_uid,
        status=status,
        completed_local_dates=tuple(completed),
        committed_count=committed_count,
        idempotent_count=idempotent_count,
        skipped_count=skipped_count,
        telemetry={
            "status": status,
            "days": len(completed),
            "committed": committed_count,
            "idempotent": idempotent_count,
            "skipped": skipped_count,
        },
    )


@dataclass(frozen=True)
class DailySweepRuntimeSources:
    """Structured server-owned sources adapted by the maintenance scheduler.

    ``daily_summary`` is the normal completed-day producer.  The two explicit
    auxiliary channels keep onboarding cold-start facts and reconciliation of
    already-standing triggers visible in the contract; neither channel may
    create a trigger from passive behavior.
    """

    daily_summary: Tuple[DailySweepCandidate, ...] = ()
    onboarding_cold_start: Tuple[DailySweepCandidate, ...] = ()
    existing_trigger_reconciliation: Tuple[DailySweepCandidate, ...] = ()
    # ``complete`` is an immutable producer attestation. False means the
    # source is absent/partial and the cursor must not advance, even when the
    # candidate list is empty (the explicit complete-zero case is True).
    complete: bool = False
    source_status: Literal["complete", "complete_zero", "incomplete", "absent"] = "incomplete"
    # All unconsumed onboarding source identities observed by the producer.
    # This includes zero-candidate sources and is completed only after the
    # corresponding candidate receipts are durable.
    onboarding_source_keys: Tuple[str, ...] = ()
    onboarding_source_progress: Mapping[str, int] = field(default_factory=dict)
    eligibility_proof: Literal["completed_transcript_v1", "none"] = "none"
    # Content-free accounting used to enforce the model budget.  It is never
    # emitted as a user-facing telemetry payload.
    model_cost_usd: float = 0.0
    # Content-free provider dispatch and usage evidence for qualification.
    model_dispatch_evidence: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_iterables(
        cls,
        *,
        daily_summary: Iterable[DailySweepCandidate] = (),
        onboarding_cold_start: Iterable[DailySweepCandidate] = (),
        existing_trigger_reconciliation: Iterable[DailySweepCandidate] = (),
        complete: bool = False,
        source_status: Literal["complete", "complete_zero", "incomplete", "absent"] = "incomplete",
        onboarding_source_keys: Iterable[str] = (),
        onboarding_source_progress: Optional[Mapping[str, int]] = None,
        eligibility_proof: Literal["completed_transcript_v1", "none"] = "none",
        model_cost_usd: float = 0.0,
        model_dispatch_evidence: Optional[Mapping[str, Any]] = None,
    ) -> "DailySweepRuntimeSources":
        summary_values = tuple(daily_summary)
        onboarding_values = tuple(onboarding_cold_start)
        trigger_values = tuple(existing_trigger_reconciliation)
        normalized_status: Literal["complete", "complete_zero", "incomplete", "absent"] = (
            "complete"
            if complete and source_status == "complete_zero" and (summary_values or onboarding_values or trigger_values)
            else source_status
        )
        return cls(
            daily_summary=summary_values,
            onboarding_cold_start=onboarding_values,
            existing_trigger_reconciliation=trigger_values,
            complete=complete,
            source_status=normalized_status,
            onboarding_source_keys=tuple(sorted(set(onboarding_source_keys))),
            onboarding_source_progress=dict(onboarding_source_progress or {}),
            eligibility_proof=eligibility_proof,
            model_cost_usd=model_cost_usd,
            model_dispatch_evidence=dict(model_dispatch_evidence or {}),
        )

    def candidates(self) -> Tuple[DailySweepCandidate, ...]:
        return self.daily_summary + self.onboarding_cold_start + self.existing_trigger_reconciliation


def build_daily_sweep_input(
    uid: str,
    local_date: date,
    *,
    account_generation: int,
    source_generation: int,
    sweep_generation: int = 1,
    timezone_name: str,
    sources: DailySweepRuntimeSources,
    window_override: Optional[CompletedLocalDayWindow] = None,
) -> DailySweepInput:
    """Adapt typed daily-summary/onboarding/trigger sources into one packet."""

    window = window_override or completed_local_day_window(local_date, timezone_name)
    window_kind: Literal["local_day", "timezone_transition"] = (
        "timezone_transition" if window_override is not None else "local_day"
    )
    return DailySweepInput(
        uid=uid,
        local_date=local_date,
        account_generation=account_generation,
        source_generation=source_generation,
        sweep_generation=sweep_generation,
        timezone_name=timezone_name,
        window_id=window.window_id,
        window_start_utc=window.start_utc,
        window_end_utc=window.end_utc,
        window_kind=window_kind,
        complete=sources.complete,
        candidates=sources.candidates(),
        onboarding_source_keys=sources.onboarding_source_keys,
        onboarding_source_progress=dict(sources.onboarding_source_progress or {}),
        eligibility_proof=sources.eligibility_proof,
    )


def _bounded_candidate_channel(
    raw: Any,
    *,
    source_type: Optional[str] = None,
    authority: Optional[SweepAuthority] = None,
    trusted_direct: bool = False,
    max_candidates: int = MAX_CANDIDATES_PER_DAY,
) -> Tuple[DailySweepCandidate, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, (list, tuple)) or len(raw) > max_candidates:
        raise ValueError("daily sweep source channel exceeds its bounded candidate budget")
    parsed: List[DailySweepCandidate] = []
    for item in raw:
        if isinstance(item, DailySweepCandidate):
            payload = item.model_dump(mode="python")
        elif isinstance(item, dict):
            payload = dict(item)
        else:
            raise ValueError("daily sweep source candidate must be an object")
        # Source producers are not authorities.  Never let a producer payload
        # smuggle in direct-user authority (or a different source type).  The
        # only exception is the trusted canonical onboarding channel, whose
        # adapter has already authenticated that the evidence came from an
        # onboarding conversation.
        if source_type is not None:
            supplied_source_type = payload.get("source_type")
            if supplied_source_type is not None and supplied_source_type != source_type:
                if not (trusted_direct and supplied_source_type == "explicit_user_statement"):
                    raise ValueError("daily sweep candidate source type is not trusted")
            payload["source_type"] = source_type
        if authority is not None:
            supplied_authority = payload.get("authority")
            if supplied_authority is not None:
                try:
                    supplied_authority = SweepAuthority(supplied_authority)
                except ValueError as exc:
                    raise ValueError("daily sweep candidate authority is invalid") from exc
                if supplied_authority != authority and not (
                    trusted_direct and supplied_authority == SweepAuthority.direct_user_statement
                ):
                    raise ValueError("daily sweep candidate authority is not trusted")
            payload["authority"] = authority
        candidate = DailySweepCandidate.model_validate(payload)
        parsed.append(candidate)
    return tuple(parsed)


@dataclass(frozen=True)
class CompletedDayConversationSource:
    """One eligible conversation: summary spine row + transcript for lookup."""

    conversation_id: str
    summary_text: str
    transcript_text: str
    needs_folder: bool


def _read_completed_day_conversation_sources(
    uid: str,
    window: CompletedLocalDayWindow,
    *,
    db_client: Any,
    max_conversations: int,
    max_summary_characters: int,
) -> Tuple[Tuple[CompletedDayConversationSource, ...], Literal["complete", "incomplete"]]:
    """Read bounded conversation summaries (plus transcripts) in one UTC window.

    The SUMMARY texts form the agent's spine and are what the character budget
    bounds; transcripts ride along only for the bounded verification lookup.
    Photos and other media are stripped by construction.  A query failure, an
    over-budget page, or an undecodable conversation is incomplete rather than
    an empty source, so callers cannot move the cursor past unprocessed data.
    """

    collection = db_client.collection(f"users/{uid}/conversations")
    where = getattr(collection, "where", None)
    if not callable(where):
        return (), "incomplete"
    try:
        try:
            query: Any = where(filter=FieldFilter("started_at", ">=", window.start_utc))
            query = query.where(filter=FieldFilter("started_at", "<", window.end_utc))
        except TypeError:
            query = where("started_at", ">=", window.start_utc)
            query = query.where("started_at", "<", window.end_utc)
        try:
            query = query.order_by("started_at")
        except (AttributeError, TypeError):
            # A small injected emulator fake may not implement ordering; the
            # identity and bounded page still hold, and model output is sorted
            # below by the stable document id.
            pass
        snapshots = list(query.limit(max_conversations + 1).stream())
    except Exception:
        return (), "incomplete"
    if len(snapshots) > max_conversations:
        return (), "incomplete"

    from database.conversations import (  # pyright: ignore[reportPrivateUsage]
        _prepare_conversation_for_read as prepare_conversation_for_read,  # pyright: ignore[reportPrivateUsage]
    )
    from models.conversation import Conversation

    rows: List[CompletedDayConversationSource] = []
    total_characters = 0
    for snapshot in snapshots:
        conversation_id = str(getattr(snapshot, "id", "") or "")
        raw = snapshot.to_dict() or {}
        if not conversation_id or not isinstance(raw, dict):
            return (), "incomplete"
        # A timestamp range is not an eligibility proof.  Discarded rows are
        # intentionally excluded, while processing/in-progress/unfinished
        # rows keep the source incomplete so a later retry cannot advance the
        # cursor past a transcript that may still change.
        eligibility = _completed_day_row_eligibility(raw)
        if eligibility == "discarded":
            continue
        if eligibility != "eligible":
            return (), "incomplete"
        try:
            prepared = prepare_conversation_for_read(raw, uid)  # pyright: ignore[reportPrivateUsage]
            conversation = Conversation(**(prepared or {}))
            # TranscriptSegment.segments_as_string is the canonical textual
            # rendering.  It ignores photos by construction.
            transcript = (conversation.get_transcript(include_timestamps=False) or "").strip()
            structured = conversation.structured
            title = (getattr(structured, "title", "") or "").strip() if structured else ""
            overview = (getattr(structured, "overview", "") or "").strip() if structured else ""
            category = getattr(getattr(structured, "category", None), "value", "") if structured else ""
            started = getattr(conversation, "started_at", None)
            started_label = started.astimezone(timezone.utc).strftime("%H:%M") if started else ""
        except Exception:
            return (), "incomplete"
        if title or overview:
            summary = " ".join(
                part for part in (started_label, f"({category})" if category else "", title, "—", overview) if part
            )
        else:
            # A finished conversation without a structured summary still counts
            # toward the day: fall back to a bounded transcript head so the
            # spine never silently omits an eligible source. The marker lets
            # the prompt hold these rows to a higher verification bar (raw
            # speech is the least trusted input in the spine).
            head = transcript[:MAX_SUMMARY_FALLBACK_TRANSCRIPT_CHARACTERS]
            summary = f"{UNSTRUCTURED_SUMMARY_MARKER} {head}" if head else ""
        summary = summary.strip()
        if not summary and not transcript:
            continue
        total_characters += len(summary)
        if total_characters > max_summary_characters:
            return (), "incomplete"
        rows.append(
            CompletedDayConversationSource(
                conversation_id=conversation_id,
                summary_text=summary,
                transcript_text=transcript,
                needs_folder=not (raw.get("folder_id") or "") and isinstance(raw.get("jit_first_open"), Mapping),
            )
        )
    rows.sort(key=lambda row: row.conversation_id)
    return tuple(rows), "complete"


def _completed_day_row_eligibility(raw: Mapping[str, Any]) -> Literal["eligible", "discarded", "unfinished"]:
    """Return the pre-extraction eligibility proof for one conversation row."""

    if bool(raw.get("discarded", False)):
        return "discarded"
    raw_status = raw.get("status")
    status = getattr(raw_status, "value", raw_status)
    if status != "completed" or not isinstance(raw.get("finished_at"), datetime):
        return "unfinished"
    return "eligible"


def _onboarding_transcript_eligibility(raw: Mapping[str, Any]) -> Literal["eligible", "discarded", "unfinished"]:
    """Require an onboarding transcript to be terminal and finalized."""

    if bool(raw.get("discarded", False)):
        return "discarded"
    raw_status = raw.get("status")
    status = getattr(raw_status, "value", raw_status)
    if status != "completed" or not isinstance(raw.get("finished_at"), datetime):
        return "unfinished"
    finalization_status = raw.get("finalization_status")
    if getattr(finalization_status, "value", finalization_status) != "completed":
        return "unfinished"
    return "eligible"


def _extract_daily_memory_candidates(uid: str, text: str) -> Tuple[Any, ...]:
    """Invoke Omi's existing bounded memory extractor for sweep input."""

    from utils.llm.memories import extract_memories_from_text

    # The model receives transcript text only.  ``strict`` makes provider or
    # parser failure visible to the producer rather than silently attesting an
    # empty day.
    return tuple(extract_memories_from_text(uid, text, "daily_summary", strict=True))


def _cached_summary_eligibility_attested(
    payload: Mapping[str, Any],
    *,
    local_date: date,
    window: CompletedLocalDayWindow,
    timezone_name: Optional[str] = None,
) -> bool:
    """Prove a cached candidate channel came from a completed-day producer.

    ``memory_candidates`` was historically an opportunistic cache field.  It
    is not sufficient evidence that all conversations in the UTC window were
    terminal, or that discarded/processing rows were excluded.  The cache is
    therefore accepted only with the producer's immutable attestation.
    """

    if payload.get("complete") is not True or payload.get("eligibility_proof") != "completed_transcript_v1":
        return False
    if payload.get("source_status") not in {"complete", "complete_zero"}:
        return False
    attestation = payload.get("eligibility_attestation")
    if not isinstance(attestation, Mapping):
        return False
    if (
        attestation.get("schema_version") != "completed_day_eligibility.v1"
        or attestation.get("local_date") != local_date.isoformat()
        or not isinstance(attestation.get("timezone_name"), str)
        or (timezone_name is not None and attestation.get("timezone_name") != timezone_name)
        or attestation.get("window_id") != window.window_id
        or attestation.get("window_start_utc") != window.start_utc
        or attestation.get("window_end_utc") != window.end_utc
    ):
        return False
    # Any discarded, processing, unfinished, or missing row makes the packet
    # incomplete.  Complete-zero is represented by all counts being zero.
    for key in ("eligible_count", "discarded_count", "processing_count", "unfinished_count"):
        value = attestation.get(key)
        if not isinstance(value, int) or value < 0:
            return False
    return (
        attestation["discarded_count"] == 0
        and attestation["processing_count"] == 0
        and attestation["unfinished_count"] == 0
    )


def _onboarding_consumed_keys(db_client: Any, uid: str) -> frozenset[str]:
    snapshot = db_client.document(f"users/{uid}/{ONBOARDING_CONSUMED_STATE_PATH}").get()
    if not getattr(snapshot, "exists", False):
        return frozenset()
    payload = snapshot.to_dict() or {}
    values = payload.get("consumed_source_keys") if isinstance(payload, dict) else None
    if not isinstance(values, list):
        return frozenset()
    return frozenset(str(value) for value in values if isinstance(value, str))


def _onboarding_source_receipt_is_committed(
    db_client: Any,
    uid: str,
    source_key: str,
    *,
    account_generation: Optional[int] = None,
) -> bool:
    """Read the exhaustive once-only receipt for one bounded source row."""

    try:
        snapshot = _onboarding_permanent_receipt_ref(db_client, uid, source_key).get()
    except Exception:
        return False
    payload = snapshot.to_dict() or {}
    if not getattr(snapshot, "exists", False) or payload.get("receipt_state") != "committed":
        return False
    if account_generation is not None:
        try:
            if int(payload.get("account_generation", -1)) != account_generation:
                return False
        except (TypeError, ValueError):
            return False
    return True


@dataclass(frozen=True)
class OnboardingSourceProduction:
    """Named result for the bounded onboarding producer contract."""

    candidates: Tuple[DailySweepCandidate, ...] = ()
    complete: bool = False
    source_keys: Tuple[str, ...] = ()
    source_progress: Mapping[str, int] = field(default_factory=dict)


def _load_or_stage_onboarding_candidates(
    uid: str,
    source_key: str,
    conversation_id: str,
    text: str,
    *,
    db_client: Any,
    extractor: Any,
    account_generation: Optional[int] = None,
    source_generation: Optional[int] = None,
    sweep_generation: Optional[int] = None,
    window_id: Optional[str] = None,
) -> Optional[Tuple[DailySweepCandidate, ...]]:
    """Materialize one deterministic candidate page before continuation slicing.

    Model extraction is intentionally outside the canonical write transaction,
    but it must never be repeated to obtain page two.  A durable stage stores
    the complete bounded page and both the transcript and candidate digests;
    any changed retry is rejected rather than silently selecting a different
    numeric slice from a nondeterministic model response.
    """

    stage_ref = _onboarding_staged_candidates_ref(
        db_client,
        uid,
        source_key,
        account_generation=account_generation,
        source_generation=source_generation,
        sweep_generation=sweep_generation or 1,
        window_id=window_id,
    )
    transcript_digest = deterministic_contract_id(
        "daily-sweep-onboarding-transcript", {"source_key": source_key, "text": text}
    )

    def read_staged(snapshot: Any) -> Optional[Tuple[DailySweepCandidate, ...]]:
        if not getattr(snapshot, "exists", False):
            return None
        payload = snapshot.to_dict() or {}
        expires_raw = payload.get("expires_at") if isinstance(payload, dict) else None
        try:
            expires_at = (
                expires_raw
                if isinstance(expires_raw, datetime)
                else datetime.fromisoformat(str(expires_raw).replace("Z", "+00:00"))
            )
            if expires_at.tzinfo is None or expires_at.astimezone(timezone.utc) <= datetime.now(timezone.utc):
                return None
        except (TypeError, ValueError):
            return None
        if (
            not isinstance(payload, dict)
            or payload.get("uid") != uid
            or payload.get("source_key") != source_key
            or payload.get("transcript_digest") != transcript_digest
            or not isinstance(payload.get("candidate_page"), list)
            or len(payload.get("candidate_page", ())) > MAX_ONBOARDING_STAGED_CANDIDATES
            or (account_generation is not None and payload.get("account_generation") != account_generation)
            or (source_generation is not None and payload.get("source_generation") != source_generation)
            or (sweep_generation is not None and payload.get("sweep_generation") != sweep_generation)
            or (window_id is not None and payload.get("window_id") != window_id)
        ):
            return None
        try:
            staged = tuple(DailySweepCandidate.model_validate(item) for item in payload["candidate_page"])
        except Exception:
            return None
        expected_digest = deterministic_contract_id(
            "daily-sweep-onboarding-candidate-page", {"digests": [item.digest() for item in staged]}
        )
        if payload.get("candidate_digest") != expected_digest:
            return None
        return staged

    try:
        staged_snapshot = stage_ref.get()
    except Exception:
        return None
    if getattr(staged_snapshot, "exists", False):
        # An existing but malformed stage is a durable integrity failure, not
        # a cache miss. Never rerun nondeterministic extraction against the
        # same source and then slice a different candidate page.
        try:
            return read_staged(staged_snapshot)
        except Exception:
            return None

    invocation_id = deterministic_contract_id(
        "daily-sweep-onboarding-model-invocation",
        {
            "uid": uid,
            "source_key": source_key,
            "transcript_digest": transcript_digest,
            "account_generation": account_generation,
            "source_generation": source_generation,
            "sweep_generation": sweep_generation,
            "window_id": window_id,
        },
    )[:96]

    def build_candidate_page() -> Tuple[dict[str, Any], ...]:
        extracted = tuple(extractor(uid, text) or ())
        if len(extracted) > MAX_ONBOARDING_STAGED_CANDIDATES:
            raise ValueError("onboarding model candidate budget exceeded")
        staged_list: List[DailySweepCandidate] = []
        for index, memory in enumerate(extracted):
            content = str(getattr(memory, "content", "") or "").strip()
            if not content:
                continue
            staged_list.append(
                DailySweepCandidate(
                    candidate_id=deterministic_contract_id(
                        "daily-sweep-onboarding-candidate",
                        {"uid": uid, "source": conversation_id, "index": index},
                    )[:128],
                    kind="fact",
                    operation="add",
                    content=content,
                    source_id=source_key,
                    source_type="onboarding",
                    source_version="onboarding-memory-model.v1",
                    source_refs=(f"conversation:{conversation_id}",),
                    authority=SweepAuthority.direct_user_statement,
                    subject_scope=MemorySubjectScope.primary_user,
                    subject_entity_id=getattr(memory, "subject_entity_id", None),
                )
            )
        if len(staged_list) > MAX_ONBOARDING_STAGED_CANDIDATES:
            raise ValueError("onboarding model candidate budget exceeded")
        return tuple(item.model_dump(mode="json") for item in staged_list)

    try:
        raw_staged = _invoke_model_once(
            db_client,
            uid,
            invocation_id,
            candidate_builder=build_candidate_page,
            account_generation=account_generation,
            source_generation=source_generation,
            sweep_generation=sweep_generation,
            window_id=window_id,
        )
        if raw_staged is None:
            return None
        staged = tuple(DailySweepCandidate.model_validate(item) for item in raw_staged)
        stage_payload = {
            "schema_version": "daily_memory_sweep_onboarding_stage.v1",
            "uid": uid,
            "source_key": source_key,
            "transcript_digest": transcript_digest,
            "candidate_digest": deterministic_contract_id(
                "daily-sweep-onboarding-candidate-page", {"digests": [item.digest() for item in staged]}
            ),
            "candidate_page": [item.model_dump(mode="json") for item in staged],
            "candidate_count": len(staged),
            "staged_at": datetime.now(timezone.utc),
            "expires_at": datetime.now(timezone.utc) + STAGED_CANDIDATE_RETENTION,
            "model_invocation_id": invocation_id,
        }
        if account_generation is not None:
            stage_payload["account_generation"] = account_generation
        if source_generation is not None:
            stage_payload["source_generation"] = source_generation
        if sweep_generation is not None:
            stage_payload["sweep_generation"] = sweep_generation
        if window_id is not None:
            stage_payload["window_id"] = window_id

        if (
            account_generation is not None
            and source_generation is not None
            and sweep_generation is not None
            and window_id
        ):

            def stage_if_open(transaction: Any) -> bool:
                deletion_ref, control_ref = _live_fence_refs(db_client, uid)
                if not _transaction_fence_open(
                    transaction,
                    deletion_ref,
                    control_ref,
                    uid=uid,
                    account_generation=account_generation,
                    source_generation=source_generation,
                ):
                    return False
                existing = stage_ref.get(transaction=transaction)
                if getattr(existing, "exists", False):
                    return False
                create = getattr(transaction, "create", None)
                if callable(create):
                    create(stage_ref, stage_payload)
                else:
                    transaction.set(stage_ref, stage_payload)
                return True

            try:
                if not firestore.transactional(stage_if_open)(db_client.transaction()):
                    return read_staged(stage_ref.get())
            except Exception:
                try:
                    return read_staged(stage_ref.get())
                except Exception:
                    return None
        else:
            create = getattr(stage_ref, "create", None)
            if callable(create):
                try:
                    create(stage_payload)
                except Exception:
                    return read_staged(stage_ref.get())
            else:
                stage_ref.set(stage_payload)
        return staged
    except Exception:
        return None


def _produce_onboarding_sources(
    uid: str,
    *,
    db_client: Any,
    max_candidates: int,
    model_authority: DailySweepModelAuthority,
    model_extractor: Optional[Any] = None,
    account_generation: Optional[int] = None,
    source_generation: Optional[int] = None,
    sweep_generation: Optional[int] = None,
) -> OnboardingSourceProduction:
    """Produce once-only facts from server-marked onboarding conversations.

    ``request.source`` and client onboarding flags are not provenance.  The
    listen runtime writes a random server-generated onboarding session marker
    into ``external_data``; only that marker is accepted here.  The returned
    source keys are consumed later, after all candidate receipts (or an
    explicit zero-candidate source receipt) commit.
    """

    collection = db_client.collection(f"users/{uid}/conversations")
    where = getattr(collection, "where", None)
    if not callable(where):
        return OnboardingSourceProduction()
    consumed = _onboarding_consumed_keys(db_client, uid)
    try:
        # The server-generated marker is the only provenance predicate. Read
        # bounded ordered pages and keep paging past consumed rows before the
        # processable cap. This cannot starve behind hundreds of old sources.
        snapshots: List[Any] = []
        after_snapshot: Optional[Any] = None
        for _ in range(MAX_ONBOARDING_SCAN_PAGES):
            query: Any = DAILY_SWEEP_ONBOARDING_CONVERSATIONS_QUERY.build(
                collection,
                {"onboarding_marker": ""},
                field_filter_factory=FieldFilter,
            )
            try:
                query = query.order_by("external_data.onboarding_session_id")
            except (AttributeError, TypeError):
                return OnboardingSourceProduction()
            if after_snapshot is not None:
                start_after = getattr(query, "start_after", None)
                if not callable(start_after):
                    return OnboardingSourceProduction()
                query = start_after(after_snapshot)
            page = list(query.limit(MAX_ONBOARDING_CONVERSATIONS).stream())
            if not page:
                break
            snapshots.extend(page)
            after_snapshot = page[-1]
            processable = sum(
                1
                for row in snapshots
                if f"onboarding:{getattr(row, 'id', '')}" not in consumed
                and not _onboarding_source_receipt_is_committed(
                    db_client,
                    uid,
                    f"onboarding:{getattr(row, 'id', '')}",
                    account_generation=account_generation,
                )
                and _onboarding_transcript_eligibility(row.to_dict() or {}) != "discarded"
            )
            if processable >= MAX_ONBOARDING_CONVERSATIONS or len(page) < MAX_ONBOARDING_CONVERSATIONS:
                break
    except Exception:
        return OnboardingSourceProduction()
    progress_snapshot = db_client.document(f"users/{uid}/{ONBOARDING_CONSUMED_STATE_PATH}").get()
    progress_payload = progress_snapshot.to_dict() if getattr(progress_snapshot, "exists", False) else {}
    raw_progress = progress_payload.get("candidate_offsets", {}) if isinstance(progress_payload, dict) else {}
    candidate_offsets = {
        key: int(value)
        for key, value in raw_progress.items()
        if isinstance(key, str) and key.startswith("onboarding:") and isinstance(value, int) and value >= 0
    }
    from database.conversations import (  # pyright: ignore[reportPrivateUsage]
        _prepare_conversation_for_read as prepare_conversation_for_read,  # pyright: ignore[reportPrivateUsage]
    )
    from models.conversation import Conversation

    rows: List[Tuple[str, str]] = []
    source_keys: List[str] = []
    source_progress: Dict[str, int] = {}
    zero_source_keys: List[str] = []
    total_characters = 0
    for snapshot in snapshots:
        conversation_id = str(getattr(snapshot, "id", "") or "")
        raw = snapshot.to_dict() or {}
        if not conversation_id or not isinstance(raw, dict):
            return OnboardingSourceProduction()
        external_data = raw.get("external_data")
        onboarding_session_id = external_data.get("onboarding_session_id") if isinstance(external_data, dict) else None
        if not isinstance(onboarding_session_id, str) or len(onboarding_session_id) < 16:
            continue
        source_key = f"onboarding:{conversation_id}"
        if source_key in consumed or _onboarding_source_receipt_is_committed(
            db_client, uid, source_key, account_generation=account_generation
        ):
            continue
        eligibility = _onboarding_transcript_eligibility(raw)
        if eligibility == "discarded":
            # Discarded captures are not consumed. If restored later, the
            # marker remains discoverable and can be processed once finalized.
            continue
        if eligibility != "eligible":
            return OnboardingSourceProduction()
        # Filtering occurs before the processable cap.  A consumed row never
        # occupies one of the eight source slots.
        if len(source_keys) >= MAX_ONBOARDING_CONVERSATIONS:
            continue
        source_keys.append(source_key)
        try:
            prepared = prepare_conversation_for_read(raw, uid)  # pyright: ignore[reportPrivateUsage]
            conversation = Conversation(**(prepared or {}))
            text = (conversation.get_transcript(include_timestamps=False) or "").strip()
        except Exception:
            return OnboardingSourceProduction()
        if not text:
            # An empty onboarding recording is a complete, consumed source; it
            # cannot become a direct memory later.
            zero_source_keys.append(source_key)
            continue
        total_characters += len(text)
        if total_characters > MAX_ONBOARDING_INPUT_CHARACTERS:
            return OnboardingSourceProduction()
        rows.append((conversation_id, text))
    if not rows:
        # Includes non-empty source rows whose model output is empty and
        # genuinely empty transcripts.  The caller still receives source_keys
        # so the source is consumed exactly once after the day packet commits.
        return OnboardingSourceProduction(complete=True, source_keys=tuple(source_keys))
    if not model_authority.route_is_budgeted:
        return OnboardingSourceProduction()
    extractor = model_extractor or _extract_daily_memory_candidates
    if model_extractor is None:
        from utils.llm.model_config import get_model

        if model_authority.model_name != get_model("memories"):
            return OnboardingSourceProduction()
    estimated_cost = (total_characters / 1000.0) * MODEL_COST_PER_1K_INPUT_CHARACTERS_USD
    if estimated_cost > model_authority.max_cost_usd:
        return OnboardingSourceProduction()
    candidates: List[DailySweepCandidate] = []
    processed_source_keys = list(zero_source_keys)
    try:
        for conversation_id, text in rows:
            source_key = f"onboarding:{conversation_id}"
            offset = candidate_offsets.get(source_key, 0)
            staged = _load_or_stage_onboarding_candidates(
                uid,
                source_key,
                conversation_id,
                text,
                db_client=db_client,
                extractor=extractor,
                account_generation=account_generation,
                source_generation=source_generation,
                sweep_generation=sweep_generation,
                window_id=f"onboarding:{source_key}" if source_generation is not None else None,
            )
            if staged is None or offset > len(staged):
                return OnboardingSourceProduction()
            available = max(0, max_candidates - len(candidates))
            row_candidates = list(staged[offset : offset + available])
            candidates.extend(row_candidates)
            next_offset = offset + len(row_candidates)
            if next_offset >= len(staged):
                processed_source_keys.append(source_key)
            else:
                # Preserve the unconsumed tail for a later bounded packet. The
                # page itself is durable, so this offset is never applied to a
                # fresh nondeterministic model response.
                source_progress[source_key] = next_offset
                processed_source_keys.append(source_key)
            if len(candidates) >= max_candidates:
                break
    except Exception:
        return OnboardingSourceProduction()
    # Sources after the bounded candidate page remain retryable.  They are not
    # included in the source-completion attestation for this packet.
    return OnboardingSourceProduction(
        candidates=tuple(candidates),
        complete=True,
        source_keys=tuple(sorted(set(processed_source_keys))),
        source_progress=source_progress,
    )


_FOLDER_ASSIGNMENT_PAGE_KIND = "__daily_sweep_kind"


def _split_daily_summary_page(
    page: Sequence[Mapping[str, Any]],
) -> Tuple[Tuple[dict[str, Any], ...], Tuple[Dict[str, str], ...]]:
    """Split one invocation page into candidate dicts and folder assignments."""

    candidates: List[dict[str, Any]] = []
    assignments: List[Dict[str, str]] = []
    for item in page:
        if item.get(_FOLDER_ASSIGNMENT_PAGE_KIND) == "folder_assignment":
            conversation_id = str(item.get("conversation_id") or "")
            folder_id = str(item.get("folder_id") or "")
            if conversation_id and folder_id:
                assignments.append({"conversation_id": conversation_id, "folder_id": folder_id})
            continue
        candidates.append(dict(item))
    assignments.sort(key=lambda row: row["conversation_id"])
    return tuple(candidates), tuple(assignments)


def _load_or_stage_daily_summary_candidates(
    uid: str,
    local_date: date,
    timezone_name: str,
    control: MemoryControlState,
    window: CompletedLocalDayWindow,
    conversation_rows: Sequence[CompletedDayConversationSource],
    *,
    db_client: Any,
    agent_runner: Any,
    folder_options: Sequence[Tuple[str, str]] = (),
    max_candidates: int,
    max_transcript_fetches: int = MAX_DAILY_TRANSCRIPT_FETCHES,
    max_fetch_characters: int = MAX_DAILY_TRANSCRIPT_FETCH_CHARACTERS,
    max_memory_lookups: int = MAX_DAILY_MEMORY_LOOKUPS,
    max_provider_retries: Optional[int] = None,
    dispatch_evidence: Optional[Dict[str, Any]] = None,
    max_input_tokens: Optional[int] = None,
    max_output_tokens: Optional[int] = None,
    jit_run_id: Optional[str] = None,
    jit_max_spend_micro_usd: Optional[int] = None,
    sweep_generation: int = 1,
) -> Optional[Tuple[Tuple[DailySweepCandidate, ...], Tuple[Dict[str, str], ...]]]:
    """Stage the complete bounded daily-summary agent page before apply.

    The whole two-phase agent run (summary spine plus bounded transcript
    verification) is ONE at-most-once invocation; the staged page carries both
    the memory candidates and the folder assignments for unopened
    conversations, so a crash-and-retry replays the exact same outputs.
    """

    stage_ref = _daily_summary_staged_candidates_ref(
        db_client,
        uid,
        local_date,
        account_generation=control.account_generation,
        source_generation=control.source_generation,
        window_id=window.window_id,
        sweep_generation=sweep_generation,
    )
    transcript_digest = deterministic_contract_id(
        "daily-sweep-daily-summary-transcript",
        {
            "uid": uid,
            "local_date": local_date.isoformat(),
            "rows": [{"source": row.conversation_id, "text": row.summary_text} for row in conversation_rows],
        },
    )

    def read_staged(
        snapshot: Any,
    ) -> Optional[Tuple[Tuple[DailySweepCandidate, ...], Tuple[Dict[str, str], ...]]]:
        if not getattr(snapshot, "exists", False):
            return None
        payload = snapshot.to_dict() or {}
        if (
            isinstance(payload, dict)
            and payload.get("schema_version") != DAILY_SUMMARY_STAGE_SCHEMA_VERSION
            and str(payload.get("schema_version") or "").startswith("daily_memory_sweep_daily_summary_stage.")
        ):
            # A stage written by a different deployment of this module is
            # unreadable here, but it is not corrupt: the deployment that
            # wrote it owned this window's model invocation and its own apply
            # path.  Re-extracting would double-bill and could conflict with
            # that deployment's receipts, and refusing forever would stall the
            # cursor on every schema bump.  Attest the day as consumed with no
            # further candidates so the cursor can advance.
            return (), ()
        expires_raw = payload.get("expires_at") if isinstance(payload, dict) else None
        try:
            expires_at = (
                expires_raw
                if isinstance(expires_raw, datetime)
                else datetime.fromisoformat(str(expires_raw).replace("Z", "+00:00"))
            )
            if expires_at.tzinfo is None or expires_at.astimezone(timezone.utc) <= datetime.now(timezone.utc):
                return None
        except (TypeError, ValueError):
            return None
        raw_assignments = payload.get("folder_assignments", []) if isinstance(payload, dict) else None
        if (
            not isinstance(payload, dict)
            or payload.get("schema_version") != DAILY_SUMMARY_STAGE_SCHEMA_VERSION
            or payload.get("uid") != uid
            or payload.get("local_date") != local_date.isoformat()
            or payload.get("timezone_name") != timezone_name
            or payload.get("account_generation") != control.account_generation
            or payload.get("source_generation") != control.source_generation
            or payload.get("sweep_generation") != sweep_generation
            or payload.get("window_id") != window.window_id
            or payload.get("window_start_utc") != window.start_utc
            or payload.get("window_end_utc") != window.end_utc
            or payload.get("transcript_digest") != transcript_digest
            or not isinstance(payload.get("candidate_page"), list)
            or len(payload["candidate_page"]) > MAX_CANDIDATES_PER_DAY
            or payload.get("candidate_count") != len(payload["candidate_page"])
            or not isinstance(raw_assignments, list)
            or len(raw_assignments) > MAX_COMPLETED_DAY_SUMMARY_CONVERSATIONS
        ):
            return None
        try:
            staged = tuple(DailySweepCandidate.model_validate(item) for item in payload["candidate_page"])
            assignments = tuple(
                {"conversation_id": str(item["conversation_id"]), "folder_id": str(item["folder_id"])}
                for item in raw_assignments
            )
        except Exception:
            return None
        expected_digest = deterministic_contract_id(
            "daily-sweep-daily-summary-candidate-page",
            {"digests": [item.digest() for item in staged], "folder_assignments": list(assignments)},
        )
        if payload.get("candidate_digest") != expected_digest:
            return None
        if jit_run_id is not None:
            # A QA run may reuse only a stage created by this exact server run.
            # A pre-existing stage has no trustworthy relationship to the
            # current gateway request, so treating it as a cache hit would
            # bypass the one-request QA proof and could double-apply stale
            # candidates.
            if payload.get("jit_run_id") != jit_run_id:
                return None
            staged_dispatch = payload.get("dispatch_evidence")
            if not isinstance(staged_dispatch, Mapping):
                return None
            requests = staged_dispatch.get("requests")
            if (
                staged_dispatch.get("feature") != "memories"
                or staged_dispatch.get("jit_run_id") != jit_run_id
                or not isinstance(requests, list)
                or len(requests) != 1
            ):
                return None
        if dispatch_evidence is not None and isinstance(payload.get("dispatch_evidence"), Mapping):
            dispatch_evidence.update(dict(payload["dispatch_evidence"]))
        return staged, assignments

    try:
        staged_snapshot = stage_ref.get()
    except Exception:
        return None
    if getattr(staged_snapshot, "exists", False):
        # An existing malformed stage is an integrity failure. Re-extracting
        # would let a nondeterministic model response conflict with receipts
        # created by the first attempt.
        return read_staged(staged_snapshot)

    invocation_id = deterministic_contract_id(
        "daily-sweep-daily-summary-model-invocation",
        {
            "uid": uid,
            "local_date": local_date.isoformat(),
            "transcript_digest": transcript_digest,
            "account_generation": control.account_generation,
            "source_generation": control.source_generation,
            "sweep_generation": sweep_generation,
            "window_id": window.window_id,
        },
    )[:96]

    def build_candidate_page() -> Tuple[dict[str, Any], ...]:
        summary_rows = tuple((row.conversation_id, row.summary_text) for row in conversation_rows)
        transcript_lookup = {row.conversation_id: row.transcript_text for row in conversation_rows}
        needs_folder_ids = tuple(row.conversation_id for row in conversation_rows if row.needs_folder)
        # The server-owned UID must be in the context at the model boundary so
        # GatewayContextChatOpenAI emits X-Omi-User-Uid and feature headers.
        # Keep this around the actual runner call: QA and production adapters
        # can supply different runners, and the context must not leak between
        # scheduler users.
        with track_usage(uid, Features.MEMORIES):
            output = agent_runner(
                uid,
                summary_rows,
                transcript_lookup,
                folder_options=tuple(folder_options) if needs_folder_ids else (),
                needs_folder_ids=needs_folder_ids,
                max_candidates=max_candidates,
                max_transcript_fetches=max_transcript_fetches,
                max_fetch_characters=max_fetch_characters,
                memory_searcher=_daily_sweep_ledger_searcher(uid, db_client=db_client),
                max_memory_lookups=max_memory_lookups,
                cache_key=f"daily-sweep:{uid}",
                max_provider_retries=max_provider_retries,
                max_input_tokens=max_input_tokens,
                max_output_tokens=max_output_tokens,
                jit_run_id=jit_run_id,
                jit_max_spend_micro_usd=jit_max_spend_micro_usd,
                dispatch_evidence=dispatch_evidence,
            )
        candidates: List[DailySweepCandidate] = []
        for index, memory in enumerate(getattr(output, "memories", ()) or ()):
            content = str(getattr(memory, "content", "") or "").strip()[:MAX_CONTENT_CHARACTERS]
            cited = [
                str(conversation_id)
                for conversation_id in (getattr(memory, "conversation_ids", ()) or ())
                if str(conversation_id) in transcript_lookup
            ]
            if not content or not cited:
                # A memory without provenance into this day's rows is dropped:
                # candidates may never fabricate source references.
                continue
            candidates.append(
                DailySweepCandidate(
                    candidate_id=deterministic_contract_id(
                        "daily-sweep-model-candidate",
                        {
                            "uid": uid,
                            "date": local_date.isoformat(),
                            "source": f"conversation:{cited[0]}",
                            "index": index,
                        },
                    )[:128],
                    kind="fact",
                    operation="add",
                    content=content,
                    source_id=f"conversation:{cited[0]}",
                    source_type="daily_summary",
                    source_version="daily-memory-agent.v1",
                    source_refs=tuple(f"conversation:{conversation_id}" for conversation_id in cited[:MAX_SOURCE_REFS]),
                    authority=SweepAuthority.sweep_inference,
                    subject_scope=MemorySubjectScope.primary_user,
                    subject_entity_id=getattr(memory, "subject_entity_id", None),
                    # A slot names a standing attribute; the canonical occupancy
                    # check turns an occupied-slot add into an amend, which is
                    # how the daily run maintains the rendered profile.
                    slot=(str(getattr(memory, "slot", "") or "").strip() or None),
                )
            )
            if len(candidates) >= max_candidates:
                break
        if len(candidates) > MAX_CANDIDATES_PER_DAY:
            raise ValueError("daily summary model candidate budget exceeded")
        valid_folder_ids = {folder_id for folder_id, _name in folder_options}
        assignment_rows = [
            {
                _FOLDER_ASSIGNMENT_PAGE_KIND: "folder_assignment",
                "conversation_id": str(getattr(assignment, "conversation_id", "") or ""),
                "folder_id": str(getattr(assignment, "folder_id", "") or ""),
            }
            for assignment in (getattr(output, "folder_assignments", ()) or ())
            if str(getattr(assignment, "conversation_id", "") or "") in set(needs_folder_ids)
            and str(getattr(assignment, "folder_id", "") or "") in valid_folder_ids
        ]
        assignment_rows.sort(key=lambda row: row["conversation_id"])
        return tuple(item.model_dump(mode="json") for item in candidates) + tuple(assignment_rows)

    try:
        raw_candidates = _invoke_model_once(
            db_client,
            uid,
            invocation_id,
            candidate_builder=build_candidate_page,
            account_generation=control.account_generation,
            source_generation=control.source_generation,
            sweep_generation=sweep_generation,
            window_id=window.window_id,
        )
        if raw_candidates is None:
            return None
        candidate_dicts, folder_assignments = _split_daily_summary_page(raw_candidates)
        candidate_page = tuple(DailySweepCandidate.model_validate(item) for item in candidate_dicts)
        stage_payload = {
            "schema_version": DAILY_SUMMARY_STAGE_SCHEMA_VERSION,
            "uid": uid,
            "local_date": local_date.isoformat(),
            "timezone_name": timezone_name,
            "account_generation": control.account_generation,
            "source_generation": control.source_generation,
            "sweep_generation": sweep_generation,
            "window_id": window.window_id,
            "window_start_utc": window.start_utc,
            "window_end_utc": window.end_utc,
            "transcript_digest": transcript_digest,
            "candidate_digest": deterministic_contract_id(
                "daily-sweep-daily-summary-candidate-page",
                {
                    "digests": [item.digest() for item in candidate_page],
                    "folder_assignments": list(folder_assignments),
                },
            ),
            "candidate_page": [item.model_dump(mode="json") for item in candidate_page],
            "candidate_count": len(candidate_page),
            "folder_assignments": list(folder_assignments),
            "staged_at": datetime.now(timezone.utc),
            "expires_at": datetime.now(timezone.utc) + STAGED_CANDIDATE_RETENTION,
            "model_invocation_id": invocation_id,
            "dispatch_evidence": dict(dispatch_evidence or {}),
        }
        if jit_run_id is not None:
            stage_payload["jit_run_id"] = jit_run_id

        def stage_if_open(transaction: Any) -> bool:
            deletion_ref, control_ref = _live_fence_refs(db_client, uid)
            if not _transaction_fence_open(
                transaction,
                deletion_ref,
                control_ref,
                uid=uid,
                account_generation=control.account_generation,
                source_generation=control.source_generation,
            ):
                return False
            existing = stage_ref.get(transaction=transaction)
            if getattr(existing, "exists", False):
                return False
            create = getattr(transaction, "create", None)
            if callable(create):
                create(stage_ref, stage_payload)
            else:
                transaction.set(stage_ref, stage_payload)
            return True

        try:
            if not firestore.transactional(stage_if_open)(db_client.transaction()):
                return read_staged(stage_ref.get())
        except Exception:
            return read_staged(stage_ref.get())
        return candidate_page, folder_assignments
    except Exception:
        return None


def _daily_sweep_ledger_searcher(uid: str, *, db_client: Any) -> Any:
    """Build the read-only prior-memory search seam for the daily agent.

    Keyword search runs against the versioned ledger projection (provider
    fail-soft: an unconfigured or failing index yields no matches, never a
    failed day) and every hit is re-read through the authoritative canonical
    store before its content is disclosed to the model.
    """

    def search(query: str) -> Tuple[str, ...]:
        try:
            from utils.memory.atom_keyword_index import keyword_search_ledger_memory_ids

            memory_ids = keyword_search_ledger_memory_ids(uid, query, limit=8, db_client=db_client)
        except Exception:
            return ()
        results: List[str] = []
        for memory_id in memory_ids[:8]:
            try:
                item = read_canonical_memory_item(uid, memory_id, db_client=db_client)
            except Exception:
                continue
            if item is None or item.status != MemoryItemStatus.active:
                continue
            slot_label = f" [slot: {item.slot}]" if getattr(item, "slot", None) else ""
            results.append(f"{item.content}{slot_label}")
        return tuple(results)

    return search


def _read_daily_sweep_folder_options(uid: str, *, db_client: Any) -> Tuple[Tuple[str, str], ...]:
    """Read the user's folder taxonomy for the agent's folder task, fail-soft.

    Folder metadata is a prompt convenience, never an eligibility proof: any
    failure returns an empty tuple so the day's memory formation proceeds
    without a folder task rather than blocking on cosmetic data.
    """

    try:
        collection = db_client.collection(f"users/{uid}/folders")
        snapshots = list(collection.limit(MAX_LEGACY_COMPAT_OCCUPANTS).stream())
    except Exception:
        return ()
    options: List[Tuple[str, str]] = []
    for snapshot in snapshots:
        payload = snapshot.to_dict() if hasattr(snapshot, "to_dict") else None
        if not isinstance(payload, dict) or payload.get("deleted"):
            continue
        folder_id = str(getattr(snapshot, "id", "") or payload.get("id") or "").strip()
        name = str(payload.get("name") or "").strip()[:64]
        if folder_id:
            options.append((folder_id, name))
    options.sort(key=lambda option: option[0])
    return tuple(options)


def _apply_daily_sweep_folder_assignments(
    uid: str,
    assignments: Sequence[Mapping[str, str]],
    *,
    db_client: Any,
    valid_folder_ids: set,
) -> int:
    """Idempotently backstop folder assignment for unopened conversations.

    Guards per row: the conversation must still exist, be non-discarded, carry
    a first-open obligation, and have no folder yet — a folder set by the
    first-open worker (or the user) in the meantime always wins.  The check
    and the write share one transaction so a concurrent first-open or user
    assignment cannot be clobbered by a stale read.  Every row is
    best-effort: replaying a staged page after a crash re-applies only the
    rows that are still unfiled.
    """

    def assign_if_unfiled(transaction: Any, reference: Any, folder_id: str) -> bool:
        snapshot = reference.get(transaction=transaction)
        raw = snapshot.to_dict() if getattr(snapshot, "exists", False) else None
        if (
            not isinstance(raw, dict)
            or raw.get("discarded")
            or (raw.get("folder_id") or "")
            or not isinstance(raw.get("jit_first_open"), Mapping)
        ):
            return False
        transaction.set(reference, {"folder_id": folder_id}, merge=True)
        return True

    applied = 0
    for assignment in assignments:
        conversation_id = str(assignment.get("conversation_id") or "")
        folder_id = str(assignment.get("folder_id") or "")
        if not conversation_id or folder_id not in valid_folder_ids:
            continue
        try:
            reference = db_client.document(f"users/{uid}/conversations/{conversation_id}")
            if not firestore.transactional(assign_if_unfiled)(db_client.transaction(), reference, folder_id):
                continue
            applied += 1
        except Exception:
            continue
        try:
            from database.folders import update_folder_conversation_count

            update_folder_conversation_count(uid, folder_id)
        except Exception:
            # Count refresh is a display convenience; the next assignment or
            # first-open count commit converges it.
            pass
    return applied


def produce_completed_day_daily_summary_sources(
    uid: str,
    local_date: date,
    timezone_name: str,
    control: MemoryControlState,
    *,
    db_client: Any,
    model_authority: Optional[DailySweepModelAuthority] = None,
    agent_runner: Optional[Any] = None,
    window_override: Optional[CompletedLocalDayWindow] = None,
    sweep_generation: int = 1,
    qa_run_id: Optional[str] = None,
) -> DailySweepRuntimeSources:
    """Produce the exact completed-day source, including its bounded agent run.

    A summary document is a cache, not a producer authority.  When its
    candidate channel is absent, this function reads the completed day's
    conversation SUMMARIES as one spine and runs the bounded two-phase daily
    agent (summaries in; the agent may pull a bounded number of raw transcript
    excerpts to verify specifics) behind the explicit model/cost seam.  The
    same run assigns folders for the day's unopened, unfiled conversations.
    The cursor advances for an empty day only after a bounded source query
    proves that the day contained no textual conversations (or a summary
    explicitly attests zero conversations).
    """

    window = window_override or completed_local_day_window(local_date, timezone_name)
    collection = db_client.collection(f"users/{uid}/daily_summaries")
    where = getattr(collection, "where", None)
    if not callable(where):
        raise ValueError("daily summary completed-day query is unavailable")
    try:
        try:
            query: Any = where(filter=FieldFilter("date", "==", local_date.isoformat()))
        except TypeError:
            query = where("date", "==", local_date.isoformat())
        snapshots = list(query.limit(1).stream())
    except Exception as exc:
        raise ValueError("daily summary completed-day query failed") from exc
    payload: Dict[str, Any] = {}
    if snapshots:
        payload_value = snapshots[0].to_dict() or {}
        if not isinstance(payload_value, dict):
            raise ValueError("daily summary payload is malformed")
        payload = payload_value
        if payload.get("date") != local_date.isoformat():
            raise ValueError("daily summary date identity mismatch")
        if any(key in payload for key in ("window_id", "window_start_utc", "window_end_utc")) and (
            payload.get("window_id") != window.window_id
            or payload.get("window_start_utc") != window.start_utc
            or payload.get("window_end_utc") != window.end_utc
        ):
            raise ValueError("daily summary window identity mismatch")

    model = model_authority or daily_memory_sweep_model_authority_from_environment()

    is_qa_run = qa_run_id is not None
    # A persisted candidate list is accepted only when the model authority is
    # open.  In particular, a missing key is not interpreted as []: older
    # summary writers did not produce this field and must not advance the new
    # cursor without a producer proof.
    if "memory_candidates" in payload:
        if is_qa_run:
            # QA must observe a fresh, bounded gateway request. A historical
            # summary cache is a producer artifact from another run and cannot
            # prove this run's request, usage, or spend.
            return DailySweepRuntimeSources.from_iterables(source_status="incomplete")
        raw_candidates = payload.get("memory_candidates")
        if (
            raw_candidates is None
            or payload.get("uid") != uid
            or payload.get("account_generation") != control.account_generation
            or payload.get("source_generation") != control.source_generation
            or payload.get("timezone_name") != timezone_name
            or not _cached_summary_eligibility_attested(
                payload, local_date=local_date, window=window, timezone_name=timezone_name
            )
        ):
            return DailySweepRuntimeSources.from_iterables(source_status="incomplete")
        if not model.route_is_budgeted:
            return DailySweepRuntimeSources.from_iterables(source_status="incomplete")
        persisted_candidates = _bounded_candidate_channel(
            raw_candidates,
            source_type="daily_summary",
            authority=SweepAuthority.sweep_inference,
            max_candidates=model.max_candidates,
        )
        return DailySweepRuntimeSources.from_iterables(
            daily_summary=persisted_candidates,
            complete=True,
            source_status="complete" if persisted_candidates else "complete_zero",
            model_cost_usd=0.0,
        )

    max_summary_conversations = (
        QA_SWEEP_MAX_SUMMARY_CONVERSATIONS if is_qa_run else MAX_COMPLETED_DAY_SUMMARY_CONVERSATIONS
    )
    max_summary_characters = (
        QA_SWEEP_MAX_SUMMARY_INPUT_CHARACTERS if is_qa_run else MAX_COMPLETED_DAY_SUMMARY_INPUT_CHARACTERS
    )
    max_transcript_fetches = QA_SWEEP_MAX_TRANSCRIPT_FETCHES if is_qa_run else MAX_DAILY_TRANSCRIPT_FETCHES
    max_fetch_characters = (
        QA_SWEEP_MAX_TRANSCRIPT_FETCH_CHARACTERS if is_qa_run else MAX_DAILY_TRANSCRIPT_FETCH_CHARACTERS
    )
    max_memory_lookups = QA_SWEEP_MAX_MEMORY_LOOKUPS if is_qa_run else MAX_DAILY_MEMORY_LOOKUPS
    conversation_rows, conversation_status = _read_completed_day_conversation_sources(
        uid,
        window,
        db_client=db_client,
        max_conversations=max_summary_conversations,
        max_summary_characters=max_summary_characters,
    )
    if conversation_status == "incomplete":
        return DailySweepRuntimeSources.from_iterables(source_status="incomplete")
    if not conversation_rows:
        # The query itself is the producer's complete-zero attestation.  A
        # missing summary is therefore safe only after this proof, never from
        # a missing Firestore document alone.
        return DailySweepRuntimeSources.from_iterables(
            complete=True,
            source_status="complete_zero",
            eligibility_proof="completed_transcript_v1",
        )
    if not model.route_is_budgeted:
        return DailySweepRuntimeSources.from_iterables(source_status="incomplete")

    runner = agent_runner
    dispatch_evidence: Dict[str, Any] = {}
    if runner is None:
        # The deployment may only name the model configured for the existing
        # memory route.  It cannot select an arbitrary model through a source
        # packet or staging document.
        from utils.llm.model_config import get_model

        if model.model_name != get_model("memories"):
            return DailySweepRuntimeSources.from_iterables(source_status="incomplete")
        from utils.llm.memories import run_daily_sweep_summary_agent

        runner = run_daily_sweep_summary_agent
    from utils.llm.memories import daily_sweep_phase_b_overhead_characters

    spine_characters = sum(len(row.summary_text) for row in conversation_rows)
    # Conservative ceiling: the spine is sent in phase A, and a verification
    # phase may re-send the spine plus the full transcript-fetch budget plus
    # the clamped model-controlled additions (draft memories, request reasons,
    # lookup queries and results).  The budget check must hold for the worst
    # case before any provider call.
    estimated_cost = (
        (
            2 * spine_characters
            + max_transcript_fetches * max_fetch_characters
            + (
                daily_sweep_phase_b_overhead_characters(
                    max_memory_lookups,
                    max_candidate_rows=model.max_candidates,
                )
                if is_qa_run
                else daily_sweep_phase_b_overhead_characters(max_memory_lookups)
            )
        )
        / 1000.0
    ) * MODEL_COST_PER_1K_INPUT_CHARACTERS_USD
    if is_qa_run:
        # The character heuristic above prices only the source spine.  The
        # gateway reservation is the final authority, but the producer should
        # also refuse a QA run whose configured worst-case input/output
        # envelope would exceed its own model budget.  Read the checked-in
        # gateway card instead of duplicating its rates here.
        from llm_gateway.gateway.accounting import rate_card_for, rounded_micro_usd

        rate_card = rate_card_for("openai", QA_SWEEP_MODEL_NAME)
        if rate_card is None:
            return DailySweepRuntimeSources.from_iterables(source_status="incomplete")
        rates = rate_card.effective_rates(QA_SWEEP_MAX_INPUT_TOKENS)
        envelope_cost_usd = (
            rounded_micro_usd(
                QA_SWEEP_MAX_INPUT_TOKENS * rates.input_micro_usd_per_million
                + QA_SWEEP_MAX_OUTPUT_TOKENS * rates.output_micro_usd_per_million
            )
            / 1_000_000
        )
        estimated_cost = max(estimated_cost, envelope_cost_usd)
    if estimated_cost > model.max_cost_usd:
        return DailySweepRuntimeSources.from_iterables(source_status="incomplete")
    folder_options = (
        _read_daily_sweep_folder_options(uid, db_client=db_client)
        if any(row.needs_folder for row in conversation_rows)
        else ()
    )
    staged = _load_or_stage_daily_summary_candidates(
        uid,
        local_date,
        timezone_name,
        control,
        window,
        conversation_rows,
        db_client=db_client,
        agent_runner=runner,
        folder_options=folder_options,
        max_candidates=model.max_candidates,
        max_transcript_fetches=max_transcript_fetches,
        max_fetch_characters=max_fetch_characters,
        max_memory_lookups=max_memory_lookups,
        max_provider_retries=QA_SWEEP_MAX_SDK_RETRIES if is_qa_run else None,
        dispatch_evidence=dispatch_evidence if is_qa_run else None,
        max_input_tokens=QA_SWEEP_MAX_INPUT_TOKENS if is_qa_run else None,
        max_output_tokens=QA_SWEEP_MAX_OUTPUT_TOKENS if is_qa_run else None,
        jit_run_id=qa_run_id,
        jit_max_spend_micro_usd=QA_SWEEP_MAX_SPEND_MICRO_USD if is_qa_run else None,
        sweep_generation=sweep_generation,
    )
    if staged is None:
        # Model/provider failures and malformed existing stages are source
        # incompleteness, never permission to re-extract or advance.
        return DailySweepRuntimeSources.from_iterables(source_status="incomplete")
    candidates, folder_assignments = staged
    if folder_assignments:
        # Folder assignment is cosmetic and idempotent; a partial failure here
        # must never block or invalidate the day's memory formation.
        _apply_daily_sweep_folder_assignments(
            uid,
            folder_assignments,
            db_client=db_client,
            valid_folder_ids={folder_id for folder_id, _name in folder_options},
        )
    return DailySweepRuntimeSources.from_iterables(
        daily_summary=candidates,
        complete=True,
        source_status="complete" if candidates else "complete_zero",
        eligibility_proof="completed_transcript_v1",
        model_cost_usd=estimated_cost,
        model_dispatch_evidence=dispatch_evidence,
    )


def produce_onboarding_seed_sources(
    uid: str,
    *,
    db_client: Any,
    max_candidates: int = 8,
) -> Tuple[DailySweepCandidate, ...]:
    """Return candidates from the real onboarding conversation source.

    The old adapter read ``users.onboarding.memory_candidates`` even though no
    writer ever persisted that field.  Onboarding is represented by
    conversations carrying a server-generated session marker.  Consumption is
    marked transactionally after the source's candidate receipts complete.
    """

    control = ensure_canonical_apply_control_state(uid, db_client=db_client)
    cursor = _read_cursor(db_client, uid, control)
    production = _produce_onboarding_sources(
        uid,
        db_client=db_client,
        max_candidates=max_candidates,
        model_authority=daily_memory_sweep_model_authority_from_environment(),
        account_generation=control.account_generation,
        source_generation=control.source_generation,
        sweep_generation=cursor.sweep_generation,
    )
    return production.candidates


def _iter_active_standing_triggers(uid: str, *, db_client: Any) -> Tuple[MemoryItem, ...]:
    """Read the bounded trigger-repair cohort through an authoritative query."""

    collection = db_client.collection(MemoryCollections(uid=uid).memory_items)
    where = getattr(collection, "where", None)
    if not callable(where):
        raise ValueError("standing-trigger reconciliation query is unavailable")
    query = collection
    for field_name, value in (
        ("status", MemoryItemStatus.active.value),
        ("kind", MemoryKind.trigger.value),
        ("write_reason", LedgerWriteReason.standing_trigger.value),
    ):
        try:
            query = query.where(filter=FieldFilter(field_name, "==", value))
        except TypeError:
            query = query.where(field_name, "==", value)
    try:
        snapshots = list(query.limit(MAX_WRITES_PER_DAY + 1).stream())
    except Exception as exc:
        raise ValueError("standing-trigger reconciliation query failed") from exc
    if len(snapshots) > MAX_WRITES_PER_DAY:
        raise ValueError("standing-trigger reconciliation exceeded proof budget")
    items: List[MemoryItem] = []
    for snapshot in snapshots:
        payload = snapshot.to_dict() or {}
        if not isinstance(payload, dict):
            raise ValueError("standing-trigger row is malformed")
        item = MemoryItem.model_validate(payload)
        if (
            item.uid == uid
            and item.status == MemoryItemStatus.active
            and item.kind == MemoryKind.trigger
            and item.write_reason == LedgerWriteReason.standing_trigger
        ):
            items.append(item)
    return tuple(sorted(items, key=lambda item: item.memory_id))


def firestore_daily_sweep_source_provider(
    uid: str,
    local_date: date,
    control: MemoryControlState,
    *,
    db_client: Any,
    timezone_name: str = "UTC",
    window_override: Optional[CompletedLocalDayWindow] = None,
    qa_run_id: Optional[str] = None,
) -> DailySweepRuntimeSources:
    """Read one bounded backend-produced source packet for the scheduler.

    The document is intentionally a staging/adaptor record, not a second
    memory authority.  Existing daily-summary, onboarding-cold-start, and
    standing-trigger reconciliation producers may write this typed packet;
    canonical memory remains the only durable output authority.
    """

    current_cursor = _read_cursor(db_client, uid, control)

    ref = db_client.document(f"{MemoryCollections(uid=uid).daily_memory_sweep_sources}/{local_date.isoformat()}")
    snapshot = ref.get()
    if not getattr(snapshot, "exists", False):
        # The source is not allowed to advance the cursor merely because the
        # staging document is absent. Fall back only to the durable completed-
        # day summary producer; its missing-summary result remains incomplete.
        summary_sources = produce_completed_day_daily_summary_sources(
            uid,
            local_date,
            timezone_name,
            control,
            db_client=db_client,
            window_override=window_override,
            sweep_generation=current_cursor.sweep_generation,
            qa_run_id=qa_run_id,
        )
        if qa_run_id is not None:
            # Onboarding is a separate producer path and may add another model
            # invocation.  QA input must come from an eligible completed
            # recorded conversation source, so stop at the summary producer.
            return summary_sources
        model_authority = daily_memory_sweep_model_authority_from_environment()
        onboarding_production = _produce_onboarding_sources(
            uid,
            db_client=db_client,
            max_candidates=model_authority.max_candidates,
            model_authority=model_authority,
            account_generation=control.account_generation,
            source_generation=control.source_generation,
            sweep_generation=current_cursor.sweep_generation,
        )
        return DailySweepRuntimeSources.from_iterables(
            daily_summary=summary_sources.daily_summary,
            onboarding_cold_start=onboarding_production.candidates,
            onboarding_source_keys=onboarding_production.source_keys,
            onboarding_source_progress=onboarding_production.source_progress,
            complete=summary_sources.complete and onboarding_production.complete,
            source_status=(
                "incomplete"
                if not (summary_sources.complete and onboarding_production.complete)
                else (
                    "complete" if summary_sources.candidates() or onboarding_production.candidates else "complete_zero"
                )
            ),
            eligibility_proof=summary_sources.eligibility_proof,
            model_cost_usd=summary_sources.model_cost_usd,
            model_dispatch_evidence=summary_sources.model_dispatch_evidence,
        )
    if qa_run_id is not None:
        # The QA producer must read the completed conversation source and make
        # its bounded gateway request in this run. A pre-existing adapter
        # packet can contain ordinary production-sized candidates and has no
        # trustworthy request/usage join, even when its generations match.
        raise ValueError("QA sweep cannot reuse a pre-existing source packet")
    raw_payload = snapshot.to_dict() or {}
    payload: Dict[str, Any] = raw_payload if isinstance(raw_payload, dict) else {}
    # A staged packet is an immutable producer artifact.  Missing identity is
    # not repaired from scheduler state: accepting it would let a stale packet
    # be restamped into a new account/source generation or timezone window.
    if not payload or payload.get("schema_version") != SCHEMA_VERSION or payload.get("uid") != uid:
        raise ValueError("daily sweep source packet owner mismatch")
    if payload.get("local_date") != local_date.isoformat():
        raise ValueError("daily sweep source packet local date mismatch")
    if payload.get("account_generation") != control.account_generation:
        raise ValueError("daily sweep source packet account generation mismatch")
    if payload.get("source_generation") != control.source_generation:
        raise ValueError("daily sweep source packet source generation mismatch")
    if payload.get("sweep_generation") != current_cursor.sweep_generation:
        raise ValueError("daily sweep source packet sweep generation mismatch")
    raw_timezone_name = payload.get("timezone_name")
    if not isinstance(raw_timezone_name, str) or not raw_timezone_name.strip():
        raise ValueError("daily sweep source packet timezone is required")
    if raw_timezone_name != timezone_name:
        raise ValueError("daily sweep source packet timezone mismatch")
    expected_window = window_override or completed_local_day_window(local_date, timezone_name)
    if (
        payload.get("complete") is not True
        or payload.get("window_id") != expected_window.window_id
        or payload.get("window_start_utc") != expected_window.start_utc
        or payload.get("window_end_utc") != expected_window.end_utc
    ):
        raise ValueError("daily sweep source packet is not an exact complete window")

    def parse(
        name: str,
        *,
        source_type: str,
        authority: SweepAuthority,
        trusted_direct: bool = False,
    ) -> Tuple[DailySweepCandidate, ...]:
        raw = payload.get(name, ())
        if not isinstance(raw, (list, tuple)):
            raise ValueError("daily sweep source channel must be a list")
        if len(raw) > MAX_CANDIDATES_PER_DAY:
            raise ValueError("daily sweep source packet exceeds candidate budget")
        return _bounded_candidate_channel(
            raw,
            source_type=source_type,
            authority=authority,
            trusted_direct=trusted_direct,
            max_candidates=MAX_CANDIDATES_PER_DAY,
        )

    trigger_repairs = list(
        parse(
            "existing_trigger_reconciliation",
            source_type="agent_conclusion",
            authority=SweepAuthority.agent_reusable_conclusion,
        )
    )
    # Reconcile only active, already-standing triggers whose strict compiled
    # representation differs from the stored payload. This is repeatable and
    # cannot invent a trigger from passive behavior.
    try:
        for item in _iter_active_standing_triggers(uid, db_client=db_client):
            if (
                item.status != MemoryItemStatus.active
                or item.kind != MemoryKind.trigger
                or item.write_reason != LedgerWriteReason.standing_trigger
                or not item.content
            ):
                continue
            try:
                normalized_condition = compile_trigger_condition(item.trigger_condition).as_condition()
            except Exception:
                continue
            if normalized_condition == item.trigger_condition:
                continue
            trigger_repairs.append(
                DailySweepCandidate(
                    candidate_id=f"trigger-repair-{item.memory_id}",
                    kind="trigger",
                    operation="repair",
                    content=item.content,
                    source_id=f"standing-trigger:{item.memory_id}",
                    source_type="agent_conclusion",
                    source_version="jit-trigger-compile.v1",
                    source_refs=(f"memory:{item.memory_id}",),
                    authority=SweepAuthority.agent_reusable_conclusion,
                    target_memory_id=item.memory_id,
                    slot=item.slot,
                    subject_scope=item.subject_scope,
                    subject_entity_id=item.subject_entity_id,
                    trigger_condition=normalized_condition,
                )
            )
            if len(trigger_repairs) >= MAX_WRITES_PER_DAY:
                break
    except ValueError:
        # Reconciliation is auxiliary, but a truncated authoritative query is
        # not equivalent to an empty set. The source remains unavailable and
        # the scheduler must not advance its cursor.
        raise
    parsed_daily_summary = parse("daily_summary", source_type="daily_summary", authority=SweepAuthority.sweep_inference)
    parsed_onboarding = (
        parse(
            "onboarding_cold_start",
            source_type="onboarding",
            authority=SweepAuthority.direct_user_statement,
            trusted_direct=True,
        )
        if qa_run_id is None
        else ()
    )
    raw_onboarding_source_keys = payload.get("onboarding_source_keys", ()) if qa_run_id is None else ()
    if not isinstance(raw_onboarding_source_keys, (list, tuple)):
        raise ValueError("daily sweep onboarding source keys must be a list")
    onboarding_source_keys = tuple(
        sorted({item.strip() for item in raw_onboarding_source_keys if isinstance(item, str) and item.strip()})
    )
    if len(onboarding_source_keys) > MAX_CANDIDATES_PER_DAY or any(
        not item.startswith("onboarding:") for item in onboarding_source_keys
    ):
        raise ValueError("daily sweep onboarding source keys are invalid")
    raw_onboarding_progress = payload.get("onboarding_source_progress", {}) if qa_run_id is None else {}
    if not isinstance(raw_onboarding_progress, Mapping):
        raise ValueError("daily sweep onboarding source progress is invalid")
    onboarding_source_progress = {
        key.strip(): int(value)
        for key, value in raw_onboarding_progress.items()
        if isinstance(key, str) and key.strip()
    }
    if len(onboarding_source_progress) > MAX_CANDIDATES_PER_DAY or any(
        not key.startswith("onboarding:") or value < 0 for key, value in onboarding_source_progress.items()
    ):
        raise ValueError("daily sweep onboarding source progress is invalid")
    all_candidates = parsed_daily_summary + parsed_onboarding + tuple(trigger_repairs)
    return DailySweepRuntimeSources(
        daily_summary=parsed_daily_summary,
        onboarding_cold_start=parsed_onboarding,
        existing_trigger_reconciliation=tuple(trigger_repairs),
        onboarding_source_keys=onboarding_source_keys,
        onboarding_source_progress=onboarding_source_progress,
        complete=True,
        source_status="complete" if all_candidates else "complete_zero",
    )


def daily_memory_sweep_authority_from_environment() -> SweepAuthorityState:
    """Resolve the backend-only activation seam; both switches default closed."""

    truthy = {"1", "true", "yes", "on"}
    return SweepAuthorityState(
        enabled=os.getenv(DAILY_MEMORY_SWEEP_ENABLED_ENV, "false").casefold() in truthy,
        kill_switch_active=os.getenv(DAILY_MEMORY_SWEEP_KILL_SWITCH_ENV, "false").casefold() in truthy,
    )


@dataclass(frozen=True)
class DailySweepSchedulerSummary:
    """Content-free scheduler receipt for bounded per-user runs."""

    attempted_users: int = 0
    committed_users: int = 0
    blocked_users: int = 0
    committed_candidates: int = 0
    idempotent_candidates: int = 0
    skipped_candidates: int = 0
    errors: Tuple[str, ...] = ()
    # Accounts in this tuple reached a terminal bounded decision for this
    # inventory page. The maintenance adaptor records failures in independent
    # per-UID retry documents before advancing fair source cursors; a failed
    # account therefore stays eligible without imposing head-of-line blocking.
    completed_uids: Tuple[str, ...] = ()
    failed_uids: Tuple[str, ...] = ()
    model_dispatch_evidence: Tuple[Mapping[str, Any], ...] = ()


def _qa_sweep_run_ref(db_client: Any, run_id: str) -> Any:
    return db_client.document(f"{QA_SWEEP_RUN_COLLECTION}/{run_id}")


def _qa_sweep_output_ref(db_client: Any, run_id: str) -> Any:
    return db_client.document(f"{QA_SWEEP_RUN_COLLECTION}/{run_id}/{QA_SWEEP_OUTPUT_SUBCOLLECTION}/{QA_SWEEP_UID}")


def _create_or_verify_qa_sweep_document(db_client: Any, ref: Any, payload: Mapping[str, Any], *, label: str) -> None:
    create = getattr(ref, "create", None)
    if not callable(create):
        raise RuntimeError(f"QA sweep {label} requires create-only Firestore writes")
    try:
        create(dict(payload))
        return
    except Exception as exc:
        snapshot = ref.get()
        existing = snapshot.to_dict() if getattr(snapshot, "exists", False) else None
        if isinstance(existing, Mapping) and dict(existing) == dict(payload):
            return
        raise RuntimeError(f"QA sweep {label} already exists with a different run result") from exc


def write_qa_sweep_run_receipt(
    db_client: Any,
    *,
    run_id: str,
    summary: DailySweepSchedulerSummary,
) -> None:
    """Persist the content-free producer receipt after one QA scheduler run.

    Candidate receipts carry ``qa_run_id`` and remain the durable output rows;
    this run-level document only records bounded counters and the exact
    consumer join path. It is create-only so a retry cannot rewrite a prior
    run's evidence.
    """

    run_id = validate_run_id_for_qa_receipt(run_id)
    status = "failed" if summary.errors else "completed"
    policy = {
        "model_name": QA_SWEEP_MODEL_NAME,
        "max_model_candidates": QA_SWEEP_MAX_MODEL_CANDIDATES,
        "max_model_cost_usd": QA_SWEEP_MAX_MODEL_COST_USD,
        "max_catch_up_days": QA_SWEEP_MAX_CATCH_UP_DAYS,
        "max_summary_conversations": QA_SWEEP_MAX_SUMMARY_CONVERSATIONS,
        "max_summary_input_characters": QA_SWEEP_MAX_SUMMARY_INPUT_CHARACTERS,
        "max_transcript_fetches": QA_SWEEP_MAX_TRANSCRIPT_FETCHES,
        "max_transcript_fetch_characters": QA_SWEEP_MAX_TRANSCRIPT_FETCH_CHARACTERS,
        "max_memory_lookups": QA_SWEEP_MAX_MEMORY_LOOKUPS,
        "sdk_max_retries": QA_SWEEP_MAX_SDK_RETRIES,
        "gateway_max_attempts": QA_SWEEP_MAX_GATEWAY_ATTEMPTS,
        "provider_calls_allowed": QA_SWEEP_MAX_PROVIDER_CALLS,
        "max_input_tokens": QA_SWEEP_MAX_INPUT_TOKENS,
        "max_output_tokens": QA_SWEEP_MAX_OUTPUT_TOKENS,
        "max_spend_micro_usd": QA_SWEEP_MAX_SPEND_MICRO_USD,
        "jit_contract_version": QA_SWEEP_JIT_CONTRACT_VERSION,
    }
    output_path = f"users/{QA_SWEEP_UID}/daily_memory_sweep_receipts"
    output_payload = {
        "schema_version": QA_SWEEP_OUTPUT_SCHEMA_VERSION,
        "run_id": run_id,
        "uid": QA_SWEEP_UID,
        "project": QA_SWEEP_PROJECT,
        "database": QA_SWEEP_DATABASE,
        "status": status,
        "attempted_users": summary.attempted_users,
        "committed_users": summary.committed_users,
        "blocked_users": summary.blocked_users,
        "committed_candidates": summary.committed_candidates,
        "idempotent_candidates": summary.idempotent_candidates,
        "skipped_candidates": summary.skipped_candidates,
        "error_count": len(summary.errors),
        "model_policy": policy,
        "model_dispatch_evidence": [dict(item) for item in summary.model_dispatch_evidence],
        "candidate_receipt_collection": output_path,
        "candidate_receipt_join_field": "qa_run_id",
    }
    _create_or_verify_qa_sweep_document(
        db_client,
        _qa_sweep_output_ref(db_client, run_id),
        output_payload,
        label="output row",
    )
    run_payload = {
        "schema_version": QA_SWEEP_RECEIPT_SCHEMA_VERSION,
        "run_id": run_id,
        "uid": QA_SWEEP_UID,
        "project": QA_SWEEP_PROJECT,
        "database": QA_SWEEP_DATABASE,
        "status": status,
        "output_row_path": f"{QA_SWEEP_RUN_COLLECTION}/{run_id}/{QA_SWEEP_OUTPUT_SUBCOLLECTION}/{QA_SWEEP_UID}",
        "candidate_receipt_collection": output_path,
        "candidate_receipt_join_field": "qa_run_id",
        "model_policy": policy,
        "model_dispatch_evidence": [dict(item) for item in summary.model_dispatch_evidence],
        "error_count": len(summary.errors),
    }
    _create_or_verify_qa_sweep_document(
        db_client, _qa_sweep_run_ref(db_client, run_id), run_payload, label="run receipt"
    )


def validate_run_id_for_qa_receipt(run_id: str) -> str:
    """Keep receipt validation local to this module's public QA seam."""

    return validate_qa_sweep_run_id(run_id)


def _pending_completed_dates(
    cursor: DailySweepCursor,
    *,
    timezone_name: str,
    now: datetime,
    max_days: int = MAX_CATCH_UP_DAYS,
) -> Tuple[date, ...]:
    local_today = now.astimezone(ZoneInfo(timezone_name)).date()
    eligible_through = local_today - timedelta(days=1)
    first_pending = (
        cursor.pending_transition_local_date
        if cursor.pending_transition_local_date is not None
        else (
            cursor.last_completed_local_date + timedelta(days=1)
            if cursor.last_completed_local_date is not None
            else eligible_through
        )
    )
    if first_pending > eligible_through:
        return ()
    return tuple(
        day for day in (first_pending + timedelta(days=index) for index in range(max_days)) if day <= eligible_through
    )


def run_daily_memory_sweep_scheduler(
    *,
    db_client: Any,
    now: datetime,
    uid_inventory: Iterable[str],
    source_provider: Any,
    timezone_resolver: Any,
    authority: Optional[SweepAuthorityState] = None,
    cohort_authority: Optional[DailySweepCohortAuthority] = None,
    cohort_authorizer: Optional[Any] = None,
    timezone_reconciler: Optional[Any] = None,
    max_users: int = 400,
    qa_run_id: Optional[str] = None,
    max_catch_up_days: Optional[int] = None,
) -> DailySweepSchedulerSummary:
    """Runtime producer/scheduler/adaptor behind the closed backend authority.

    The caller supplies a bounded registry page and a server-only
    ``source_provider(uid, completed_local_date, control)``.  The provider is
    where daily-summary extraction, onboarding cold-start, and existing-trigger
    reconciliation are joined; clients and passive observation streams never
    call this function.  No current writer is changed while the environment
    authority remains closed.
    """

    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    if qa_run_id is not None:
        qa_run_id = validate_qa_sweep_run_id(qa_run_id)
    catch_up_days = (
        QA_SWEEP_MAX_CATCH_UP_DAYS
        if qa_run_id is not None
        else (MAX_CATCH_UP_DAYS if max_catch_up_days is None else max_catch_up_days)
    )
    if catch_up_days < 1 or catch_up_days > MAX_CATCH_UP_DAYS:
        raise ValueError("max_catch_up_days must be between 1 and the bounded maximum")
    bounded_uids = tuple(sorted({uid.strip() for uid in uid_inventory if uid.strip()}))[: max(1, min(400, max_users))]

    # Crash-recovery cleanup is a privacy lifecycle operation, not a rollout
    # decision. Run it before authority, kill-switch, and cohort gates so a
    # disabled/skipped account cannot retain transcript-derived pages forever.
    drain_sweep_uids(bounded_uids, lambda uid: (cleanup_expired_daily_memory_sweep_stages(uid, db_client=db_client, now=now), cleanup_expired_memory_deletion_receipts(uid, db_client=db_client, now=now), ProcessOutcome.ack())[-1])  # fmt: skip
    resolved_authority = authority or daily_memory_sweep_authority_from_environment()
    if not resolved_authority.may_write:
        return DailySweepSchedulerSummary()
    resolved_cohort = cohort_authority or daily_memory_sweep_cohort_authority_from_environment()
    # A write-enabled scheduler must always have an explicit backend cohort
    # gate.  A disabled/missing cohort is not an unrestricted all-user mode;
    # it is a closed rollout.  The flag name is deployment-fixed and supplied
    # only by the server-owned authority seam.
    if not resolved_cohort.enabled:
        return DailySweepSchedulerSummary(errors=("cohort_disabled",))
    if not resolved_cohort.cohort_name:
        return DailySweepSchedulerSummary(errors=("cohort_name_missing",))
    attempted = committed_users = blocked_users = 0
    committed = idempotent = skipped = 0
    errors: List[str] = []
    completed_uids: List[str] = []
    failed_uids: List[str] = []
    model_dispatch_evidence: List[Mapping[str, Any]] = []

    def process_one(uid: str) -> ProcessOutcome:
        nonlocal attempted, committed_users, blocked_users, committed, idempotent, skipped
        attempted += 1
        try:
            # This callback is intentionally read-only.  A PostHog client can
            # be supplied by the maintenance deployment, but no
            # identify/flag mutation is performed by this scheduler.
            if not callable(cohort_authorizer):
                blocked_users += 1
                failed_uids.append(uid)
                errors.append(f"uid={uid}:cohort_unavailable")
                return ProcessOutcome.reject("cohort_unavailable", reason="cohort_unavailable")
            try:
                enrolled = cohort_authorizer(uid, resolved_cohort.cohort_name)
            except TypeError:
                enrolled = cohort_authorizer(uid)
            if isinstance(enrolled, DailySweepCohortDecision):
                cohort_decision = enrolled
            elif enrolled is True:
                cohort_decision = DailySweepCohortDecision.enabled
            elif enrolled is False:
                cohort_decision = DailySweepCohortDecision.disabled
            else:
                cohort_decision = DailySweepCohortDecision.unavailable
            if cohort_decision is DailySweepCohortDecision.disabled:
                # A definite false assignment is a successful bounded
                # decision and may advance the fair page cursor.
                blocked_users += 1
                completed_uids.append(uid)
                return ProcessOutcome.ack()
            if cohort_decision is not DailySweepCohortDecision.enabled:
                blocked_users += 1
                failed_uids.append(uid)
                errors.append(f"uid={uid}:cohort_unavailable")
                return ProcessOutcome.reject("cohort_unavailable", reason="cohort_unavailable")
            control = ensure_canonical_apply_control_state(uid, db_client=db_client)
            if control.writer_mode is not WriterMode.ledger:
                # An enrolled account that has not completed ledger cutover
                # cannot commit ordinary ledger writes (require_writer_admitted
                # refuses them in compatibility mode), so claiming its day only
                # burns receipt leases and fails the whole hourly job with
                # WriterAdmissionError. Pre-drain is an expected rollout state:
                # skip quietly and retry after the maintenance drain moves the
                # account to ledger mode. The account's day cursor does not
                # advance, so no day is lost — pending days catch up in
                # bounded windows once the account drains.
                logger.info(
                    "daily-memory-sweep skipping uid=%s: writer_mode=%s awaits ledger cutover",
                    uid,
                    control.writer_mode.value,
                )
                blocked_users += 1
                completed_uids.append(uid)
                return ProcessOutcome.ack()
            if free_tier_memory_suppression_enabled():
                # §1.8: a basic account is not admitted to the sweep at all, so
                # an account that downgrades stops being swept rather than
                # having its already-claimed day fail late. Ack like the
                # disabled-cohort branch above: a definite plan answer is a
                # successful bounded decision and may advance the fair page
                # cursor. Rejecting instead would burn receipt leases and
                # strand the tail. The sweep is a cron with no request, so the
                # funding owner is always the platform.
                verdict = memory_formation_verdict(
                    decision_for=lambda feature: authorize_managed_compute(uid, feature, "omi")
                )
                if verdict.suppressed:
                    logger.info(
                        "daily-memory-sweep skipping uid=%s: plan denies managed formation reason=%s",
                        uid,
                        verdict.reason,
                    )
                    blocked_users += 1
                    completed_uids.append(uid)
                    return ProcessOutcome.ack()
            timezone_name = str(timezone_resolver(uid) or "UTC")
            cursor = _read_cursor(db_client, uid, control)
            if cursor.last_completed_local_date is not None and cursor.timezone_name != timezone_name:
                # Reconciliation is itself a cursor/control write. It must be
                # reached only after the per-UID backend cohort decision above;
                # the old inventory-wide pre-pass wrote disabled and unknown
                # users before this gate. A failed/absent reconciler remains a
                # retryable account failure and cannot advance the page.
                if not callable(timezone_reconciler) or not timezone_reconciler(uid, timezone_name):
                    raise ValueError("timezone_changed_requires_reconciliation")
                cursor = _read_cursor(db_client, uid, control)
            pending_dates = _pending_completed_dates(
                cursor,
                timezone_name=timezone_name,
                now=now,
                max_days=catch_up_days,
            )
            if not pending_dates:
                completed_uids.append(uid)
                return ProcessOutcome.ack()
            packets: Dict[date, DailySweepInput] = {}
            for local_date in pending_dates:
                transition_window = None
                if cursor.pending_transition_local_date == local_date:
                    if cursor.pending_transition_start_utc is None:
                        raise ValueError("timezone transition cursor is incomplete")
                    transition_window = timezone_transition_window(
                        local_date,
                        timezone_name,
                        coverage_start_utc=cursor.pending_transition_start_utc,
                    )
                try:
                    sources = source_provider(
                        uid,
                        local_date,
                        control,
                        timezone_name=timezone_name,
                        window_override=transition_window,
                        qa_run_id=qa_run_id,
                    )
                except TypeError:
                    # Preserve the narrow three-argument provider contract for
                    # existing test/deployment adapters.
                    sources = source_provider(uid, local_date, control)
                if not isinstance(sources, DailySweepRuntimeSources):
                    raise ValueError("daily sweep source provider returned an invalid source bundle")
                if sources.model_dispatch_evidence:
                    model_dispatch_evidence.append(dict(sources.model_dispatch_evidence))
                packets[local_date] = build_daily_sweep_input(
                    uid,
                    local_date,
                    account_generation=control.account_generation,
                    source_generation=control.source_generation,
                    sweep_generation=cursor.sweep_generation,
                    timezone_name=timezone_name,
                    sources=sources,
                    window_override=transition_window,
                )
            output = run_daily_memory_sweep(
                uid,
                timezone_name,
                now,
                packets,
                db_client=db_client,
                authority=resolved_authority,
                claimant=f"scheduler:{uuid4().hex}",
                qa_run_id=qa_run_id,
                max_catch_up_days=catch_up_days,
            )
            committed += output.committed_count
            idempotent += output.idempotent_count
            skipped += output.skipped_count
            if output.status == "committed":
                committed_users += 1
                completed_uids.append(uid)
                return ProcessOutcome.ack()
            blocked_users += 1
            failed_uids.append(uid)
            errors.append(f"uid={uid}:{output.blocked_reason or output.status}")
            return ProcessOutcome.reject(output.blocked_reason or output.status, reason="sweep_blocked")
        except Exception as exc:
            blocked_users += 1
            failed_uids.append(uid)
            errors.append(f"uid={uid}:{type(exc).__name__}")
            return ProcessOutcome.reject(type(exc).__name__, reason="processor_exception")

    drain_sweep_uids(bounded_uids, process_one)
    return DailySweepSchedulerSummary(
        attempted_users=attempted,
        committed_users=committed_users,
        blocked_users=blocked_users,
        committed_candidates=committed,
        idempotent_candidates=idempotent,
        skipped_candidates=skipped,
        errors=tuple(errors[:16]),
        completed_uids=tuple(completed_uids),
        failed_uids=tuple(failed_uids),
        model_dispatch_evidence=tuple(model_dispatch_evidence),
    )


__all__ = [
    "CURSOR_SCHEMA_VERSION",
    "DailySweepCandidate",
    "DailySweepInput",
    "DailySweepOutput",
    "DailySweepPlan",
    "DailySweepRuntimeSources",
    "DailySweepSchedulerSummary",
    "DailySweepCohortDecision",
    "CompletedLocalDayWindow",
    "DailySweepSkip",
    "MAX_CANDIDATES_PER_DAY",
    "MAX_CATCH_UP_DAYS",
    "MAX_WRITES_PER_DAY",
    "MAX_COMPLETED_DAY_CONVERSATIONS",
    "MAX_COMPLETED_DAY_INPUT_CHARACTERS",
    "MAX_COMPLETED_DAY_SUMMARY_CONVERSATIONS",
    "MAX_COMPLETED_DAY_SUMMARY_INPUT_CHARACTERS",
    "MAX_DAILY_TRANSCRIPT_FETCHES",
    "MAX_DAILY_TRANSCRIPT_FETCH_CHARACTERS",
    "CompletedDayConversationSource",
    "MAX_ONBOARDING_CONVERSATIONS",
    "MAX_ONBOARDING_RECEIPT_KEYS",
    "MAX_ONBOARDING_SOURCE_KEYS_PER_PACKET",
    "MAX_LEGACY_COMPAT_OCCUPANTS",
    "ONBOARDING_SOURCE_RECEIPT_PATH",
    "DAILY_MEMORY_SWEEP_ENABLED_ENV",
    "DAILY_MEMORY_SWEEP_KILL_SWITCH_ENV",
    "DAILY_MEMORY_SWEEP_MODEL_ENABLED_ENV",
    "DAILY_MEMORY_SWEEP_MODEL_NAME_ENV",
    "DAILY_MEMORY_SWEEP_MAX_MODEL_CANDIDATES_ENV",
    "DAILY_MEMORY_SWEEP_MAX_MODEL_COST_USD_ENV",
    "DAILY_MEMORY_SWEEP_COHORT_ENABLED_ENV",
    "DAILY_MEMORY_SWEEP_COHORT_NAME_ENV",
    "DAILY_MEMORY_SWEEP_COHORT_FLAG_ENV",
    "DAILY_MEMORY_SWEEP_TIMEZONE_RECONCILIATION_ENV",
    "QA_SWEEP_RUN_ID_ENV",
    "QA_SWEEP_ADMISSION_ENV",
    "QA_SWEEP_PROJECT",
    "QA_SWEEP_DATABASE",
    "QA_SWEEP_UID",
    "QA_SWEEP_COHORT",
    "QA_SWEEP_MODEL_NAME",
    "QA_SWEEP_MAX_MODEL_CANDIDATES",
    "QA_SWEEP_MAX_MODEL_COST_USD",
    "QA_SWEEP_MAX_CATCH_UP_DAYS",
    "QA_SWEEP_MAX_SUMMARY_CONVERSATIONS",
    "QA_SWEEP_MAX_SUMMARY_INPUT_CHARACTERS",
    "QA_SWEEP_MAX_TRANSCRIPT_FETCHES",
    "QA_SWEEP_MAX_TRANSCRIPT_FETCH_CHARACTERS",
    "QA_SWEEP_MAX_MEMORY_LOOKUPS",
    "QA_SWEEP_MAX_SDK_RETRIES",
    "QA_SWEEP_MAX_GATEWAY_ATTEMPTS",
    "QA_SWEEP_MAX_PROVIDER_CALLS",
    "QA_SWEEP_MAX_INPUT_TOKENS",
    "QA_SWEEP_MAX_OUTPUT_TOKENS",
    "QA_SWEEP_MAX_SPEND_MICRO_USD",
    "QA_SWEEP_JIT_CONTRACT_VERSION",
    "QA_SWEEP_RECEIPT_SCHEMA_VERSION",
    "QA_SWEEP_OUTPUT_SCHEMA_VERSION",
    "QA_SWEEP_RUN_COLLECTION",
    "QA_SWEEP_OUTPUT_SUBCOLLECTION",
    "SCHEMA_VERSION",
    "SweepAuthority",
    "SweepAuthorityState",
    "DailySweepModelAuthority",
    "DailySweepCohortAuthority",
    "daily_memory_sweep_model_authority_from_environment",
    "validate_qa_sweep_run_id",
    "qa_sweep_run_id_from_environment",
    "validate_qa_sweep_environment",
    "qa_sweep_cohort_authorizer",
    "write_qa_sweep_run_receipt",
    "daily_memory_sweep_cohort_authority_from_environment",
    "read_daily_memory_sweep_cohort_assignment",
    "close_daily_memory_sweep_cohort_clients",
    "plan_daily_memory_sweep",
    "build_daily_sweep_input",
    "produce_completed_day_daily_summary_sources",
    "produce_onboarding_seed_sources",
    "completed_local_day_window",
    "timezone_transition_window",
    "reconcile_daily_memory_sweep_timezone",
    "reconcile_daily_memory_sweep_timezones_for_maintenance",
    "daily_memory_sweep_authority_from_environment",
    "firestore_daily_sweep_source_provider",
    "run_daily_memory_sweep_scheduler",
    "run_daily_memory_sweep",
]
