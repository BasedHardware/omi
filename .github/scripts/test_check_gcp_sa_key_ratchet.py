#!/usr/bin/env python3
"""Hermetic tests for the #6800 GCP SA key ratchet."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKER = REPO_ROOT / ".github" / "scripts" / "check_gcp_sa_key_ratchet.py"


def load_checker():
    spec = importlib.util.spec_from_file_location("check_gcp_sa_key_ratchet", CHECKER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GcpSaKeyRatchetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = load_checker()

    def _write(self, root: Path, relative: str, contents: str) -> None:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")

    def _baseline(self, root: Path, entries: dict[str, int]) -> Path:
        path = root / ".github" / "scripts" / "gcp_sa_key_ratchet_baseline.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.mod.baseline_document(entries), indent=2) + "\n", encoding="utf-8")
        return path

    def test_docs_and_tests_are_out_of_scope(self) -> None:
        self.assertFalse(self.mod.is_scanned_path("docs/doc/developer/backend/Backend_Setup.mdx"))
        self.assertFalse(self.mod.is_scanned_path("backend/tests/unit/test_google_credentials.py"))
        self.assertFalse(self.mod.is_scanned_path("backend/scripts/stt/d_test_models.py"))
        self.assertFalse(self.mod.is_scanned_path("backend/migrations/001_enhanced_protection_default.py"))

    def test_prod_surfaces_are_in_scope(self) -> None:
        self.assertTrue(self.mod.is_scanned_path("backend/charts/agent-proxy/prod_omi_agent_proxy_values.yaml"))
        self.assertTrue(self.mod.is_scanned_path("backend/main.py"))
        self.assertTrue(self.mod.is_scanned_path(".github/workflows/gcp_backend_pusher.yml"))
        self.assertTrue(self.mod.is_scanned_path("backend/Dockerfile"))
        self.assertTrue(self.mod.is_scanned_path("backend/charts/agent-proxy/templates/_helpers.tpl"))
        self.assertTrue(self.mod.is_scanned_path("backend/charts/deepgram-self-hosted/nova-2/README.md.gotmpl"))

    def test_quoted_credentials_json_is_detected(self) -> None:
        counts = self.mod.count_kinds_in_text(
            'with:\n  "credentials_json": "${{ secrets.GCP_CREDENTIALS }}"\n'
            "  'credentials_json': leaked\n"
            "  credentials_json: bare\n"
        )
        self.assertEqual(counts.get("credentials-json-gh-action"), 3)

    def test_google_application_credentials_is_tracked(self) -> None:
        counts = self.mod.count_kinds_in_text(
            "- name: GOOGLE_APPLICATION_CREDENTIALS\n  value: /secrets/sa.json\n"
        )
        self.assertEqual(counts.get("google-application-credentials-env"), 1)

    def test_new_helm_template_key_path_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(
                root,
                "backend/charts/new-service/templates/secret.yaml.tpl",
                'env:\n  - name: GOOGLE_APPLICATION_CREDENTIALS\n    value: "/keys/sa.json"\n',
            )
            self._baseline(root, {})
            completed = subprocess.run(
                [sys.executable, str(CHECKER), "--root", str(root)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
            self.assertIn("google-application-credentials-env", completed.stdout)
            self.assertIn("backend/charts/new-service/templates/secret.yaml.tpl", completed.stdout)

    def test_new_chart_key_path_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(
                root,
                "backend/charts/new-service/values.yaml",
                "env:\n  - name: SERVICE_ACCOUNT_JSON\n    value: leaked\n",
            )
            self._baseline(root, {})
            completed = subprocess.run(
                [sys.executable, str(CHECKER), "--root", str(root)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
            self.assertIn("service-account-json-env", completed.stdout)
            self.assertIn("backend/charts/new-service/values.yaml", completed.stdout)

    def test_baselined_path_passes_and_shrink_is_required(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            relative = "backend/charts/pusher/prod_omi_pusher_values.yaml"
            self._write(root, relative, "SERVICE_ACCOUNT_JSON: keep\n")
            key = f"{relative}:service-account-json-env"
            baseline = self._baseline(root, {key: 1})

            ok = subprocess.run(
                [sys.executable, str(CHECKER), "--root", str(root)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)

            # Removal without shrinking baseline fails closed.
            self._write(root, relative, "env: []\n")
            stale = subprocess.run(
                [sys.executable, str(CHECKER), "--root", str(root)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(stale.returncode, 1, stale.stdout + stale.stderr)
            self.assertIn("shrink the baseline", stale.stdout)

            # --write-baseline may shrink.
            written = subprocess.run(
                [sys.executable, str(CHECKER), "--root", str(root), "--write-baseline"],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(written.returncode, 0, written.stdout + written.stderr)
            payload = json.loads(baseline.read_text(encoding="utf-8"))
            self.assertEqual(payload["entries"], {})

    def test_write_baseline_refuses_to_raise(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            relative = "backend/main.py"
            self._write(root, relative, "SERVICE_ACCOUNT_JSON\n")
            key = f"{relative}:service-account-json-env"
            self._baseline(root, {key: 1})
            self._write(root, relative, "SERVICE_ACCOUNT_JSON\nSERVICE_ACCOUNT_JSON\n")
            completed = subprocess.run(
                [sys.executable, str(CHECKER), "--root", str(root), "--write-baseline"],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
            self.assertIn("refuses to raise", completed.stdout)

    def test_repo_baseline_matches_current_tree(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(CHECKER), "--root", str(REPO_ROOT)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)


if __name__ == "__main__":
    unittest.main()
