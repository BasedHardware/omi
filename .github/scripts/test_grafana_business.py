import unittest
import importlib.util
import json
from pathlib import Path
import tempfile
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from grafana_business import ensure_business, permission_set, secure_business_dashboard


class FakeGrafana:
    def __init__(self):
        self.org = {"id": 2, "name": "Omi Business"}
        self.folder = None
        self.teams = []
        self.permissions = [{"role": "Viewer", "permission": 1}]
        self.dashboard_permissions = [{"role": "Editor", "permission": 2}]
        self.writes = []

    def optional(self, path):
        return self.folder

    def call(self, method, path, body=None):
        if method == "POST":
            self.writes.append((path, body))
            if path == "/api/teams":
                self.teams = [{"name": "business-viewers", "id": 9}]
                return {"teamId": 9}
            if path == "/api/folders":
                self.folder = {"title": "Business"}
            if path == "/api/folders/business/permissions":
                self.permissions = body["items"]
            if path == "/api/dashboards/uid/omi-tv-v2/permissions":
                self.dashboard_permissions = [{"isInherited": True, "role": "Admin", "permission": 4}]
            return {}
        if path == "/api/org":
            return self.org
        if path.startswith("/api/teams/search?"):
            return {"teams": self.teams}
        if path == "/api/folders/business/permissions":
            return self.permissions
        if path == "/api/dashboards/uid/omi-tv-v2/permissions":
            return self.dashboard_permissions
        if path == "/api/dashboards/uid/omi-tv-v2":
            return {"meta": {"folderUid": "business"}}
        raise AssertionError(path)


class BusinessTest(unittest.TestCase):
    def test_idempotent_and_removes_org_role_grants(self):
        fake = FakeGrafana()
        self.assertEqual(ensure_business(fake), (2, 9))
        self.assertEqual(permission_set(fake.permissions), {("Admin", 0, 0, 4), ("", 9, 0, 1)})
        writes = list(fake.writes)
        ensure_business(fake)
        self.assertEqual(fake.writes, writes)
        secure_business_dashboard(fake, "omi-tv-v2")
        self.assertTrue(all(item["isInherited"] for item in fake.dashboard_permissions))

    def test_monitoring_token_fails_before_any_write(self):
        fake = FakeGrafana()
        fake.org = {"id": 1, "name": "Main Org."}
        with self.assertRaises(ValueError):
            ensure_business(fake)
        self.assertEqual(fake.writes, [])


class BootstrapTest(unittest.TestCase):
    def test_both_accounts_get_org_unique_tokens_and_private_receipts(self):
        script = Path(__file__).resolve().parents[2] / "backend/charts/monitoring/grafana/bootstrap_business.py"
        spec = importlib.util.spec_from_file_location("bootstrap_business", script)
        bootstrap = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bootstrap)

        class FakeBootstrap(FakeGrafana):
            def __init__(self, *_args):
                super().__init__()
                self.accounts, self.tokens = {}, {}
                self.org_id = None

            def optional(self, path):
                return self.org if path.startswith("/api/orgs/name/") else super().optional(path)

            def call(self, method, path, body=None):
                if path.startswith("/api/serviceaccounts/search?"):
                    name = parse_qs(urlsplit(path).query)["query"][0]
                    return {"serviceAccounts": [self.accounts[name]] if name in self.accounts else []}
                if method == "POST" and path == "/api/serviceaccounts":
                    account = {**body, "id": len(self.accounts) + 10}
                    self.accounts[body["name"]] = account
                    return account
                if path.startswith("/api/serviceaccounts/") and path.endswith("/tokens"):
                    if method == "GET":
                        return self.tokens.get(path, [])
                    # Grafana's API key store enforces names across the org,
                    # including tokens belonging to different service accounts.
                    if any(token["name"] == body["name"] for tokens in self.tokens.values() for token in tokens):
                        raise ValueError("duplicate token name in organization")
                    self.tokens.setdefault(path, []).append(body)
                    return {"key": "synthetic-key"}
                return super().call(method, path, body)

        client = FakeBootstrap()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            argv = [str(script), "--output-dir", directory, "--token-name", "rotation-01"]
            with patch.object(bootstrap, "Bootstrap", return_value=client), patch("sys.argv", argv), patch.dict(
                "os.environ", {"GRAFANA_ADMIN_USER": "fixture", "GRAFANA_ADMIN_PASSWORD": "fixture"}
            ):
                bootstrap.main()
                names = {token["name"] for tokens in client.tokens.values() for token in tokens}
                self.assertEqual(names, {"omi-admin-business-enrollment:rotation-01", "gha-business-provisioning:rotation-01"})
                for filename in ["runtime.json", "ci.json", "runtime-configmap.json"]:
                    self.assertEqual((output / filename).stat().st_mode & 0o777, 0o600)
                    self.assertTrue(json.loads((output / filename).read_text()))
                with self.assertRaisesRegex(ValueError, "Token receipt already exists"):
                    bootstrap.main()


if __name__ == "__main__":
    unittest.main()
