import math
import sys
from unittest.mock import MagicMock, patch
import pytest

from testing.import_isolation import AutoMockModule

for mod in ["google", "google.cloud", "google.cloud.firestore"]:
    if mod not in sys.modules:
        sys.modules[mod] = AutoMockModule(mod)

# Ensure transactional decorator passes through callable
sys.modules["google.cloud.firestore"].transactional = lambda fn: fn
if hasattr(sys.modules["google.cloud"], "firestore"):
    sys.modules["google.cloud"].firestore.transactional = lambda fn: fn

from database.dream_canary import (
    _coerce_failure_count,
    _is_safe_doc_id,
    ensure_synthetic_owner,
    failure_count,
    record_result,
    reset_failures,
)



class MockSnapshot:
    def __init__(self, data):
        self._data = data

    def to_dict(self):
        return self._data


class MockDocRef:
    def __init__(self, data=None, raise_on_get=False):
        self.data = data
        self.raise_on_get = raise_on_get

    def get(self, transaction=None):
        if self.raise_on_get:
            raise RuntimeError("Simulated Firestore error")
        return MockSnapshot(self.data)


class MockTransaction:
    def set(self, ref, data, merge=False):
        if merge and isinstance(ref.data, dict):
            ref.data.update(data)
        elif isinstance(data, dict):
            ref.data = dict(data)
        else:
            ref.data = data


class MockCollection:
    def __init__(self):
        self.docs = {}

    def document(self, doc_id):
        if doc_id not in self.docs:
            self.docs[doc_id] = MockDocRef()
        return self.docs[doc_id]


class MockFirestoreClient:
    def __init__(self):
        self.collections = {}

    def collection(self, name):
        if name not in self.collections:
            self.collections[name] = MockCollection()
        return self.collections[name]

    def transaction(self):
        return MockTransaction()


# 1. _is_safe_doc_id tests
def test_is_safe_doc_id_non_string():
    assert not _is_safe_doc_id(None)
    assert not _is_safe_doc_id(123)
    assert not _is_safe_doc_id([])
    assert not _is_safe_doc_id({})


def test_is_safe_doc_id_empty_or_whitespace():
    assert not _is_safe_doc_id("")
    assert not _is_safe_doc_id("   ")
    assert not _is_safe_doc_id(" valid ")  # leading/trailing whitespace rejected


def test_is_safe_doc_id_too_long():
    assert not _is_safe_doc_id("a" * 129)


def test_is_safe_doc_id_path_separators():
    assert not _is_safe_doc_id("user/123")
    assert not _is_safe_doc_id("user\\123")
    assert not _is_safe_doc_id("..")
    assert not _is_safe_doc_id("../etc")


def test_is_safe_doc_id_control_characters():
    assert not _is_safe_doc_id("user\x00name")
    assert not _is_safe_doc_id("user\nname")
    assert not _is_safe_doc_id("user\x7fname")


def test_is_safe_doc_id_valid():
    assert _is_safe_doc_id("dream-canary-account")
    assert _is_safe_doc_id("user_12345-abc")


# 2. _coerce_failure_count tests
def test_coerce_failure_count_none_or_bool():
    assert _coerce_failure_count(None) == 0
    assert _coerce_failure_count(True) == 0
    assert _coerce_failure_count(False) == 0


def test_coerce_failure_count_valid_int():
    assert _coerce_failure_count(0) == 0
    assert _coerce_failure_count(42) == 42
    assert _coerce_failure_count(100) == 100


def test_coerce_failure_count_bounds_clamping():
    assert _coerce_failure_count(-5) == 0
    assert _coerce_failure_count(150) == 100


def test_coerce_failure_count_valid_float():
    assert _coerce_failure_count(12.7) == 12
    assert _coerce_failure_count(-2.5) == 0
    assert _coerce_failure_count(105.2) == 100


def test_coerce_failure_count_non_finite_float():
    assert _coerce_failure_count(float("nan")) == 0
    assert _coerce_failure_count(float("inf")) == 0
    assert _coerce_failure_count(float("-inf")) == 0


def test_coerce_failure_count_numeric_string():
    assert _coerce_failure_count("25") == 25
    assert _coerce_failure_count("  10  ") == 10
    assert _coerce_failure_count("99.4") == 99


def test_coerce_failure_count_string_bounds():
    assert _coerce_failure_count("-20") == 0
    assert _coerce_failure_count("500") == 100


def test_coerce_failure_count_invalid_string():
    assert _coerce_failure_count("") == 0
    assert _coerce_failure_count("   ") == 0
    assert _coerce_failure_count("not_a_number") == 0


def test_coerce_failure_count_invalid_types():
    assert _coerce_failure_count([]) == 0
    assert _coerce_failure_count({}) == 0


# 3. ensure_synthetic_owner tests
@patch("database.dream_canary.canary_uid", return_value="dream-canary-account")
def test_ensure_synthetic_owner_success_new_owner(mock_canary):
    client = MockFirestoreClient()
    ensure_synthetic_owner("dream-canary-account", firestore_client=client)
    assert client.collection("users").document("dream-canary-account").data == {"dream_canary": True}


@patch("database.dream_canary.canary_uid", return_value="dream-canary-account")
def test_ensure_synthetic_owner_idempotent_existing_canary(mock_canary):
    client = MockFirestoreClient()
    client.collection("users").document("dream-canary-account").data = {"dream_canary": True, "name": "Canary"}
    ensure_synthetic_owner("dream-canary-account", firestore_client=client)
    # Remains unchanged and succeeds
    assert client.collection("users").document("dream-canary-account").data["dream_canary"] is True


