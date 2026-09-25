"""Hermetic unit tests for error sanitization in the candidates router.

Verifies that:
1. WorkstreamCandidateResolverUnavailableError, generic CandidateStoreError, and
   TaskLinkValidationError route through _sanitize_candidate_error.
2. The _sanitize_candidate_error helper filters raw exception details and returns clean,
   structured fallback messages to external callers.
3. No raw detail=str(exc), detail=str(e), or detail=str(error) leaks remain across candidates.py.
4. Behavioral executions for candidate error paths return sanitized responses.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

from pydantic import BaseModel

BACKEND_DIR = Path(__file__).resolve().parents[2]
CANDIDATES_ROUTER_FILE = BACKEND_DIR / "routers" / "candidates.py"


class CandidatesErrorSanitizationTests(unittest.TestCase):
    _stubbed_modules: dict = {}
    _modified_parent_attrs: list = []
    _sanitize_fn = None
    _router_mod = None

    @classmethod
    def setUpClass(cls):
        cls._stubbed_modules = {}
        cls._modified_parent_attrs = []

        class StubCandidateStoreError(Exception):
            pass

        class StubCandidateNotFoundError(StubCandidateStoreError):
            pass

        class StubCandidateGenerationMismatchError(StubCandidateStoreError):
            pass

        class StubWorkstreamCandidateResolverUnavailableError(StubCandidateStoreError):
            pass

        class StubTaskLinkValidationError(Exception):
            pass

        class StubModel(BaseModel):
            pass

        class StubStrEnum(str, Enum):
            SUGGESTED = "suggested"
            ACCEPTED = "accepted"
            REJECTED = "rejected"
            EXPIRE = "expire"
            DISMISS = "dismiss"
            ACCEPT = "accept"
            REJECT = "reject"
            TASK_RECOMMENDATION = "task_recommendation"

        stub_names = [
            "database",
            "database.candidates",
            "database.task_recommendations",
            "database.task_intelligence_control",
            "models",
            "models.action_item",
            "models.candidate",
            "models.task_intelligence",
            "utils",
            "utils.other",
            "utils.other.endpoints",
            "utils.task_intelligence",
            "utils.task_intelligence.capture_policy",
            "utils.task_intelligence.recommendations",
            "utils.task_intelligence.rollout",
            "utils.task_intelligence.chat_first_e2e_fixture",
            "utils.task_intelligence.task_links",
            "utils.task_intelligence.staged_migration",
        ]
        for mod in stub_names:
            if mod not in sys.modules:
                mock_mod = MagicMock()
                cls._stubbed_modules[mod] = mock_mod
                sys.modules[mod] = mock_mod

        # Link parent/child modules cleanly with undo tracking
        for mod in stub_names:
            if "." in mod:
                parent, child = mod.rsplit(".", 1)
                if parent in sys.modules:
                    parent_mod = sys.modules[parent]
                    had_attr = hasattr(parent_mod, child)
                    old_val = getattr(parent_mod, child, None) if had_attr else None
                    cls._modified_parent_attrs.append((parent_mod, child, had_attr, old_val))
                    setattr(parent_mod, child, sys.modules[mod])

        # Inject Pydantic models into models stubs
        sys.modules["models.action_item"].TaskCreatePayload = StubModel
        sys.modules["models.candidate"].CandidateAction = StubStrEnum
        sys.modules["models.candidate"].CandidateCreate = StubModel
        sys.modules["models.candidate"].CandidateListResponse = StubModel
        sys.modules["models.candidate"].CandidateMigrationReport = StubModel
        sys.modules["models.candidate"].CandidateMigrationRequest = StubModel
        sys.modules["models.candidate"].CandidateRecord = StubModel
        sys.modules["models.candidate"].CandidateResolutionReceipt = StubModel
        sys.modules["models.candidate"].CandidateResolutionRequest = StubModel
        sys.modules["models.candidate"].CandidateStatus = StubStrEnum
        sys.modules["models.candidate"].CandidateSubjectKind = StubStrEnum
        sys.modules["models.task_intelligence"].TaskWorkflowControl = StubModel
        sys.modules["models.task_intelligence"].TaskWorkflowMode = StubStrEnum

        sys.modules["database.candidates"].CandidateStoreError = StubCandidateStoreError
        sys.modules["database.candidates"].CandidateNotFoundError = StubCandidateNotFoundError
        sys.modules["database.candidates"].CandidateGenerationMismatchError = StubCandidateGenerationMismatchError
        sys.modules["database.candidates"].WorkstreamCandidateResolverUnavailableError = (
            StubWorkstreamCandidateResolverUnavailableError
        )
        sys.modules["database.candidates"].SUGGESTION_TTL = 3600
        sys.modules["utils.task_intelligence.capture_policy"].MINIMUM_CAPTURE_CONFIDENCE = 0.5
        sys.modules["utils.task_intelligence.task_links"].TaskLinkValidationError = StubTaskLinkValidationError

        if str(BACKEND_DIR) not in sys.path:
            sys.path.insert(0, str(BACKEND_DIR))

        try:
            from routers.candidates import _sanitize_candidate_error, _raise_store_error, accept_candidate
            import routers.candidates as candidates_mod
        except ImportError:
            import candidates as candidates_mod
            from candidates import _sanitize_candidate_error, _raise_store_error, accept_candidate

        cls._sanitize_fn = staticmethod(_sanitize_candidate_error)
        cls._router_mod = candidates_mod
        cls._StubCandidateStoreError = StubCandidateStoreError
        cls._StubCandidateNotFoundError = StubCandidateNotFoundError
        cls._StubCandidateGenerationMismatchError = StubCandidateGenerationMismatchError
        cls._StubWorkstreamCandidateResolverUnavailableError = StubWorkstreamCandidateResolverUnavailableError
        cls._StubTaskLinkValidationError = StubTaskLinkValidationError

    @classmethod
    def tearDownClass(cls):
        for parent_mod, child, had_attr, old_val in reversed(cls._modified_parent_attrs):
            if had_attr:
                setattr(parent_mod, child, old_val)
            else:
                try:
                    delattr(parent_mod, child)
                except AttributeError:
                    pass
        for mod in cls._stubbed_modules:
            sys.modules.pop(mod, None)

    def test_sanitize_candidate_error_behavior(self):
        fallback = "Candidate operation could not be completed"
        sanitize = self._sanitize_fn

        # 1. Store error returns fallback
        self.assertEqual(
            sanitize(self._StubCandidateStoreError("database query failed with internal schema"), fallback),
            fallback,
        )

        # 2. Raw traceback filtered to fallback
        self.assertEqual(
            sanitize(
                ValueError("Traceback (most recent call last):\n  File 'x.py', line 1\nZeroDivisionError"),
                fallback,
            ),
            fallback,
        )

        # 3. Empty exception detail falls back cleanly
        self.assertEqual(
            sanitize(self._StubCandidateStoreError(""), fallback),
            fallback,
        )

    def test_no_raw_str_exc_leak_in_candidates(self):
        target_path = CANDIDATES_ROUTER_FILE
        if not target_path.exists():
            target_path = Path(__file__).parent / "candidates.py"
        source = target_path.read_text(encoding="utf-8")

        self.assertIn("_sanitize_candidate_error", source)
        self.assertNotIn("detail=str(exc)", source)
        self.assertNotIn("detail=str(e)", source)
        self.assertNotIn("detail=str(error)", source)

    def test_raise_store_error_sanitization(self):
        from fastapi import HTTPException

        _raise_store_error = self._router_mod._raise_store_error

        # 1. NotFound preserves 404
        with self.assertRaises(HTTPException) as ctx:
            _raise_store_error(self._StubCandidateNotFoundError("not found"))
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertEqual(ctx.exception.detail, "Candidate or task not found")

        # 2. GenerationMismatch preserves 409
        with self.assertRaises(HTTPException) as ctx:
            _raise_store_error(self._StubCandidateGenerationMismatchError("mismatch"))
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(ctx.exception.detail, "Account generation mismatch")

        # 3. Workstream resolver unavailable sanitizes to clean detail
        with self.assertRaises(HTTPException) as ctx:
            _raise_store_error(
                self._StubWorkstreamCandidateResolverUnavailableError("resolver socket timeout: port 9000")
            )
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(ctx.exception.detail, "Workstream candidate resolver is temporarily unavailable")

        # 4. Generic CandidateStoreError sanitizes to clean detail
        with self.assertRaises(HTTPException) as ctx:
            _raise_store_error(self._StubCandidateStoreError("unhandled internal postgres table lock"))
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(ctx.exception.detail, "Candidate operation could not be completed")

    def test_accept_candidate_store_error_sanitization(self):
        from fastapi import HTTPException

        router_mod = self._router_mod
        accept_candidate = router_mod.accept_candidate

        with patch.object(router_mod, "_require_candidate_write_control"), patch.object(
            router_mod.candidate_service,
            "accept_candidate",
            side_effect=self._StubCandidateStoreError("internal firestore index conflict"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                accept_candidate(candidate_id="c-1", account_generation=1, uid="u-1")
            self.assertEqual(ctx.exception.status_code, 409)
            self.assertEqual(ctx.exception.detail, "Candidate operation could not be completed")

    def test_accept_candidate_task_link_validation_error_sanitization(self):
        from fastapi import HTTPException

        router_mod = self._router_mod
        accept_candidate = router_mod.accept_candidate

        with patch.object(router_mod, "_require_candidate_write_control"), patch.object(
            router_mod.candidate_service,
            "accept_candidate",
            side_effect=self._StubTaskLinkValidationError("internal resolver failed with secret state"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                accept_candidate(candidate_id="c-1", account_generation=1, uid="u-1")
            self.assertEqual(ctx.exception.status_code, 409)
            self.assertEqual(ctx.exception.detail, "Invalid candidate task link parameters")


if __name__ == "__main__":
    unittest.main()
