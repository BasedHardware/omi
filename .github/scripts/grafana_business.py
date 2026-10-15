"""Idempotent Business-folder capability setup; scoped to the Business org."""

import json
import urllib.error
import urllib.request
from urllib.parse import urlencode


class Grafana:
    def __init__(self, base, token):
        self.base, self.token = base.rstrip("/"), token

    def call(self, method, path, body=None, *, timeout=30):
        request = urllib.request.Request(
            self.base + path,
            data=None if body is None else json.dumps(body).encode(),
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
            method=method,
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)

    def optional(self, path):
        try:
            return self.call("GET", path)
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
            exc.close()
            return None


def permission_set(items):
    return {
        (item.get("role") or "", item.get("teamId", 0), item.get("userId", 0), item["permission"])
        for item in items
    }


def ensure_business(grafana):
    org = grafana.call("GET", "/api/org")
    if org.get("name") != "Omi Business":
        raise ValueError("Business provisioning requires a token scoped to Omi Business")
    result = grafana.call("GET", "/api/teams/search?" + urlencode({"name": "business-viewers", "perpage": 1000}))
    teams = [team for team in result["teams"] if team["name"] == "business-viewers"]
    if len(teams) > 1:
        raise ValueError("duplicate business-viewers team")
    team_id = teams[0]["id"] if teams else grafana.call("POST", "/api/teams", {"name": "business-viewers"})["teamId"]
    folder = grafana.optional("/api/folders/business")
    if folder is None:
        grafana.call("POST", "/api/folders", {"uid": "business", "title": "Business"})
    elif folder.get("title") != "Business" or folder.get("parentUid"):
        raise ValueError("Business folder has unexpected title or parent")
    desired = [{"role": "Admin", "permission": 4}, {"teamId": team_id, "permission": 1}]
    path = "/api/folders/business/permissions"
    if permission_set(grafana.call("GET", path)) != permission_set(desired):
        grafana.call("POST", path, {"items": desired})
    if permission_set(grafana.call("GET", path)) != permission_set(desired):
        raise ValueError("Business folder permissions read-back mismatch")
    return org["id"], team_id


def secure_business_dashboard(grafana, uid):
    path = f"/api/dashboards/uid/{uid}/permissions"
    # Folder inheritance is the only access path. Remove any old explicit
    # Viewer/Editor/user grants left by an earlier manual board import.
    if any(not item.get("isInherited") for item in grafana.call("GET", path)):
        grafana.call("POST", path, {"items": []})
    if any(not item.get("isInherited") for item in grafana.call("GET", path)):
        raise ValueError("Business dashboard retains explicit permissions")
    served = grafana.call("GET", f"/api/dashboards/uid/{uid}")
    if served["meta"].get("folderUid") != "business":
        raise ValueError("Business dashboard was served outside the Business folder")