@patch("database.dream_canary.canary_uid", return_value="dream-canary-account")
def test_ensure_synthetic_owner_rejects_existing_non_canary(mock_canary):
    client = MockFirestoreClient()
    client.collection("users").document("dream-canary-account").data = {"dream_canary": False}
    with pytest.raises(ValueError, match="dream_canary_existing_owner"):
        ensure_synthetic_owner("dream-canary-account", firestore_client=client)


@patch("database.dream_canary.canary_uid", return_value="dream-canary-account")
def test_ensure_synthetic_owner_rejects_malformed_snapshot(mock_canary):
    client = MockFirestoreClient()
    client.collection("users").document("dream-canary-account").data = "not-a-dict"
    with pytest.raises(ValueError, match="dream_canary_existing_owner"):
        ensure_synthetic_owner("dream-canary-account", firestore_client=client)


@patch("database.dream_canary.canary_uid", return_value="dream-canary-account")
def test_ensure_synthetic_owner_rejects_mismatched_uid(mock_canary):
    client = MockFirestoreClient()
    with pytest.raises(ValueError, match="dream_canary_configuration"):
        ensure_synthetic_owner("other-user-uid", firestore_client=client)


@patch("database.dream_canary.canary_uid", return_value="dream-canary-account")
def test_ensure_synthetic_owner_rejects_unsafe_uid(mock_canary):
    client = MockFirestoreClient()
    with pytest.raises(ValueError, match="dream_canary_configuration"):
        ensure_synthetic_owner("dream-canary-account/../root", firestore_client=client)
    with pytest.raises(ValueError, match="dream_canary_configuration"):
        ensure_synthetic_owner(" dream-canary-account ", firestore_client=client)


@patch("database.dream_canary.canary_uid", return_value="")
def test_ensure_synthetic_owner_rejects_empty_canary_uid(mock_canary):
    client = MockFirestoreClient()
    with pytest.raises(ValueError, match="dream_canary_configuration"):
        ensure_synthetic_owner("dream-canary-account", firestore_client=client)


# 4. failure_count tests
def test_failure_count_valid():
    client = MockFirestoreClient()
    client.collection("dream_canary_health").document("current").data = {"canary_failures": 5}
    assert failure_count(firestore_client=client) == 5


def test_failure_count_missing_document():
    client = MockFirestoreClient()
    assert failure_count(firestore_client=client) == 0


def test_failure_count_explicit_none():
    client = MockFirestoreClient()
    client.collection("dream_canary_health").document("current").data = {"canary_failures": None}
    assert failure_count(firestore_client=client) == 0


def test_failure_count_invalid_string():
    client = MockFirestoreClient()
    client.collection("dream_canary_health").document("current").data = {"canary_failures": "not_an_int"}
    assert failure_count(firestore_client=client) == 0


def test_failure_count_negative_clamped():
    client = MockFirestoreClient()
    client.collection("dream_canary_health").document("current").data = {"canary_failures": -10}
    assert failure_count(firestore_client=client) == 0


def test_failure_count_error_boundary():
    client = MockFirestoreClient()
    client.collection("dream_canary_health").document("current").raise_on_get = True
    assert failure_count(firestore_client=client) == 0


# 5. record_result tests
def test_record_result_rejects_non_boolean():
    client = MockFirestoreClient()
    with pytest.raises(ValueError, match="dream_canary_invalid_passed_type"):
        record_result("true", firestore_client=client)
    with pytest.raises(ValueError, match="dream_canary_invalid_passed_type"):
        record_result(1, firestore_client=client)
    with pytest.raises(ValueError, match="dream_canary_invalid_passed_type"):
        record_result(None, firestore_client=client)


def test_record_result_passed_resets_failures():
    client = MockFirestoreClient()
    client.collection("dream_canary_health").document("current").data = {"canary_failures": 7}
    res = record_result(True, firestore_client=client)
    assert res == 0
    assert client.collection("dream_canary_health").document("current").data["canary_failures"] == 0


def test_record_result_passed_when_no_prior_document():
    client = MockFirestoreClient()
    res = record_result(True, firestore_client=client)
    assert res == 0
    assert client.collection("dream_canary_health").document("current").data["canary_failures"] == 0



def test_record_result_failed_increments_failures():
    client = MockFirestoreClient()
    client.collection("dream_canary_health").document("current").data = {"canary_failures": 3}
    res = record_result(False, firestore_client=client)
    assert res == 4
    assert client.collection("dream_canary_health").document("current").data["canary_failures"] == 4


def test_record_result_failed_clamped_at_100():
    client = MockFirestoreClient()
    client.collection("dream_canary_health").document("current").data = {"canary_failures": 100}
    res = record_result(False, firestore_client=client)
    assert res == 100
    assert client.collection("dream_canary_health").document("current").data["canary_failures"] == 100


def test_record_result_failed_handles_malformed_initial_state():
    client = MockFirestoreClient()
    client.collection("dream_canary_health").document("current").data = {"canary_failures": "invalid"}
    res = record_result(False, firestore_client=client)
    assert res == 1
    assert client.collection("dream_canary_health").document("current").data["canary_failures"] == 1


# 6. reset_failures tests
def test_reset_failures():
    client = MockFirestoreClient()
    client.collection("dream_canary_health").document("current").data = {"canary_failures": 9}
    res = reset_failures(firestore_client=client)
    assert res == 0
    assert client.collection("dream_canary_health").document("current").data["canary_failures"] == 0
