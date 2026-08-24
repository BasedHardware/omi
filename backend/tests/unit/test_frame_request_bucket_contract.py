import json
from pathlib import Path

from scripts.validate_frame_request_bucket_contract import (
    validate_bucket_contract,
    validate_contract_document,
    validate_runtime_binding,
)


def test_permanent_frame_bucket_contract_requires_a_binding():
    assert validate_bucket_contract("")


def test_permanent_frame_bucket_contract_rejects_expiring_lifecycle_rule():
    errors = validate_bucket_contract(
        "omi-frame-requests",
        {"lifecycle": {"rule": [{"condition": {"age": 30}}]}},
    )
    assert any("expires objects" in error for error in errors)


def test_permanent_frame_bucket_contract_accepts_non_expiring_bucket():
    assert validate_bucket_contract("omi-frame-requests", {"lifecycle": {"rule": []}}) == []


def test_runtime_manifest_and_contract_bind_permanent_bucket():
    root = Path(__file__).resolve().parents[2]
    import yaml

    runtime = yaml.safe_load((root / "deploy/runtime_env.yaml").read_text())
    contract = json.loads((root / "deploy/frame-request-bucket-contract.json").read_text())
    assert validate_runtime_binding(runtime) == []
    assert validate_contract_document(contract) == []
