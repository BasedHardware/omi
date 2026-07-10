from pydantic import ValidationError

from models.memory_contracts import (
    DurableMemoryPatch,
    L1MemoryArchiveClass,
    L1MemoryArchiveItem,
    L2SearchPlan,
    LifecycleState,
    WorkingMemoryObservation,
    derive_allowed_use,
    deterministic_contract_id,
    filter_l1_archive_for_normal_search,
)


def test_working_memory_observation_uses_canonical_status_and_derived_allowed_use():
    observation = WorkingMemoryObservation(
        observation_id="obs_existing",
        packet_id="pkt_1",
        content="User prefers automatic memory capture.",
        evidence_ids=["ev_1"],
        source_refs=[{"source_id": "src_1", "quote": "I want something automatic."}],
        status=LifecycleState.working,
        confidence="high",
        risk_flags=[],
    )

    assert observation.allowed_use == "read_with_status"
    assert derive_allowed_use(LifecycleState.active, []) == "stable_profile_fact"
    assert derive_allowed_use(LifecycleState.review, []) == "review_only"
    assert derive_allowed_use(LifecycleState.working, ["secret"]) == "hidden"


def test_unknown_lifecycle_status_is_rejected():
    try:
        WorkingMemoryObservation(
            observation_id="obs_bad",
            packet_id="pkt_1",
            content="User prefers automatic memory capture.",
            evidence_ids=["ev_1"],
            source_refs=[{"source_id": "src_1", "quote": "I want something automatic."}],
            status="pending_consolidation",
            confidence="high",
        )
    except ValidationError as exc:
        assert "status" in str(exc)
    else:
        raise AssertionError("unknown lifecycle status should be rejected")


def test_durable_memory_patch_requires_target_for_merge_update_and_add_evidence():
    for decision in ["merge", "update", "add_evidence", "skip_duplicate"]:
        try:
            DurableMemoryPatch(
                patch_id="patch_1",
                packet_id="pkt_1",
                run_id="memory_test",
                observed_head_commit_id="head_1",
                idempotency_key="idem_1",
                decision=decision,
                result_status=LifecycleState.active,
                evidence_ids=["ev_1"],
            )
        except ValidationError as exc:
            assert "target_memory_id" in str(exc)
        else:
            raise AssertionError(f"{decision} should require target_memory_id")


def test_durable_memory_patch_idempotency_key_is_deterministic():
    first = deterministic_contract_id(
        "durable-patch",
        {"packet_id": "pkt_1", "decision": "add", "memory_text": "User prefers automatic memory capture."},
    )
    second = deterministic_contract_id(
        "durable-patch",
        {"memory_text": "User prefers automatic memory capture.", "decision": "add", "packet_id": "pkt_1"},
    )

    assert first == second
    assert len(first) == 64


def test_l2_search_plan_enforces_same_user_budget_and_labels_results():
    plan = L2SearchPlan(
        packet_id="pkt_1",
        search_budget=3,
        searches=[
            {"query": "automatic memory capture", "reason": "find existing preference memories"},
            {"query": "manual knowledge base", "reason": "find related dislike memories"},
            {"query": "digital second brain", "reason": "find related knowledge management memories"},
        ],
    )

    assert plan.same_user_only is True
    assert plan.read_only is True

    try:
        L2SearchPlan(
            packet_id="pkt_1",
            search_budget=3,
            searches=[
                {"query": "one", "reason": "1"},
                {"query": "two", "reason": "2"},
                {"query": "three", "reason": "3"},
                {"query": "four", "reason": "4"},
            ],
        )
    except ValidationError as exc:
        assert "searches" in str(exc)
    else:
        raise AssertionError("custom search plans must enforce the three-search budget")


def test_l1_archive_item_uses_only_general_or_sensitive_and_deterministic_id():
    item = L1MemoryArchiveItem(
        user_id="user_1",
        source_id="raw_voice_1",
        source_type="voice_transcript",
        text="User was troubleshooting Rust graphics fog and TAA settings.",
        evidence_quotes=["why does the distance look foggy in Rust with TAA"],
        source_refs=[{"unit_id": "seg_1", "quote": "why does the distance look foggy in Rust with TAA"}],
        speaker_label="speaker_0",
        confidence="medium",
    )

    assert item.schema_version == "l1_memory_archive_item.v1"
    assert item.archive_class == L1MemoryArchiveClass.general
    assert item.archive_id.startswith("l1_")
    assert item.normal_search_allowed is True
    assert item.is_stable_profile_fact is False

    same = L1MemoryArchiveItem(
        user_id="user_1",
        source_id="raw_voice_1",
        source_type="voice_transcript",
        text="User was troubleshooting Rust graphics fog and TAA settings.",
        evidence_quotes=["why does the distance look foggy in Rust with TAA"],
        source_refs=[{"unit_id": "seg_1", "quote": "why does the distance look foggy in Rust with TAA"}],
        speaker_label="speaker_0",
        confidence="medium",
    )
    assert same.archive_id == item.archive_id


def test_l1_archive_item_normalizes_secrets_to_sensitive_and_blocks_normal_search():
    item = L1MemoryArchiveItem(
        user_id="user_1",
        source_id="desktop_1",
        source_type="screenshot_ocr",
        text="A password is visible in the terminal.",
        archive_class="general",
        evidence_quotes=["password: hunter2"],
        risk_flags=["credential"],
    )

    assert item.archive_class == L1MemoryArchiveClass.sensitive
    assert item.normal_search_allowed is False
    assert item.allowed_use == "restricted_archive_only"


def test_normal_l1_archive_search_excludes_sensitive_and_labels_evidence():
    general = L1MemoryArchiveItem(
        user_id="user_1",
        source_id="raw_chat_1",
        source_type="chat_exchange",
        text="User is evaluating MCP access instructions for agents.",
        evidence_quotes=["agents should use the MCP and CLI instructions"],
    )
    sensitive = L1MemoryArchiveItem(
        user_id="user_1",
        source_id="raw_chat_2",
        source_type="chat_exchange",
        text="User shared a password manager credential.",
        archive_class="sensitive",
        evidence_quotes=["the password is ..."],
    )

    results = filter_l1_archive_for_normal_search([general, sensitive], query="MCP agents")

    assert [row.archive_id for row in results] == [general.archive_id]
    assert results[0].normal_search_allowed is True
    assert results[0].search_result_label == "archived_evidence_not_stable_memory"


def test_l1_archive_rejects_route_like_classes():
    try:
        L1MemoryArchiveItem(
            user_id="user_1",
            source_id="raw_chat_1",
            source_type="chat_exchange",
            text="User said something useful.",
            archive_class="working_note",
            evidence_quotes=["useful"],
        )
    except ValidationError as exc:
        assert "archive_class" in str(exc)
    else:
        raise AssertionError("L1 archive must not accept working_note/review/context_only classes")
