"""Empirical stress, performance, and adversarial test harness for focus_sessions read boundary.

Tests:
1. 10,000 mixed records safe deserialization throughput and memory stability.
2. Router GET /v1/focus-sessions end-to-end throughput and non-PII sanitization under load.
3. Adversarial boundary conditions (generators, custom Mappings, log-injection strings, massive payloads).
"""

from __future__ import annotations

import collections.abc
import gc
import importlib.abc
import importlib.machinery
import logging
import os
import sys
import time
import tracemalloc
import types
import unittest
from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

try:
    import email.message  # noqa: F401
    import anyio.from_thread  # noqa: F401
except ImportError:
    pass


# Ensure backend root is in sys.path
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from testing.import_isolation import AutoMockModule, stub_modules

# Mark the entire module as slow so it does not run in the fast PR unit lane
pytestmark = pytest.mark.slow


# Configure safe test environment
os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")
os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

# Hermetic isolation stubs for external cloud and telemetry packages
_STUB_MODULES = [
    "google",
    "google.api_core",
    "google.api_core.exceptions",
    "google.cloud",
    "google.cloud.firestore",
    "google.cloud.firestore_v1",
    "google.cloud.firestore_v1.base_query",
    "google.cloud.storage",
    "firebase_admin",
    "firebase_admin.auth",
    "firebase_admin.firestore",
    "redis",
    "sentry_sdk",
    "requests",
    "pinecone",
    "typesense",
    "opuslib",
    "pydub",
    "pusher",
    "modal",
    "ulid",
    "langchain",
    "langchain_core",
    "stripe",
    "openai",
    "anthropic",
    "prometheus_client",
    "database._client",
    "utils.other.storage",
]

_fakes = {}
for _name in _STUB_MODULES:
    _m = AutoMockModule(_name)
    _m.__path__ = []
    _fakes[_name] = _m

with stub_modules(_fakes):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from models.focus_session import FocusSession
    import database.focus_sessions as focus_sessions_db
    import routers.focus_sessions as focus_sessions_router
    from utils.other import endpoints as auth



def _generate_10k_mixed_dataset() -> tuple[List[Any], int, int]:
    """Generate 10,000 mixed records: exactly 5,000 valid and 5,000 poisoned.

    Returns:
        (records, expected_valid_count, expected_poisoned_count)
    """
    records: List[Any] = []
    base_time = datetime(2026, 10, 3, 12, 0, 0, tzinfo=timezone.utc)
    now_iso = base_time.isoformat()

    valid_count = 5000
    poisoned_count = 5000

    # 1. 5000 Valid records
    for i in range(valid_count):
        status = "focused" if i % 2 == 0 else "distracted"
        rec = {
            "id": f"fs-valid-{i:05d}",
            "status": status,
            "app_or_site": f"Application_{i % 20}",
            "description": f"Valid working session description #{i}",
            "message": f"Concentrated on task #{i}" if i % 3 == 0 else None,
            "created_at": now_iso,
            "duration_seconds": (i * 10) % 3600,
        }
        records.append(rec)

    # 2. 5000 Poisoned records across 10 distinct failure archetypes
    for i in range(poisoned_count):
        archetype = i % 10
        pid = f"fs-poison-{i:05d}"
        if archetype == 0:
            # Missing required field 'status'
            records.append({
                "id": pid,
                "app_or_site": "IDE",
                "description": "Missing status",
                "created_at": now_iso,
            })
        elif archetype == 1:
            # Missing required field 'description'
            records.append({
                "id": pid,
                "status": "focused",
                "app_or_site": "Terminal",
                "created_at": now_iso,
            })
        elif archetype == 2:
            # Missing required field 'created_at'
            records.append({
                "id": pid,
                "status": "focused",
                "app_or_site": "Docs",
                "description": "No timestamp",
            })
        elif archetype == 3:
            # Invalid created_at string
            records.append({
                "id": pid,
                "status": "focused",
                "app_or_site": "Browser",
                "description": "Unparseable timestamp",
                "created_at": "not-a-timestamp-never-parseable",
            })
        elif archetype == 4:
            # Non-dict: None
            records.append(None)
        elif archetype == 5:
            # Non-dict: Primitive types (str, int, float, bool, list)
            primitives = ["corrupted_raw_text", 12345, 99.9, True, ["nested", "list"]]
            records.append(primitives[i % len(primitives)])
        elif archetype == 6:
            # Empty dictionary
            records.append({})
        elif archetype == 7:
            # Invalid type for duration_seconds (negative)
            records.append({
                "id": pid,
                "status": "focused",
                "app_or_site": "Slack",
                "description": "Negative duration",
                "created_at": now_iso,
                "duration_seconds": -500,  # ge=0 violation in Pydantic
            })
        elif archetype == 8:
            # Corrupted nested object where primitive is expected
            records.append({
                "id": pid,
                "status": {"nested": "corrupted_status"},
                "app_or_site": "Code",
                "description": "Nested dict status",
                "created_at": now_iso,
            })
        elif archetype == 9:
            # Log injection attempt in id and sensitive fields
            records.append({
                "id": f"{pid}\r\nINJECTED_LOG_LEVEL_CRITICAL: fake breach",
                "status": "focused",
                "app_or_site": "VulnerableApp",
                "description": "Sensitive user password leaked here: P@ssw0rd123!",
                "created_at": None,  # Causes validation error
            })

    # Interleave to simulate real-world chaotic database stream order
    interleaved: List[Any] = []
    for v, p in zip(records[:valid_count], records[valid_count:]):
        interleaved.append(v)
        interleaved.append(p)

    return interleaved, valid_count, poisoned_count


