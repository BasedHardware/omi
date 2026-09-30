from __future__ import annotations

import hashlib
import math
from typing import Any

from google.api_core.exceptions import AlreadyExists
from google.cloud import firestore
import pytest

from database.llm_gateway_accounting import (
    ATTEMPTS_COLLECTION,
    USER_DAYS_COLLECTION,
    _feature_class,
    _hashed_uid,
    _micro_usd,
    _platform,
    _provider_cost_field,
    _required_string,
    _subscription_tier,
    record_llm_gateway_attempt,
)


class _FakeSnapshot:
    def __init__(self, data: dict[str, Any] | None) -> None:
        self.exists = data is not None
        self._data = data

    def to_dict(self) -> dict[str, Any] | None:
        return self._data


class _FakeDocument:
    def __init__(self, collection: '_FakeCollection', document_id: str) -> None:
        self._collection = collection
        self._document_id = document_id

    def create(self, data: dict[str, Any]) -> None:
        if self._document_id in self._collection.documents:
            raise AlreadyExists('attempt already exists')
        self._collection.documents[self._document_id] = dict(data)

    def set(self, data: dict[str, Any], merge: bool = False) -> None:
        current = self._collection.documents.get(self._document_id, {})
        stored = dict(current) if merge else {}
        for key, value in data.items():
            if isinstance(value, firestore.Increment):
                stored[key] = current.get(key, 0) + value.value
            else:
                stored[key] = value
        self._collection.documents[self._document_id] = stored

    def get(self, _fields: list[str] | None = None) -> _FakeSnapshot:
        return _FakeSnapshot(self._collection.documents.get(self._document_id))


class _FakeCollection:
    def __init__(self, documents: dict[str, dict[str, Any]]) -> None:
        self.documents = documents

    def document(self, document_id: str) -> _FakeDocument:
        return _FakeDocument(self, document_id)


class _FakeFirestoreClient:
    def __init__(self, *, subscription_plan: str = 'pro') -> None:
        self.collections: dict[str, dict[str, dict[str, Any]]] = {
            ATTEMPTS_COLLECTION: {},
            USER_DAYS_COLLECTION: {},
            'users': {'user-123': {'subscription': {'plan': subscription_plan}}},
        }

    def collection(self, name: str) -> _FakeCollection:
        return _FakeCollection(self.collections.setdefault(name, {}))


# ==============================================================================
# Micro-USD Clamping & Validation Tests
# ==============================================================================


def test_micro_usd_clamping_and_types() -> None:
    # Standard positive integer
    assert _micro_usd(500) == 500
    assert _micro_usd(0) == 0

    # Negative integer must clamp to 0 to prevent ledger decrement
    assert _micro_usd(-100) == 0
    assert _micro_usd(-1) == 0

    # Float conversion & rounding
    assert _micro_usd(12.4) == 12
    assert _micro_usd(12.6) == 13
    assert _micro_usd(2500.5) == 2500 or _micro_usd(2500.5) == 2501  # standard round half to even
    assert _micro_usd(-25.5) == 0

    # Infinite and NaN floats
    assert _micro_usd(float('inf')) == 0
    assert _micro_usd(float('-inf')) == 0
    assert _micro_usd(float('nan')) == 0

    # Booleans are subclasses of int in Python but must be rejected
    assert _micro_usd(True) == 0
    assert _micro_usd(False) == 0
    assert _micro_usd(None) == 0

    # Numeric strings
    assert _micro_usd('2500') == 2500
    assert _micro_usd(' 12.8 ') == 13
    assert _micro_usd('-50') == 0
    assert _micro_usd('not-a-number') == 0
    assert _micro_usd('') == 0


# ==============================================================================
# Required String & Document Path Traversal Tests
# ==============================================================================


