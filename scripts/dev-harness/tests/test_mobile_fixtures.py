from __future__ import annotations

import json
import sys
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dev_harness import mobile_fixtures as mf
from dev_harness.session_evidence import EvidenceError


class TestFixtureLoading:
    def test_v1_fixture_loads_deterministically(self) -> None:
        fixture = mf.load_fixture("v1")
        assert fixture.version == "v1"
        user = fixture.default_user
        assert user.uid == "omi-fixture-v1-user-1"
        assert user.email.endswith("@local.test")
        # Deterministic: same file, same identity, every load.
        assert mf.load_fixture("v1").default_user == user

    def test_unknown_version_names_available_fixtures(self) -> None:
        with pytest.raises(mf.FixtureError, match="available: \\['v1'\\]"):
            mf.load_fixture("v99")

    def test_fixture_declaring_the_wrong_version_is_rejected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        directory = tmp_path / "fixtures"
        directory.mkdir()
        (directory / "v2.json").write_text(json.dumps({"fixture_version": "v3", "auth": {"users": []}}), "utf-8")
        monkeypatch.setattr(mf, "FIXTURES_DIR", directory)
        with pytest.raises(mf.FixtureError, match="declares version 'v3'"):
            mf.load_fixture("v2")

    def test_non_reserved_domain_email_is_rejected(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        directory = tmp_path / "fixtures"
        directory.mkdir()
        (directory / "v5.json").write_text(
            json.dumps(
                {
                    "fixture_version": "v5",
                    "auth": {"users": [{"uid": "real-ish", "email": "someone@gmail.com"}]},
                }
            ),
            "utf-8",
        )
        monkeypatch.setattr(mf, "FIXTURES_DIR", directory)
        with pytest.raises(mf.FixtureError, match="@local.test"):
            mf.load_fixture("v5")


class TestEgressFailClosed:
    @pytest.mark.parametrize(
        "base_url",
        ["https://api.omi.me/", "https://api.omiapi.com/", "http://api.omi.me/", "https://10.0.2.2:8000/"],
    )
    def test_off_loopback_backends_are_refused_before_any_request(self, base_url: str) -> None:
        def _must_not_request(url: str, form: dict) -> dict:
            raise AssertionError(f"request escaped to {url}")

        with pytest.raises((mf.FixtureError, Exception)) as excinfo:
            mf.seed_synthetic_user(base_url, mf.load_fixture("v1"), post=_must_not_request)
        message = str(excinfo.value)
        assert "loopback" in message or "production host" in message or "plain http" in message

    def test_production_host_is_named_explicitly(self) -> None:
        with pytest.raises(Exception, match="production host 'api.omi.me'"):
            mf.backend_endpoint("https://api.omi.me/")

    def test_https_loopback_is_refused(self) -> None:
        with pytest.raises(Exception, match="plain http"):
            mf.backend_endpoint("https://127.0.0.1:8000/")


def _ok_post(url: str, form: dict) -> dict:
    assert url == "http://127.0.0.1:8300/v1/auth/local-dev/custom-token"
    assert form["uid"] == "omi-fixture-v1-user-1"
    return {"custom_token": "minted-token-value", "uid": form["uid"], "provider": "local_dev"}


class TestSeeding:

    def test_happy_path_receipt_never_contains_the_token(self) -> None:
        receipt = mf.seed_synthetic_user("http://127.0.0.1:8300/", mf.load_fixture("v1"), post=_ok_post)
        serialized = json.dumps(receipt)
        assert "minted-token-value" not in serialized
        assert receipt["token_minted"] is True
        assert receipt["token_retained"] is False
        assert receipt["fixture_version"] == "v1"
        assert receipt["uid"] == "omi-fixture-v1-user-1"

    def test_404_explains_the_emulator_gate(self) -> None:
        def _not_found(url: str, form: dict) -> dict:
            raise urllib.error.HTTPError(url, 404, "Not Found", None, None)  # type: ignore[arg-type]

        with pytest.raises(mf.FixtureError, match="Firebase Auth emulator"):
            mf.seed_synthetic_user("http://127.0.0.1:8300/", mf.load_fixture("v1"), post=_not_found)

    def test_unreachable_backend_fails_closed_with_reason(self) -> None:
        def _down(url: str, form: dict) -> dict:
            raise urllib.error.URLError("connection refused")

        with pytest.raises(mf.FixtureError, match="unreachable"):
            mf.seed_synthetic_user("http://127.0.0.1:8300/", mf.load_fixture("v1"), post=_down)

    def test_token_for_the_wrong_uid_is_rejected(self) -> None:
        def _wrong_uid(url: str, form: dict) -> dict:
            return {"custom_token": "tok", "uid": "someone-else"}

        with pytest.raises(mf.FixtureError, match="someone-else"):
            mf.seed_synthetic_user("http://127.0.0.1:8300/", mf.load_fixture("v1"), post=_wrong_uid)

    def test_missing_token_in_response_is_rejected(self) -> None:
        with pytest.raises(mf.FixtureError, match="no custom_token"):
            mf.seed_synthetic_user("http://127.0.0.1:8300/", mf.load_fixture("v1"), post=lambda url, form: {})


class TestSeedReceipts:
    def test_receipt_with_credential_key_is_refused(self, tmp_path: Path) -> None:
        receipt = mf.seed_synthetic_user("http://127.0.0.1:8300/", mf.load_fixture("v1"), post=_ok_post)
        receipt["custom_token"] = "minted-token-value"
        with pytest.raises(EvidenceError, match="credential-free"):
            mf.write_seed_receipt(tmp_path / "seed.json", receipt)

    def test_clean_receipt_roundtrips(self, tmp_path: Path) -> None:
        receipt = mf.seed_synthetic_user("http://127.0.0.1:8300/", mf.load_fixture("v1"), post=_ok_post)
        path = mf.write_seed_receipt(tmp_path / "seed.json", receipt)
        assert mf.read_seed_receipt(path)["uid"] == receipt["uid"]
