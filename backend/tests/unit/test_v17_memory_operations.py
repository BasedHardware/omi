from models.v17_memory_operations import MemoryOperation, MemoryOperationStatus, MemoryOperationType, build_operation_id


def test_operation_id_is_server_owned_and_independent_of_head_or_array_index():
    first = build_operation_id(
        uid="u1",
        operation_type=MemoryOperationType.long_term_apply,
        source_packet_id="pkt1",
        target_memory_id="mem1",
        evidence_ids=["ev2", "ev1"],
        logical_payload={"decision": "add", "memory_text": "User prefers concise updates."},
    )
    second = build_operation_id(
        uid="u1",
        operation_type=MemoryOperationType.long_term_apply,
        source_packet_id="pkt1",
        target_memory_id="mem1",
        evidence_ids=["ev1", "ev2"],
        logical_payload={"memory_text": "User prefers concise updates.", "decision": "add"},
        observed_head_commit_id="head_999",
        output_index=7,
    )

    assert first == second


def test_memory_operation_records_generations_and_retryable_status():
    operation = MemoryOperation.new(
        uid="u1",
        operation_type=MemoryOperationType.long_term_apply,
        source_packet_id="pkt1",
        target_memory_id="mem1",
        evidence_ids=["ev1"],
        logical_payload={"decision": "add"},
        account_generation=3,
        source_generation=5,
    )

    assert operation.operation_id
    assert operation.status == MemoryOperationStatus.pending
    assert operation.account_generation == 3
    assert operation.source_generation == 5
    assert operation.attempt_count == 0

    retry = operation.mark_retryable("transaction_conflict")
    assert retry.status == MemoryOperationStatus.retryable_failure
    assert retry.attempt_count == 1
    assert retry.error_code == "transaction_conflict"


def test_memory_operation_rejects_user_or_model_supplied_operation_id():
    operation = MemoryOperation.new(
        uid="u1",
        operation_type=MemoryOperationType.synthesis,
        source_packet_id="pkt1",
        target_memory_id=None,
        evidence_ids=["ev1"],
        logical_payload={"decision": "review"},
        proposed_operation_id="model_supplied",
    )

    assert operation.operation_id != "model_supplied"
    assert operation.untrusted_proposed_operation_id == "model_supplied"


def test_operation_is_stale_when_generation_fences_move():
    operation = MemoryOperation.new(
        uid="u1",
        operation_type=MemoryOperationType.long_term_apply,
        source_packet_id="pkt1",
        target_memory_id="mem1",
        evidence_ids=["ev1"],
        logical_payload={"decision": "add"},
        account_generation=1,
        source_generation=2,
    )

    assert operation.is_stale(account_generation=1, source_generation=2) is False
    assert operation.is_stale(account_generation=2, source_generation=2) is True
    assert operation.is_stale(account_generation=1, source_generation=3) is True
