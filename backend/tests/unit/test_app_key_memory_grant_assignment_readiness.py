import importlib.util
import json
import subprocess
import sys
from pathlib import Path


class FakeDocRef:
    def __init__(self, path, store, writes):
        self.path = path
        self._store = store
        self._writes = writes

    def set(self, payload, merge=False):
        self._writes.append((self.path, dict(payload), merge))
        if merge and self.path in self._store:
            self._store[self.path].update(payload)
        else:
            self._store[self.path] = dict(payload)


class FakeDb:
    def __init__(self):
        self.store = {}
        self.writes = []

    def document(self, path):
        return FakeDocRef(path, self.store, self.writes)


def load_module():
    root = Path(__file__).resolve().parents[2]
    script_path = root / "scripts" / "app_key_memory_grant_assignment_readiness.py"
    spec = importlib.util.spec_from_file_location("app_key_memory_grant_assignment_readiness", script_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_default_cli_is_not_run_and_performs_no_firestore_read_or_write():
    root = Path(__file__).resolve().parents[2]
    script_path = root / "scripts" / "app_key_memory_grant_assignment_readiness.py"
    assert script_path.exists(), "missing memory app/key memory grant assignment readiness runner"

    completed = subprocess.run([sys.executable, str(script_path)], text=True, capture_output=True, check=False)

    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["status"] == "NOT_RUN"
    assert payload["read_only"] is True
    assert payload["mutation_allowed"] is False
    assert "no Firestore reads or writes were executed" in payload["non_claims"]


def test_writes_unreachable_without_execute_allow_write_and_assignment_file():
    module = load_module()
    db = FakeDb()
    assignment = {
        "uid": "u1",
        "consumer": "mcp",
        "app_id": "mcp-api",
        "key_id": "key-1",
        "scopes": ["memories.read"],
        "default_read": True,
        "archive_read": False,
        "write": False,
        "archive_default_visible": False,
    }

    not_executed = module.run_assignment_readiness(
        db_client=db, execute=False, allow_write=True, assignments=[assignment]
    )
    assert not_executed["status"] == "NOT_RUN"
    assert db.writes == []

    dry_run = module.run_assignment_readiness(db_client=db, execute=True, allow_write=False, assignments=[assignment])
    assert dry_run["status"] == "DRY_RUN"
    assert dry_run["read_only"] is True
    assert dry_run["mutation_allowed"] is False
    assert dry_run["planned_writes"][0]["document_path"] == "users/u1/memory_control/app_key_memory_grants"
    assert dry_run["planned_writes"][0]["grant_path"] == "grants.mcp.apps.mcp-api.keys.key-1"
    assert db.writes == []

    missing_assignment_file_gate = module.main(["--execute", "--allow-write"], db_client=db)
    assert missing_assignment_file_gate == 2
    assert db.writes == []


def test_invalid_consumer_unknown_scope_and_archive_default_exposure_are_denied_before_writes():
    module = load_module()
    db = FakeDb()

    bad = module.run_assignment_readiness(
        db_client=db,
        execute=True,
        allow_write=True,
        assignments=[
            {
                "uid": "u1",
                "consumer": "client_supplied_consumer",
                "app_id": "app",
                "key_id": "key",
                "scopes": ["tool.search_memories"],
                "default_read": True,
                "archive_read": True,
                "write": False,
                "archive_default_visible": True,
            }
        ],
    )

    assert bad["status"] == "DENIED"
    assert any("unknown_consumer" in error for error in bad["errors"])
    assert any("unknown_scope" in error for error in bad["errors"])
    assert any("archive_default_visible_not_allowed" in error for error in bad["errors"])
    assert db.writes == []


def test_valid_write_targets_only_server_owned_grant_path_and_keeps_archive_not_default_visible():
    module = load_module()
    db = FakeDb()
    assignment = {
        "uid": "u1",
        "consumer": "developer_api",
        "app_id": "developer-api",
        "key_id": "dev-key-1",
        "scopes": ["memories.read", "memories.archive.read"],
        "default_read": True,
        "archive_read": True,
        "write": False,
        "archive_default_visible": False,
    }

    applied = module.run_assignment_readiness(db_client=db, execute=True, allow_write=True, assignments=[assignment])

    assert applied["status"] == "APPLIED"
    assert applied["read_only"] is False
    assert db.writes == [
        (
            "users/u1/memory_control/app_key_memory_grants",
            {
                "grants": {
                    "developer_api": {
                        "apps": {
                            "developer-api": {
                                "keys": {
                                    "dev-key-1": {
                                        "enabled": True,
                                        "scopes": ["memories.read", "memories.archive.read"],
                                        "default_read": True,
                                        "archive_read": True,
                                        "write": False,
                                        "archive_default_visible": False,
                                    }
                                }
                            }
                        }
                    }
                }
            },
            True,
        )
    ]
    assert "mcp_api_keys" not in db.writes[0][0]


def test_docs_reference_runner_non_claims_and_no_archive_default():
    root = Path(__file__).resolve().parents[2].parent
    readiness = (root / "docs" / "epics" / "memory_app_key_memory_grants_readiness.md").read_text()
    evidence_markers = (root / "docs" / "operational" / "memory_readiness_evidence_markers.md").read_text()

    assert "app_key_memory_grant_assignment_readiness.py" in readiness
    assert "--execute --allow-write" in readiness
    assert "archive_default_visible" in readiness
    assert "not executed against production" in readiness
    assert "no app/key grants assigned" in readiness
    assert "app_key_memory_grant_assignment_readiness.py" in evidence_markers
