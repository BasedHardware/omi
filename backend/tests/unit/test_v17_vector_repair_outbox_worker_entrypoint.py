import json

from scripts import v17_vector_repair_outbox_worker_entrypoint as entrypoint


class _Printer:
    def __init__(self):
        self.lines = []

    def __call__(self, line):
        self.lines.append(line)

    def payload(self):
        assert len(self.lines) == 1
        return json.loads(self.lines[0])


def test_entrypoint_absent_enabled_env_fails_closed_without_tick_or_side_effects():
    calls = []
    printer = _Printer()

    exit_code = entrypoint.run_v17_vector_repair_outbox_worker_entrypoint(
        env={},
        db_client=object(),
        authoritative_item_loader=lambda record: calls.append("load"),
        vector_deleter=lambda record: calls.append("delete"),
        vector_repairer=lambda record, item: calls.append("repair"),
        tick_runner=lambda **kwargs: calls.append("tick"),
        print_json=printer,
    )

    assert exit_code == 0
    assert calls == []
    assert printer.payload() == {
        "enabled": False,
        "config_valid": True,
        "uid": None,
        "worker_id": None,
        "leased_count": 0,
        "processed_count": 0,
        "skipped_count": 0,
        "failed_count": 0,
        "ack_failed_count": 0,
        "actions": [],
        "errors": [],
    }


def test_entrypoint_malformed_enabled_env_is_denied_without_tick():
    calls = []
    printer = _Printer()

    exit_code = entrypoint.run_v17_vector_repair_outbox_worker_entrypoint(
        env={"V17_VECTOR_REPAIR_OUTBOX_WORKER_ENABLED": "yes"},
        db_client=object(),
        authoritative_item_loader=lambda record: calls.append("load"),
        vector_deleter=lambda record: calls.append("delete"),
        vector_repairer=lambda record, item: calls.append("repair"),
        tick_runner=lambda **kwargs: calls.append("tick"),
        print_json=printer,
    )

    payload = printer.payload()
    assert exit_code == 2
    assert calls == []
    assert payload["enabled"] is False
    assert payload["config_valid"] is False
    assert payload["errors"] == [
        {"stage": "config", "error": "V17_VECTOR_REPAIR_OUTBOX_WORKER_ENABLED must be 'true' or 'false'"}
    ]


def test_entrypoint_enabled_requires_explicit_uid_and_stable_worker_id():
    calls = []
    printer = _Printer()

    exit_code = entrypoint.run_v17_vector_repair_outbox_worker_entrypoint(
        env={"V17_VECTOR_REPAIR_OUTBOX_WORKER_ENABLED": "true", "V17_VECTOR_REPAIR_OUTBOX_UID": "u1"},
        db_client=object(),
        authoritative_item_loader=lambda record: calls.append("load"),
        vector_deleter=lambda record: calls.append("delete"),
        vector_repairer=lambda record, item: calls.append("repair"),
        tick_runner=lambda **kwargs: calls.append("tick"),
        print_json=printer,
    )

    payload = printer.payload()
    assert exit_code == 2
    assert calls == []
    assert payload["config_valid"] is False
    assert payload["errors"] == [
        {"stage": "config", "error": "V17_VECTOR_REPAIR_OUTBOX_WORKER_ID is required when enabled"}
    ]


def test_entrypoint_enabled_invokes_injected_tick_and_prints_deterministic_summary():
    printer = _Printer()
    captured = {}

    def fake_tick_runner(**kwargs):
        captured.update(kwargs)
        return {
            "enabled": True,
            "worker_id": "worker-a",
            "uid": "u1",
            "leased_count": 1,
            "processed_count": 1,
            "skipped_count": 0,
            "failed_count": 0,
            "ack_failed_count": 0,
            "actions": [{"record_id": "rec-1", "idempotency_key": "idem-1", "action": "delete"}],
            "errors": [],
        }

    db = object()
    loader = object()
    deleter = object()
    repairer = object()
    exit_code = entrypoint.run_v17_vector_repair_outbox_worker_entrypoint(
        env={
            "V17_VECTOR_REPAIR_OUTBOX_WORKER_ENABLED": "true",
            "V17_VECTOR_REPAIR_OUTBOX_UID": "u1",
            "V17_VECTOR_REPAIR_OUTBOX_WORKER_ID": "worker-a",
            "V17_VECTOR_REPAIR_OUTBOX_LIMIT": "7",
            "V17_VECTOR_REPAIR_OUTBOX_LEASE_SECONDS": "90",
            "V17_VECTOR_REPAIR_OUTBOX_MAX_ATTEMPTS": "4",
        },
        db_client=db,
        authoritative_item_loader=loader,
        vector_deleter=deleter,
        vector_repairer=repairer,
        tick_runner=fake_tick_runner,
        print_json=printer,
    )

    assert exit_code == 0
    assert captured["db_client"] is db
    assert captured["uid"] == "u1"
    assert captured["config"].enabled is True
    assert captured["config"].worker_id == "worker-a"
    assert captured["config"].limit == 7
    assert captured["config"].lease_seconds == 90
    assert captured["config"].max_attempts == 4
    assert captured["authoritative_item_loader"] is loader
    assert captured["vector_deleter"] is deleter
    assert captured["vector_repairer"] is repairer
    assert printer.payload()["actions"] == [{"record_id": "rec-1", "idempotency_key": "idem-1", "action": "delete"}]


