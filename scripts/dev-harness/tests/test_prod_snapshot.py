"""The production snapshot and the load balancer's routing."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dev_harness import edge_router, local_scheduler, local_task_queue, prod_parity, prod_snapshot  # noqa: E402

PRODUCTION_ROUTES = [
    ("/v1/users/migration/batch-requests", "backend-sync"),
    ("/v1/sync-local-files", "backend-sync"),
    ("/v2/sync-local-files", "backend-sync"),
    ("/v2/integrations/*", "backend-integration"),
    ("/v1/sync/audio/*", "backend-sync"),
    ("/v4/web/listen", "backend-listen"),
    ("/v3/listen", "backend-listen"),
    ("/v4/listen", "backend-listen"),
    ("/v1/mcp/*", "backend-integration"),
    ("/v1/mcp", "backend-integration"),
]


@pytest.mark.parametrize(
    "path,service",
    [
        ("/v2/sync-local-files", "backend-sync"),  # the upload itself
        ("/v2/sync-local-files/bp_123", "backend"),  # the status poll for that upload
        ("/v2/sync-local-files/receipts/wait", "backend"),
        ("/v2/sync-capture-manifest", "backend"),
        ("/v1/sync/audio/merge", "backend-sync"),
        ("/v1/sync/audio", "backend"),  # a /* rule matches below the prefix only
        ("/v4/listen", "backend-listen"),
        ("/v4/listen/extra", "backend"),
        ("/v2/integrations/x/y", "backend-integration"),
        ("/v1/mcp", "backend-integration"),
        ("/v1/conversations", "backend"),
    ],
)
def test_router_follows_the_load_balancers_path_rules(path, service):
    assert edge_router.upstream_for_routes(PRODUCTION_ROUTES, "backend", path) == service


def test_container_env_separates_settings_from_secrets():
    container = {
        "envFrom": [{"configMapRef": {"name": "shared"}}],
        "env": [
            {"name": "LITERAL", "value": "1"},
            {"name": "OVERRIDDEN", "value": "explicit"},
            {"name": "FROM_KEY", "valueFrom": {"configMapKeyRef": {"name": "shared", "key": "KEYED"}}},
            {"name": "SECRET", "valueFrom": {"secretKeyRef": {"name": "s", "key": "k"}}},
            {"name": "POD_NAME", "valueFrom": {"fieldRef": {"fieldPath": "metadata.name"}}},
        ],
    }
    values, bound = prod_snapshot._container_env(
        container, {"shared": {"BULK": "b", "OVERRIDDEN": "bulk", "KEYED": "k"}}
    )
    assert values == {"BULK": "b", "OVERRIDDEN": "explicit", "KEYED": "k", "LITERAL": "1", "FROM_KEY": "k"}
    assert bound == ["SECRET"]  # a secret is a name only; pod metadata is not a setting


def test_routes_come_from_the_api_host_matcher_most_specific_first():
    backend = "https://compute/backendServices/custom-domains-api-omi-me-backend-49a4-be"
    url_map = {
        "hostRules": [{"hosts": ["web.omi.me"], "pathMatcher": "web"}, {"hosts": ["api.omi.me"], "pathMatcher": "api"}],
        "pathMatchers": [
            {"name": "web", "defaultService": backend, "pathRules": []},
            {
                "name": "api",
                "defaultService": backend,
                "pathRules": [
                    {"paths": ["/*"], "service": backend},
                    {
                        "paths": ["/v2/sync-local-files", "/v1/sync/audio/*"],
                        "service": "https://compute/backendServices/custom-domains-api-omi-me-backend-sync-49a4-be",
                    },
                    {
                        "paths": ["/v4/listen"],
                        "service": "https://compute/backendServices/custom-domains-api-omi-me-backend-listen-49a4-be",
                    },
                    {"paths": ["/v1/mcp"], "service": "https://compute/backendServices/prod-omi-backend-integration"},
                ],
            },
        ],
    }
    routes, default = prod_snapshot._routes(url_map)
    assert default == "backend"
    assert routes == [
        ("/v2/sync-local-files", "backend-sync"),
        ("/v1/sync/audio/*", "backend-sync"),
        ("/v4/listen", "backend-listen"),
        ("/v1/mcp", "backend-integration"),
    ]


def test_live_queue_settings_keep_productions_retry_contract_and_cap_concurrency():
    live = {
        "batch-quarantine-recovery": {
            "rate_limits": {"maxConcurrentDispatches": 16, "maxDispatchesPerSecond": 8.0},
            "retry_config": {"maxAttempts": 5, "minBackoff": "0.100s", "maxBackoff": "60s"},
        }
    }
    queues = local_task_queue.production_queue_settings(Path("/nonexistent"), 4, live=live)
    settings = queues["batch-quarantine-recovery"]
    assert (settings.max_attempts, settings.min_backoff, settings.max_backoff) == (5, 0.1, 60.0)
    assert (settings.max_concurrent, settings.max_per_second) == (4, 8.0)


def test_scheduler_plan_uses_only_enabled_live_jobs_it_can_reach():
    live = [
        {"name": "cap-hold-durable-redrive", "schedule": "*/2 * * * *", "state": "ENABLED"}
        | {"uri": "https://backend-sync-x.a.run.app/v2/cap", "audience": "https://backend-sync-x.a.run.app"},
        {"name": "enrichment-maintenance", "schedule": "*/2 * * * *", "state": "PAUSED"}
        | {
            "uri": "https://backend-integration-x.a.run.app/v2/e",
            "audience": "https://backend-integration-x.a.run.app",
        },
        {"name": "sync-backfill-uid-sequencer", "schedule": "*/2 * * * *", "state": "ENABLED"}
        | {"uri": "https://admin.omi.me/x", "audience": "https://admin.omi.me"},
        {"name": "dream-agent-sweep-hourly", "schedule": "0 * * * *", "state": "ENABLED"}
        | {"uri": "https://backend-sync-x.a.run.app/v2/dream", "audience": "https://backend-sync-x.a.run.app"},
    ]

    def localize(value: str) -> str | None:
        return (
            value.replace("https://backend-sync-x.a.run.app", "https://127.0.0.1:8012") if "run.app" in value else None
        )

    jobs = local_scheduler.plan_live(live, localize=localize, identity_for=lambda url: "invoker")
    assert [(job.name, job.url) for job in jobs] == [("cap-hold-durable-redrive", "https://127.0.0.1:8012/v2/cap")]


def _snapshot(tmp_path: Path) -> Path:
    def service(name: str, platform: str, extra: dict[str, str]) -> dict:
        values = {"OMI_ENV_STAGE": "prod", "BATCH_PIPELINE_ENABLED": "true", "GOOGLE_CLOUD_PROJECT": "based-hardware"}
        values.update(extra)
        return {
            "name": name,
            "platform": platform,
            "image": f"gcr.io/x/{name}:abc1234",
            "commit": "abc1234",
            "command": [],
            "args": [],
            "values": values,
            "bound": ["OPENAI_API_KEY"],
            "replicas": None,
            "concurrency": None,
            "timeout_seconds": None,
        }

    services = {
        name: service(
            name, "cloud_run", {"HOSTED_PUSHER_API_URL": "http://prod-omi-pusher.prod.svc.cluster.local:8080"}
        )
        for name in prod_parity.CLOUD_RUN_SERVICES
    }
    services["backend-sync"]["values"]["BATCH_PIPELINE_API_URL"] = "https://backend-sync-x.a.run.app"
    services["backend"]["values"]["ONLY_ON_BACKEND"] = "live-value"
    for name in prod_parity.GKE_SERVICES:
        services[name] = service(name, "gke", {"STT_SERVICE_MODELS": "soniox"})
    services["batch-worker"] = service("batch-worker", "gke", {"BATCH_PIPELINE_WORKER_PROCESSES": "2"})
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "snapshot.json").write_text(
        json.dumps(
            {
                "captured_at": "2026-11-21T06:00:00Z",
                "services": services,
                "routes": PRODUCTION_ROUTES,
                "default_route": "backend",
                "queues": {},
                "scheduler_jobs": [],
                "unreadable": [],
                "rollout_ramp": {"envs": {"prod": {"percents": {"batch-pipeline": 100}, "legacy_sync": "dark"}}},
            }
        )
    )
    return tmp_path


def test_profile_composes_from_the_snapshot_without_logic_differences(tmp_path, monkeypatch):
    monkeypatch.setenv(prod_snapshot.SNAPSHOT_ENV, str(_snapshot(tmp_path)))
    monkeypatch.setattr(prod_parity, "_staging_resolved", lambda _root: {})
    topology = prod_parity.Topology(
        project_id="demo-omi-local",
        database_id="(default)",
        ports={**{name: 8010 + index for index, name in enumerate(prod_parity.CLOUD_RUN_SERVICES)}}
        | {"backend-listen": 8020, "pusher": 8090},
        llm_gateway_url="http://127.0.0.1:9080",
        redis_host="127.0.0.1",
        redis_port=6380,
    )
    composed = prod_parity.compose(Path("/nonexistent"), topology)
    # Behaviour settings are the running service's own, per service.
    assert composed["backend"]["ONLY_ON_BACKEND"] == "live-value"
    assert "ONLY_ON_BACKEND" not in composed["backend-sync"]
    assert composed["backend-listen"]["STT_SERVICE_MODELS"] == "soniox"
    # Addresses point at this machine; nothing names a production host.
    assert composed["backend-sync"]["BATCH_PIPELINE_API_URL"].startswith("https://127.0.0.1:")
    assert composed["backend"]["HOSTED_PUSHER_API_URL"] == "http://127.0.0.1:8090"
    assert prod_parity.remote_addresses(composed) == []
    assert prod_parity.logic_differences(Path("/nonexistent"), composed) == []
    assert prod_parity.declared_batch_worker(Path("/nonexistent"))["BATCH_PIPELINE_WORKER_PROCESSES"] == "2"


def test_user_id_lists_never_reach_the_snapshot():
    container = {
        "env": [
            {"name": "SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST", "value": "uidA,uidB"},
            {"name": "FAIR_USE_EXEMPT_UIDS", "value": "uidC"},
            {"name": "EMPTY_UID_ALLOWLIST", "value": ""},
            {"name": "BATCH_PIPELINE_SERVE_UID_SHA256S", "value": "0a1b"},
            {"name": "BATCH_PIPELINE_SERVE_PERCENT", "value": "100"},
        ]
    }
    values, _bound = prod_snapshot._container_env(container, {})
    # A non-empty list keeps its meaning (some accounts, not this stack's) without its members.
    assert values["SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST"] == prod_snapshot.REDACTED_UID
    assert values["FAIR_USE_EXEMPT_UIDS"] == prod_snapshot.REDACTED_UID
    assert values["EMPTY_UID_ALLOWLIST"] == ""
    # Cohort settings are hashes and percentages, and they decide behaviour.
    assert values["BATCH_PIPELINE_SERVE_UID_SHA256S"] == "0a1b"
    assert values["BATCH_PIPELINE_SERVE_PERCENT"] == "100"


def test_a_snapshot_is_never_written_inside_a_checkout(tmp_path, capsys):
    (tmp_path / ".git").mkdir()
    assert prod_snapshot.capture_command(tmp_path / "snapshots" / "now", None) == 2
    assert "outside the repository" in capsys.readouterr().out
    assert not (tmp_path / "snapshots").exists()


def test_drift_names_what_changed_without_values(tmp_path, capsys):
    old = _snapshot(tmp_path / "old")
    new = _snapshot(tmp_path / "new")
    document = json.loads((new / "snapshot.json").read_text())
    document["services"]["backend"]["values"]["ONLY_ON_BACKEND"] = "another-live-value"
    (new / "snapshot.json").write_text(json.dumps(document))
    assert prod_snapshot.drift_command(old, old) == 0
    assert prod_snapshot.drift_command(old, new) == 1
    out = capsys.readouterr().out
    assert "backend: 1 setting(s) changed: ONLY_ON_BACKEND" in out
    assert "live-value" not in out
