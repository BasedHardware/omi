"""Unit tests for the server-driven app-review config gate.

Hermetic: the Firestore client and the process-wide memory cache are replaced
with in-memory fakes, so nothing here touches Redis, Firestore, or the network.
"""

from database import app_review_config as arc

PLATFORM_DOC = "app_review_config"
REVIEWER_UID = "uid-review-1"


class _Snapshot:
    def __init__(self, data):
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return None if self._data is None else dict(self._data)


class _DocRef:
    def __init__(self, data):
        self._data = data

    def get(self):
        return _Snapshot(self._data)


class _Collection:
    def __init__(self, docs):
        self._docs = docs

    def document(self, doc_id):
        return _DocRef(self._docs.get(doc_id))


class _FakeFirestore:
    def __init__(self, collections=None):
        self._collections = collections or {}

    def collection(self, name):
        return _Collection(self._collections.get(name, {}))


class _MemoryCache:
    def __init__(self):
        self._store = {}

    def get_or_fetch(self, key, fetch, ttl=None):
        if key not in self._store:
            self._store[key] = fetch()
        return self._store[key]


def _install(monkeypatch, config, cache=None):
    firestore = _FakeFirestore({PLATFORM_DOC: config})
    monkeypatch.setattr(arc, "get_firestore_client", lambda: firestore)
    monkeypatch.setattr(arc, "get_memory_cache", lambda: cache if cache is not None else _MemoryCache())
    return firestore


def test_platform_header_is_trimmed_and_lowercased(monkeypatch):
    _install(monkeypatch, {"ios": {"reviewer_uids": [REVIEWER_UID]}})

    assert arc.should_hide_subscription_ui(REVIEWER_UID, " iOS ", None) is True
    assert arc.should_hide_subscription_ui(REVIEWER_UID, "\tIOS\n", None) is True


def test_unknown_or_missing_platform_does_not_hide(monkeypatch):
    _install(monkeypatch, {"ios": {"reviewer_uids": [REVIEWER_UID]}})

    assert arc.should_hide_subscription_ui(REVIEWER_UID, "android", None) is False
    assert arc.should_hide_subscription_ui(REVIEWER_UID, None, None) is False


def test_reviewer_uid_whitespace_matches_canonically(monkeypatch):
    _install(monkeypatch, {"ios": {"reviewer_uids": [f"  {REVIEWER_UID}  "]}})

    assert arc.should_hide_subscription_ui(REVIEWER_UID, "ios", None) is True
    assert arc.should_hide_subscription_ui(f"  {REVIEWER_UID}  ", "ios", None) is True
    assert arc.should_hide_subscription_ui("uid-someone-else", "ios", None) is False


def test_hidden_semver_matches_every_build_of_that_version(monkeypatch):
    _install(monkeypatch, {"ios": {"hidden_versions": ["1.0.531"]}})

    assert arc.should_hide_subscription_ui("uid-1", "ios", "1.0.531") is True
    assert arc.should_hide_subscription_ui("uid-1", "ios", "1.0.531+607") is True
    assert arc.should_hide_subscription_ui("uid-1", "ios", "1.0.532") is False


def test_pinned_build_still_distinguishes_build_numbers(monkeypatch):
    _install(monkeypatch, {"ios": {"hidden_versions": ["1.0.531+607"]}})

    assert arc.should_hide_subscription_ui("uid-1", "ios", "1.0.531+607") is True
    assert arc.should_hide_subscription_ui("uid-1", "ios", "1.0.531+608") is False


def test_malformed_versions_never_collide(monkeypatch):
    _install(monkeypatch, {"ios": {"hidden_versions": ["malformed..version", "", "1.0.x"]}})

    assert arc.should_hide_subscription_ui("uid-1", "ios", "another..version") is False
    assert arc.should_hide_subscription_ui("uid-1", "ios", "") is False
    assert arc.should_hide_subscription_ui("uid-1", "ios", "1.0.531") is False


def test_firestore_failure_falls_back_to_empty_config(monkeypatch):
    class _ExplodingFirestore:
        def collection(self, name):
            raise RuntimeError("firestore unavailable")

    monkeypatch.setattr(arc, "get_firestore_client", lambda: _ExplodingFirestore())
    monkeypatch.setattr(arc, "get_memory_cache", lambda: _MemoryCache())

    assert arc.get_review_config("ios") == {}
    assert arc.should_hide_subscription_ui("uid-1", "ios", "1.0.531") is False


def test_review_config_is_cached_per_normalized_platform(monkeypatch):
    cache = _MemoryCache()
    calls = []

    class _CountingFirestore(_FakeFirestore):
        def collection(self, name):
            calls.append(name)
            return super().collection(name)

    firestore = _CountingFirestore({PLATFORM_DOC: {"ios": {"reviewer_uids": [REVIEWER_UID]}}})
    monkeypatch.setattr(arc, "get_firestore_client", lambda: firestore)
    monkeypatch.setattr(arc, "get_memory_cache", lambda: cache)

    assert arc.get_review_config(" iOS ") == {"reviewer_uids": [REVIEWER_UID]}
    assert arc.get_review_config("ios") == {"reviewer_uids": [REVIEWER_UID]}
    assert len(calls) == 1
