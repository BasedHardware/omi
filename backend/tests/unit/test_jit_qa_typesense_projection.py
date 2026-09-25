from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "jit_qa_typesense_projection.py"

spec = importlib.util.spec_from_file_location("jit_qa_typesense_projection_for_test", SCRIPT)
assert spec is not None and spec.loader is not None
PROJECTION = importlib.util.module_from_spec(spec)
spec.loader.exec_module(PROJECTION)


@pytest.fixture(autouse=True)
def restore_environment():
    original = os.environ.copy()
    yield
    os.environ.clear()
    os.environ.update(original)


def _environment() -> dict[str, str]:
    return {
        "GOOGLE_CLOUD_PROJECT": PROJECTION.PROJECT_ID,
        "OMI_FIRESTORE_DATA_PLANE_PROJECT": PROJECTION.PROJECT_ID,
        "FIRESTORE_DATABASE_ID": PROJECTION.DATABASE_ID,
        "OMI_ENV_STAGE": "dev",
        "OMI_JIT_QA_AUTH_ONLY": "true",
        "OMI_JIT_QA_UID_ALLOWLIST": PROJECTION.QA_UID,
        "MEMORY_TYPESENSE_COLLECTION": PROJECTION.COLLECTION,
        "MEMORY_TYPESENSE_READINESS_REQUIRED": "true",
        "MEMORY_TYPESENSE_READINESS_COLLECTION": PROJECTION.READINESS_COLLECTION,
        "TYPESENSE_PROTOCOL": "https",
        "TYPESENSE_HOST_PORT": "443",
        "TYPESENSE_API_KEY": "opaque-qa-key",
    }


def test_typesense_url_accepts_only_the_named_cloud_run_service():
    assert PROJECTION.parse_typesense_url("https://typesense-jit-qa-1031333818730.us-central1.run.app/") == (
        "https://typesense-jit-qa-1031333818730.us-central1.run.app",
        "typesense-jit-qa-1031333818730.us-central1.run.app",
    )
    assert PROJECTION.parse_typesense_url("https://typesense-jit-qa-dt5lrfkkoa-uc.a.run.app/") == (
        "https://typesense-jit-qa-dt5lrfkkoa-uc.a.run.app",
        "typesense-jit-qa-dt5lrfkkoa-uc.a.run.app",
    )
    for value in (
        "https://canonical-memory.run.app",
        "http://typesense-jit-qa-1031333818730.us-central1.run.app",
        "http://127.0.0.1:8108",
        "https://typesense-jit-qa-1031333818730.us-central1.run.app/other",
    ):
        with pytest.raises(PROJECTION.ProjectionError):
            PROJECTION.parse_typesense_url(value)


def test_typesense_entrypoint_keeps_api_key_out_of_process_arguments():
    entrypoint = (ROOT / "scripts" / "jit_qa_typesense_entrypoint.sh").read_text(encoding="utf-8")
    assert "TYPESENSE_API_KEY" in entrypoint
    assert "--api-key" not in entrypoint
    assert 'elif [ -x /opt/typesense-server ]; then' in entrypoint
    assert "/opt/typesense-server/typesense-server" not in entrypoint


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


def test_projection_digest_hashes_content_without_emitting_it():
    first = {
        "id": "atom:one",
        "memory_id": "one",
        "userId": PROJECTION.QA_UID,
        "content": "private body one",
        "ledger_schema_version": "knowledge_ledger.v1",
        "ledger_row_state": "open",
    }
    second = {**first, "content": "private body changed"}
    assert PROJECTION._projection_digest([first]) != PROJECTION._projection_digest([second])
    assert PROJECTION._projection_digest([first]) != PROJECTION._projection_digest(
        [{**first, "ledger_row_state": "closed"}]
    )


