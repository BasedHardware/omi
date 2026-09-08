import json
from pathlib import Path

from scripts.validate_storage_lifecycle import (
    LEGACY_DELETE_RULES,
    validate_against_live,
    validate_desired_document,
    validate_notifications,
)

DEPLOY_DIR = Path(__file__).resolve().parents[2] / "deploy" / "storage-lifecycle"
APPLY_FILES = ("prod.json", "development.json")
ROLLBACK_FILES = ("prod.rollback.json", "development.rollback.json")


def _load(name: str) -> dict:
    return json.loads((DEPLOY_DIR / name).read_text(encoding="utf-8"))


def _rules(document: dict) -> list:
    return document["lifecycle"]["rule"]


def test_checked_in_documents_pass_the_source_contract():
    for name in APPLY_FILES + ROLLBACK_FILES:
        assert validate_desired_document(_load(name)) == [], name


def test_no_delete_rule_can_reach_chunks():
    for name in APPLY_FILES + ROLLBACK_FILES:
        for rule in _rules(_load(name)):
            if rule["action"]["type"] != "Delete":
                continue
            prefixes = rule["condition"].get("matchesPrefix")
            assert prefixes, f"{name}: unscoped Delete rule"
            for prefix in prefixes:
                assert not prefix.startswith("chunks/"), f"{name}: {prefix}"
                assert not "chunks/".startswith(prefix), f"{name}: {prefix}"


def test_apply_files_declare_exactly_one_coldline_rule_scoped_to_chunks():
    for name in APPLY_FILES:
        set_class = [r for r in _rules(_load(name)) if r["action"]["type"] == "SetStorageClass"]
        assert len(set_class) == 1, name
        rule = set_class[0]
        assert rule["action"]["storageClass"] == "COLDLINE"
        assert rule["condition"]["age"] == 30
        assert rule["condition"]["matchesPrefix"] == ["chunks/"]


def test_prod_re_declares_the_two_legacy_delete_rules_verbatim():
    for name in ("prod.json", "prod.rollback.json"):
        rules = _rules(_load(name))
        assert {"action": {"type": "Delete"}, "condition": {"age": 3, "matchesPrefix": ["merged/"]}} in rules, name
        assert {"action": {"type": "Delete"}, "condition": {"age": 30, "matchesPrefix": ["playback/"]}} in rules, name
        for legacy in LEGACY_DELETE_RULES:
            assert legacy in rules, name


def test_rollback_files_only_drop_the_set_storage_class_rule():
    for apply_name, rollback_name in zip(APPLY_FILES, ROLLBACK_FILES):
        apply_rules = _rules(_load(apply_name))
        rollback_rules = _rules(_load(rollback_name))
        assert all(rule["action"]["type"] == "Delete" for rule in rollback_rules)
        assert all(rule in apply_rules for rule in rollback_rules)
        dropped = [rule for rule in apply_rules if rule not in rollback_rules]
        assert [rule["action"]["type"] for rule in dropped] == ["SetStorageClass"]
        assert _load(apply_name)["bucket"] == _load(rollback_name)["bucket"]


def test_bucket_wide_set_storage_class_rule_is_rejected():
    errors = validate_desired_document(
        {
            "bucket": "omi-dev-private-cloud-sync",
            "project": "based-hardware-dev",
            "lifecycle": {
                "rule": [
                    {
                        "action": {"type": "SetStorageClass", "storageClass": "COLDLINE"},
                        "condition": {"age": 30},
                    }
                ]
            },
        }
    )
    assert any("prefix-scoped to exactly" in error for error in errors)


def test_unscoped_delete_rule_is_rejected():
    errors = validate_desired_document(
        {
            "bucket": "omi-dev-private-cloud-sync",
            "project": "based-hardware-dev",
            "lifecycle": {"rule": [{"action": {"type": "Delete"}, "condition": {"age": 365}}]},
        }
    )
    assert any("unscoped Delete" in error for error in errors)


def test_delete_rule_on_chunks_is_rejected():
    errors = validate_desired_document(
        {
            "bucket": "omi-dev-private-cloud-sync",
            "project": "based-hardware-dev",
            "lifecycle": {
                "rule": [{"action": {"type": "Delete"}, "condition": {"age": 365, "matchesPrefix": ["chunks/"]}}]
            },
        }
    )
    assert any("can match 'chunks/'" in error for error in errors)


