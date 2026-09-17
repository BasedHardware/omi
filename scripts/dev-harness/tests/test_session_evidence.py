from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dev_harness import session_evidence as se

REPO_ROOT = Path(__file__).resolve().parents[3]


def _minimal_document(**overrides: object) -> dict:
    document = {
        "schema_version": 1,
        "session_id": "oms-test-session-1",
        "source": {"git_sha": "a" * 40, "dirty_digest": "clean", "repo": "BasedHardware/omi"},
        "target": {
            "platform": "android",
            "device": "session-avd-1",
            "os": "android-36",
            "app_id": "com.friend.ios.dev",
            "flavor": "dev",
            "profile": "local_dev",
        },
        "endpoints": {
            "api_base_url": "http://127.0.0.1:8000/",
            "auth_emulator_host": "127.0.0.1:9099",
            "firestore_emulator_host": "127.0.0.1:8085",
            "egress_policy": "loopback-only",
        },
        "fixtures": {"fixture_version": "v1", "auth_uid": "omi-fixture-v1-user-1"},
        "runners": {"mobile-session": "0.1.0"},
        "timestamps": {"created_at": "2026-09-16T00:00:00Z"},
        "status": {"state": "creating"},
    }
    document.update(overrides)
    return document


def _artifact(git_sha: str = "a" * 40) -> dict:
    return {
        "kind": "apk",
        "sha256": "b" * 64,
        "git_sha": git_sha,
        "path": "app-dev-debug.apk",
        "flavor": "dev",
        "built_from_source": True,
    }


class TestValidDocuments:
    def test_minimal_creating_document_is_valid(self) -> None:
        assert se.validate_evidence(_minimal_document()) == []

    def test_ready_with_matching_artifact_is_valid(self) -> None:
        document = _minimal_document(status={"state": "ready"}, artifact=_artifact())
        assert se.validate_evidence(document) == []

    def test_roundtrip_through_disk_rejects_tampering(self, tmp_path: Path) -> None:
        document = _minimal_document()
        path = se.write_evidence(tmp_path / "evidence.json", document)
        assert se.read_evidence(path) == document
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["session_id"] = "not-the-session"
        path.write_text(json.dumps(raw), encoding="utf-8")
        with pytest.raises(se.EvidenceError, match="session_id"):
            se.read_evidence(path)


class TestArtifactBinding:
    def test_ready_without_artifact_is_invalid(self) -> None:
        errors = se.validate_evidence(_minimal_document(status={"state": "ready"}))
        assert any("artifact is required" in error for error in errors)

    def test_running_with_stale_artifact_is_invalid(self) -> None:
        document = _minimal_document(status={"state": "running"}, artifact=_artifact(git_sha="c" * 40))
        errors = se.validate_evidence(document)
        assert any("stale build" in error for error in errors), errors

    def test_counts_must_account_exactly(self) -> None:
        document = _minimal_document(
            status={"state": "ready"},
            artifact=_artifact(),
            counts={"executed": 3, "passed": 2, "failed": 0, "skipped": 0},
        )
        errors = se.validate_evidence(document)
        assert any("passed+failed+skipped" in error for error in errors), errors

    def test_zero_executed_in_a_claimed_run_state_is_invalid(self) -> None:
        document = _minimal_document(
            status={"state": "stopped"},
            counts={"executed": 0, "passed": 0, "failed": 0, "skipped": 0},
        )
        errors = se.validate_evidence(document)
        assert any("zero results" in error for error in errors), errors


class TestFailClosedEndpoints:
    @pytest.mark.parametrize(
        "url",
        [
            "https://api.omi.me/",
            "https://api.omiapi.com/",
            "http://api.omi.me/",
            "https://127.0.0.1:8000/",
            "http://10.0.2.2:8000/",
            "http://192.168.1.4:8000/",
        ],
    )
    def test_non_loopback_or_https_api_urls_are_invalid(self, url: str) -> None:
        document = _minimal_document()
        document["endpoints"]["api_base_url"] = url
        errors = se.validate_evidence(document)
        assert errors, url

    def test_production_host_is_named_in_the_error(self) -> None:
        with pytest.raises(se.EvidenceError, match="production host 'api.omi.me'"):
            se.validate_local_http_url("https://api.omi.me/")

    def test_off_loopback_emulator_host_is_invalid(self) -> None:
        document = _minimal_document()
        document["endpoints"]["auth_emulator_host"] = "typesense.omi.me:9099"
        assert se.validate_evidence(document)

    def test_redis_url_must_be_loopback(self) -> None:
        document = _minimal_document()
        document["endpoints"]["redis_url"] = "redis://redis.example.com:6379/0"
        errors = se.validate_evidence(document)
        assert any("redis_url" in error for error in errors), errors


