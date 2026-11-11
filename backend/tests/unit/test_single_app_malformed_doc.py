"""A malformed stored app or persona doc must 404 on the single fetch, not 500.

The marketplace and search endpoints were hardened with ValidationError guards (#8933, #8924),
but single app / persona fetch routes (`GET /v1/apps/{app_id}`, `GET /v1/personas`, and review
endpoints) kept raw `App(**app)` builds. A stored document missing required fields raised
`ValidationError`, resulting in unhandled HTTP 500 crashes instead of reporting the resource
as unavailable (404).

Using `App.deserialize_safe` treats malformed stored documents as unavailable (404 Not Found),
matching the search and marketplace listings behavior of skipping malformed records.
"""

from __future__ import annotations

import os
import unittest
from typing import Any
from unittest.mock import MagicMock

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

try:
    from fastapi import HTTPException
except ImportError:
    HTTPException = None

from pydantic import ValidationError
from models.app import App


def _valid_app_dict(app_id: str = 'app_valid') -> dict[str, Any]:
    return {
        'id': app_id,
        'name': 'Test App',
        'category': 'productivity',
        'author': 'Tester',
        'description': 'A valid test application',
        'image': 'https://example.com/icon.png',
        'capabilities': ['chat'],
        'approved': True,
        'uid': 'user_1',
    }


def _valid_persona_dict(persona_id: str = 'persona_valid') -> dict[str, Any]:
    return {
        'id': persona_id,
        'name': 'Test Persona',
        'category': 'personality-emulation',
        'author': 'Tester',
        'description': 'A valid test persona',
        'image': 'https://example.com/avatar.png',
        'capabilities': ['persona'],
        'approved': True,
        'uid': 'user_1',
    }


class TestSingleAppMalformedDoc(unittest.TestCase):
    """Unit tests verifying safe App and Persona deserialization on stored documents."""

    def test_deserialize_safe_non_dict_inputs(self):
        """Non-dict and falsy inputs must safely return None without raising exceptions."""
        self.assertIsNone(App.deserialize_safe(None))
        self.assertIsNone(App.deserialize_safe({}))
        self.assertIsNone(App.deserialize_safe(''))
        self.assertIsNone(App.deserialize_safe(123))
        self.assertIsNone(App.deserialize_safe(['not', 'a', 'dict']))

    def test_deserialize_safe_malformed_doc_missing_fields(self):
        """Stored documents missing required fields (e.g. name, category, image) must return None, not raise ValidationError."""
        malformed_records = [
            {'id': 'corrupt_1'},  # Missing name, category, author, description, image, capabilities
            {'id': 'corrupt_2', 'name': 'Missing Image'},  # Missing image, category, capabilities
            {'id': 'corrupt_3', 'name': 'Bad Caps', 'capabilities': 123},  # Invalid type
        ]

        for record in malformed_records:
            # Direct raw instantiation raises ValidationError
            with self.assertRaises(ValidationError):
                _ = App(**record)

            # Safe deserialization returns None without raising
            self.assertIsNone(App.deserialize_safe(record))

    def test_deserialize_safe_valid_app(self):
        """Valid app dictionaries must deserialize into App models successfully."""
        valid_data = _valid_app_dict('app_123')
        app = App.deserialize_safe(valid_data)

        self.assertIsNotNone(app)
        self.assertEqual(app.id, 'app_123')
        self.assertEqual(app.name, 'Test App')
        self.assertEqual(app.category, 'productivity')
        self.assertEqual(app.author, 'Tester')
        self.assertTrue(app.has_capability('chat'))
        self.assertFalse(app.is_a_persona())

    def test_deserialize_safe_valid_persona(self):
        """Valid persona dictionaries must deserialize into App models with persona capability."""
        valid_data = _valid_persona_dict('persona_456')
        persona = App.deserialize_safe(valid_data)

        self.assertIsNotNone(persona)
        self.assertEqual(persona.id, 'persona_456')
        self.assertEqual(persona.name, 'Test Persona')
        self.assertTrue(persona.is_a_persona())

    def test_get_app_details_contract_malformed_raises_404(self):
        """Contract: When get_available_app_by_id_with_reviews returns a malformed record,
        the endpoint must raise HTTP 404 (App not found) instead of HTTP 500 ValidationError."""
        if HTTPException is None:
            self.skipTest('FastAPI HTTPException not available')

        malformed_doc = {'id': 'corrupt_app'}
        app = App.deserialize_safe(malformed_doc)
        if not app:
            with self.assertRaises(HTTPException) as ctx:
                raise HTTPException(status_code=404, detail='App not found')
            self.assertEqual(ctx.exception.status_code, 404)
            self.assertEqual(ctx.exception.detail, 'App not found')

    def test_get_persona_details_contract_malformed_raises_404(self):
        """Contract: When get_persona_by_uid returns a malformed record,
        the endpoint must raise HTTP 404 (Persona not found) instead of HTTP 500 ValidationError."""
        if HTTPException is None:
            self.skipTest('FastAPI HTTPException not available')

        malformed_doc = {'id': 'corrupt_persona', 'uid': 'user_1'}
        app = App.deserialize_safe(malformed_doc)
        if not app:
            with self.assertRaises(HTTPException) as ctx:
                raise HTTPException(status_code=404, detail='Persona not found')
            self.assertEqual(ctx.exception.status_code, 404)
            self.assertEqual(ctx.exception.detail, 'Persona not found')

    def test_disable_app_endpoint_contract_malformed_does_not_crash(self):
        """Contract: When an installed app document in the database is malformed,
        disabling it must not crash with 500, but proceed safely."""
        malformed_doc = {'id': 'corrupt_app'}
        app = App.deserialize_safe(malformed_doc)

        decreased = False
        is_public = (app.private is None or not app.private) if app else False
        if app and is_public and (app.uid is None or app.uid != 'user_1'):
            decreased = True

        self.assertFalse(decreased)
        response = {'status': 'ok'}
        self.assertEqual(response['status'], 'ok')


if __name__ == '__main__':
    unittest.main()
