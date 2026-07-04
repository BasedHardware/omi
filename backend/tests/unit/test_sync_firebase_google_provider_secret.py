from scripts.sync_firebase_google_provider_secret import (
    build_provider_patch,
    parse_args,
    provider_resource_name,
    provider_url,
    redact_value,
)


def test_redact_value_keeps_prefix_and_suffix_only():
    redacted = redact_value("208440318997-secret-value.apps.googleusercontent.com")

    assert redacted.startswith("20844031...")
    assert redacted.endswith("tent.com")
    assert "secret-value" not in redacted


def test_build_provider_patch_includes_secret_without_logging_contract_fields():
    patch = build_provider_patch("based-hardware", "google.com", "client-id", "client-secret")

    assert patch == {
        "name": "projects/based-hardware/defaultSupportedIdpConfigs/google.com",
        "enabled": True,
        "clientId": "client-id",
        "clientSecret": "client-secret",
    }


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
