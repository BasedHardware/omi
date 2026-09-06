from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "jit_qa_typesense_projection.py"

for key, value in {
    "ENCRYPTION_SECRET": "12345678901234567890123456789012",
    "TYPESENSE_HOST": "typesense-jit-qa-example.run.app",
    "TYPESENSE_HOST_PORT": "443",
    "TYPESENSE_PROTOCOL": "https",
    "TYPESENSE_API_KEY": "qa-typesense-test-key",
    "MEMORY_TYPESENSE_COLLECTION": "jit_qa_canonical_memory_atoms",
    "GOOGLE_CLOUD_PROJECT": "based-hardware-dev",
    "OMI_FIRESTORE_DATA_PLANE_PROJECT": "based-hardware-dev",
    "FIRESTORE_DATABASE_ID": "jit-qa",
    "OMI_ENV_STAGE": "dev",
    "OMI_JIT_QA_AUTH_ONLY": "true",
    "OMI_JIT_QA_UID_ALLOWLIST": "vi7SA9ckQCe4ccobWNxlbdcNdC23",
}.items():
    os.environ.setdefault(key, value)

spec = importlib.util.spec_from_file_location("jit_qa_typesense_projection_for_test", SCRIPT)
assert spec is not None and spec.loader is not None
PROJECTION = importlib.util.module_from_spec(spec)
spec.loader.exec_module(PROJECTION)


def _environment() -> dict[str, str]:
    return {
        "GOOGLE_CLOUD_PROJECT": PROJECTION.PROJECT_ID,
        "OMI_FIRESTORE_DATA_PLANE_PROJECT": PROJECTION.PROJECT_ID,
        "FIRESTORE_DATABASE_ID": PROJECTION.DATABASE_ID,
        "OMI_ENV_STAGE": "dev",
        "OMI_JIT_QA_AUTH_ONLY": "true",
        "OMI_JIT_QA_UID_ALLOWLIST": PROJECTION.QA_UID,
        "MEMORY_TYPESENSE_COLLECTION": PROJECTION.COLLECTION,
        "TYPESENSE_PROTOCOL": "https",
        "TYPESENSE_HOST_PORT": "443",
        "TYPESENSE_API_KEY": "opaque-qa-key",
    }


def test_typesense_url_accepts_only_the_named_cloud_run_service():
    assert PROJECTION.parse_typesense_url("https://typesense-jit-qa-abc.run.app/") == (
        "https://typesense-jit-qa-abc.run.app",
        "typesense-jit-qa-abc.run.app",
    )
    for value in (
        "https://canonical-memory.run.app",
        "http://typesense-jit-qa-abc.run.app",
        "http://127.0.0.1:8108",
        "https://typesense-jit-qa-abc.run.app/other",
    ):
        with pytest.raises(PROJECTION.ProjectionError):
            PROJECTION.parse_typesense_url(value)


def test_runtime_environment_rejects_shared_data_plane_and_emulator():
    environment = _environment()
    PROJECTION.validate_runtime_environment(environment)
    with pytest.raises(PROJECTION.ProjectionError, match="OMI_FIRESTORE_DATA_PLANE_PROJECT"):
        PROJECTION.validate_runtime_environment({**environment, "OMI_FIRESTORE_DATA_PLANE_PROJECT": "based-hardware"})
    with pytest.raises(PROJECTION.ProjectionError, match="emulator"):
        PROJECTION.validate_runtime_environment({**environment, "FIRESTORE_EMULATOR_HOST": "127.0.0.1:8085"})
    with pytest.raises(PROJECTION.ProjectionError, match="MEMORY_TYPESENSE_COLLECTION"):
        PROJECTION.validate_runtime_environment(
            {**environment, "MEMORY_TYPESENSE_COLLECTION": "canonical_memory_atoms"}
        )


def test_projection_digest_excludes_content_but_tracks_owner_and_ledger_metadata():
    first = {
        "id": "atom:one",
        "memory_id": "one",
        "userId": PROJECTION.QA_UID,
        "content": "private body one",
        "ledger_schema_version": "knowledge_ledger.v1",
        "ledger_row_state": "open",
    }
    second = {**first, "content": "private body changed"}
    assert PROJECTION._projection_digest([first]) == PROJECTION._projection_digest([second])
    assert PROJECTION._projection_digest([first]) != PROJECTION._projection_digest(
        [{**first, "ledger_row_state": "closed"}]
    )


