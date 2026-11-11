"""Tests for safe Geolocation deserialization in conversation ingestion and background finalization.

Regression tests for:
1. Geolocation.deserialize_safe (models/geolocation.py):
   - Safely parses valid geolocation dictionaries.
   - Gracefully migrates legacy cached records using {'lat': ..., 'lng': ...} keys to
     latitude/longitude (as documented in test_redis_db_cache_serialization.py).
   - Returns None on missing required fields, non-numeric values, or out-of-bounds coordinates
     without raising unhandled pydantic.ValidationError.
   - Safely returns None on non-dict, empty, or None inputs.
   - Returns existing Geolocation instances unchanged.
2. Synchronous REST conversation creation (POST /v1/conversations in routers/conversations.py):
   - When a conversation in progress lacks geolocation and falls back to Redis cached user location,
     corrupted or legacy records must not raise unhandled ValidationError (HTTP 500), but log
     a warning and allow conversation finalization to proceed safely.
3. Asynchronous conversation finalization (finalize_conversation in utils/conversations/finalizer.py):
   - When background finalizer falls back to cached geolocation, corrupted records must not crash
     the background worker task.
4. AST structural invariants:
   - routers/conversations.py and utils/conversations/finalizer.py must not contain bare
     Geolocation(**...) calls on cached user geolocation fallbacks.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any
import unittest

from pydantic import ValidationError

from models.geolocation import Geolocation


def _valid_geo_dict(lat: float = 37.7749, lon: float = -122.4194) -> dict[str, Any]:
    return {
        "latitude": lat,
        "longitude": lon,
        "google_place_id": "place_san_francisco_123",
        "address": "Market St, San Francisco, CA",
        "location_type": "street_address",
        "accuracy": 15.0,
    }


class TestConversationGeolocationSafeDeserialization(unittest.TestCase):
    """Unit tests verifying safe Geolocation deserialization."""

    def test_raw_instantiation_raises_on_malformed_dict(self):
        """Confirm that bare Geolocation(**data) raises ValidationError on missing or invalid fields."""
        malformed_records = [
            {},
            {"latitude": 37.77},  # missing longitude
            {"longitude": -122.42},  # missing latitude
            {"lat": 37.77, "lng": -122.42},  # legacy keys unmapped
            {"latitude": 999.0, "longitude": -122.42},  # latitude out of bounds (> 90)
            {"latitude": -95.0, "longitude": 0.0},  # latitude out of bounds (< -90)
            {"latitude": 0.0, "longitude": 250.0},  # longitude out of bounds (> 180)
            {"latitude": 0.0, "longitude": -200.0},  # longitude out of bounds (< -180)
            {"latitude": "not-a-float", "longitude": -122.42},  # invalid type
            {"latitude": 37.77, "longitude": -122.42, "accuracy": -10.0},  # negative accuracy
            {"latitude": 37.77, "longitude": -122.42, "capture_source": "invalid_source"},  # invalid literal
        ]

        for record in malformed_records:
            with self.assertRaises(ValidationError):
                _ = Geolocation(**record)

    def test_deserialize_safe_valid_dict(self):
        """Confirm that Geolocation.deserialize_safe properly parses a valid dictionary."""
        valid_dict = _valid_geo_dict()
        geo = Geolocation.deserialize_safe(valid_dict)

        self.assertIsNotNone(geo)
        self.assertEqual(geo.latitude, 37.7749)
        self.assertEqual(geo.longitude, -122.4194)
        self.assertEqual(geo.google_place_id, "place_san_francisco_123")
        self.assertEqual(geo.address, "Market St, San Francisco, CA")
        self.assertEqual(geo.accuracy, 15.0)

    def test_deserialize_safe_legacy_lat_lng_mapping(self):
        """Confirm that legacy cached records with 'lat' and 'lng' keys are seamlessly normalized."""
        legacy_record = {"lat": 40.7128, "lng": -74.0060}
        geo = Geolocation.deserialize_safe(legacy_record)

        self.assertIsNotNone(geo)
        self.assertEqual(geo.latitude, 40.7128)
        self.assertEqual(geo.longitude, -74.0060)
        self.assertIsNone(geo.google_place_id)

    def test_deserialize_safe_already_instance(self):
        """Passing an existing Geolocation instance returns it directly."""
        existing = Geolocation(latitude=12.34, longitude=56.78)
        self.assertIs(Geolocation.deserialize_safe(existing), existing)

    def test_deserialize_safe_returns_none_for_corrupted_records(self):
        """Confirm that Geolocation.deserialize_safe returns None without raising on corrupted docs."""
        corrupted_records = [
            None,
            "",
            12345,
            [],
            {},
            {"latitude": "not-a-float", "longitude": -122.4194},
            {"latitude": 37.7749},  # Missing longitude
            {"longitude": -122.4194},  # Missing latitude
            {"latitude": 999.0, "longitude": -122.4194},  # Latitude > 90 out of bounds
            {"latitude": -95.0, "longitude": 0.0},  # Latitude < -90 out of bounds
            {"latitude": 0.0, "longitude": 250.0},  # Longitude > 180 out of bounds
            {"latitude": 0.0, "longitude": -200.0},  # Longitude < -180 out of bounds
            {"latitude": 37.77, "longitude": -122.42, "accuracy": -5.0},  # Negative accuracy
            {"latitude": 37.77, "longitude": -122.42, "capture_source": "invalid_source"},  # Invalid enum literal
            {"corrupted_payload": True},
        ]

        for record in corrupted_records:
            geo = Geolocation.deserialize_safe(record)
            self.assertIsNone(geo)

    def test_conversation_geolocation_fallback_simulation(self):
        """Simulate the fallback logic in conversation creation with mixed cache results."""
        test_cases = [
            ("valid", _valid_geo_dict(10.0, 20.0), True, 10.0, 20.0),
            ("legacy", {"lat": 30.0, "lng": 40.0}, True, 30.0, 40.0),
            ("corrupted_bounds", {"latitude": 999.0, "longitude": 0.0}, False, None, None),
            ("corrupted_missing", {"random_key": "junk"}, False, None, None),
            ("empty", {}, False, None, None),
            ("none", None, False, None, None),
        ]

        for case_name, cached_record, should_succeed, expected_lat, expected_lon in test_cases:
            cached_geo = Geolocation.deserialize_safe(cached_record)
            if should_succeed:
                self.assertIsNotNone(cached_geo, f"Failed on valid/legacy case: {case_name}")
                self.assertEqual(cached_geo.latitude, expected_lat)
                self.assertEqual(cached_geo.longitude, expected_lon)
            else:
                self.assertIsNone(cached_geo, f"Expected None on corrupted case: {case_name}")

    def test_ast_conversations_router_uses_deserialize_safe(self):
        """Static AST check verifying routers/conversations.py does not call bare Geolocation(**...)."""
        router_path = Path(__file__).resolve().parents[2] / "routers" / "conversations.py"
        source = router_path.read_text(encoding="utf-8")
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "process_in_progress_conversation":
                for child in ast.walk(node):
                    if isinstance(child, ast.Call):
                        if isinstance(child.func, ast.Name) and child.func.id == "Geolocation":
                            has_double_star = any(kw.arg is None for kw in child.keywords)
                            self.assertFalse(
                                has_double_star,
                                "process_in_progress_conversation must not call bare Geolocation(**...); use Geolocation.deserialize_safe",
                            )

    def test_ast_finalizer_uses_deserialize_safe(self):
        """Static AST check verifying utils/conversations/finalizer.py does not call bare Geolocation(**...)."""
        finalizer_path = Path(__file__).resolve().parents[2] / "utils" / "conversations" / "finalizer.py"
        source = finalizer_path.read_text(encoding="utf-8")
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "finalize_conversation":
                for child in ast.walk(node):
                    if isinstance(child, ast.Call):
                        if isinstance(child.func, ast.Name) and child.func.id == "Geolocation":
                            has_double_star = any(kw.arg is None for kw in child.keywords)
                            self.assertFalse(
                                has_double_star,
                                "finalize_conversation must not call bare Geolocation(**...); use Geolocation.deserialize_safe",
                            )


if __name__ == "__main__":
    unittest.main()
