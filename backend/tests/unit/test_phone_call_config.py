"""Unit tests for backend/database/phone_call_config.py — #21895.

Covers the four acceptance items: sanitized allowed_countries, strict
bool/negative limit rejection, resilient Firestore fetch via
firestore_client injection, and catalog default fallbacks.
"""

import database.phone_call_config as pcc


class FakeDoc:
    def __init__(self, exists=True, data=None):
        self._exists = exists
        self._data = data

    @property
    def exists(self):
        return self._exists

    def to_dict(self):
        return self._data


class FakeDocumentRef:
    def __init__(self, doc):
        self._doc = doc

    def get(self):
        return self._doc


class FakeCollection:
    def __init__(self, doc):
        self._doc = doc

    def document(self, name):
        return FakeDocumentRef(self._doc)


class FakeClient:
    def __init__(self, doc=None, error=None):
        self._doc = doc or FakeDoc(False)
        self._error = error

    def collection(self, name):
        if self._error:
            raise self._error
        return FakeCollection(self._doc)


def cfg(override=None, profile='free'):
    doc = FakeDoc(exists=override is not None, data=override)
    return pcc._effective_config(profile, pcc._get_config(FakeClient(doc)))


def test_defaults_when_document_missing():
    eff = pcc._effective_config('free', pcc._get_config(FakeClient(FakeDoc(False))))
    assert eff['monthly_call_limit'] == pcc._DEFAULT_FREE_PLAN['monthly_call_limit']
    assert eff['max_duration_seconds'] == pcc._DEFAULT_FREE_PLAN['max_duration_seconds']
    assert eff['allowed_countries'] == []
    assert eff['effective_overlay']['source'] == 'catalog'


def test_countries_normalized_to_uppercase_iso2():
    eff = cfg({'free_plan': {'allowed_countries': [' us ', 'ca', 'GB']}})
    assert eff['allowed_countries'] == ['US', 'CA', 'GB']


def test_countries_drop_malformed_items():
    eff = cfg({'free_plan': {'allowed_countries': [None, 42, 'united states', 'X', '', 'US']}})
    assert eff['allowed_countries'] == ['US']


def test_countries_non_list_becomes_empty():
    eff = cfg({'free_plan': {'allowed_countries': 'US'}})
    assert eff['allowed_countries'] == []


def test_bool_limit_rejected_falls_back_to_default():
    for field in ('monthly_call_limit', 'max_duration_seconds'):
        eff = cfg({'free_plan': {field: True}})
        assert eff[field] == pcc._DEFAULT_FREE_PLAN[field]


def test_negative_limit_rejected_falls_back_to_default():
    for field in ('monthly_call_limit', 'max_duration_seconds'):
        eff = cfg({'free_plan': {field: -1}})
        assert eff[field] == pcc._DEFAULT_FREE_PLAN[field]


def test_zero_limit_preserved():
    eff = cfg({'free_plan': {'monthly_call_limit': 0}})
    assert eff['monthly_call_limit'] == 0


def test_none_limit_preserved_as_unlimited():
    eff = cfg({'free_plan': {'max_duration_seconds': None}})
    assert eff['max_duration_seconds'] is None


def test_valid_positive_limit_preserved():
    eff = cfg({'free_plan': {'monthly_call_limit': 25, 'max_duration_seconds': 900}})
    assert eff['monthly_call_limit'] == 25
    assert eff['max_duration_seconds'] == 900


def test_fetch_error_returns_empty_and_defaults_apply():
    assert pcc._fetch_config(FakeClient(error=OSError('down'))) == {}
    eff = pcc._effective_config('free', {})
    assert eff['allowed_countries'] == []
    assert eff['effective_overlay']['source'] == 'catalog'


def test_non_dict_document_returns_empty():
    doc = FakeDoc(exists=True, data=['not', 'a', 'dict'])
    assert pcc._fetch_config(FakeClient(doc)) == {}


def test_unknown_override_fields_ignored_and_reported():
    eff = cfg({'free_plan': {'typo_field': 1, 'allowed_countries': ['US']}})
    assert 'typo_field' not in eff
    assert eff['effective_overlay']['ignored_fields'] == ['typo_field']


def test_paid_plan_profile_uses_paid_defaults():
    eff = pcc._effective_config('paid', {})
    assert eff['phone_calls_profile'] == 'paid'


def test_plan_profile_resolution_never_raises():
    # plan resolution must never raise on unusual inputs
    for bad in (None, 'unknown-plan', 42):
        eff = pcc._effective_config(pcc._phone_call_profile_for_plan(bad), {})
        assert eff['phone_calls_profile'] in ('free', 'paid')
