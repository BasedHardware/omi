from utils.memory.v17_v3_f6_pre_gcp_aggregate import (
    F6_LOCAL_GATE_IDS,
    GCP_ACCESS_GATE_IDS,
    build_pre_gcp_aggregate_report,
    build_report_from_current_local_contracts,
)


def _all_passed_local_proofs():
    return {gate_id: {"status": "PASS", "evidence": f"{gate_id} proof"} for gate_id in F6_LOCAL_GATE_IDS}


def test_f6h_aggregate_requires_every_local_f6_gate_before_pre_gcp_ready():
    proofs = _all_passed_local_proofs()
    proofs.pop("f6d_read_rpc_allowlist_client")

    report = build_pre_gcp_aggregate_report(local_proofs=proofs)

    assert report["artifact_version"] == "V17-V3-F6H"
    assert report["status"] == "BLOCKED"
    assert report["decision"] == "NO_GO"
    assert report["missing_local_gates"] == ["f6d_read_rpc_allowlist_client"]
    assert report["remaining_blockers"] != ["gcp_access"]


def test_f6h_aggregate_marks_only_gcp_access_when_all_local_gates_pass():
    report = build_pre_gcp_aggregate_report(local_proofs=_all_passed_local_proofs())

    assert report["status"] == "PRE_GCP_READY"
    assert report["decision"] == "BLOCKED_ON_GCP_ACCESS"
    assert report["missing_local_gates"] == []
    assert report["remaining_blockers"] == ["gcp_access"]
    assert [row["status"] for row in report["gcp_access_gates"]] == ["BLOCKED_ON_GCP_ACCESS"] * len(GCP_ACCESS_GATE_IDS)
    assert report["non_claims"] == [
        "no real GCP execution performed",
        "no credentials, secrets, or project identifiers committed",
        "no production activation, canary, shadow, or cutover approved",
        "prod read-only evidence remains blocked on separate access and approval",
    ]


def test_f6h_aggregate_rejects_unknown_or_failing_local_proofs():
    proofs = _all_passed_local_proofs()
    proofs["surprise_gate"] = {"status": "PASS"}
    proofs["f6f_redaction_output_contract"] = {"status": "FAIL"}

    report = build_pre_gcp_aggregate_report(local_proofs=proofs)

    assert report["status"] == "BLOCKED"
    assert report["decision"] == "NO_GO"
    assert report["unknown_local_gates"] == ["surprise_gate"]
    assert report["failed_local_gates"] == ["f6f_redaction_output_contract"]


def test_f6h_aggregate_can_build_from_current_local_contract_smoke():
    report = build_report_from_current_local_contracts()

    assert report["artifact_version"] == "V17-V3-F6H"
    assert report["status"] == "PRE_GCP_READY"
    assert report["decision"] == "BLOCKED_ON_GCP_ACCESS"
    assert report["remaining_blockers"] == ["gcp_access"]