def test_entrypoint_dependency_or_action_failure_is_summarized_and_nonzero():
    printer = _Printer()

    def fake_tick_runner(**kwargs):
        return {
            "enabled": True,
            "worker_id": "worker-a",
            "uid": "u1",
            "leased_count": 1,
            "processed_count": 0,
            "skipped_count": 0,
            "failed_count": 1,
            "ack_failed_count": 0,
            "actions": [],
            "errors": [{"stage": "process", "record_id": "rec-1", "error": "pinecone unavailable"}],
        }

    exit_code = entrypoint.run_v17_vector_repair_outbox_worker_entrypoint(
        env={
            "V17_VECTOR_REPAIR_OUTBOX_WORKER_ENABLED": "true",
            "V17_VECTOR_REPAIR_OUTBOX_UID": "u1",
            "V17_VECTOR_REPAIR_OUTBOX_WORKER_ID": "worker-a",
        },
        db_client=object(),
        authoritative_item_loader=lambda record: None,
        vector_deleter=lambda record: None,
        vector_repairer=lambda record, item: None,
        tick_runner=fake_tick_runner,
        print_json=printer,
    )

    payload = printer.payload()
    assert exit_code == 1
    assert payload["failed_count"] == 1
    assert payload["errors"] == [{"stage": "process", "record_id": "rec-1", "error": "pinecone unavailable"}]


def test_entrypoint_contract_has_no_scheduler_enqueue_side_effects():
    source = entrypoint.__loader__.get_source(entrypoint.__name__)

    assert "enqueue_" not in source
    assert "CloudTasksClient" not in source
    assert "firebase emulators" not in source


def test_main_disabled_path_does_not_initialize_production_dependencies(monkeypatch):
    printer = _Printer()
    calls = []

    monkeypatch.setattr(
        entrypoint, "build_v17_vector_repair_outbox_production_dependencies", lambda env: calls.append("deps")
    )

    exit_code = entrypoint.main(env={}, print_json=printer)

    assert exit_code == 0
    assert calls == []
    assert printer.payload()["enabled"] is False


def test_main_enabled_calls_production_dependency_resolver_once(monkeypatch):
    printer = _Printer()
    calls = []
    deps = entrypoint.V17VectorRepairOutboxProductionDependencies(
        db_client=object(),
        authoritative_item_loader=object(),
        vector_deleter=object(),
        vector_repairer=object(),
    )

    def fake_resolver(env):
        calls.append(dict(env))
        return deps

    def fake_runner(**kwargs):
        return {
            "enabled": True,
            "worker_id": "worker-a",
            "uid": "u1",
            "leased_count": 0,
            "processed_count": 0,
            "skipped_count": 0,
            "failed_count": 0,
            "ack_failed_count": 0,
            "actions": [],
            "errors": [],
        }

    monkeypatch.setattr(entrypoint, "build_v17_vector_repair_outbox_production_dependencies", fake_resolver)

    exit_code = entrypoint.main(
        env={
            "V17_VECTOR_REPAIR_OUTBOX_WORKER_ENABLED": "true",
            "V17_VECTOR_REPAIR_OUTBOX_UID": "u1",
            "V17_VECTOR_REPAIR_OUTBOX_WORKER_ID": "worker-a",
        },
        tick_runner=fake_runner,
        print_json=printer,
    )

    assert exit_code == 0
    assert len(calls) == 1
    assert calls[0]["V17_VECTOR_REPAIR_OUTBOX_WORKER_ENABLED"] == "true"
    assert printer.payload()["config_valid"] is True