def test_required_string_validation_and_stripping() -> None:
    # Valid string
    assert _required_string({'key': 'valid_id'}, 'key') == 'valid_id'
    assert _required_string({'key': '  spaced_id  '}, 'key') == 'spaced_id'

    # Non-string or missing
    with pytest.raises(ValueError, match='gateway accounting event requires key'):
        _required_string({}, 'key')
    with pytest.raises(ValueError, match='gateway accounting event requires key'):
        _required_string({'key': 123}, 'key')
    with pytest.raises(ValueError, match='gateway accounting event requires key'):
        _required_string({'key': None}, 'key')

    # Empty or whitespace-only
    with pytest.raises(ValueError, match='gateway accounting event requires valid non-empty key'):
        _required_string({'key': ''}, 'key')
    with pytest.raises(ValueError, match='gateway accounting event requires valid non-empty key'):
        _required_string({'key': '   '}, 'key')

    # Path traversal and subcollection injection prevention
    with pytest.raises(ValueError, match='gateway accounting event requires valid non-empty key'):
        _required_string({'key': 'path/traversal'}, 'key')
    with pytest.raises(ValueError, match='gateway accounting event requires valid non-empty key'):
        _required_string({'key': 'path\\traversal'}, 'key')


# ==============================================================================
# Platform, Provider, and Feature Normalization Tests
# ==============================================================================


def test_platform_normalization() -> None:
    assert _platform('desktop') == 'desktop'
    assert _platform('  ios  ') == 'ios'
    assert _platform('') == 'unattributed'
    assert _platform('   ') == 'unattributed'
    assert _platform(None) == 'unattributed'
    assert _platform(123) == 'unattributed'


def test_provider_cost_field_normalization() -> None:
    assert _provider_cost_field('openai') == 'cost_openai'
    assert _provider_cost_field(' OPENAI ') == 'cost_openai'
    assert _provider_cost_field('gemini') == 'cost_gemini'
    assert _provider_cost_field(' GEMINI ') == 'cost_gemini'
    assert _provider_cost_field('anthropic') == 'cost_other_provider'
    assert _provider_cost_field('other') == 'cost_other_provider'
    assert _provider_cost_field(None) == 'cost_other_provider'


def test_feature_class_normalization() -> None:
    assert _feature_class('chat') == 'chat'
    assert _feature_class(' CHAT ') == 'chat'
    assert _feature_class('persona_gen') == 'chat'
    assert _feature_class('desktop_chat') == 'desktop'
    assert _feature_class('proactive_notification') == 'proactive_notification'
    assert _feature_class('translation') == 'translation'
    assert _feature_class('text_embeddings') == 'embeddings'
    assert _feature_class('screen_summary') == 'extraction'
    assert _feature_class('') == 'extraction'
    assert _feature_class('   ') == 'extraction'
    assert _feature_class(None) == 'extraction'


# ==============================================================================
# Subscription Tier & UID Hardening Tests
# ==============================================================================


def test_subscription_tier_uid_sanitization() -> None:
    client = _FakeFirestoreClient(subscription_plan='pro')

    # Valid user
    assert _subscription_tier(client, 'user-123') == 'pro'

    # Unattributed cases
    assert _subscription_tier(client, '') == 'unattributed'
    assert _subscription_tier(client, '   ') == 'unattributed'
    assert _subscription_tier(client, None) == 'unattributed'
    assert _subscription_tier(client, 123) == 'unattributed'

    # Path traversal injection attempts
    assert _subscription_tier(client, 'user/subcollection') == 'unattributed'
    assert _subscription_tier(client, 'user\\subcollection') == 'unattributed'


def test_hashed_uid_sanitization() -> None:
    assert _hashed_uid('user-123') == hashlib.sha256(b'user-123').hexdigest()[:16]
    assert _hashed_uid('  user-123  ') == hashlib.sha256(b'user-123').hexdigest()[:16]
    assert _hashed_uid('') == 'anonymous'
    assert _hashed_uid('   ') == 'anonymous'
    assert _hashed_uid(None) == 'anonymous'


# ==============================================================================
# Record Gateway Attempt End-to-End Resilience Tests
# ==============================================================================


def test_record_attempt_clamps_negative_cost_and_prevents_ledger_decrement() -> None:
    client = _FakeFirestoreClient(subscription_plan='pro')
    event = {
        'attempt_id': 'attempt-neg-1',
        'date': '2026-09-14',
        'provider': 'openai',
        'user_uid': 'user-123',
        'feature': 'chat',
        'payer': 'omi',
        'cost_status': 'estimated',
        'estimated_cost_micro_usd': -5000,
    }

    assert record_llm_gateway_attempt(event, firestore_client=client)

    # Attempt doc should have clamped cost
    stored = client.collections[ATTEMPTS_COLLECTION]['attempt-neg-1']
    assert stored['estimated_cost_micro_usd'] == 0

    # User day rollup must not have negative cost or decrement
    uid_hash = hashlib.sha256(b'user-123').hexdigest()[:16]
    rollup = client.collections[USER_DAYS_COLLECTION][f'2026-09-14_{uid_hash}']
    assert rollup['attempts'] == 1
    assert 'cost_micro_usd_sum' not in rollup
    assert 'cost_openai' not in rollup


