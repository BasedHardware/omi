import json
from pathlib import Path

from scripts.validate_frame_request_bucket_contract import (
    main,
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
    contract = {
        "allowed_locations": ["US-CENTRAL1"],
        "uniform_bucket_level_access": True,
        "public_access_prevention": "enforced",
    }
    state = {
        "name": "omi-frame-requests",
        "location": "US-CENTRAL1",
        "lifecycle": {"rule": []},
        "iamConfiguration": {
            "uniformBucketLevelAccess": {"enabled": True},
            "publicAccessPrevention": "enforced",
        },
    }
    assert validate_bucket_contract("omi-frame-requests", state, contract) == []


def test_live_bucket_contract_rejects_wrong_or_public_bucket():
    contract = {
        "allowed_locations": ["US-CENTRAL1"],
        "uniform_bucket_level_access": True,
        "public_access_prevention": "enforced",
    }
    errors = validate_bucket_contract(
        "dev-omi-frame-requests",
        {
            "name": "shared-images",
            "location": "EU",
            "lifecycle": {"rule": []},
            "iamConfiguration": {
                "uniformBucketLevelAccess": {"enabled": False},
                "publicAccessPrevention": "inherited",
            },
        },
        contract,
    )
    assert len(errors) == 4


def test_runtime_manifest_and_contract_bind_permanent_bucket():
    root = Path(__file__).resolve().parents[2]
    import yaml

    runtime = yaml.safe_load((root / "deploy/runtime_env.yaml").read_text())
    contract = json.loads((root / "deploy/frame-request-bucket-contract.json").read_text())
    assert validate_runtime_binding(runtime) == []
    assert validate_contract_document(contract) == []


def test_runtime_manifest_alone_cannot_claim_live_bucket_validation(monkeypatch):
    root = Path(__file__).resolve().parents[2]
    monkeypatch.setattr(
        "sys.argv",
        [
            "validate_frame_request_bucket_contract.py",
            "--runtime-env",
            str(root / "deploy/runtime_env.yaml"),
            "--contract",
            str(root / "deploy/frame-request-bucket-contract.json"),
        ],
    )

    assert main() == 1