def test_readiness_invalidation_accepts_missing_marker_but_fails_other_errors(monkeypatch: pytest.MonkeyPatch):
    def missing_marker(*_args, **_kwargs):
        raise PROJECTION.ProjectionError("Typesense request returned HTTP 404")

    monkeypatch.setattr(PROJECTION, "_typesense_request", missing_marker)
    PROJECTION._invalidate_readiness_marker("https://typesense-jit-qa-1031333818730.us-central1.run.app")

    def unavailable(*_args, **_kwargs):
        raise PROJECTION.ProjectionError("Typesense request returned HTTP 503")

    monkeypatch.setattr(PROJECTION, "_typesense_request", unavailable)
    with pytest.raises(PROJECTION.ProjectionError, match="503"):
        PROJECTION._invalidate_readiness_marker("https://typesense-jit-qa-1031333818730.us-central1.run.app")


def test_build_receipt_requires_a_real_provider_and_consumed_result():
    report = SimpleNamespace(verified=True, indexed_count=1, expected_count=1)
    receipt = PROJECTION.build_projection_receipt(
        source_sha="a" * 40,
        run_id="projection-run-1",
        typesense_url="https://typesense-jit-qa-1031333818730.us-central1.run.app",
        typesense_image="gcr.io/based-hardware-dev/typesense-jit-qa@sha256:" + "b" * 64,
        typesense_base_image=PROJECTION.TYPESENSE_BASE_IMAGE_27_1,
        query="travel plan",
        kinds=["fact"],
        rebuild_report=report,
        projection_count=1,
        projection_digest="c" * 64,
        schema_digest="d" * 64,
        schema_fields=["content", "memory_id"],
        provider_ids=["one"],
        result_ids=["one"],
        readiness_epoch="a" * 40 + ":projection-run-1",
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
            typesense_url="https://typesense-jit-qa-1031333818730.us-central1.run.app",
            typesense_image="gcr.io/based-hardware-dev/typesense-jit-qa@sha256:" + "b" * 64,
            typesense_base_image=PROJECTION.TYPESENSE_BASE_IMAGE_27_1,
            query="travel plan",
            kinds=["fact"],
            rebuild_report=report,
            projection_count=1,
            projection_digest="c" * 64,
            schema_digest="d" * 64,
            schema_fields=["content", "memory_id"],
            provider_ids=[],
            result_ids=[],
            readiness_epoch="a" * 40 + ":projection-run-1",
        )
    with pytest.raises(PROJECTION.ProjectionError, match="counts do not agree"):
        PROJECTION.build_projection_receipt(
            source_sha="a" * 40,
            run_id="projection-run-1",
            typesense_url="https://typesense-jit-qa-1031333818730.us-central1.run.app",
            typesense_image="gcr.io/based-hardware-dev/typesense-jit-qa@sha256:" + "b" * 64,
            typesense_base_image=PROJECTION.TYPESENSE_BASE_IMAGE_27_1,
            query="travel plan",
            kinds=["fact"],
            rebuild_report=report,
            projection_count=2,
            projection_digest="c" * 64,
            schema_digest="d" * 64,
            schema_fields=["content", "memory_id"],
            provider_ids=["one"],
            result_ids=["one"],
            readiness_epoch="a" * 40 + ":projection-run-1",
        )