def test_record_attempt_handles_float_costs_safely() -> None:
    client = _FakeFirestoreClient(subscription_plan='pro')
    event = {
        'attempt_id': 'attempt-float-1',
        'date': '2026-09-14',
        'provider': 'openai',
        'user_uid': 'user-123',
        'feature': 'chat',
        'payer': 'omi',
        'cost_status': 'estimated',
        'estimated_cost_micro_usd': 2500.6,
    }

    assert record_llm_gateway_attempt(event, firestore_client=client)

    stored = client.collections[ATTEMPTS_COLLECTION]['attempt-float-1']
    assert stored['estimated_cost_micro_usd'] == 2501

    uid_hash = hashlib.sha256(b'user-123').hexdigest()[:16]
    rollup = client.collections[USER_DAYS_COLLECTION][f'2026-09-14_{uid_hash}']
    assert rollup['cost_micro_usd_sum'] == 2501
    assert rollup['cost_openai'] == 2501


def test_record_attempt_date_sanitization_and_rejection() -> None:
    client = _FakeFirestoreClient(subscription_plan='pro')

    # Valid date with whitespace gets trimmed
    event_valid = {
        'attempt_id': 'attempt-date-1',
        'date': '  2026-09-14  ',
        'provider': 'openai',
        'user_uid': 'user-123',
        'cost_status': 'estimated',
        'estimated_cost_micro_usd': 100,
    }
    assert record_llm_gateway_attempt(event_valid, firestore_client=client)
    uid_hash = hashlib.sha256(b'user-123').hexdigest()[:16]
    assert f'2026-09-14_{uid_hash}' in client.collections[USER_DAYS_COLLECTION]

    # Date with path traversal / slashes is skipped from rollup but writes attempt doc
    event_slash = {
        'attempt_id': 'attempt-date-2',
        'date': '2026/09/14',
        'provider': 'openai',
        'user_uid': 'user-123',
        'cost_status': 'estimated',
        'estimated_cost_micro_usd': 100,
    }
    assert record_llm_gateway_attempt(event_slash, firestore_client=client)
    assert 'attempt-date-2' in client.collections[ATTEMPTS_COLLECTION]
    assert f'2026/09/14_{uid_hash}' not in client.collections[USER_DAYS_COLLECTION]

    # Date with backslash traversal is also skipped from rollup
    event_backslash = {
        'attempt_id': 'attempt-date-3',
        'date': '2026\\09\\14',
        'provider': 'openai',
        'user_uid': 'user-123',
    }
    assert record_llm_gateway_attempt(event_backslash, firestore_client=client)
    assert 'attempt-date-3' in client.collections[ATTEMPTS_COLLECTION]


def test_record_attempt_strips_attempt_id() -> None:
    client = _FakeFirestoreClient(subscription_plan='pro')
    event = {
        'attempt_id': '   attempt-trimmed-1   ',
        'date': '2026-09-14',
        'provider': 'openai',
        'user_uid': 'user-123',
    }

    assert record_llm_gateway_attempt(event, firestore_client=client)
    assert 'attempt-trimmed-1' in client.collections[ATTEMPTS_COLLECTION]
    assert client.collections[ATTEMPTS_COLLECTION]['attempt-trimmed-1']['attempt_id'] == 'attempt-trimmed-1'


def test_record_attempt_idempotency() -> None:
    client = _FakeFirestoreClient(subscription_plan='pro')
    event = {
        'attempt_id': 'attempt-idempotent-1',
        'date': '2026-09-14',
        'provider': 'openai',
        'user_uid': 'user-123',
        'estimated_cost_micro_usd': 100,
    }

    assert record_llm_gateway_attempt(event, firestore_client=client) is True
    # Re-recording returns False and does not double-count
    assert record_llm_gateway_attempt(event, firestore_client=client) is False
    uid_hash = hashlib.sha256(b'user-123').hexdigest()[:16]
    assert client.collections[USER_DAYS_COLLECTION][f'2026-09-14_{uid_hash}']['attempts'] == 1