class CustomUserMapping(collections.abc.Mapping):
    """Custom Mapping implementation to test collections.abc.Mapping support."""

    def __init__(self, data: dict):
        self._data = data

    def __getitem__(self, key):
        return self._data[key]

    def __iter__(self):
        return iter(self._data)

    def __len__(self):
        return len(self._data)


@pytest.mark.slow
class TestFocusSessionsStressAndThroughput(unittest.TestCase):

    """Rigorous stress and throughput benchmark for 10,000 mixed records."""

    def setUp(self):
        gc.collect()

    def test_deserialize_many_safe_10k_throughput_and_memory(self):
        """Benchmark 10,000 mixed records deserialization."""
        dataset, expected_valid, expected_poisoned = _generate_10k_mixed_dataset()
        self.assertEqual(len(dataset), 10000)

        error_calls = []

        def track_error(record: Any, exc: Exception):
            error_calls.append((record, exc))

        # Start memory tracing
        gc.collect()
        tracemalloc.start()
        start_mem, _ = tracemalloc.get_traced_memory()
        start_time = time.perf_counter()

        parsed = FocusSession.deserialize_many_safe(dataset, on_error=track_error)

        elapsed_seconds = time.perf_counter() - start_time
        current_mem, peak_mem = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        # Empirical Assertions
        # 1. Correctness
        self.assertEqual(len(parsed), expected_valid, f"Expected {expected_valid} valid sessions, got {len(parsed)}")
        self.assertEqual(len(error_calls), expected_poisoned, f"Expected {expected_poisoned} errors, got {len(error_calls)}")

        # 2. Integrity of parsed data
        self.assertTrue(all(isinstance(s, FocusSession) for s in parsed))
        self.assertEqual(parsed[0].id, "fs-valid-00000")
        self.assertEqual(parsed[-1].id, "fs-valid-04999")

        # 3. Throughput metrics
        throughput = len(dataset) / elapsed_seconds
        peak_mb = peak_mem / (1024 * 1024)
        print(f"\n[STRESS BENCHMARK RESULTS]")
        print(f"Total Records: {len(dataset):,}")
        print(f"Elapsed Time:  {elapsed_seconds:.4f} seconds")
        print(f"Throughput:    {throughput:,.2f} records/sec")
        print(f"Peak Memory:   {peak_mb:.2f} MB")

        # Performance gates:
        # 10,000 records deserialization must finish within 3.0 seconds (well above 3,000 rec/sec)
        self.assertLess(elapsed_seconds, 3.0, f"Deserialization too slow: {elapsed_seconds:.2f}s for 10k records")
        # Peak memory must remain under 60 MB for 10k records
        self.assertLess(peak_mb, 60.0, f"Peak memory excessive: {peak_mb:.2f} MB")

    def test_deserialize_many_safe_lazy_generator(self):
        """Verify deserialize_many_safe accepts lazy generators without buffering entire input first."""
        def lazy_stream():
            now_iso = datetime.now(timezone.utc).isoformat()
            yield {"id": "g-1", "status": "focused", "app_or_site": "Git", "description": "Commit", "created_at": now_iso}
            yield None
            yield {"id": "g-2", "status": "distracted", "app_or_site": "YouTube", "description": "Music", "created_at": now_iso}

        errors = []
        parsed = FocusSession.deserialize_many_safe(lazy_stream(), on_error=lambda r, e: errors.append(e))
        self.assertEqual(len(parsed), 2)
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], TypeError)

    def test_deserialize_many_safe_custom_mapping(self):
        """Verify custom collections.abc.Mapping types are processed safely."""
        now_iso = datetime.now(timezone.utc).isoformat()
        mapping_data = CustomUserMapping({
            "id": "map-1",
            "status": "focused",
            "app_or_site": "CustomMapApp",
            "description": "Mapping test",
            "created_at": now_iso,
        })
        parsed = FocusSession.deserialize_many_safe([mapping_data])
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0].id, "map-1")


