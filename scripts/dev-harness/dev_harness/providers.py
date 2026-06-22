"""Provider broker/governor guardrails for the local dev harness.

This module is intentionally small and fail-closed. It does not execute real
provider calls; it is the local-harness policy layer used by dev-check,
dev-status, and future provider call sites before anything can leave the
machine.
"""

from __future__ import annotations

import hashlib
import importlib.util
import os
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Mapping
from urllib.parse import urlparse

from . import safety

PROVIDER_MODES = {"real", "offline"}
SECRET_REDACTION = "<redacted>"
DEFAULT_SESSION_BUDGET_USD = 2.00
DEFAULT_DAILY_BUDGET_USD = 10.00
DEFAULT_MAX_CONCURRENCY = 2
DEFAULT_IDEMPOTENT_RETRIES = 1
DEFAULT_NON_IDEMPOTENT_RETRIES = 0

_STATEFUL_CAPABILITY_MARKERS = ("vector", "index", "webhook", "callback", "queue")
_PROVIDER_SECRET_NAMES = (
    "OPENAI_API_KEY",
    "DEEPGRAM_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENROUTER_API_KEY",
    "GROQ_API_KEY",
    "ELEVENLABS_API_KEY",
    "PINECONE_API_KEY",
    "TYPESENSE_API_KEY",
)


class ProviderPolicyError(safety.SafetyError):
    """Raised when provider mode or provider request policy fails closed."""


@dataclass(frozen=True)
class ProviderBudget:
    max_requests_per_session: int
    max_requests_per_day: int
    max_cost_per_session_usd: float = DEFAULT_SESSION_BUDGET_USD
    max_cost_per_day_usd: float = DEFAULT_DAILY_BUDGET_USD
    max_concurrency: int = DEFAULT_MAX_CONCURRENCY
    idempotent_retries: int = DEFAULT_IDEMPOTENT_RETRIES
    non_idempotent_retries: int = DEFAULT_NON_IDEMPOTENT_RETRIES
    timeout_seconds: float = 30.0
    max_tokens: int | None = None
    max_upload_bytes: int | None = None
    max_audio_seconds: int | None = None

    def validate_bounded(self) -> None:
        for name in (
            "max_requests_per_session",
            "max_requests_per_day",
            "max_cost_per_session_usd",
            "max_cost_per_day_usd",
            "max_concurrency",
            "timeout_seconds",
        ):
            value = getattr(self, name)
            if value is None or value <= 0:
                raise ProviderPolicyError(f"Provider budget {name} must be explicitly bounded")
        if self.idempotent_retries > DEFAULT_IDEMPOTENT_RETRIES:
            raise ProviderPolicyError("Idempotent provider retries may not exceed one in the local harness")
        if self.non_idempotent_retries != DEFAULT_NON_IDEMPOTENT_RETRIES:
            raise ProviderPolicyError("Non-idempotent provider retries are disabled in the local harness")


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    credential_env: str | None
    billing_owner: str
    quota: str
    data_use: str
    retention: str
    region: str
    allowed_endpoints: tuple[str, ...]
    allowed_capabilities: tuple[str, ...]
    budget: ProviderBudget
    pricing_bounded: bool = True
    permits_stateful_resources: bool = False
    permits_async_jobs: bool = False
    permits_external_files: bool = False
    fake_module: str | None = None
    fake_source_path: str | None = None


