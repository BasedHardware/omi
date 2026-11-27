"""The prod-parity profile: a local stack that runs production's application logic.

"Prod-parity" is the usual name for this (dev/prod parity, The Twelve-Factor App,
factor X). It is still a local stack: every process runs on this machine against
emulators and local stand-ins, with no production credentials or connections.
What it takes from production is behaviour, by reading production's settings.

The default harness gives each service a short hand-written environment. Every
setting production declares and the harness does not falls back to its code
default, and most rollout switches default to the path production has already
left. A harness stack therefore runs different application logic from
production: live speech-to-text where production records for the batch
pipeline, inline uploads where production queues them, no safety sweeps.

With ``OMI_HARNESS_PROFILE=prod-parity`` the harness stops choosing logic. Each
production service runs as its own local process (``dev_harness.parity_stack``),
and its environment is composed from a production snapshot when one is
configured (``dev_harness.prod_snapshot``), else from the files production
deploys from:

* ``backend/deploy/runtime_env.yaml`` (composed Cloud Run and GKE settings),
* ``backend/deploy/ops/prod.yaml`` (ops-owned live values),
* the listen and pusher chart values, and
* the repo's staging composition, which already resolves deploy-time inputs and
  live-only values for "production logic on other infrastructure".

Only *infrastructure* settings may differ from production: where a service
lives, which project, database, bucket, queue, account or secret it uses, and
where telemetry goes. ``INFRASTRUCTURE`` names them; every other setting takes
production's declared value, and ``logic_differences`` reports any that does
not (the harness test fails on one).
"""

from __future__ import annotations

import fnmatch
import importlib.util
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

from . import prod_snapshot

PROFILE_ENV = "OMI_HARNESS_PROFILE"
PROD_PARITY = "prod-parity"
# Credentials production's serving chain cannot run without: the LLM gateway's
# provider, and the two speech vendors (listen and pusher refuse to start when the
# chain lists Soniox without a key; Modulate serves pre-recorded audio).
REQUIRED_CREDENTIALS = ("OPENAI_API_KEY", "MODULATE_API_KEY", "SONIOX_API_KEY")

CLOUD_RUN_SERVICES = ("backend", "backend-sync", "backend-sync-backfill", "backend-integration")
GKE_SERVICES = ("backend-listen", "pusher")
SERVICES = (*CLOUD_RUN_SERVICES, *GKE_SERVICES)
CHART_VALUES = {
    "backend-listen": "backend/charts/backend-listen/prod_omi_backend_listen_values.yaml",
    "pusher": "backend/charts/pusher/prod_omi_pusher_values.yaml",
}

# Settings that say where something lives or who it is, not how the application
# behaves. Modelled on STAGING_DIFF_ALLOWLIST (backend/scripts/cross_service_checks/
# staging.py), minus its staging-only rollout exceptions.
INFRASTRUCTURE: tuple[str, ...] = (
    # identity and projects
    "*_PROJECT",
    "*_PROJECT_ID",
    "GOOGLE_CLOUD_PROJECT",
    "GCP_LOCATION",
    "*_TASKS_LOCATION",
    "OMI_DEPLOYMENT",
    "*_SERVICE_ACCOUNT",
    "*_INVOKER_SA",
    "FIREBASE_*",
    "GOOGLE_CLIENT_ID",
    "MCP_OAUTH_*",
    # addresses
    "*_URL",
    "*_URI",
    "*_URIS",
    "*_AUDIENCE",
    "*_POOL_HOST",
    # data plane
    "FIRESTORE_DATABASE_ID",
    "OMI_FLAGS_FIRESTORE_*",
    "REDIS_DB_*",
    "PROACTIVITY_REDIS_*",
    "TYPESENSE_*",
    "PINECONE_*",
    "BUCKET_*",
    "*_KMS_KEY",
    "*_QUEUE",
    "JOBSTORE_*",
    # where telemetry goes
    "DD_*",
    "LANGCHAIN_*",
    "LANGSMITH_*",
    "POSTHOG_*",
    "*_POSTHOG_*",
    "PROMETHEUS_*",
    "SYNC_PHASE_METRICS_*",
    "FIRESTORE_READ_LEDGER*",
    # outward channels and vendor accounts that only production owns
    "OMI_TELEGRAM_ENABLED",
    "OMI_IMESSAGE_ENABLED",
    "OMI_WHATSAPP_ENABLED",
    "*_EMAIL_FROM_ADDRESS",
    "*_PRICE_ID",
    "*_CEILING_USD",
    "*_DAILY_USD",
    # which LLM transport serves a call (the harness gateway, not Vertex)
    "USE_VERTEX_AI",
)