def test_run_projection_rebuilds_then_proves_provider_and_search_consumer(monkeypatch: pytest.MonkeyPatch):
    calls: list[str] = []
    request_calls: list[tuple[str, str]] = []
    persisted_marker: dict[str, object] = {}

    def fake_typesense_request(_base_url, path, *, query=None, method="GET", payload=None):
        calls.append(path)
        request_calls.append((method, path))
        if path == "/health":
            return {"ok": True}
        if path == f"/collections/{PROJECTION.COLLECTION}":
            return {"name": PROJECTION.COLLECTION, "fields": [{"name": "memory_id", "type": "string"}]}
        if path == f"/collections/{PROJECTION.READINESS_COLLECTION}":
            return {
                "name": PROJECTION.READINESS_COLLECTION,
                "fields": list(PROJECTION._READINESS_SCHEMA_FIELDS),
            }
        if path == f"/collections/{PROJECTION.READINESS_COLLECTION}/documents":
            assert method == "POST"
            assert query == {"action": "upsert"}
            assert isinstance(payload, dict)
            persisted_marker.update(payload)
            return {"success": True}
        if (
            path
            == f"/collections/{PROJECTION.READINESS_COLLECTION}/documents/{PROJECTION.TYPESENSE_PROJECTION_READINESS_DOCUMENT_ID}"
        ):
            if method == "DELETE":
                persisted_marker.clear()
                return {"success": True}
            return dict(persisted_marker)
        raise AssertionError(path)

    monkeypatch.setattr(
        PROJECTION,
        "_projection_documents",
        lambda *_args, **_kwargs: [
            {
                "id": "atom:one",
                "memory_id": "one",
                "userId": PROJECTION.QA_UID,
                "ledger_schema_version": "knowledge_ledger.v1",
            }
        ],
    )

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
        typesense_url="https://typesense-jit-qa-1031333818730.us-central1.run.app",
        typesense_image="gcr.io/based-hardware-dev/typesense-jit-qa@sha256:" + "b" * 64,
        typesense_base_image=PROJECTION.TYPESENSE_BASE_IMAGE_27_1,
        query="travel plan",
        kinds="fact",
        limit=8,
        environment=_environment(),
    )
    assert receipt["status"] == "ready"
    assert receipt["readiness_epoch"] == "a" * 40 + ":projection-run-2"
    assert "ensure" in calls and "ledger-schema" in calls
    marker_path = (
        f"/collections/{PROJECTION.READINESS_COLLECTION}/documents/"
        f"{PROJECTION.TYPESENSE_PROJECTION_READINESS_DOCUMENT_ID}"
    )
    assert ("DELETE", marker_path) in request_calls
    assert request_calls.index(("DELETE", marker_path)) < request_calls.index(
        ("POST", f"/collections/{PROJECTION.READINESS_COLLECTION}/documents")
    )


def test_failed_consumer_proof_removes_new_readiness_marker(monkeypatch: pytest.MonkeyPatch):
    request_calls: list[tuple[str, str]] = []
    persisted_marker: dict[str, object] = {
        "id": PROJECTION.TYPESENSE_PROJECTION_READINESS_DOCUMENT_ID,
        "userId": PROJECTION.QA_UID,
        "projection_epoch": "old-source:old-run",
    }

    def fake_typesense_request(_base_url, path, *, query=None, method="GET", payload=None):
        request_calls.append((method, path))
        if path == "/health":
            return {"ok": True}
        if path == f"/collections/{PROJECTION.COLLECTION}":
            return {"name": PROJECTION.COLLECTION, "fields": [{"name": "memory_id", "type": "string"}]}
        if path == f"/collections/{PROJECTION.READINESS_COLLECTION}":
            return {"name": PROJECTION.READINESS_COLLECTION, "fields": list(PROJECTION._READINESS_SCHEMA_FIELDS)}
        marker_path = (
            f"/collections/{PROJECTION.READINESS_COLLECTION}/documents/"
            f"{PROJECTION.TYPESENSE_PROJECTION_READINESS_DOCUMENT_ID}"
        )
        if path == marker_path:
            if method == "DELETE":
                persisted_marker.clear()
                return {"success": True}
            return dict(persisted_marker)
        if path == f"/collections/{PROJECTION.READINESS_COLLECTION}/documents":
            assert method == "POST"
            assert query == {"action": "upsert"}
            assert isinstance(payload, dict)
            persisted_marker.update(payload)
            return {"success": True}
        raise AssertionError((method, path))

    monkeypatch.setattr(
        PROJECTION,
        "_projection_documents",
        lambda *_args, **_kwargs: [
            {
                "id": "atom:one",
                "memory_id": "one",
                "userId": PROJECTION.QA_UID,
                "ledger_schema_version": "knowledge_ledger.v1",
            }
        ],
    )

    class FailingTool:
        def invoke(self, payload, *, config):
            assert payload["query"] == "travel plan"
            assert config["configurable"]["user_id"] == PROJECTION.QA_UID
            raise RuntimeError("consumer proof unavailable")

    monkeypatch.setattr(PROJECTION, "_typesense_request", fake_typesense_request)
    monkeypatch.setattr(PROJECTION, "ensure_memories_collection", lambda: None)
    monkeypatch.setattr(PROJECTION, "ensure_ledger_keyword_schema", lambda: None)
    monkeypatch.setattr(
        PROJECTION,
        "rebuild_atom_keyword_index",
        lambda uid, db_client: SimpleNamespace(verified=True, indexed_count=1, expected_count=1),
    )
    monkeypatch.setattr(PROJECTION, "keyword_search_ledger_memory_ids", lambda *args, **kwargs: ["one"])
    monkeypatch.setattr(PROJECTION, "search_knowledge", FailingTool())
    monkeypatch.setattr(PROJECTION.firestore, "Client", lambda **kwargs: object())

    with pytest.raises(RuntimeError, match="consumer proof unavailable"):
        PROJECTION.run_projection(
            source_sha="a" * 40,
            run_id="projection-run-failure",
            typesense_url="https://typesense-jit-qa-1031333818730.us-central1.run.app",
            typesense_image="gcr.io/based-hardware-dev/typesense-jit-qa@sha256:" + "b" * 64,
            typesense_base_image=PROJECTION.TYPESENSE_BASE_IMAGE_27_1,
            query="travel plan",
            kinds="fact",
            limit=8,
            environment=_environment(),
        )

    marker_path = (
        f"/collections/{PROJECTION.READINESS_COLLECTION}/documents/"
        f"{PROJECTION.TYPESENSE_PROJECTION_READINESS_DOCUMENT_ID}"
    )
    marker_deletes = [call for call in request_calls if call == ("DELETE", marker_path)]
    assert len(marker_deletes) == 2
    assert not persisted_marker


