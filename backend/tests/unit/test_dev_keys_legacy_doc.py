"""get_dev_keys_for_user must fall back to doc.id and skip a malformed legacy key, not 500 the list.

GET /v1/dev/keys built DevApiKey.model_validate(doc.to_dict()) per key with no id fallback and no
try/except. DevApiKey requires id/name/key_prefix/created_at, and Firestore doc.to_dict() omits the
doc id, so one legacy or malformed key doc raised ValidationError and 500'd the whole list. It now
falls back to doc.id (mirroring get_mcp_keys_for_user in the sibling module) and skips a genuinely
malformed key. database.dev_api_key is light (module-level db proxy), so the test drives it directly.
"""

import os

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

from unittest.mock import MagicMock

import pytest
from pydantic import BaseModel, ValidationError

import database.dev_api_key as dev_key


class _Probe(BaseModel):
    x: int


def _validation_error() -> ValidationError:
    try:
        _Probe.model_validate({})  # missing required field -> a real ValidationError
    except ValidationError as exc:
        return exc
    raise AssertionError('expected a ValidationError')


def _doc(doc_id, data):
    doc = MagicMock()
    doc.id = doc_id
    doc.to_dict.return_value = data
    return doc


def _patch_client(monkeypatch, docs):
    fake = MagicMock()
    for attr in ('collection', 'where', 'order_by'):
        getattr(fake, attr).return_value = fake
    fake.stream.return_value = docs
    monkeypatch.setattr(dev_key, 'db', fake)


def test_id_fallback_and_skip_malformed(monkeypatch):
    err = _validation_error()

    def fake_validate(data):
        if data.get('_bad'):
            raise err
        return data  # return the dict so the resolved id is inspectable

    monkeypatch.setattr(dev_key.DevApiKey, 'model_validate', staticmethod(fake_validate))
    _patch_client(
        monkeypatch,
        [
            _doc('k1', {'id': 'k1', 'name': 'n'}),  # explicit id preserved
            _doc('legacy-id', {'name': 'n2'}),  # missing id field -> falls back to doc.id
            _doc('bad-id', {'_bad': True}),  # malformed -> skipped, not a 500
        ],
    )
    result = dev_key.get_dev_keys_for_user('u1')
    assert [k['id'] for k in result] == ['k1', 'legacy-id']  # malformed key skipped, list survives


def test_unexpected_error_propagates(monkeypatch):
    # Only ValidationError is skipped; an unexpected error must surface, not be hidden as a skip.
    def boom(data):
        raise RuntimeError('unexpected')

    monkeypatch.setattr(dev_key.DevApiKey, 'model_validate', staticmethod(boom))
    _patch_client(monkeypatch, [_doc('k1', {'id': 'k1'})])
    with pytest.raises(RuntimeError):
        dev_key.get_dev_keys_for_user('u1')