def test_main_enabled_missing_production_dependency_config_fails_before_lease(monkeypatch):
    printer = _Printer()
    calls = []

    def fake_runner(**kwargs):
        calls.append("tick")
        return {}

    exit_code = entrypoint.main(
        env={
            "V17_VECTOR_REPAIR_OUTBOX_WORKER_ENABLED": "true",
            "V17_VECTOR_REPAIR_OUTBOX_UID": "u1",
            "V17_VECTOR_REPAIR_OUTBOX_WORKER_ID": "worker-a",
        },
        tick_runner=fake_runner,
        print_json=printer,
    )

    payload = printer.payload()
    assert exit_code == 2
    assert calls == []
    assert payload["config_valid"] is False
    assert payload["errors"] == [
        {
            "stage": "dependencies",
            "error": "PINECONE_API_KEY is required when V17 vector repair worker is enabled",
        }
    ]


def test_production_dependency_resolver_builds_lazy_clients_and_loader_from_env():
    calls = []
    docs = {
        "users/u1/memory_items/mem1": {
            "memory_id": "mem1",
            "uid": "u1",
            "version": 1,
            "tier": "long_term",
            "status": "active",
            "processing_state": "processed",
            "content": "User prefers concise updates.",
            "evidence": [
                {
                    "evidence_id": "ev1",
                    "source_id": "src1",
                    "source_version": "v1",
                    "source_type": "conversation",
                    "artifact_preservation": "preserved",
                    "source_state": "active",
                }
            ],
            "source_state": "active",
            "sensitivity_labels": [],
            "visibility": "private",
            "user_asserted": False,
            "captured_at": "2026-06-19T00:00:00+00:00",
            "updated_at": "2026-06-19T00:00:00+00:00",
            "ledger_commit_id": "ledger-1",
            "ledger_sequence": 1,
            "item_revision": 2,
            "source_commit_id": "source-1",
            "content_hash": "hash-1",
            "account_generation": 7,
        }
    }

    class Snapshot:
        def __init__(self, data):
            self.exists = data is not None
            self._data = data

        def to_dict(self):
            return self._data

    class Document:
        def __init__(self, path):
            self.path = path

        def get(self):
            calls.append(("get", self.path))
            return Snapshot(docs.get(self.path))

    class DB:
        def document(self, path):
            return Document(path)

    class Index:
        def delete(self, **kwargs):
            calls.append(("delete", kwargs))
            return {"deleted": 1}

        def upsert(self, **kwargs):
            calls.append(("upsert", kwargs))
            return {"upserted": 1}

    class PineconeClient:
        def __init__(self, api_key):
            calls.append(("pinecone", api_key))

        def Index(self, name):
            calls.append(("index", name))
            return Index()

    class PineconeModule:
        Pinecone = PineconeClient

    class ClientModule:
        db = DB()

    class Embeddings:
        def embed_query(self, content):
            calls.append(("embed", content))
            return [0.1, 0.2]

    class LlmClientsModule:
        embeddings = Embeddings()

    def module_loader(name):
        calls.append(("import", name))
        if name == "pinecone":
            return PineconeModule
        if name == "database._client":
            return ClientModule
        if name == "utils.llm.clients":
            return LlmClientsModule
        raise AssertionError(name)

    deps = entrypoint.build_v17_vector_repair_outbox_production_dependencies(
        {
            "PINECONE_API_KEY": "pc-key",
            "PINECONE_INDEX_NAME": "memory-index",
            "OPENAI_API_KEY": "openai-key",
        },
        module_loader=module_loader,
    )

    item = deps.authoritative_item_loader({"uid": "u1", "memory_id": "mem1"})
    deps.vector_deleter({"vector_id": "vec1"})
    deps.vector_repairer({"required_projection_commit_id": "projection-1"}, item)

    assert ("pinecone", "pc-key") in calls
    assert ("index", "memory-index") in calls
    assert ("get", "users/u1/memory_items/mem1") in calls
    assert ("delete", {"ids": ["vec1"], "namespace": "ns2"}) in calls
    assert ("embed", "User prefers concise updates.") in calls
    assert any(call[0] == "upsert" and call[1]["namespace"] == "ns2" for call in calls)
