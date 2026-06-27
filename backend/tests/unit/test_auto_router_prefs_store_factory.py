"""Tests for prefs_store_factory (v4, T-403)."""

import pytest

from utils.auto_router.prefs_store_factory import (
    BACKEND_FIRESTORE,
    BACKEND_MEMORY,
    DEFAULT_BACKEND,
    ENV_VAR,
    get_user_prefs_store,
    reset_user_prefs_store_for_testing,
)
from utils.auto_router.user_prefs_store import UserPrefsStore
from utils.auto_router.user_prefs_store_protocol import UserPrefsStoreProtocol


class TestFactoryBackendSelection:
    """The factory picks the correct backend based on env var."""

    def test_default_returns_firestore(self, monkeypatch):
        # Ensure env var is unset → defaults to firestore
        monkeypatch.delenv(ENV_VAR, raising=False)
        reset_user_prefs_store_for_testing()
        store = get_user_prefs_store()
        assert isinstance(store, UserPrefsStoreProtocol)
        # Should NOT be the in-memory store
        assert not isinstance(
            store, UserPrefsStore
        ), "default backend should be Firestore (UserPrefsStore is the v3 in-memory)"

    def test_memory_backend_returns_user_prefs_store(self, monkeypatch):
        monkeypatch.setenv(ENV_VAR, BACKEND_MEMORY)
        reset_user_prefs_store_for_testing()
        store = get_user_prefs_store()
        assert isinstance(store, UserPrefsStore)

    def test_firestore_backend_explicit(self, monkeypatch):
        monkeypatch.setenv(ENV_VAR, BACKEND_FIRESTORE)
        reset_user_prefs_store_for_testing()
        store = get_user_prefs_store()
        assert isinstance(store, UserPrefsStoreProtocol)
        assert not isinstance(store, UserPrefsStore)

    def test_invalid_value_falls_back_to_firestore(self, monkeypatch):
        monkeypatch.setenv(ENV_VAR, "garbage")
        reset_user_prefs_store_for_testing()
        store = get_user_prefs_store()
        # Falls back to firestore (the safe default)
        assert not isinstance(store, UserPrefsStore)

    def test_empty_value_falls_back_to_firestore(self, monkeypatch):
        monkeypatch.setenv(ENV_VAR, "")
        reset_user_prefs_store_for_testing()
        store = get_user_prefs_store()
        assert not isinstance(store, UserPrefsStore)

    def test_whitespace_value_falls_back_to_firestore(self, monkeypatch):
        monkeypatch.setenv(ENV_VAR, "   ")
        reset_user_prefs_store_for_testing()
        store = get_user_prefs_store()
        assert not isinstance(store, UserPrefsStore)


class TestFactorySingleton:
    """The factory caches the store on first call."""

    def test_singleton_reused(self, monkeypatch):
        monkeypatch.setenv(ENV_VAR, BACKEND_MEMORY)
        reset_user_prefs_store_for_testing()
        store_a = get_user_prefs_store()
        store_b = get_user_prefs_store()
        assert store_a is store_b

    def test_reset_creates_new_instance(self, monkeypatch):
        monkeypatch.setenv(ENV_VAR, BACKEND_MEMORY)
        reset_user_prefs_store_for_testing()
        store_a = get_user_prefs_store()
        reset_user_prefs_store_for_testing()
        store_b = get_user_prefs_store()
        # Different singleton instance (but may share underlying state for memory)
        assert store_a is not store_b


class TestFactoryConstants:
    """The exported constants are correct."""

    def test_env_var_name(self):
        assert ENV_VAR == "AUTO_ROUTER_PREFS_BACKEND"

    def test_default_backend(self):
        assert DEFAULT_BACKEND == "firestore"

    def test_backend_values(self):
        assert BACKEND_FIRESTORE == "firestore"
        assert BACKEND_MEMORY == "memory"
