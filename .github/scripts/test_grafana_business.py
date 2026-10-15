import unittest
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


if __name__ == "__main__":
    unittest.main()
