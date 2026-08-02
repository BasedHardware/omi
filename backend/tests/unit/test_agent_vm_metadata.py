import pytest

from utils.agent_vm_metadata import backend_url_metadata, validate_agent_vm_backend_url


def test_backend_url_metadata_replaces_only_backend_url():
    instance = {
        "metadata": {
            "fingerprint": "fingerprint",
            "items": [
                {"key": "auth-token", "value": "redacted-token"},
                {"key": "backend-url", "value": "https://api.omi.me"},
                {"key": "startup-script", "value": "script"},
            ],
        }
    }

    update = backend_url_metadata(instance, "https://api.omiapi.com")

    assert update == {
        "fingerprint": "fingerprint",
        "items": [
            {"key": "auth-token", "value": "redacted-token"},
            {"key": "startup-script", "value": "script"},
            {"key": "backend-url", "value": "https://api.omiapi.com"},
        ],
    }


def test_backend_url_metadata_is_idempotent():
    instance = {
        "metadata": {
            "fingerprint": "fingerprint",
            "items": [{"key": "backend-url", "value": "https://api.omi.me"}],
        }
    }

    assert backend_url_metadata(instance, "https://api.omi.me") is None


def test_backend_url_validation_rejects_untrusted_origin():
    with pytest.raises(RuntimeError, match="not an allowed backend"):
        validate_agent_vm_backend_url("https://attacker.example")
