import importlib.util
import json
import subprocess
import sys
from pathlib import Path

from tests.store_fakes import FakeDocumentStore

MCP_API_KEY_COLLECTION = "mcp_api_keys"


def seed_store(docs):
    """Seed a FakeDocumentStore with mcp_api_keys documents keyed by key id."""
    fake = FakeDocumentStore()
    for key_id, data in docs.items():
        fake.set(f"{MCP_API_KEY_COLLECTION}/{key_id}", data)
    return fake


def store_snapshot(fake, key_ids):
    """Current stored body for each key id (None when absent) — used to assert no writes."""
    return {key_id: fake.get(f"{MCP_API_KEY_COLLECTION}/{key_id}").to_dict() for key_id in key_ids}


def load_module():
    root = Path(__file__).resolve().parents[2]
    script_path = root / "scripts" / "mcp_api_key_scope_readiness.py"
    spec = importlib.util.spec_from_file_location("mcp_api_key_scope_readiness", script_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_default_cli_is_not_run_and_does_not_import_firestore_or_write():
    root = Path(__file__).resolve().parents[2]
    script_path = root / "scripts" / "mcp_api_key_scope_readiness.py"
    assert script_path.exists(), "missing MCP API-key scope readiness runner"
    script = script_path.read_text()
    assert "NOT_RUN" in script
    assert "--execute" in script
    assert "--allow-write" in script
    assert "never infer" in script
    assert "mcp_api_keys" in script

    completed = subprocess.run([sys.executable, str(script_path)], text=True, capture_output=True, check=False)

    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["status"] == "NOT_RUN"
    assert payload["read_only"] is True
    assert payload["mutation_allowed"] is False
    assert "no Firestore reads or writes were executed" in payload["non_claims"]


def test_inventory_distinguishes_missing_app_scopes_and_verified_memories_read_without_writes():
    module = load_module()
    seed = {
        "legacy-key": {"id": "legacy-key", "user_id": "u1", "name": "legacy"},
        "no-read-key": {"id": "no-read-key", "user_id": "u1", "app_id": "mcp-api", "scopes": []},
        "read-key": {"id": "read-key", "user_id": "u2", "app_id": "mcp-api", "scopes": ["memories.read"]},
        "bad-scope-key": {
            "id": "bad-scope-key",
            "user_id": "u3",
            "app_id": "mcp-api",
            "scopes": ["tool.search_memories"],
        },
    }
    fake = seed_store(seed)
    before = store_snapshot(fake, seed)

    result = module.run_readiness_inventory(fake, execute=True, allow_write=False, assignments={})

    assert result["status"] == "DRY_RUN"
    assert result["read_only"] is True
    assert result["summary"]["total_keys"] == 4
    assert result["summary"]["missing_app_id"] == 1
    assert result["summary"]["missing_scopes"] == 1
    assert result["summary"]["verified_memories_read"] == 1
    assert result["summary"]["unknown_scopes"] == 1
    assert store_snapshot(fake, seed) == before


def test_write_plan_requires_execute_and_allow_write_and_rejects_unknown_scopes():
    module = load_module()
    seed = {"legacy-key": {"id": "legacy-key", "user_id": "u1", "name": "legacy"}}
    fake = seed_store(seed)
    unwritten = store_snapshot(fake, seed)
    assignments = {"legacy-key": {"app_id": "mcp-api", "scopes": ["memories.read"]}}

    not_executed = module.run_readiness_inventory(fake, execute=False, allow_write=True, assignments=assignments)
    assert not_executed["status"] == "NOT_RUN"
    assert store_snapshot(fake, seed) == unwritten

    no_write_flag = module.run_readiness_inventory(fake, execute=True, allow_write=False, assignments=assignments)
    assert no_write_flag["status"] == "DRY_RUN"
    assert no_write_flag["mutation_allowed"] is False
    assert store_snapshot(fake, seed) == unwritten

    bad_scope = module.run_readiness_inventory(
        fake,
        execute=True,
        allow_write=True,
        assignments={"legacy-key": {"app_id": "mcp-api", "scopes": ["tool.search_memories"]}},
    )
    assert bad_scope["status"] == "DENIED"
    assert "unknown_scope" in bad_scope["errors"][0]
    assert store_snapshot(fake, seed) == unwritten

    applied = module.run_readiness_inventory(fake, execute=True, allow_write=True, assignments=assignments)
    assert applied["status"] == "APPLIED"
    assert applied["applied_assignments"] == [
        {"key_id": "legacy-key", "patch": {"app_id": "mcp-api", "scopes": ["memories.read"]}}
    ]
    stored = fake.get(f"{MCP_API_KEY_COLLECTION}/legacy-key").to_dict()
    assert stored["app_id"] == "mcp-api"
    assert stored["scopes"] == ["memories.read"]
    assert stored["user_id"] == "u1"
    assert stored["id"] == "legacy-key"


def test_docs_reference_non_claims_and_server_owned_scope_assignment():
    root = Path(__file__).resolve().parents[2].parent
    readiness_doc = root / "docs" / "epics" / "memory_mcp_app_key_scope_readiness.md"
    evidence_markers_doc = root / "docs" / "operational" / "memory_readiness_evidence_markers.md"
    readiness = readiness_doc.read_text()
    evidence_markers = evidence_markers_doc.read_text()

    assert "python3 backend/scripts/mcp_api_key_scope_readiness.py" in readiness
    assert "--execute --allow-write" in readiness
    assert "server-owned" in readiness
    assert "do not infer scopes from advertised MCP tool metadata" in readiness
    assert "not executed against production" in readiness
    assert "no OAuth introspection" in readiness
    assert "mcp_api_key_scope_readiness.py" in evidence_markers
