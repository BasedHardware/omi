"""Gateway routing config and validation helpers."""

from llm_gateway.gateway.config_loader import ConfigValidationError, GatewayConfig, load_gateway_config
from llm_gateway.gateway.user_prefs import ObjectiveOverrides, UserPrefs
from llm_gateway.gateway.user_prefs_store import (
    FirestoreUserPrefsStore,
    InMemoryUserPrefsStore,
    StoredPrefs,
    UserPrefsStore,
    UserPrefsStoreError,
    get_user_prefs_store,
    reset_user_prefs_store_for_testing,
    set_user_prefs_store,
)

__all__ = [
    'ConfigValidationError',
    'GatewayConfig',
    'load_gateway_config',
    'ObjectiveOverrides',
    'UserPrefs',
    'StoredPrefs',
    'UserPrefsStore',
    'UserPrefsStoreError',
    'InMemoryUserPrefsStore',
    'FirestoreUserPrefsStore',
    'get_user_prefs_store',
    'set_user_prefs_store',
    'reset_user_prefs_store_for_testing',
]
