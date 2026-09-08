#!/usr/bin/env python3
"""Sync Firebase Auth's Google provider secret from Secret Manager.

Firebase Auth stores a separate copy of the Google OAuth client secret used by
the hosted `__/auth/handler` flow. Rotating GOOGLE_CLIENT_SECRET in Secret
Manager is not enough; this script patches the Firebase provider copy too.
"""

import argparse
import json
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Optional, Sequence

IDENTITY_TOOLKIT_BASE_URL = "https://identitytoolkit.googleapis.com/admin/v2"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
DEFAULT_PROVIDER_ID = "google.com"
DEFAULT_CLIENT_ID_SECRET = "GOOGLE_CLIENT_ID"
DEFAULT_CLIENT_SECRET_SECRET = "GOOGLE_CLIENT_SECRET"
SENSITIVE_ERROR_RE = re.compile(
    r"(?i)(client[_-]?secret|secret|access[_-]?token|refresh[_-]?token|id[_-]?token)(['\"\s:=]+)([^,\s}\"']+)"
)


@dataclass(frozen=True)
class SyncConfig:
    project: str
    quota_project: str
    provider_id: str
    client_id_secret: str
    client_secret_secret: str
    apply: bool
    validate_google_secret: bool
    auth_domain: Optional[str]


def redact_value(value: str, *, visible_prefix: int = 8, visible_suffix: int = 8) -> str:
    if not value:
        return ""
    if len(value) <= visible_prefix + visible_suffix:
        return "***"
    return f"{value[:visible_prefix]}...{value[-visible_suffix:]}"


def provider_url(project: str, provider_id: str) -> str:
    quoted_provider = urllib.parse.quote(provider_id, safe="")
    return f"{IDENTITY_TOOLKIT_BASE_URL}/projects/{project}/defaultSupportedIdpConfigs/{quoted_provider}"


def provider_resource_name(project: str, provider_id: str) -> str:
    return f"projects/{project}/defaultSupportedIdpConfigs/{provider_id}"


def build_provider_patch(project: str, provider_id: str, client_id: str, client_secret: str) -> dict[str, Any]:
    return {
        "name": provider_resource_name(project, provider_id),
        "clientId": client_id,
        "clientSecret": client_secret,
    }


def project_config_url(project: str) -> str:
    return f"{IDENTITY_TOOLKIT_BASE_URL}/projects/{project}/config"


def safe_http_error_message(error_body: str) -> str:
    try:
        payload = json.loads(error_body)
    except json.JSONDecodeError:
        return "<unparseable>"

    error = payload.get("error")
    if isinstance(error, dict):
        message = str(error.get("message") or error.get("status") or "<no message>")
    elif error:
        message = str(error)
    else:
        message = "<no message>"

    redacted = SENSITIVE_ERROR_RE.sub(r"\1\2***", message)
    return redacted[:300]


def firebase_auth_redirect_uri(project: str, project_config: dict[str, Any], auth_domain: Optional[str] = None) -> str:
    if auth_domain:
        domain = auth_domain.removeprefix("https://").removeprefix("http://").rstrip("/")
    else:
        client = project_config.get("client") if isinstance(project_config.get("client"), dict) else {}
        subdomain = str(client.get("firebaseSubdomain") or project).strip()
        domain = f"{subdomain}.firebaseapp.com"
    return f"https://{domain}/__/auth/handler"