def test_noncurrent_version_rule_is_rejected():
    document = _load("development.json")
    document["lifecycle"]["rule"].append(
        {
            "action": {"type": "SetStorageClass", "storageClass": "COLDLINE"},
            "condition": {"isLive": False, "daysSinceNoncurrentTime": 30},
        }
    )
    errors = validate_desired_document(document)
    assert any("noncurrent" in error for error in errors)


def test_live_rule_not_present_in_desired_fails_without_allow_rule_removal():
    desired = _load("development.json")
    live = {
        "name": "omi-dev-private-cloud-sync",
        "versioning": {"enabled": True},
        "lifecycle": {
            "rule": _rules(desired)[:1]
            + [{"action": {"type": "Delete"}, "condition": {"age": 7, "matchesPrefix": ["scratch/"]}}]
        },
    }
    errors = validate_against_live(desired, live)
    assert any("drops a rule that is live" in error for error in errors)
    assert validate_against_live(desired, live, allow_rule_removal=True) == []


def test_expect_applied_requires_equality_and_versioning_stays_on():
    desired = _load("prod.json")
    live = {"name": "omi-private-cloud-sync", "versioning": {"enabled": True}, "lifecycle": {"rule": _rules(desired)}}
    assert validate_against_live(desired, live, expect_applied=True) == []
    live["versioning"] = {"enabled": False}
    assert any("versioning must be enabled" in error for error in validate_against_live(desired, live))


def test_notification_configs_block_the_apply():
    assert validate_notifications([]) == []
    assert validate_notifications([{"id": "1", "topic": "projects/x/topics/y"}])


def test_non_string_action_type_is_rejected_not_crashed():
    document = _load("development.json")
    document["lifecycle"]["rule"].append(
        {"action": {"type": ["Delete", "SetStorageClass"]}, "condition": {"age": 30, "matchesPrefix": ["chunks/"]}}
    )
    errors = validate_desired_document(document)
    assert any("unsupported action" in error for error in errors)


def test_missing_or_malformed_matches_storage_class_is_rejected():
    document = _load("development.json")
    document["lifecycle"]["rule"] = [
        {
            "action": {"type": "SetStorageClass", "storageClass": "COLDLINE"},
            "condition": {"age": 30, "matchesPrefix": ["chunks/"]},
        }
    ]
    errors = validate_desired_document(document)
    assert any("matchesStorageClass must be exactly" in error for error in errors), "omitted matchesStorageClass"

    document["lifecycle"]["rule"][0]["condition"]["matchesStorageClass"] = ["STANDARD"]
    errors = validate_desired_document(document)
    assert any("matchesStorageClass must be exactly" in error for error in errors), "subset is no longer accepted"

    document["lifecycle"]["rule"][0]["condition"]["matchesStorageClass"] = ["STANDARD", 7]
    errors = validate_desired_document(document)
    assert any("matchesStorageClass must be exactly" in error for error in errors), "malformed element"


def test_scoped_rule_removal_blocks_rules_the_apply_never_declared():
    desired = _load("development.rollback.json")
    apply_rules = _rules(_load("development.json"))
    later_rule = {"action": {"type": "Delete"}, "condition": {"age": 7, "matchesPrefix": ["scratch/"]}}
    live = {
        "name": "omi-dev-private-cloud-sync",
        "versioning": {"enabled": True},
        "lifecycle": {"rule": _rules(desired) + [later_rule]},
    }
    # The Coldline rule (declared by the apply variant) is droppable...
    coldline_live = {
        "name": "omi-dev-private-cloud-sync",
        "versioning": {"enabled": True},
        "lifecycle": {"rule": apply_rules},
    }
    assert validate_against_live(desired, coldline_live, allow_rule_removal_of=apply_rules) == []
    # ...but a later live rule the apply never contained still blocks.
    errors = validate_against_live(desired, live, allow_rule_removal_of=apply_rules)
    assert any("drops a rule that is live" in error for error in errors)
    # And the blanket override still exists for operators.
    assert validate_against_live(desired, live, allow_rule_removal=True) == []
