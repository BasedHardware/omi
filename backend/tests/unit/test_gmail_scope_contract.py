"""Behavioral contract for capability-to-provider OAuth resolution."""

from utils.integrations_registry import (
    GMAIL_READ_SCOPE,
    INTEGRATION_PROVIDERS,
    oauth_authorization_query,
    resolve_integration_provider,
)


def test_google_capabilities_resolve_to_one_provider_with_required_scopes():
    expected = {
        'calendar': 'https://www.googleapis.com/auth/calendar',
        'gmail': GMAIL_READ_SCOPE,
        'email': GMAIL_READ_SCOPE,
        'contacts': 'https://www.googleapis.com/auth/contacts.readonly',
    }

    for capability, required_scope in expected.items():
        resolved = resolve_integration_provider(capability)
        assert resolved is not None
        provider_key, provider = resolved
        assert provider_key == 'google_calendar'
        assert required_scope in oauth_authorization_query(provider)['scope'].split()


def test_provider_resolution_normalizes_agent_and_callback_keys():
    for key in ('Gmail', ' GMAIL ', 'google_mail', 'google-calendar', 'google_calendar'):
        resolved = resolve_integration_provider(key)
        assert resolved is not None
        assert resolved[0] == 'google_calendar'


def test_capabilities_have_one_authoritative_provider():
    capabilities = [
        capability for provider in INTEGRATION_PROVIDERS.values() for capability in provider['capabilities']
    ]
    assert len(capabilities) == len(set(capabilities))