def run_command(args: Sequence[str]) -> str:
    completed = subprocess.run(args, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return completed.stdout.strip()


def access_secret(project: str, secret_name: str) -> str:
    return run_command(
        [
            "gcloud",
            "secrets",
            "versions",
            "access",
            "latest",
            f"--secret={secret_name}",
            f"--project={project}",
        ]
    )


def access_token() -> str:
    try:
        return run_command(["gcloud", "auth", "application-default", "print-access-token"])
    except subprocess.CalledProcessError:
        return run_command(["gcloud", "auth", "print-access-token"])


def identity_toolkit_request(
    method: str,
    url: str,
    token: str,
    quota_project: str,
    body: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    data = None
    headers = {
        "Authorization": f"Bearer {token}",
        "x-goog-user-project": quota_project,
    }
    if body is not None:
        data = json.dumps(body, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        error_body = error.read().decode("utf-8", errors="replace")
        safe_message = safe_http_error_message(error_body)
        raise RuntimeError(f"Identity Toolkit {method} failed status={error.code} message={safe_message}") from error


def validate_google_secret(client_id: str, client_secret: str, redirect_uri: str) -> None:
    body = urllib.parse.urlencode(
        {
            "code": "bogus-code-for-secret-validation",
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
    ).encode("utf-8")
    request = urllib.request.Request(GOOGLE_TOKEN_URL, data=body, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=30):
            raise RuntimeError("Unexpected Google token success with bogus code")
    except urllib.error.HTTPError as error:
        payload = json.loads(error.read().decode("utf-8"))
    if payload.get("error") == "invalid_client":
        raise RuntimeError("GOOGLE_CLIENT_SECRET is invalid for GOOGLE_CLIENT_ID")
    if payload.get("error") != "invalid_grant":
        raise RuntimeError(f"Unexpected Google token response: {payload.get('error')}")


def sync(config: SyncConfig) -> int:
    client_id = access_secret(config.project, config.client_id_secret)
    client_secret = access_secret(config.project, config.client_secret_secret)
    if not client_id or not client_secret:
        raise RuntimeError("Client ID and client secret must both be non-empty")

    token = access_token()
    project_config = identity_toolkit_request("GET", project_config_url(config.project), token, config.quota_project)
    redirect_uri = firebase_auth_redirect_uri(config.project, project_config, config.auth_domain)
    if config.validate_google_secret:
        validate_google_secret(client_id, client_secret, redirect_uri)
        print("google_secret=valid")
        print(f"google_redirect_uri={redirect_uri}")

    url = provider_url(config.project, config.provider_id)
    provider = identity_toolkit_request("GET", url, token, config.quota_project)
    existing_client_id = provider.get("clientId") or ""
    print(f"provider={config.provider_id}")
    print(f"project={config.project}")
    print(f"provider_enabled={provider.get('enabled') is True}")
    print(f"provider_client_id={redact_value(existing_client_id)}")
    print(f"secret_client_id={redact_value(client_id)}")

    if existing_client_id and existing_client_id != client_id:
        raise RuntimeError(
            f"Firebase provider client ID differs from {config.client_id_secret}; "
            "fix the client ID before syncing the secret"
        )

    if not config.apply:
        print("status=dry_run")
        print("client_secret_readback=unavailable")
        print("next=rerun with --apply after rotating GOOGLE_CLIENT_SECRET")
        return 0

    patch = build_provider_patch(config.project, config.provider_id, client_id, client_secret)
    patched = identity_toolkit_request(
        "PATCH",
        f"{url}?updateMask=clientSecret,clientId",
        token,
        config.quota_project,
        body=patch,
    )
    print("status=applied")
    print(f"patched_enabled={patched.get('enabled') is True}")
    print(f"patched_client_id={redact_value(patched.get('clientId') or '')}")
    return 0


def parse_args(argv: Optional[Sequence[str]] = None) -> SyncConfig:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default="based-hardware", help="GCP/Firebase project ID")
    parser.add_argument("--quota-project", help="Quota project for Identity Toolkit Admin API")
    parser.add_argument("--provider-id", default=DEFAULT_PROVIDER_ID)
    parser.add_argument("--client-id-secret", default=DEFAULT_CLIENT_ID_SECRET)
    parser.add_argument("--client-secret-secret", default=DEFAULT_CLIENT_SECRET_SECRET)
    parser.add_argument(
        "--auth-domain",
        help="Firebase Auth domain for Google token validation. Defaults to the project's Firebase subdomain.",
    )
    parser.add_argument("--apply", action="store_true", help="Patch Firebase Auth provider. Default is dry-run.")
    parser.add_argument(
        "--skip-google-secret-validation",
        action="store_true",
        help="Skip token-endpoint validation of the Secret Manager client secret.",
    )
    args = parser.parse_args(argv)
    quota_project = args.quota_project or args.project
    return SyncConfig(
        project=args.project,
        quota_project=quota_project,
        provider_id=args.provider_id,
        client_id_secret=args.client_id_secret,
        client_secret_secret=args.client_secret_secret,
        apply=args.apply,
        validate_google_secret=not args.skip_google_secret_validation,
        auth_domain=args.auth_domain,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    try:
        return sync(parse_args(argv))
    except Exception as error:
        print(f"error={error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
