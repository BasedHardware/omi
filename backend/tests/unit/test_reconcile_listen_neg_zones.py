"""Hermetic coverage for standalone listen NEG attachment reconciliation."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ops" / "reconcile_listen_neg_zones.py"
NEG_NAME = "prod-backend-listen-neg"
ZONES = ("us-central1-a", "us-central1-b", "us-central1-c", "us-central1-f")


FAKE_KUBECTL = r'''#!/usr/bin/env python3
import json
import os
declared = ["us-central1-a", "us-central1-b", "us-central1-c", "us-central1-f"]
if os.environ.get("FAKE_STATUS_OMITS_F"):
    declared = declared[:3]
print(json.dumps({
    "metadata": {
        "annotations": {
            "cloud.google.com/neg-status": json.dumps({
                "network_endpoint_groups": {"8080": "prod-backend-listen-neg"},
                "zones": declared,
            })
        }
    }
}))
'''


FAKE_GCLOUD = r'''#!/usr/bin/env python3
import json
import os
import sys

args = sys.argv[1:]
with open(os.environ["FAKE_GCLOUD_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps(args) + "\n")

if args[:3] == ["compute", "network-endpoint-groups", "list"]:
    owner = json.dumps({"cluster-uid": "uid-1", "namespace": "prod-omi-backend", "service-name": "prod-omi-backend-listen", "port": "8080"})
    foreign_owner = json.dumps({"cluster-uid": "uid-2", "namespace": "prod-omi-backend", "service-name": "prod-omi-backend-listen", "port": "8080"})
    listed = [
        {"name": "prod-backend-listen-neg", "description": owner, "zone": "https://www.googleapis.com/compute/v1/projects/based-hardware/zones/us-central1-a"},
        {"name": "prod-backend-listen-neg", "description": owner, "zone": "https://www.googleapis.com/compute/v1/projects/based-hardware/zones/us-central1-b"},
        {"name": "prod-backend-listen-neg", "description": owner, "zone": "https://www.googleapis.com/compute/v1/projects/based-hardware/zones/us-central1-c"},
        {"name": "prod-backend-listen-neg", "description": foreign_owner if os.environ.get("FAKE_F_FOREIGN_OWNER") else owner, "zone": "https://www.googleapis.com/compute/v1/projects/based-hardware/zones/us-central1-f"},
        {"name": "prod-backend-listen-neg-shadow", "zone": "https://www.googleapis.com/compute/v1/projects/based-hardware/zones/us-central1-x"},
    ]
    if os.environ.get("FAKE_FOREIGN_ZONE_NEG"):
        listed.append(
            {"name": "prod-backend-listen-neg", "zone": "https://www.googleapis.com/compute/v1/projects/based-hardware/zones/europe-west1-b"}
        )
    if os.environ.get("FAKE_GLOBAL_NEG"):
        listed.append({"name": "prod-backend-listen-neg", "region": "https://www.googleapis.com/compute/v1/projects/based-hardware/regions/us-central1"})
    missing_zone = os.environ.get("FAKE_MISSING_ZONE")
    if missing_zone:
        listed = [item for item in listed if not item["zone"].endswith("/" + missing_zone)]
    print(json.dumps(listed))
elif args[:3] == ["compute", "backend-services", "describe"]:
    attached_zones = ["us-central1-a", "us-central1-b"]
    if os.environ.get("FAKE_ALL_ATTACHED"):
        attached_zones = ["us-central1-a", "us-central1-b", "us-central1-c", "us-central1-f"]
    backends = [
        {
            "group": "https://www.googleapis.com/compute/v1/projects/based-hardware/zones/" + zone + "/networkEndpointGroups/prod-backend-listen-neg",
            "balancingMode": "IN_FLIGHT",
            "maxInFlightRequestsPerEndpoint": 15,
            "capacityScaler": 1.0,
            "trafficDuration": "LONG",
        }
        for zone in attached_zones
    ]
    if os.environ.get("FAKE_DISAGREE_TRAFFIC") and len(backends) > 1:
        backends[1]["trafficDuration"] = "SHORT"
    print(json.dumps({"backends": backends}))
elif args[:3] == ["compute", "backend-services", "add-backend"]:
    if os.environ.get("FAKE_ADD_MODE") == "permission-denied":
        print(
            "Required 'compute.networkEndpointGroups.use' permission for "
            "'projects/based-hardware/zones/us-central1-c/networkEndpointGroups/prod-backend-listen-neg' "
            "raw-resource-id",
            file=sys.stderr,
        )
        sys.exit(1)
    elif os.environ.get("FAKE_ADD_MODE") == "permission-denied-generic":
        print("PERMISSION_DENIED raw-resource-id", file=sys.stderr)
        sys.exit(1)
else:
    print("unexpected fake gcloud command", file=sys.stderr)
    sys.exit(2)
'''


class ReconcileListenNegZonesTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.bin_dir = Path(self.temp.name) / "bin"
        self.bin_dir.mkdir()
        self.log_path = Path(self.temp.name) / "gcloud.jsonl"
        self._write_executable(self.bin_dir / "kubectl", FAKE_KUBECTL)
        self._write_executable(self.bin_dir / "gcloud", FAKE_GCLOUD)

    @staticmethod
    def _write_executable(path, content):
        path.write_text(content, encoding="utf-8")
        path.chmod(0o755)

    def _run(
        self,
        *extra_args,
        add_mode=None,
        missing_zone=None,
        all_attached=False,
        disagree_traffic=False,
        foreign_zone_neg=False,
        global_neg=False,
        status_omits_f=False,
        f_foreign_owner=False,
    ):
        env = os.environ.copy()
        env["PATH"] = f"{self.bin_dir}{os.pathsep}{env.get('PATH', '')}"
        env["FAKE_GCLOUD_LOG"] = str(self.log_path)
        if add_mode:
            env["FAKE_ADD_MODE"] = add_mode
        if missing_zone:
            env["FAKE_MISSING_ZONE"] = missing_zone
        if all_attached:
            env["FAKE_ALL_ATTACHED"] = "1"
        if disagree_traffic:
            env["FAKE_DISAGREE_TRAFFIC"] = "1"
        if foreign_zone_neg:
            env["FAKE_FOREIGN_ZONE_NEG"] = "1"
        if global_neg:
            env["FAKE_GLOBAL_NEG"] = "1"
        if status_omits_f:
            env["FAKE_STATUS_OMITS_F"] = "1"
        if f_foreign_owner:
            env["FAKE_F_FOREIGN_OWNER"] = "1"
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--project",
                "based-hardware",
                "--namespace",
                "prod-omi-backend",
                "--service",
                "prod-omi-backend-listen",
                "--backend-service",
                "custom-domains-api-omi-me-backend-listen-49a4-be",
                *extra_args,
            ],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )

    def _gcloud_calls(self):
        return [json.loads(line) for line in self.log_path.read_text(encoding="utf-8").splitlines()]

    def test_dry_run_discovers_exact_name_and_never_attaches(self):
        result = self._run("--dry-run")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("NEG zones discovered (4): " + ", ".join(ZONES), result.stdout)
        self.assertIn("NEG zones already attached (2): us-central1-a, us-central1-b", result.stdout)
        self.assertIn("NEG zones missing (2): us-central1-c, us-central1-f", result.stdout)
        self.assertIn("dry-run: would attach 2 zone(s)", result.stdout)
        self.assertNotIn(NEG_NAME, result.stdout)
        self.assertNotIn("custom-domains-api-omi-me-backend-listen-49a4-be", result.stdout)

        calls = self._gcloud_calls()
        self.assertEqual(len(calls), 2)
        self.assertIn("--filter=name=prod-backend-listen-neg", calls[0])
        self.assertTrue(all("add-backend" not in call for call in calls))

    def test_adds_only_missing_zones_with_live_balancing_settings(self):
        result = self._run()

        self.assertEqual(result.returncode, 0, result.stderr)
        add_calls = [call for call in self._gcloud_calls() if "add-backend" in call]
        self.assertEqual(len(add_calls), 2)
        for zone, call in zip(("us-central1-c", "us-central1-f"), add_calls):
            self.assertIn(f"--network-endpoint-group-zone={zone}", call)
            self.assertIn("--balancing-mode=IN_FLIGHT", call)
            self.assertIn("--capacity-scaler=1.0", call)
            self.assertIn("--max-in-flight-requests-per-endpoint=15", call)
            self.assertIn("--traffic-duration=LONG", call)
            self.assertNotIn("--max-rate-per-endpoint", " ".join(call))
            self.assertNotIn("--max-connections-per-endpoint", " ".join(call))

    def test_attach_permission_error_reports_denied_permission_and_resource(self):
        result = self._run(add_mode="permission-denied")

        self.assertEqual(result.returncode, 1)
        self.assertIn("compute.networkEndpointGroups.use", result.stderr)
        self.assertIn(
            "projects/based-hardware/zones/us-central1-c/networkEndpointGroups/prod-backend-listen-neg", result.stderr
        )
        self.assertIn("us-central1-c", result.stderr)
        for permission in (
            "compute.backendServices.get",
            "compute.backendServices.list",
            "compute.backendServices.update",
            "compute.networkEndpointGroups.get",
            "compute.networkEndpointGroups.list",
            "compute.networkEndpointGroups.use",
            "compute.globalOperations.get",
        ):
            self.assertIn(permission, result.stderr)
        self.assertNotIn("raw-resource-id", result.stderr)

    def test_attach_permission_error_does_not_guess_when_gcloud_omits_permission(self):
        result = self._run(add_mode="permission-denied-generic")

        self.assertEqual(result.returncode, 1)
        self.assertIn("permission unavailable", result.stderr)
        self.assertIn("required permissions:", result.stderr)
        self.assertNotIn("raw-resource-id", result.stderr)

    def test_fails_when_service_status_declares_an_unlistable_zone(self):
        result = self._run("--dry-run", missing_zone="us-central1-f")

        self.assertEqual(result.returncode, 1)
        self.assertIn("us-central1-f", result.stderr)
        self.assertIn("no listable NEG", result.stderr)
        self.assertFalse(any("add-backend" in call for call in self._gcloud_calls()))

    def test_rejects_exact_name_neg_in_zone_outside_declared_zones(self):
        result = self._run(foreign_zone_neg=True)

        self.assertEqual(result.returncode, 1)
        self.assertIn("outside the listen Service's declared zones: europe-west1-b", result.stderr)
        self.assertFalse(any("add-backend" in call for call in self._gcloud_calls()))

    def test_attaches_owned_neg_in_zone_missing_from_stale_service_status(self):
        # 2026-10-18: neg-status listed a/b/c while GKE had created the f NEG for
        # the same Service; owner metadata, not the stale zone list, decides scope.
        result = self._run(status_omits_f=True)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("accepted by matching GKE owner metadata: us-central1-f", result.stdout)
        add_calls = [call for call in self._gcloud_calls() if "add-backend" in call]
        self.assertEqual(
            [next(a for a in call if a.startswith("--network-endpoint-group-zone=")) for call in add_calls],
            ["--network-endpoint-group-zone=us-central1-c", "--network-endpoint-group-zone=us-central1-f"],
        )

    def test_rejects_undeclared_zone_neg_owned_by_another_cluster(self):
        result = self._run(status_omits_f=True, f_foreign_owner=True)

        self.assertEqual(result.returncode, 1)
        self.assertIn("outside the listen Service's declared zones: us-central1-f", result.stderr)
        self.assertFalse(any("add-backend" in call for call in self._gcloud_calls()))

    def test_rejects_exact_name_neg_without_a_zone_scope(self):
        result = self._run(global_neg=True)

        self.assertEqual(result.returncode, 1)
        self.assertIn("outside the listen Service's declared zones: a regional or global scope", result.stderr)
        self.assertFalse(any("add-backend" in call for call in self._gcloud_calls()))

    def test_dry_run_with_all_zones_attached_is_an_idempotent_noop(self):
        result = self._run("--dry-run", all_attached=True)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("NEG zones missing (0): none", result.stdout)
        self.assertIn("dry-run: would attach 0 zone(s)", result.stdout)
        calls = self._gcloud_calls()
        self.assertEqual(len(calls), 2)
        self.assertTrue(all("add-backend" not in call for call in calls))

    def test_fails_closed_when_attached_backends_disagree_on_traffic_duration(self):
        result = self._run("--dry-run", disagree_traffic=True)

        self.assertEqual(result.returncode, 1)
        self.assertIn("disagree on balancing settings or traffic duration", result.stderr)
        self.assertFalse(any("add-backend" in call for call in self._gcloud_calls()))


if __name__ == "__main__":
    unittest.main()