# Production values that are set on the live services outside the composed file.
# The staging overlay records them as "prod live-service residue"; they are
# logic, so the local stack takes them.
LIVE_RESIDUE = ("SUBSCRIPTION_LAUNCH_DATE", "SYNC_DISPATCH_MODE", "ACCOUNT_DELETION_DISPATCH_MODE")
# Operated on the live services and declared in no tracked file. Production's
# value is inferred, and each inference is stated here.
OPERATED_OUTSIDE_GIT = {
    # Code default is closed, which defers every recording's batch admission. Production
    # transcribes phone recordings through batch, so it runs open. The repo's own
    # batch-path stack makes the same assumption (testing/listen_pusher_stack/recording_batch_path.py).
    "BATCH_PIPELINE_RECORD_PROTOCOL_READY": "true",
}

BLACKHOLE = "http://127.0.0.1:9"
# Hosted GPU and model services with no local counterpart. Staging points the
# same names at a closed port so the callers take their production fallback.
HOSTED_WITHOUT_LOCAL_COUNTERPART = (
    "HOSTED_PARAKEET_API_URL",
    "HOSTED_DIARIZATION_API_URL",
    "HOSTED_SPEAKER_EMBEDDING_API_URL",
    "HOSTED_LID_API_URL",
    "HOSTED_VAD_API_URL",
)
_STAGING_QUEUE_PREFIX = "staging-"


def enabled(env: Mapping[str, str] | None = None) -> bool:
    import os

    source = os.environ if env is None else env
    return source.get(PROFILE_ENV, "").strip().lower() == PROD_PARITY


def is_infrastructure(name: str) -> bool:
    return any(fnmatch.fnmatchcase(name, pattern) for pattern in INFRASTRUCTURE)


@dataclass(frozen=True)
class Topology:
    """Where each production service listens on this machine."""

    project_id: str
    database_id: str
    ports: Mapping[str, int]  # service name -> loopback port
    llm_gateway_url: str
    redis_host: str
    redis_port: int

    def url(self, service: str) -> str:
        # Cloud Run services are HTTPS-only and the code checks it for several
        # of their addresses; the GKE services are plain HTTP inside the cluster.
        scheme = "https" if service in CLOUD_RUN_SERVICES else "http"
        return f"{scheme}://127.0.0.1:{self.ports[service]}"


@dataclass
class Declared:
    """What production's deploy files say about one service."""

    values: dict[str, str] = field(default_factory=dict)  # literal settings
    bound: set[str] = field(default_factory=set)  # secrets, config maps and deploy-time inputs


def _load_yaml(path: Path) -> Any:
    import yaml

    return yaml.safe_load(path.read_text())