@dataclass(frozen=True)
class ProviderPreflight:
    mode: str
    enabled_external_providers: tuple[str, ...]
    missing: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    fingerprints: Mapping[str, str] = field(default_factory=dict)
    offline_fake_sources: Mapping[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.missing


@dataclass(frozen=True)
class ProviderRequest:
    provider: str
    capability: str
    endpoint: str
    method: str = "POST"
    estimated_cost_usd: float | None = None
    request_count: int = 1
    idempotent: bool = True
    synthetic_or_local_qa_data: bool = True
    writes_external_state: bool = False
    uses_callback: bool = False
    uses_webhook: bool = False
    uses_queue: bool = False
    uses_vector_or_index_write: bool = False
    durable_external_side_effect: bool = False
    replay_after_restart: bool = False


def default_provider_specs(repo_root: Path) -> tuple[ProviderSpec, ...]:
    fake_root = Path(repo_root) / "backend" / "testing" / "e2e" / "fakes"
    return (
        ProviderSpec(
            name="openai",
            credential_env="OPENAI_API_KEY",
            billing_owner="developer-local-qa",
            quota="local-harness $10/day developer budget",
            data_use="training disabled / synthetic-or-local-QA inputs only",
            retention="provider policy; not harness-authoritative state",
            region="provider default",
            allowed_endpoints=("https://api.openai.com/v1/chat/completions", "https://api.openai.com/v1/embeddings"),
            allowed_capabilities=("llm.chat", "embedding.read"),
            budget=ProviderBudget(max_requests_per_session=60, max_requests_per_day=300, max_tokens=200_000),
            fake_module="llm",
            fake_source_path=str(fake_root / "llm.py"),
        ),
        ProviderSpec(
            name="deepgram",
            credential_env="DEEPGRAM_API_KEY",
            billing_owner="developer-local-qa",
            quota="local-harness $10/day developer budget",
            data_use="synthetic-or-local-QA audio only",
            retention="provider policy; not harness-authoritative state",
            region="provider default",
            allowed_endpoints=("https://api.deepgram.com/v1/listen", "wss://api.deepgram.com/v1/listen"),
            allowed_capabilities=("stt.prerecorded", "stt.streaming"),
            budget=ProviderBudget(
                max_requests_per_session=120,
                max_requests_per_day=600,
                timeout_seconds=120.0,
                max_upload_bytes=50_000_000,
                max_audio_seconds=3_600,
            ),
            fake_module="stt",
            fake_source_path=str(fake_root / "stt.py"),
        ),
        ProviderSpec(
            name="gemini",
            credential_env="GEMINI_API_KEY",
            billing_owner="developer-local-qa",
            quota="local-harness $10/day developer budget",
            data_use="training disabled / synthetic-or-local-QA inputs only",
            retention="provider policy; not harness-authoritative state",
            region="provider default",
            allowed_endpoints=(
                "https://generativelanguage.googleapis.com/v1beta/models",
                "https://generativelanguage.googleapis.com/v1/models",
            ),
            allowed_capabilities=("llm.chat", "embedding.read"),
            budget=ProviderBudget(max_requests_per_session=60, max_requests_per_day=300, max_tokens=200_000),
        ),
        ProviderSpec(
            name="anthropic",
            credential_env="ANTHROPIC_API_KEY",
            billing_owner="developer-local-qa",
            quota="local-harness $10/day developer budget",
            data_use="training disabled / synthetic-or-local-QA inputs only",
            retention="provider policy; not harness-authoritative state",
            region="provider default",
            allowed_endpoints=("https://api.anthropic.com/v1/messages",),
            allowed_capabilities=("llm.chat",),
            budget=ProviderBudget(max_requests_per_session=60, max_requests_per_day=300, max_tokens=200_000),
        ),
        ProviderSpec(
            name="hosted-ml-local-http",
            credential_env=None,
            billing_owner="developer-local-qa",
            quota="local loopback-only hosted ML budget",
            data_use="synthetic-or-local-QA audio only",
            retention="none; local/loopback fake in offline mode",
            region="local",
            allowed_endpoints=(
                "http://127.0.0.1:8001/v2/embedding",
                "http://127.0.0.1:8001/v1/vad",
                "http://127.0.0.1:8001/v1/speaker-identification",
            ),
            allowed_capabilities=("speaker.embedding", "vad.read", "speaker.identification"),
            budget=ProviderBudget(max_requests_per_session=120, max_requests_per_day=600, timeout_seconds=30.0),
            fake_module="embeddings",
            fake_source_path=str(fake_root / "embeddings.py"),
        ),
    )


def provider_mode_from_env(env: Mapping[str, str] | None = None) -> str:
    source = os.environ if env is None else env
    mode = source.get("PROVIDER_MODE", "real").strip().lower()
    if mode not in PROVIDER_MODES:
        raise ProviderPolicyError(f"PROVIDER_MODE must be one of {sorted(PROVIDER_MODES)}, got {mode!r}")
    return mode


def secret_fingerprint(secret: str) -> str:
    if not secret:
        raise ProviderPolicyError("Cannot fingerprint an empty provider credential")
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()[:12]


_PLACEHOLDER_SECRET_VALUES = frozenset(
    {
        "changeme",
        "change-me",
        "your-key-here",
        "your_api_key",
        "replace-me",
        "todo",
        "xxx",
        "placeholder",
    }
)


def is_placeholder_secret(value: str) -> bool:
    normalized = value.strip().lower()
    if not normalized:
        return True
    if normalized in _PLACEHOLDER_SECRET_VALUES:
        return True
    if "your-key" in normalized or "changeme" in normalized:
        return True
    return False


def redact_secret(value: str | None) -> str:
    if value is None or value == "":
        return "<unset>"
    return SECRET_REDACTION


def redacted_provider_env(env: Mapping[str, str]) -> dict[str, str]:
    redacted: dict[str, str] = {}
    for key, value in env.items():
        if key in _PROVIDER_SECRET_NAMES or safety._PROVIDER_SECRET_RE.search(key):  # guarded local harness helper
            redacted[key] = redact_secret(value)
        else:
            redacted[key] = value
    return redacted


def _normalize_endpoint(endpoint: str) -> str:
    parsed = urlparse(endpoint)
    if parsed.scheme not in {"https", "wss", "http"} or not parsed.netloc:
        raise ProviderPolicyError(f"Invalid provider endpoint {endpoint!r}")
    if parsed.scheme == "http" and not safety.is_loopback_host(parsed.netloc):
        raise ProviderPolicyError(f"Plain HTTP provider endpoint must be loopback, got {endpoint!r}")
    return endpoint.rstrip("/")


def _endpoint_allowed(endpoint: str, allowed_endpoints: tuple[str, ...]) -> bool:
    candidate = _normalize_endpoint(endpoint)
    for allowed in allowed_endpoints:
        normalized = _normalize_endpoint(allowed)
        if candidate == normalized or candidate.startswith(f"{normalized}/"):
            return True
    return False


def _is_stateful_capability(capability: str) -> bool:
    lowered = capability.lower()
    return any(marker in lowered for marker in _STATEFUL_CAPABILITY_MARKERS) or lowered.endswith(".write")


def _load_module_from_path(name: str, path: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"omi_harness_fake_{name}", path)
    if spec is None or spec.loader is None:
        raise ProviderPolicyError(f"Cannot load hermetic fake provider module {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OfflineProviderRegistry:
    """Thin wrapper around backend/testing/e2e/fakes provider modules."""

    def __init__(self, repo_root: Path):
        self.repo_root = Path(repo_root)
        self._specs = {spec.name: spec for spec in default_provider_specs(self.repo_root) if spec.fake_source_path}

    def fake_source_paths(self) -> dict[str, str]:
        return {name: str(Path(spec.fake_source_path or "")) for name, spec in self._specs.items()}

    def load_fake(self, provider: str) -> ModuleType:
        spec = self._specs.get(provider)
        if spec is None or not spec.fake_source_path:
            raise ProviderPolicyError(f"No hermetic fake provider configured for {provider!r}")
        path = Path(spec.fake_source_path)
        expected_root = self.repo_root / "backend" / "testing" / "e2e" / "fakes"
        if expected_root.resolve(strict=False) not in path.resolve(strict=False).parents:
            raise ProviderPolicyError(f"Offline fake provider {path} is not shared with backend/testing/e2e/fakes")
        if not path.is_file():
            raise ProviderPolicyError(f"Missing hermetic fake provider module {path}")
        return _load_module_from_path(provider, str(path))


def provider_preflight(
    repo_root: Path,
    *,
    env: Mapping[str, str] | None = None,
    specs: tuple[ProviderSpec, ...] | None = None,
) -> ProviderPreflight:
    source = os.environ if env is None else env
    mode = provider_mode_from_env(source)
    provider_specs = specs or default_provider_specs(repo_root)
    missing: list[str] = []
    warnings: list[str] = []
    fingerprints: dict[str, str] = {}

    if mode == "offline":
        registry = OfflineProviderRegistry(repo_root)
        fake_sources = registry.fake_source_paths()
        for provider, path in fake_sources.items():
            registry.load_fake(provider)
        if any(key in source for key in _PROVIDER_SECRET_NAMES):
            warnings.append("PROVIDER_MODE=offline: provider credentials are ignored and stripped from child processes")
        return ProviderPreflight(
            mode=mode,
            enabled_external_providers=(),
            warnings=tuple(warnings),
            offline_fake_sources=fake_sources,
        )

    enabled: list[str] = []
    for spec in provider_specs:
        spec.budget.validate_bounded()
        if not spec.pricing_bounded:
            missing.append(f"{spec.name}: pricing/usage is not bounded; local harness fails closed")
            continue
        if spec.permits_stateful_resources or spec.permits_async_jobs or spec.permits_external_files:
            missing.append(f"{spec.name}: matrix permits durable external side effects; local harness requires false")
        if spec.credential_env:
            secret = source.get(spec.credential_env, "").strip()
            if not secret:
                missing.append(
                    f"{spec.credential_env} ({spec.name}; set in backend/.env.local-dev or use PROVIDER_MODE=offline)"
                )
            elif is_placeholder_secret(secret):
                missing.append(
                    f"{spec.credential_env} ({spec.name}; placeholder value rejected — set a real key in backend/.env.local-dev)"
                )
            else:
                # Non-secret fingerprint for dev-status / config digest only (never required in .env).
                fingerprints[spec.name] = secret_fingerprint(secret)
        enabled.append(spec.name)

    return ProviderPreflight(
        mode=mode,
        enabled_external_providers=tuple(enabled),
        missing=tuple(missing),
        warnings=tuple(warnings),
        fingerprints=fingerprints,
    )


class ProviderBroker:
    """Fail-closed request policy checker for future local provider call sites."""

    def __init__(
        self, repo_root: Path, *, env: Mapping[str, str] | None = None, specs: tuple[ProviderSpec, ...] | None = None
    ):
        self.repo_root = Path(repo_root)
        self.env = os.environ if env is None else env
        self.mode = provider_mode_from_env(self.env)
        self.specs = {spec.name: spec for spec in (specs or default_provider_specs(self.repo_root))}
        self.offline_registry = OfflineProviderRegistry(self.repo_root) if self.mode == "offline" else None

    def check_request(self, request: ProviderRequest) -> None:
        spec = self.specs.get(request.provider)
        if spec is None:
            raise ProviderPolicyError(
                f"Unknown provider {request.provider!r}; provider matrix is explicit and fail-closed"
            )
        if request.replay_after_restart:
            raise ProviderPolicyError("Automatic provider replay after restart is prohibited")
        if not request.synthetic_or_local_qa_data:
            raise ProviderPolicyError("Real provider inputs must be synthetic or developer-created local QA data")
        if request.capability not in spec.allowed_capabilities:
            raise ProviderPolicyError(f"Capability {request.capability!r} is not allowlisted for {request.provider}")
        if not _endpoint_allowed(request.endpoint, spec.allowed_endpoints):
            raise ProviderPolicyError(f"Endpoint {request.endpoint!r} is not allowlisted for {request.provider}")
        if request.uses_callback or request.uses_webhook or request.uses_queue or request.durable_external_side_effect:
            raise ProviderPolicyError("Callbacks, webhooks, queues, and durable external side effects are prohibited")
        if request.uses_vector_or_index_write or _is_stateful_capability(request.capability):
            raise ProviderPolicyError("Hosted vector/index writes are stateful and disallowed for the local harness")
        if request.writes_external_state:
            raise ProviderPolicyError("External providers may not hold harness-authoritative mutable state")
        spec.budget.validate_bounded()
        if request.estimated_cost_usd is None:
            raise ProviderPolicyError("Provider request must include a bounded estimated cost")
        if request.estimated_cost_usd > spec.budget.max_cost_per_session_usd:
            raise ProviderPolicyError("Provider request exceeds per-session cost budget")
        if request.request_count > spec.budget.max_requests_per_session:
            raise ProviderPolicyError("Provider request exceeds per-session request-count budget")
        retry_limit = spec.budget.idempotent_retries if request.idempotent else spec.budget.non_idempotent_retries
        if retry_limit < 0:
            raise ProviderPolicyError("Retry budget must be explicit")
        if self.mode == "offline":
            if not self.offline_registry:
                raise ProviderPolicyError("Offline provider registry is unavailable")
            self.offline_registry.load_fake(request.provider)


def status_lines(preflight: ProviderPreflight) -> list[str]:
    lines = [f"provider_mode: {preflight.mode}"]
    if preflight.enabled_external_providers:
        lines.append("enabled_external_providers: " + ", ".join(preflight.enabled_external_providers))
    else:
        lines.append("enabled_external_providers: none")
    if preflight.fingerprints:
        rendered = ", ".join(f"{name}=sha256:{fp}" for name, fp in sorted(preflight.fingerprints.items()))
        lines.append(f"credential_fingerprints: {rendered}")
    if preflight.offline_fake_sources:
        rendered = ", ".join(f"{name}={path}" for name, path in sorted(preflight.offline_fake_sources.items()))
        lines.append(f"offline_fake_sources: {rendered}")
    lines.append(
        "provider_budgets: session=$2.00 day=$10.00 concurrency=2 retries=idempotent:1/non-idempotent:0 replay_after_restart=disabled"
    )
    lines.append("provider_side_effects: callbacks/webhooks/queues/vector-or-index-writes=disallowed")
    return lines