def test_record_attempt_cost_attribution_statuses() -> None:
    client = _FakeFirestoreClient(subscription_plan='pro')

    # BYOK payer
    byok_event = {
        'attempt_id': 'attempt-byok-1',
        'provider': 'openai',
        'user_uid': 'user-123',
        'payer': 'byok',
    }
    assert record_llm_gateway_attempt(byok_event, firestore_client=client)
    stored_byok = client.collections[ATTEMPTS_COLLECTION]['attempt-byok-1']
    assert stored_byok['cost_attribution_status'] == 'excluded'
    assert stored_byok['cost_exclusion'] == 'byok_provider_cost'

    # not_omi_cost status
    not_omi_event = {
        'attempt_id': 'attempt-not-omi-1',
        'provider': 'openai',
        'user_uid': 'user-123',
        'cost_status': 'not_omi_cost',
    }
    assert record_llm_gateway_attempt(not_omi_event, firestore_client=client)
    stored_not_omi = client.collections[ATTEMPTS_COLLECTION]['attempt-not-omi-1']
    assert stored_not_omi['cost_attribution_status'] == 'excluded'
    assert stored_not_omi['cost_exclusion'] == 'provider_not_omi_cost'

    # Missing cost
    missing_cost_event = {
        'attempt_id': 'attempt-missing-cost-1',
        'provider': 'openai',
        'user_uid': 'user-123',
    }
    assert record_llm_gateway_attempt(missing_cost_event, firestore_client=client)
    stored_missing = client.collections[ATTEMPTS_COLLECTION]['attempt-missing-cost-1']
    assert stored_missing['cost_attribution_status'] == 'missing'


def test_record_attempt_plan_resolution_exception_handling(monkeypatch: pytest.MonkeyPatch) -> None:
    import database.llm_gateway_accounting as module_under_test

    def _failing_plan_resolver(*_args: Any, **_kwargs: Any) -> str | None:
        raise RuntimeError('plan catalog database temporarily down')

    monkeypatch.setattr(module_under_test, 'resolve_usage_plan_id', _failing_plan_resolver)

    client = _FakeFirestoreClient(subscription_plan='pro')
    event = {
        'attempt_id': 'attempt-plan-err-1',
        'date': '2026-09-14',
        'provider': 'openai',
        'user_uid': 'user-123',
        'cost_status': 'estimated',
        'estimated_cost_micro_usd': 500,
    }

    # Should safely record attempt without raising
    assert record_llm_gateway_attempt(event, firestore_client=client)
    stored = client.collections[ATTEMPTS_COLLECTION]['attempt-plan-err-1']
    assert stored['plan_id'] is None
    assert stored['plan_attribution_status'] == 'missing'


def test_record_attempt_multi_provider_and_feature_rollup() -> None:
    client = _FakeFirestoreClient(subscription_plan='pro')

    events = [
        {
            'attempt_id': 'att-1',
            'date': '2026-09-14',
            'provider': ' OpenAI ',
            'user_uid': 'user-123',
            'feature': 'chat',
            'cost_status': 'estimated',
            'estimated_cost_micro_usd': 1000,
        },
        {
            'attempt_id': 'att-2',
            'date': '2026-09-14',
            'provider': ' GEMINI ',
            'user_uid': 'user-123',
            'feature': 'desktop_agent',
            'cost_status': 'estimated',
            'estimated_cost_micro_usd': 2000,
        },
        {
            'attempt_id': 'att-3',
            'date': '2026-09-14',
            'provider': ' Anthropic ',
            'user_uid': 'user-123',
            'feature': 'translation',
            'cost_status': 'estimated',
            'estimated_cost_micro_usd': 3000,
        },
    ]

    for ev in events:
        assert record_llm_gateway_attempt(ev, firestore_client=client)

    uid_hash = hashlib.sha256(b'user-123').hexdigest()[:16]
    rollup = client.collections[USER_DAYS_COLLECTION][f'2026-09-14_{uid_hash}']
    assert rollup['attempts'] == 3
    assert rollup['cost_micro_usd_sum'] == 6000
    assert rollup['cost_openai'] == 1000
    assert rollup['cost_gemini'] == 2000
    assert rollup['cost_other_provider'] == 3000
    assert rollup['fc_chat'] == 1000
    assert rollup['fc_desktop'] == 2000
    assert rollup['fc_translation'] == 3000