def test_build_receipt_requires_a_real_provider_and_consumed_result():
    report = SimpleNamespace(verified=True, indexed_count=1, expected_count=1)
    receipt = PROJECTION.build_projection_receipt(
        source_sha="a" * 40,
        run_id="projection-run-1",
        typesense_url="https://typesense-jit-qa-abc.run.app",
        typesense_image="gcr.io/based-hardware-dev/typesense-jit-qa@sha256:" + "b" * 64,
        typesense_base_image="docker.io/typesense/typesense@sha256:" + "e" * 64,
        query="travel plan",
        kinds=["fact"],
        rebuild_report=report,
        projection_count=1,
        projection_digest="c" * 64,
        schema_digest="d" * 64,
        schema_fields=["content", "memory_id"],
        provider_ids=["one"],
        result_ids=["one"],
    )
    assert receipt["status"] == "ready"
    assert receipt["resource_bounds"]["max_instances"] == 1
    assert receipt["cost_attribution"]["status"] == "not_measured"
    assert (
        receipt["restart_rehydration"]["post_restart_replay"]
        == "not_run; rerun this workflow after any instance restart"
    )
    assert receipt["query_sha256"] != "travel plan"
    assert "private body" not in json.dumps(receipt)
    with pytest.raises(PROJECTION.ProjectionError, match="nonempty real"):
        PROJECTION.build_projection_receipt(
            source_sha="a" * 40,
            run_id="projection-run-1",
            typesense_url="https://typesense-jit-qa-abc.run.app",
            typesense_image="gcr.io/based-hardware-dev/typesense-jit-qa@sha256:" + "b" * 64,
            typesense_base_image="docker.io/typesense/typesense@sha256:" + "e" * 64,
            query="travel plan",
            kinds=["fact"],
            rebuild_report=report,
            projection_count=1,
            projection_digest="c" * 64,
            schema_digest="d" * 64,
            schema_fields=["content", "memory_id"],
            provider_ids=[],
            result_ids=[],
        )
    with pytest.raises(PROJECTION.ProjectionError, match="counts do not agree"):
        PROJECTION.build_projection_receipt(
            source_sha="a" * 40,
            run_id="projection-run-1",
            typesense_url="https://typesense-jit-qa-abc.run.app",
            typesense_image="gcr.io/based-hardware-dev/typesense-jit-qa@sha256:" + "b" * 64,
            typesense_base_image="docker.io/typesense/typesense@sha256:" + "e" * 64,
            query="travel plan",
            kinds=["fact"],
            rebuild_report=report,
            projection_count=2,
            projection_digest="c" * 64,
            schema_digest="d" * 64,
            schema_fields=["content", "memory_id"],
            provider_ids=["one"],
            result_ids=["one"],
        )


def test_run_projection_rebuilds_then_proves_provider_and_search_consumer(monkeypatch: pytest.MonkeyPatch):
    calls: list[str] = []

    def fake_typesense_request(_base_url, path, *, query=None):
        calls.append(path)
        if path == "/health":
            return {"ok": True}
        if path == f"/collections/{PROJECTION.COLLECTION}":
            return {"name": PROJECTION.COLLECTION, "fields": [{"name": "memory_id", "type": "string"}]}
        if path.endswith("/documents"):
            return [
                {
                    "id": "atom:one",
                    "memory_id": "one",
                    "userId": PROJECTION.QA_UID,
                    "ledger_schema_version": "knowledge_ledger.v1",
                }
            ]
        raise AssertionError(path)

    class FakeTool:
        def invoke(self, payload, *, config):
            assert payload["query"] == "travel plan"
            assert config["configurable"]["user_id"] == PROJECTION.QA_UID
            return "Current knowledge matching 'travel plan':\n- [fact] one: opaque body"

    monkeypatch.setattr(PROJECTION, "_typesense_request", fake_typesense_request)
    monkeypatch.setattr(PROJECTION, "ensure_memories_collection", lambda: calls.append("ensure"))
    monkeypatch.setattr(PROJECTION, "ensure_ledger_keyword_schema", lambda: calls.append("ledger-schema"))
    monkeypatch.setattr(
        PROJECTION,
        "rebuild_atom_keyword_index",
        lambda uid, db_client: SimpleNamespace(verified=True, indexed_count=1, expected_count=1),
    )
    monkeypatch.setattr(PROJECTION, "keyword_search_ledger_memory_ids", lambda *args, **kwargs: ["one"])
    monkeypatch.setattr(PROJECTION, "search_knowledge", FakeTool())
    monkeypatch.setattr(PROJECTION.firestore, "Client", lambda **kwargs: object())

    receipt = PROJECTION.run_projection(
        source_sha="a" * 40,
        run_id="projection-run-2",
        typesense_url="https://typesense-jit-qa-abc.run.app",
        typesense_image="gcr.io/based-hardware-dev/typesense-jit-qa@sha256:" + "b" * 64,
        typesense_base_image="docker.io/typesense/typesense@sha256:" + "e" * 64,
        query="travel plan",
        kinds="fact",
        limit=8,
        environment=_environment(),
    )
    assert receipt["status"] == "ready"
    assert "ensure" in calls and "ledger-schema" in calls
    assert calls.index("/health") < calls.index(f"/collections/{PROJECTION.COLLECTION}/documents")


def test_failed_receipt_is_content_free_and_private(tmp_path: Path):
    path = tmp_path / "receipt.json"
    PROJECTION.write_receipt(path, {"status": "failed", "failure_type": "ProjectionError"})
    assert json.loads(path.read_text(encoding="utf-8"))["status"] == "failed"
    assert path.stat().st_mode & 0o777 == 0o600
