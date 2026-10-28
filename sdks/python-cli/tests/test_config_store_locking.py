"""Integration tests for the config read-modify-write locking.

These tests verify that concurrent modifications to the OMI config file
via the omi_cli.auth.store API are serialized and do not result in
data loss.
"""

from __future__ import annotations

import threading
import unittest
import json
import os
from pathlib import Path

from omi_cli.auth.store import store_api_key
from omi_cli.config import default_config_path


class TestConcurrentConfigStore(unittest.TestCase):
    def test_concurrent_store_api_key_different_profiles_both_survive(self):
        """Verify that concurrent calls to store_api_key do not lose data.

        This test exercises the real locking mechanism by performing concurrent
        credential writes to the config file (isolated via the OMI_CONFIG
        environment variable provided by the test runner).
        """
        config_path = Path(default_config_path())
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text("{}", encoding="utf-8")

        errors = []

        def worker(profile: str, key_prefix: str) -> None:
            try:
                # Perform multiple writes to increase the likelihood of race detection
                for i in range(10):
                    store_api_key(profile, f"{key_prefix}-{i}")
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=worker, args=("alpha", "KEY-A")),
            threading.Thread(target=worker, args=("beta", "KEY-B")),
        ]

        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertFalse(errors, f"Concurrent store_api_key raised: {errors}")

        # Verify the final state contains keys for both profiles
        data = json.loads(config_path.read_text(encoding="utf-8"))
        
        # Verify the structure matches the actual implementation's expectation
        # (Assuming the implementation uses a nested structure or flat keys)
        self.assertIn("alpha", data)
        self.assertIn("beta", data)
        self.assertEqual(data["alpha"], "KEY-A-9")
        self.assertEqual(data["beta"], "KEY-B-9")