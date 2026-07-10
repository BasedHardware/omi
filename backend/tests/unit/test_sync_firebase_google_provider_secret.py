import subprocess
import sys
from pathlib import Path

from scripts.sync_firebase_google_provider_secret import (
    build_provider_patch,
    firebase_auth_redirect_uri,
    parse_args,
    provider_resource_name,
    provider_url,
    redact_value,
    safe_http_error_message,
)

BACKEND_DIR = Path(__file__).resolve().parents[2]
SCRIPT_PATH = BACKEND_DIR / "scripts" / "sync_firebase_google_provider_secret.py"
TEST_SH_PATH = BACKEND_DIR / "test.sh"


def test_redact_value_keeps_prefix_and_suffix_only():
    redacted = redact_value("208440318997-secret-value.apps.googleusercontent.com")

    assert redacted.startswith("20844031...")
    assert redacted.endswith("tent.com")
    assert "secret-value" not in redacted


def test_build_provider_patch_does_not_change_enabled_state():
    patch = build_provider_patch("based-hardware", "google.com", "client-id", "client-secret")

    assert patch == {
        "name": "projects/based-hardware/defaultSupportedIdpConfigs/google.com",
        "clientId": "client-id",
        "clientSecret": "client-secret",
    }
    assert "enabled" not in patch


def test_provider_helpers_encode_provider_for_url_but_not_resource_name():
    assert provider_resource_name("based-hardware", "google.com") == (
        "projects/based-hardware/defaultSupportedIdpConfigs/google.com"
    )
    assert provider_url("based-hardware", "google.com").endswith(
        "/projects/based-hardware/defaultSupportedIdpConfigs/google.com"
    )


def test_cli_defaults_to_dry_run_and_secret_validation():
    config = parse_args(["--project", "based-hardware"])

    assert config.project == "based-hardware"
    assert config.quota_project == "based-hardware"
    assert config.apply is False
    assert config.validate_google_secret is True
    assert config.client_id_secret == "GOOGLE_CLIENT_ID"
    assert config.client_secret_secret == "GOOGLE_CLIENT_SECRET"
    assert config.auth_domain is None


def test_cli_accepts_explicit_auth_domain_for_non_default_projects():
    config = parse_args(["--project", "staging-project", "--auth-domain", "auth.example.com"])

    assert config.project == "staging-project"
    assert config.auth_domain == "auth.example.com"


def test_firebase_auth_redirect_uri_uses_project_config_subdomain():
    redirect_uri = firebase_auth_redirect_uri(
        "fallback-project",
        {"client": {"firebaseSubdomain": "based-hardware"}},
    )

    assert redirect_uri == "https://based-hardware.firebaseapp.com/__/auth/handler"


def test_firebase_auth_redirect_uri_allows_explicit_auth_domain():
    redirect_uri = firebase_auth_redirect_uri(
        "fallback-project",
        {"client": {"firebaseSubdomain": "based-hardware"}},
        "https://auth.example.com/",
    )

    assert redirect_uri == "https://auth.example.com/__/auth/handler"


def test_safe_http_error_message_does_not_echo_secret_values():
    message = safe_http_error_message(
        '{"error":{"message":"bad client_secret=raw-secret-value and refresh_token:raw-token"}}'
    )

    assert "raw-secret-value" not in message
    assert "raw-token" not in message
    assert "client_secret=***" in message


def test_static_review_guards_cover_secret_sync_regressions():
    source = SCRIPT_PATH.read_text()

    assert "body={error_body}" not in source
    assert "failed status={error.code} body=" not in source
    assert "updateMask=clientSecret,clientId,enabled" not in source
    assert '"redirect_uri": "https://based-hardware.firebaseapp.com/__/auth/handler"' not in source


def test_secret_sync_tests_are_registered_in_backend_test_sh():
    test_sh = TEST_SH_PATH.read_text()
    selected_tests = subprocess.check_output(
        [sys.executable, str(BACKEND_DIR / "scripts" / "select_backend_unit_tests.py"), "--all"],
        text=True,
        cwd=BACKEND_DIR,
    ).splitlines()

    assert "scripts/select_backend_unit_tests.py --all" in test_sh
    assert "tests/unit/test_mcp_oauth_template.py" in selected_tests
    assert "tests/unit/test_sync_firebase_google_provider_secret.py" in selected_tests
