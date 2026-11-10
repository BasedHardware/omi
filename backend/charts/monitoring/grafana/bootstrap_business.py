#!/usr/bin/env python3
"""Parent-only Grafana bootstrap. Writes credentials to private files, never stdout.

Requires Grafana SERVER admin Basic credentials for organization creation; neither
CI nor the admin runtime receives them. Reuses existing org/team/service accounts.
Existing token names fail closed: rotate explicitly instead of minting duplicates.
"""

import argparse
import base64
import json
import os
from pathlib import Path
import sys
from urllib.parse import quote
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / ".github/scripts"))
from grafana_business import Grafana, ensure_business  # noqa: E402


class Bootstrap(Grafana):
    def __init__(self, base, username, password):
        self.base = base.rstrip("/")
        self.basic = base64.b64encode(f"{username}:{password}".encode()).decode()
        self.org_id = None

    def call(self, method, path, body=None, *, timeout=30):
        headers = {"Authorization": f"Basic {self.basic}", "Content-Type": "application/json"}
        if self.org_id:
            headers["X-Grafana-Org-Id"] = str(self.org_id)
        request = urllib.request.Request(
            self.base + path,
            headers=headers,
            method=method,
            data=None if body is None else json.dumps(body).encode(),
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)


def write_private(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as output:
        json.dump(value, output)
        output.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grafana-url", default="https://monitor.omi.me")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--token-name", required=True, help="Unique rotation receipt, e.g. 2026-10-15")
    args = parser.parse_args()
    os.umask(0o077)
    args.output_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    client = Bootstrap(args.grafana_url, os.environ["GRAFANA_ADMIN_USER"], os.environ["GRAFANA_ADMIN_PASSWORD"])
    org = client.optional("/api/orgs/name/" + quote("Omi Business", safe=""))
    client.org_id = org["id"] if org else client.call("POST", "/api/orgs", {"name": "Omi Business"})["orgId"]
    if client.org_id <= 1:
        raise ValueError("Refusing the monitoring organization")
    org_id, team_id = ensure_business(client)
    for name, filename in [("omi-admin-business-enrollment", "runtime.json"), ("gha-business-provisioning", "ci.json")]:
        accounts = client.call("GET", "/api/serviceaccounts/search?perpage=1000&query=" + quote(name))[
            "serviceAccounts"
        ]
        matches = [account for account in accounts if account["name"] == name]
        if len(matches) > 1:
            raise ValueError("Duplicate service account")
        account = (
            matches[0] if matches else client.call("POST", "/api/serviceaccounts", {"name": name, "role": "Admin"})
        )
        if account["role"] != "Admin":
            raise ValueError("Unexpected service account role")
        token_name = f"{name}:{args.token_name}"
        tokens_path = f'/api/serviceaccounts/{account["id"]}/tokens'
        if any(token["name"] == token_name for token in client.call("GET", tokens_path)):
            raise ValueError("Token receipt already exists; recover the saved output or choose an explicit rotation")
        if (args.output_dir / filename).exists():
            raise ValueError("Credential output already exists")
        token = client.call("POST", tokens_path, {"name": token_name, "secondsToLive": 7776000})["key"]
        write_private(args.output_dir / filename, {"token": token, "orgId": org_id, "teamId": team_id})
    write_private(
        args.output_dir / "runtime-configmap.json",
        {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": "grafana-business-runtime", "namespace": "prod-omi-monitoring"},
            "data": {"OMI_GRAFANA_BUSINESS_ORG_ID": str(org_id)},
        },
    )
    print(f"Business org={org_id}, team={team_id}; private credential files written; tokens expire in 90 days")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print(
            "Business bootstrap failed; no credentials printed. Inspect prerequisite permissions/output receipts.",
            file=sys.stderr,
        )
        raise SystemExit(1)
