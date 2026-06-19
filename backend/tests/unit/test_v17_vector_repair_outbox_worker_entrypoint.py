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