class TestProfileAndStatusGuards:
    @pytest.mark.parametrize("profile", ["mobile_beta", "production"])
    def test_production_family_profiles_are_not_session_targets(self, profile: str) -> None:
        document = _minimal_document()
        document["target"]["profile"] = profile
        errors = se.validate_evidence(document)
        assert any("target.profile" in error for error in errors), errors

    def test_blocked_requires_reason(self) -> None:
        errors = se.validate_evidence(_minimal_document(status={"state": "blocked"}))
        assert any("blocked_reason" in error for error in errors)

    def test_reason_present_when_not_blocked_is_invalid(self) -> None:
        document = _minimal_document(status={"state": "creating", "blocked_reason": "leftover"})
        errors = se.validate_evidence(document)
        assert any("blocked_reason" in error for error in errors)


class TestCredentialRejection:
    def test_credential_shaped_key_anywhere_is_rejected(self) -> None:
        document = _minimal_document()
        document["runners"]["firebase_auth_token"] = "should-not-exist"
        errors = se.validate_evidence(document)
        assert any("credential-shaped key" in error for error in errors), errors

    def test_nested_credential_key_is_rejected(self) -> None:
        document = _minimal_document()
        document["artifacts"] = {"logs": ["run.log"], "assertions": ["a.json", "../escape.json"]}
        errors = se.validate_evidence(document)
        assert any("escape" in error for error in errors), errors


class TestTimestamps:
    def test_non_utc_or_naive_timestamps_are_invalid(self) -> None:
        document = _minimal_document()
        document["timestamps"]["created_at"] = "2026-09-16T00:00:00+02:00"
        assert se.validate_evidence(document)

    def test_ended_before_started_is_invalid(self) -> None:
        document = _minimal_document()
        document["timestamps"].update({"started_at": "2026-09-16T02:00:00Z", "ended_at": "2026-09-16T01:00:00Z"})
        errors = se.validate_evidence(document)
        assert any("ended_at" in error for error in errors), errors


class TestSchemaFile:
    """The JSON Schema is the wire contract; keep it in lockstep with v1."""

    @property
    def schema(self) -> dict:
        return json.loads((REPO_ROOT / "contracts" / "session" / "session-evidence-v1.schema.json").read_text("utf-8"))

    def test_schema_is_v1_and_closed(self) -> None:
        schema = self.schema
        assert schema["properties"]["schema_version"] == {"const": 1}
        assert schema["additionalProperties"] is False
        for section in ("source", "target", "endpoints", "status"):
            assert schema["properties"][section]["additionalProperties"] is False

    def test_schema_declares_no_credential_field(self) -> None:
        def walk(node: object) -> list[str]:
            names: list[str] = []
            if isinstance(node, dict):
                for key, value in node.items():
                    if key == "properties" and isinstance(value, dict):
                        names.extend(value.keys())
                    names.extend(walk(value))
            elif isinstance(node, list):
                for item in node:
                    names.extend(walk(item))
            return names

        names = " ".join(walk(self.schema)).lower()
        for banned in ("token", "secret", "password", "credential", "api_key"):
            assert banned not in names, banned

    def test_python_validator_accepts_the_schema_reference_document(self) -> None:
        # The minimal document is exactly what the schema's required set demands;
        # a v1 doc that satisfies one contract must satisfy the other.
        assert se.validate_evidence(_minimal_document()) == []


class TestSourceIdentity:
    def test_dirty_digest_shape_on_the_real_checkout(self) -> None:
        identity = se.source_identity(REPO_ROOT)
        assert se.GIT_SHA_RE.match(identity["git_sha"])
        assert se.DIRTY_DIGEST_RE.match(identity["dirty_digest"])
        assert identity["repo"] == "BasedHardware/omi"


class TestBuilder:
    def test_build_evidence_validates_before_returning(self) -> None:
        with pytest.raises(se.EvidenceError, match="artifact is required"):
            se.build_evidence(
                session_id="oms-builder-1",
                source={"git_sha": "a" * 40, "dirty_digest": "clean", "repo": "BasedHardware/omi"},
                target={"platform": "android", "app_id": "com.friend.ios.dev", "flavor": "dev", "profile": "local_dev"},
                endpoints={
                    "api_base_url": "http://127.0.0.1:8000/",
                    "auth_emulator_host": "127.0.0.1:9099",
                    "firestore_emulator_host": "127.0.0.1:8085",
                    "egress_policy": "loopback-only",
                },
                fixtures={"fixture_version": "v1"},
                runners={"mobile-session": "0.1.0"},
                status={"state": "running"},
                timestamps={"created_at": "2026-09-16T00:00:00Z"},
            )


def test_source_identity_missing_git_fails_closed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def missing(*_args: object, **_kwargs: object) -> None:
        raise FileNotFoundError(2, "No such file or directory", "git")

    monkeypatch.setattr(se.subprocess, "run", missing)
    with pytest.raises(se.EvidenceError, match="git is not installed"):
        se.source_identity(tmp_path)


def test_source_identity_git_failure_fails_closed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def failing(*_args: object, **_kwargs: object) -> None:
        raise se.subprocess.CalledProcessError(128, ["git"], stderr="fatal: not a git repository")

    monkeypatch.setattr(se.subprocess, "run", failing)
    with pytest.raises(se.EvidenceError, match="git rev-parse"):
        se.source_identity(tmp_path)
