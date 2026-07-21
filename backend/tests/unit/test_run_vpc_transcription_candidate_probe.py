import importlib.util
import sys
from pathlib import Path

import pytest


def _load():
    scripts = Path(__file__).resolve().parents[2] / "scripts"
    sys.path.insert(0, str(scripts))
    spec = importlib.util.spec_from_file_location(
        "vpc_candidate_probe", scripts / "run_vpc_transcription_candidate_probe.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_requests_tagged_url_but_mints_identity_for_canonical_service(monkeypatch):
    module = _load()
    candidate = "https://candidate---backend-abc-uc.a.run.app"
    audience = "https://backend-abc-uc.a.run.app"
    monkeypatch.setenv("CANDIDATE_API_URL", candidate)
    monkeypatch.setenv("CLOUD_RUN_IDENTITY_AUDIENCE", audience)
    monkeypatch.setenv("FIREBASE_PROBE_TOKEN", "firebase-token")
    seen = {}

    def identity_token(value):
        seen["audience"] = value
        return "identity-token"

    def build_report(config):
        seen["request_url"] = config.api_url
        return {"status": "PASS"}

    monkeypatch.setattr(module, "_identity_token", identity_token)
    monkeypatch.setattr(module, "build_report", build_report)

    assert module.main() == 0
    assert seen == {"audience": audience, "request_url": candidate}


@pytest.mark.parametrize(
    "name,value", [("CANDIDATE_API_URL", "http://candidate.invalid"), ("CLOUD_RUN_IDENTITY_AUDIENCE", "")]
)
def test_fails_closed_for_missing_or_invalid_request_or_identity_url(monkeypatch, name, value):
    module = _load()
    monkeypatch.setenv("CANDIDATE_API_URL", "https://candidate.invalid")
    monkeypatch.setenv("CLOUD_RUN_IDENTITY_AUDIENCE", "https://backend.invalid")
    monkeypatch.setenv("FIREBASE_PROBE_TOKEN", "firebase-token")
    monkeypatch.setenv(name, value)
    with pytest.raises(RuntimeError):
        module.main()
