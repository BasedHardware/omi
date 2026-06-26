import importlib.util
import json
import subprocess
import sys
from pathlib import Path


class FakeSnapshot:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data

    def to_dict(self):
        return dict(self._data)


class FakeDocRef:
    def __init__(self, doc_id, store, writes):
        self.id = doc_id
        self._store = store
        self._writes = writes

    def update(self, patch):
        self._writes.append((self.id, dict(patch)))
        self._store[self.id].update(patch)


class FakeCollection:
    def __init__(self, store, writes):
        self._store = store
        self._writes = writes

    def stream(self):
        return [FakeSnapshot(doc_id, data) for doc_id, data in self._store.items()]

    def document(self, doc_id):
        return FakeDocRef(doc_id, self._store, self._writes)


class FakeDb:
    def __init__(self, store):
        self.store = store
        self.writes = []

    def collection(self, name):
        assert name == "mcp_api_keys"
        return FakeCollection(self.store, self.writes)


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
    db = FakeDb(
        {
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
    )

    result = module.run_readiness_inventory(db_client=db, execute=True, allow_write=False, assignments={})

    assert result["status"] == "DRY_RUN"
    assert result["read_only"] is True
    assert result["summary"]["total_keys"] == 4
    assert result["summary"]["missing_app_id"] == 1
    assert result["summary"]["missing_scopes"] == 1
    assert result["summary"]["verified_memories_read"] == 1
    assert result["summary"]["unknown_scopes"] == 1
    assert db.writes == []


def test_write_plan_requires_execute_and_allow_write_and_rejects_unknown_scopes():
    module = load_module()
    db = FakeDb({"legacy-key": {"id": "legacy-key", "user_id": "u1", "name": "legacy"}})
    assignments = {"legacy-key": {"app_id": "mcp-api", "scopes": ["memories.read"]}}

    not_executed = module.run_readiness_inventory(
        db_client=db, execute=False, allow_write=True, assignments=assignments
    )
    assert not_executed["status"] == "NOT_RUN"
    assert db.writes == []

    no_write_flag = module.run_readiness_inventory(
        db_client=db, execute=True, allow_write=False, assignments=assignments
    )
    assert no_write_flag["status"] == "DRY_RUN"
    assert no_write_flag["mutation_allowed"] is False
    assert db.writes == []

    bad_scope = module.run_readiness_inventory(
        db_client=db,
        execute=True,
        allow_write=True,
        assignments={"legacy-key": {"app_id": "mcp-api", "scopes": ["tool.search_memories"]}},
    )
    assert bad_scope["status"] == "DENIED"
    assert "unknown_scope" in bad_scope["errors"][0]
    assert db.writes == []

    applied = module.run_readiness_inventory(db_client=db, execute=True, allow_write=True, assignments=assignments)
    assert applied["status"] == "APPLIED"
    assert db.writes == [("legacy-key", {"app_id": "mcp-api", "scopes": ["memories.read"]})]
    assert db.store["legacy-key"]["user_id"] == "u1"
    assert db.store["legacy-key"]["id"] == "legacy-key"


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
