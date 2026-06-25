import json
from pathlib import Path

import pytest

from tests.unit.readiness._harness import (
    assert_readiness_safe_by_default,
    build_readiness_report,
    load_readiness_script,
)

_ARTIFACT = "p1_3_v3_cursor_secret_readiness"
_SCRIPT = "p1_3_v3_cursor_secret_readiness.py"


def _module():
    return load_readiness_script(_SCRIPT)


def test_cursor_secret_readiness_runner_exists_and_is_safe_by_default():
    report = build_readiness_report(_SCRIPT, execute=False)
    assert_readiness_safe_by_default(report, artifact=_ARTIFACT)


def test_cursor_secret_readiness_blocks_without_server_owned_secret_source_and_never_uses_client_secret():
    module = _module()
    report = module.build_report(execute=True)

    assert report["status"] == "BLOCKED"
    assert report["proof_status"] == "BLOCKED"
    secret_source = report["server_owned_secret_source"]
    assert secret_source["status"] == "BLOCKED"
    assert (
        secret_source["required_source"]
        == "server-owned MEMORY_V3_CURSOR_SIGNING_SECRET or managed secret injected into backend runtime"
    )
    assert secret_source["client_supplied_secret_trusted"] is False
    assert secret_source["invented_secret_material"] is False
    assert secret_source["env_secret_read_attempted"] is False
    assert (
        secret_source["blocker"] == "No existing runtime-owned memory /v3 cursor signing secret/config source is wired."
    )

    trust_boundary = {item["requirement_id"]: item for item in report["trust_boundary_requirements"]}
    assert trust_boundary["server_owned_secret_only"]["client_controlled"] is False
    assert trust_boundary["first_page_no_cursor"]["requires_cursor_secret"] is False
    assert trust_boundary["subsequent_page_cursor"]["requires_cursor_secret"] is True
    assert trust_boundary["signed_cursor_context_binding"]["bound_fields"] == [
        "uid",
        "account_generation",
        "projection_generation",
        "filter_hash",
        "source",
        "read_mode",
        "keyset",
        "expires_at_epoch_seconds",
    ]


def test_cursor_secret_readiness_proves_pure_fake_cursor_cases_fail_closed():
    module = _module()
    report = module.build_report(execute=True)

    cases = {case["case_id"]: case for case in report["pure_fake_cursor_case_matrix"]}
    assert list(cases) == [
        "first_page_no_cursor_no_secret_needed",
        "server_owned_secret_signed_cursor_round_trip",
        "tampered_cursor_rejected",
        "expired_cursor_rejected",
        "account_generation_mismatch_rejected",
        "projection_generation_mismatch_rejected",
        "source_mismatch_rejected",
        "wrong_secret_rejected",
        "client_supplied_secret_rejected_by_policy",
    ]
    assert cases["first_page_no_cursor_no_secret_needed"]["status"] == "READY"
    assert cases["first_page_no_cursor_no_secret_needed"]["client_secret_trusted"] is False
    assert cases["server_owned_secret_signed_cursor_round_trip"]["status"] == "READY"
    assert cases["server_owned_secret_signed_cursor_round_trip"]["preserved_claims"] == {
        "account_generation": 7,
        "projection_generation": 11,
        "source": "memory_compatibility_projection",
        "keyset": {"created_at_ms": 1799999123456, "memory_id": "memory-9"},
    }
    for case_id in [
        "tampered_cursor_rejected",
        "expired_cursor_rejected",
        "account_generation_mismatch_rejected",
        "projection_generation_mismatch_rejected",
        "source_mismatch_rejected",
        "wrong_secret_rejected",
        "client_supplied_secret_rejected_by_policy",
    ]:
        assert cases[case_id]["status"] == "FAIL_CLOSED"
        assert cases[case_id]["legacy_fallback_allowed"] is False
        assert cases[case_id]["client_secret_trusted"] is False


def test_cursor_secret_readiness_json_summary_and_docs_registration_are_stable():
    module = _module()
    decoded = json.loads(json.dumps(module.build_report(execute=True), sort_keys=True))

    assert decoded["summary"] == {
        "status": "BLOCKED",
        "proof_status": "BLOCKED",
        "ready_case_count": 2,
        "fail_closed_case_count": 7,
        "blocked_requirement_count": 1,
        "client_supplied_secret_trusted": False,
        "runtime_wiring_changed": False,
        "approval_claimed": False,
    }

    root = Path(__file__).resolve().parents[2]
    test_sh = (root / "test.sh").read_text(encoding="utf-8")
    ticket_doc = (root.parent / "docs" / "epics" / "memory_implementation_tickets.md").read_text(encoding="utf-8")
    oracle_doc = (root.parent / "docs" / "epics" / "memory_t20_oracle_milestone_review.md").read_text(encoding="utf-8")
    runtime_script = (root / "scripts" / "p1_3_v3_get_runtime_wiring_readiness.py").read_text(encoding="utf-8")
    external_script = (root / "scripts" / "p1_3_v3_external_compatibility_readiness.py").read_text(encoding="utf-8")

    assert "test_p1_3_v3_cursor_secret_readiness.py" in test_sh
    assert "p1_3_v3_cursor_secret_readiness.py" in ticket_doc
    assert "cursor secret/source integration readiness" in ticket_doc
    assert "p1_3_v3_cursor_secret_readiness.py" in oracle_doc
    assert "cursor secret/source integration readiness" in oracle_doc
    assert "CURSOR_SECRET_READINESS_PROOF" in runtime_script
    assert "cursor_secret_readiness_proof" in external_script
