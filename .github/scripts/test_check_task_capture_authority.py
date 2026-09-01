#!/usr/bin/env python3
"""Behavioral cover for the INV-TASK-2 guard.

A guard that cannot fail is decoration, so each case here is the exact shape of
a defect that shipped on this path before the invariant existed.
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parent / "check_task_capture_authority.py"
spec = importlib.util.spec_from_file_location("check_task_capture_authority", MODULE_PATH)
guard = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(guard)


class ForbiddenOutcomeTests(unittest.TestCase):
    def test_rejects_the_two_outcomes_that_created_tasks(self):
        for outcome in ("auto_accept_silent", "create_direct"):
            with self.subTest(outcome=outcome):
                self.assertTrue(guard.FORBIDDEN_PY_OUTCOME.search(f"    return CapturePolicyResult('{outcome}', 'none')"))

    def test_allows_naming_them_in_prose(self):
        """The policy explains why they are gone; that must not trip the guard."""
        prose = "# The auto_accept_silent and create_direct outcomes were removed (I1)."
        self.assertIsNone(guard.FORBIDDEN_PY_OUTCOME.search(prose))

    def test_allows_the_surviving_outcomes(self):
        for outcome in ("pending_candidate", "ignore", "propose_completion"):
            with self.subTest(outcome=outcome):
                self.assertIsNone(
                    guard.FORBIDDEN_PY_OUTCOME.search(f"return CapturePolicyResult('{outcome}', 'none')")
                )

    def test_rejects_the_swift_twins(self):
        for outcome in ("autoAcceptSilent", "createDirect"):
            with self.subTest(outcome=outcome):
                self.assertTrue(guard.FORBIDDEN_SWIFT_OUTCOME.search(f"    return .{outcome}"))
        self.assertIsNone(guard.FORBIDDEN_SWIFT_OUTCOME.search("    return .pendingCandidate"))


class AcceptTests(unittest.TestCase):
    def test_rejects_extraction_accepting_a_candidate(self):
        self.assertTrue(guard.ACCEPT_CALL.search("candidate_service.accept_candidate(uid, cid)"))


class ClientProtocolTests(unittest.TestCase):
    def test_finds_an_accept_on_the_capture_client(self):
        swift = (
            "protocol CanonicalScreenCandidateClient: Sendable {\n"
            "  func create(_ c: X, idempotencyKey: String) async throws -> Y\n"
            "  func accept(candidateID: String) async throws -> Y\n"
            "}\n"
        )
        self.assertTrue(guard.SWIFT_ACCEPT_DECL.search(guard._client_protocol_body(swift)))

    def test_create_only_protocol_passes(self):
        swift = (
            "protocol CanonicalScreenCandidateClient: Sendable {\n"
            "  func create(_ c: X, idempotencyKey: String) async throws -> Y\n"
            "}\n"
            "struct Elsewhere { func accept(candidateID: String) {} }\n"
        )
        self.assertIsNone(guard.SWIFT_ACCEPT_DECL.search(guard._client_protocol_body(swift)))


class RepositoryStateTests(unittest.TestCase):
    def test_the_guard_passes_on_this_checkout(self):
        self.assertEqual(guard.main(), 0)


if __name__ == "__main__":
    unittest.main()
