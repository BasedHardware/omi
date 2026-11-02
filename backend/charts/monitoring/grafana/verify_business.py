#!/usr/bin/env python3
"""Parent live acceptance: only status/counts printed, never payloads or tokens."""

import argparse
import json
import os
from pathlib import Path
import sys
import urllib.error

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / ".github/scripts"))
from grafana_business import Grafana, permission_set  # noqa: E402


def verify(base, business_token, viewer_token):
    client = Grafana(base, business_token)
    org = client.call("GET", "/api/org")
    assert org["name"] == "Omi Business"
    teams = client.call("GET", "/api/teams/search?name=business-viewers&perpage=1000")["teams"]
    team = next(team for team in teams if team["name"] == "business-viewers")
    permissions = permission_set(client.call("GET", "/api/folders/business/permissions"))
    assert permissions == {("Admin", 0, 0, 4), ("", team["id"], 0, 1)}
    board = client.call("GET", "/api/dashboards/uid/omi-tv-v2")
    assert board["meta"]["folderUid"] == "business"
    assert not any(
        not item.get("isInherited") for item in client.call("GET", "/api/dashboards/uid/omi-tv-v2/permissions")
    )
    datasource = client.call("GET", "/api/datasources/uid/omi-admin-api")
    assert datasource["url"] == "http://127.0.0.1:8899"
    assert datasource["type"] == "yesoreyeram-infinity-datasource"
    assert [item["uid"] for item in client.call("GET", "/api/datasources")] == ["omi-admin-api"]
    # The diagnostics query executes the real backend Infinity -> loopback ->
    # impersonated stats reader -> HTTPS wall route. No returned values logged.
    target = dict(board["dashboard"]["panels"][-1]["targets"][0])
    target.update({"intervalMs": 900000, "maxDataPoints": 100})
    query = client.call("POST", "/api/ds/query", {"from": "now-1h", "to": "now", "queries": [target]}, timeout=450)
    results = list(query["results"].values())
    assert results and all(
        not item.get("error") and item.get("status", 200) == 200 and item.get("frames") for item in results
    )
    print(
        "PASS Business ACL/datasource isolation/Infinity wall query; frames="
        + str(sum(len(item["frames"]) for item in results))
    )
    verify_viewer(Grafana(base, viewer_token), org["id"], client)


def verify_viewer(viewer, org_id, business_admin):
    user = viewer.call("GET", "/api/user")
    assert not user.get("isGrafanaAdmin") and user["orgId"] == org_id
    # Service-account tokens cannot call the human-only /api/user/orgs route.
    accounts = business_admin.call("GET", "/api/serviceaccounts/search?perpage=1000")["serviceAccounts"]
    matching = [account for account in accounts if account["login"] == user["login"]]
    assert len(matching) == 1 and matching[0]["orgId"] == org_id and matching[0]["role"] == "Viewer"
    for path in ("/api/folders/business", "/api/dashboards/uid/omi-tv-v2"):
        try:
            viewer.call("GET", path)
        except urllib.error.HTTPError as exc:
            assert exc.code in (403, 404)
            exc.close()
        else:
            raise ValueError("Unprivileged Viewer can read Business content")
    print("PASS unprivileged Viewer denied Business folder and board")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grafana-url", default="https://monitor.omi.me")
    args = parser.parse_args()
    verify(args.grafana_url, os.environ["BUSINESS_GRAFANA_TOKEN"], os.environ["GRAFANA_VIEWER_TOKEN"])


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("FAIL Business acceptance (details suppressed to protect credentials/payloads)", file=sys.stderr)
        raise SystemExit(1)