@pytest.mark.slow
class TestFocusSessionsRouterEndToEndStress(unittest.TestCase):

    """End-to-end FastAPI router integration test under 10,000 mixed records load."""

    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(focus_sessions_router.router)
        self.test_uid = "stress_eval_user_888"
        self.app.dependency_overrides[auth.get_current_user_uid] = lambda: self.test_uid
        self.client = TestClient(self.app)

    def tearDown(self):
        self.app.dependency_overrides.clear()

    def test_router_handles_10k_mixed_records_without_500(self):
        """Verify router survives 10,000 mixed records from DB, returning HTTP 200 with 5,000 valid items."""
        dataset, expected_valid, _ = _generate_10k_mixed_dataset()

        start_time = time.perf_counter()
        with patch.object(focus_sessions_db, "get_focus_sessions", return_value=dataset):
            response = self.client.get("/v1/focus-sessions")
        elapsed = time.perf_counter() - start_time

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), expected_valid)
        print(f"\n[ROUTER E2E BENCHMARK]")
        print(f"HTTP Status:   {response.status_code}")
        print(f"Items Returned:{len(data):,}")
        print(f"E2E Elapsed:   {elapsed:.4f} seconds")
        self.assertLess(elapsed, 5.0, f"Router E2E too slow: {elapsed:.2f}s")

    def test_router_logging_hygiene_under_adversarial_injections(self):
        """Verify router logs remain free of PII and injection attacks even under thousands of skipped records."""
        malicious_records = [
            {
                "id": f"malicious-doc-{i}",
                "status": "focused",
                "app_or_site": "HackedApp",
                "description": f"SECRET_API_KEY_SUPER_CONFIDENTIAL_{i}",
                "message": "authorization: Bearer my_jwt_token_secret",
                "created_at": "invalid_date",  # triggers validation error
            }
            for i in range(100)
        ]

        with self.assertLogs("routers.focus_sessions", level="WARNING") as captured_logs:
            with patch.object(focus_sessions_db, "get_focus_sessions", return_value=malicious_records):
                response = self.client.get("/v1/focus-sessions")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

        combined_logs = "\n".join(captured_logs.output)
        self.assertNotIn("SECRET_API_KEY_SUPER_CONFIDENTIAL", combined_logs)
        self.assertNotIn("Bearer my_jwt_token_secret", combined_logs)
        self.assertNotIn("authorization", combined_logs)
        self.assertIn("Skipping malformed focus session malicious-doc-0: ValidationError", combined_logs)


if __name__ == "__main__":
    unittest.main()