def _load_composer(repo_root: Path) -> Any:
    path = repo_root / "backend" / "deploy" / "compose_runtime_env.py"
    spec = importlib.util.spec_from_file_location("omi_compose_runtime_env", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def declared_production(repo_root: Path) -> dict[str, Declared]:
    """Production's settings per service.

    With a production snapshot these are the running services' own settings.
    Without one they come from the deploy files of ``repo_root``, which describe
    that checkout and can be days behind what runs.
    """
    snapshot = prod_snapshot.load_active()
    if snapshot is not None:
        missing = [service for service in SERVICES if service not in snapshot.services]
        if missing:
            raise RuntimeError(f"the production snapshot lacks {', '.join(missing)}")
        return {
            service: Declared(
                values=dict(snapshot.services[service].values), bound=set(snapshot.services[service].bound)
            )
            for service in SERVICES
        }
    composed = _load_yaml(repo_root / "backend" / "deploy" / "runtime_env.yaml")["environments"]["prod"]
    ops = _load_yaml(repo_root / "backend" / "deploy" / "ops" / "prod.yaml").get("cloud_run", {})
    out: dict[str, Declared] = {}

    def take(target: Declared, entries: Mapping[str, Any]) -> None:
        for name, entry in entries.items():
            if isinstance(entry, Mapping):
                if "value" in entry:
                    target.values[name] = str(entry["value"])
                else:
                    target.bound.add(name)
            else:
                target.values[name] = str(entry)

    for service in CLOUD_RUN_SERVICES:
        declared = Declared()
        config = composed["cloud_run"]["services"][service]
        take(declared, config.get("env") or {})
        declared.bound.update((config.get("secrets") or {}).keys())
        # ops-owned values are applied to the serving revision after the image deploy.
        take(declared, (ops.get(service) or {}).get("env") or {})
        out[service] = declared
    for service in GKE_SERVICES:
        declared = Declared()
        take(declared, composed["gke"][service].get("env") or {})
        for entry in _load_yaml(repo_root / CHART_VALUES[service]).get("env") or []:
            name = entry["name"]
            if "value" in entry:
                # The chart is what the pod receives; it wins over the composed copy.
                declared.values[name] = str(entry["value"])
                declared.bound.discard(name)
            elif name not in declared.values:
                declared.bound.add(name)
        out[service] = declared
    return out


def _staging_resolved(repo_root: Path) -> dict[str, dict[str, str]]:
    """Cloud Run settings with deploy-time inputs and live residue resolved (the staging composition)."""
    composer = _load_composer(repo_root)
    composed = composer.compose_staging(inputs={"STAGING_REDIS_HOST": "127.0.0.1"})
    return {
        service: {name: str(entry["value"]) for name, entry in config["env"].items() if "value" in entry}
        for service, config in composed["cloud_run"]["services"].items()
    }


_SERVICE_HOSTS = (
    # longest names first: "backend-sync-backfill" also starts with "backend-sync" and "backend"
    ("backend-sync-backfill", "backend-sync-backfill"),
    ("backend-integration", "backend-integration"),
    ("backend-sync", "backend-sync"),
    ("backend-listen", "backend-listen"),
    ("prod-omi-backend-listen", "backend-listen"),
    ("prod-omi-pusher", "pusher"),
    ("backend", "backend"),
)


def local_address(value: str, topology: Topology) -> str | None:
    """A production or staging service address rewritten to this machine, else None."""
    parsed = urlparse(value)
    host = parsed.hostname or ""
    if parsed.scheme not in ("http", "https", "ws", "wss") or not host:
        return None
    label = host.split(".", 1)[0]
    if "llm-gateway" in label:
        return topology.llm_gateway_url.rstrip("/") + parsed.path
    is_run_service = host.endswith(".run.app")
    is_cluster_service = host.endswith(".svc.cluster.local")
    if not (is_run_service or is_cluster_service):
        return None
    for prefix, service in _SERVICE_HOSTS:
        if label == prefix or label.startswith(prefix + "-"):
            if service not in topology.ports:
                return None
            base = topology.url(service)
            if parsed.scheme in ("ws", "wss"):
                base = ("wss" if base.startswith("https") else "ws") + base[base.index("://") :]
            return base + parsed.path
    return None


def _is_remote(value: str) -> bool:
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https", "ws", "wss"):
        return False
    host = parsed.hostname or ""
    return host not in ("127.0.0.1", "localhost", "::1")


# Addresses the application embeds in user-facing links or compares as an
# identifier. Nothing connects to them from a harness stack.
_NEVER_DIALLED = (
    "REFERRAL_PUBLIC_BASE_URL",
    "PUBLIC_SHARED_CONVERSATION_CHAT_FRONTEND_AUDIENCE",
    "POSTHOG_HOST",
    "PROACTIVITY_V2_POSTHOG_HOST",
    "LANGCHAIN_ENDPOINT",
)


def _localize(name: str, value: str, topology: Topology) -> str | None:
    """The local value of one infrastructure setting; None drops it."""
    if fnmatch.fnmatchcase(name, "DD_*") or fnmatch.fnmatchcase(name, "PINECONE_*"):
        return None
    if fnmatch.fnmatchcase(name, "JOBSTORE_*") or name in ("OMI_DEPLOYMENT", "PROMETHEUS_SIDECAR_PORT"):
        return None
    if name in ("LANGCHAIN_TRACING_V2", "LANGSMITH_TRACING", "SYNC_PHASE_METRICS_EXPORT_ENABLED", "USE_VERTEX_AI"):
        return "false"
    if name in ("OMI_TELEGRAM_ENABLED", "OMI_IMESSAGE_ENABLED", "OMI_WHATSAPP_ENABLED"):
        return "off"
    if name.endswith("_TOKEN") or name.endswith("_API_KEY"):
        return ""  # telemetry write keys: a harness stack reports nowhere
    if name in HOSTED_WITHOUT_LOCAL_COUNTERPART:
        return BLACKHOLE if value else ""
    if name == "OMI_LLM_GATEWAY_URL":
        return topology.llm_gateway_url
    if name == "FIRESTORE_DATABASE_ID":
        return topology.database_id
    if name == "REDIS_DB_HOST":
        return topology.redis_host
    if name == "REDIS_DB_PORT":
        return str(topology.redis_port)
    if fnmatch.fnmatchcase(name, "PROACTIVITY_REDIS_*"):
        return {"HOST": topology.redis_host, "PORT": str(topology.redis_port)}.get(name.rsplit("_", 1)[-1])
    if name == "FIRESTORE_READ_LEDGER":
        return None
    if name == "FIRESTORE_READ_LEDGER_SERVICE":
        return value
    if name.endswith("_PROJECT") or name.endswith("_PROJECT_ID") or name == "OMI_FLAGS_FIRESTORE_PROJECT":
        return topology.project_id
    if name in ("GOOGLE_CLOUD_PROJECT", "PARAKEET_BATCH_PRESSURE_POOL_HOST"):
        return None  # the harness strips cloud project defaults; the GPU pool does not exist here
    if name.endswith("_INVOKER_SA") and value and "FRONTEND" not in name:
        # One local identity: production gives the enqueuer and the verifying
        # service the same account, and so must this stack.
        return f"local-tasks-invoker@{topology.project_id}.iam.gserviceaccount.com"
    if name == "BATCH_PIPELINE_WORKER_SERVICE_ACCOUNT" and value:
        return f"local-batch-worker@{topology.project_id}.iam.gserviceaccount.com"
    if name == "FIREBASE_SIGNER_SERVICE_ACCOUNT" and value:
        return f"local-runtime@{topology.project_id}.iam.gserviceaccount.com"
    if name.endswith("_QUEUE") and value.startswith(_STAGING_QUEUE_PREFIX):
        return value[len(_STAGING_QUEUE_PREFIX) :]  # production's queue name
    local = local_address(value, topology)
    if local is not None:
        return local
    if name == "EDGE_SHADOW_URL":
        return ""
    if _is_remote(value) and name not in _NEVER_DIALLED:
        # An address this stack has no stand-in for. Fail closed instead of
        # letting a local process dial a production or staging host.
        return BLACKHOLE
    return value


def compose(repo_root: Path, topology: Topology) -> dict[str, dict[str, str]]:
    """Each production service's local environment: production logic, local infrastructure.

    Secrets, emulator endpoints, storage roots and ports are not in here; the
    harness adds those bindings, all of which are infrastructure by name.
    """
    declared = declared_production(repo_root)
    staging = _staging_resolved(repo_root)
    live = prod_snapshot.active_directory() is not None
    # Services share buckets (pusher archives what the batch workers read), so a
    # bucket keeps production's name on every service that uses it. Staging's
    # renamed buckets would split them, because listen and pusher are not part
    # of the staging composition.
    buckets: dict[str, str] = {}
    for service in SERVICES:
        for name, value in declared[service].values.items():
            if name.startswith("BUCKET_") and value:
                buckets.setdefault(name, value)
    out: dict[str, dict[str, str]] = {}
    for service in SERVICES:
        prod = declared[service]
        # 1. What production declares, logic and infrastructure alike.
        env: dict[str, str] = dict(prod.values)
        # 2. What production binds at deploy time or operates on the live service:
        #    the staging composition's resolution of the same name.
        for name, value in staging.get(service, {}).items():
            if name in env:
                continue
            # A live snapshot already holds every literal setting, so the staging
            # resolution only fills what production binds from a secret.
            if name in prod.bound or (not live and (is_infrastructure(name) or name in LIVE_RESIDUE)):
                env[name] = buckets.get(name, value) if name.startswith("BUCKET_") and value else value
        if not live:
            for name, value in OPERATED_OUTSIDE_GIT.items():
                env.setdefault(name, value)
        out[service] = localized(env, topology)
    # 3. Infrastructure a service binds from a config map or secret that the tracked
    #    files do not resolve for it (listen and pusher are outside the staging
    #    composition): the same name means the same address on every service.
    donors = ("backend-sync", "backend", "backend-integration", "backend-sync-backfill")
    for service in SERVICES:
        for name in declared[service].bound:
            if name in out[service] or not is_infrastructure(name):
                continue
            for donor in donors:
                if donor != service and name in out[donor]:
                    out[service][name] = out[donor][name]
                    break
    return out


BATCH_WORKER_CHART = "backend/charts/batch-pipeline-worker"
_CHART_ENV = re.compile(r"- \{name: ([A-Z0-9_]+), value: (.+)\}\s*$")
_CHART_VALUE = re.compile(r"\{\{ \.Values\.([A-Za-z0-9_.]+)(?: \| default (\"[^\"]*\"|[A-Za-z0-9]+))? \| quote \}\}")
# Template expressions that are not a plain ``.Values`` lookup, resolved by hand
# from the same values file.
_CHART_SPECIAL = {
    "BATCH_PIPELINE_WORKER_PIPELINE_DEPTH": "worker.pipelineDepth",
    "BATCH_PIPELINE_WORKER_PROCESSES": "worker.processes",
    "OMI_FIRESTORE_DATA_PLANE_PROJECT": "dataPlaneProject",
    "BUCKET_BATCH_PIPELINE": "bucket",
    "RECORD_SEAL_REPAIR_FRESH_ENABLED": "recordSealRepair.freshEnabled",
}


def _deep_merge(base: Any, overlay: Any) -> Any:
    if isinstance(base, Mapping) and isinstance(overlay, Mapping):
        merged = dict(base)
        for key, value in overlay.items():
            merged[key] = _deep_merge(base.get(key), value) if key in base else value
        return merged
    return overlay


def declared_batch_worker(repo_root: Path) -> dict[str, str]:
    """The production batch worker's settings: the running pod's, else the chart resolved with production's values."""
    snapshot = prod_snapshot.load_active()
    if snapshot is not None and "batch-worker" in snapshot.services:
        return dict(snapshot.services["batch-worker"].values)
    chart = repo_root / BATCH_WORKER_CHART
    values = _deep_merge(
        _load_yaml(chart / "values.yaml") or {}, _load_yaml(chart / "prod_omi_batch-pipeline-worker_values.yaml")
    )
    template = (chart / "templates" / "deployment.yaml").read_text()
    start = template.index("command: [python, -m, diarizer.batch_pipeline_runtime]")
    section = template[start : template.index("ENCRYPTION_SECRET", start)]

    def lookup(path: str) -> Any:
        current: Any = values
        for part in path.split("."):
            if not isinstance(current, Mapping) or part not in current:
                return None
            current = current[part]
        return current

    def text(value: Any) -> str:
        return str(value).lower() if isinstance(value, bool) else str(value)

    declared: dict[str, str] = {}
    for line in section.splitlines():
        match = _CHART_ENV.search(line.strip())
        if not match:
            continue
        name, expression = match.group(1), match.group(2).strip()
        if name in _CHART_SPECIAL:
            value = lookup(_CHART_SPECIAL[name])
            if value is not None:
                declared[name] = text(value)
            continue
        plain = _CHART_VALUE.fullmatch(expression)
        if plain:
            value = lookup(plain.group(1))
            if value is None and plain.group(2) is not None:
                value = plain.group(2).strip('"')
            if value is not None:
                declared[name] = text(value)
        elif not expression.startswith("{{"):
            declared[name] = expression.strip('"')
    return declared


def localized(values: Mapping[str, str], topology: Topology) -> dict[str, str]:
    """Production settings with every infrastructure setting replaced by its local value or dropped."""
    env: dict[str, str] = {}
    for name, value in values.items():
        if not is_infrastructure(name):
            env[name] = value
            continue
        local = _localize(name, value, topology)
        if local is not None:
            env[name] = local
    return env


def compose_batch_worker(repo_root: Path, topology: Topology) -> dict[str, str]:
    """The batch worker's local environment: production's worker settings, local addresses."""
    return localized(declared_batch_worker(repo_root), topology)


def logic_differences(repo_root: Path, composed: Mapping[str, Mapping[str, str]]) -> list[tuple[str, str, str]]:
    """(service, setting, problem) for every non-infrastructure setting that is not production's."""
    declared = declared_production(repo_root)
    problems: list[tuple[str, str, str]] = []
    for service, env in composed.items():
        prod = declared[service].values
        for name, value in prod.items():
            if is_infrastructure(name):
                continue
            if name not in env:
                problems.append((service, name, "missing"))
            elif env[name] != value:
                problems.append((service, name, "differs from production"))
        for name in env:
            if is_infrastructure(name) or name in prod or name in LIVE_RESIDUE or name in declared[service].bound:
                continue
            if name in OPERATED_OUTSIDE_GIT and prod_snapshot.active_directory() is None:
                continue
            problems.append((service, name, "not declared by production"))
    return problems


def remote_addresses(composed: Mapping[str, Mapping[str, str]]) -> list[tuple[str, str]]:
    """(service, setting) whose value still names a host off this machine and could be dialled."""
    found: list[tuple[str, str]] = []
    for service, env in composed.items():
        for name, value in env.items():
            if name in _NEVER_DIALLED:
                continue
            for part in re.split(r"[,\s]+", value):
                if _is_remote(part) and urlparse(part).port != 9:
                    found.append((service, name))
                    break
    return found