def test_projection_documents_uses_typesense_export_jsonl(monkeypatch: pytest.MonkeyPatch):
    class ExportResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def __iter__(self):
            return iter(
                [
                    b'{"id":"atom:one","memory_id":"one","userId":"'
                    + PROJECTION.QA_UID.encode()
                    + b'","ledger_schema_version":"knowledge_ledger.v1"}\n'
                ]
            )

    requests = []
    monkeypatch.setenv("TYPESENSE_API_KEY", "opaque-qa-key")
    monkeypatch.setattr(PROJECTION, "urlopen", lambda request, timeout: (requests.append(request), ExportResponse())[1])
    documents = PROJECTION._projection_documents(
        "https://typesense-jit-qa-1031333818730.us-central1.run.app", PROJECTION.COLLECTION
    )
    assert documents[0]["memory_id"] == "one"
    assert requests[0].full_url.endswith("/documents/export?include_fields=" + "%2C".join(PROJECTION._DIGEST_FIELDS))


def test_failed_receipt_is_content_free_and_private(tmp_path: Path):
    path = tmp_path / "receipt.json"
    PROJECTION.write_receipt(path, {"status": "failed", "failure_type": "ProjectionError"})
    assert json.loads(path.read_text(encoding="utf-8"))["status"] == "failed"
    assert path.stat().st_mode & 0o777 == 0o600


def test_cli_sanitizes_unexpected_runtime_error_into_failure_receipt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
):
    output = tmp_path / "runtime-error.json"
    monkeypatch.setattr(
        PROJECTION,
        "_parse_args",
        lambda: SimpleNamespace(
            source_sha="a" * 40,
            run_id="projection-runtime-error",
            typesense_url="https://typesense-jit-qa-1031333818730.us-central1.run.app",
            typesense_image="gcr.io/based-hardware-dev/typesense-jit-qa@sha256:" + "b" * 64,
            typesense_base_image=PROJECTION.TYPESENSE_BASE_IMAGE_27_1,
            query="travel plan",
            kinds="fact",
            limit=8,
            output=output,
        ),
    )
    monkeypatch.setattr(PROJECTION, "run_projection", lambda **_: (_ for _ in ()).throw(RuntimeError("secret body")))

    assert PROJECTION.main() == 1
    failure = json.loads(output.read_text(encoding="utf-8"))
    assert failure["status"] == "failed"
    assert failure["failure_type"] == "RuntimeError"
    assert "secret body" not in output.read_text(encoding="utf-8")
    assert "secret body" not in capsys.readouterr().err
