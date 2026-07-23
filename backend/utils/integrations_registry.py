"""Single source of truth for integration capabilities and connection providers."""

from typing import Any, Dict, Optional, Tuple

GOOGLE_CALENDAR_SCOPE = 'https://www.googleapis.com/auth/calendar'
GOOGLE_CONTACTS_SCOPES = (
    'https://www.googleapis.com/auth/contacts.readonly',
    'https://www.googleapis.com/auth/contacts.other.readonly',
)
GMAIL_READ_SCOPE = 'https://www.googleapis.com/auth/gmail.readonly'


INTEGRATION_PROVIDERS: Dict[str, Dict[str, Any]] = {
    'google_calendar': {
        'name': 'Google Calendar',
        'kind': 'oauth',
        'capabilities': {
            'calendar': (GOOGLE_CALENDAR_SCOPE,),
            'gmail': (GMAIL_READ_SCOPE,),
            'google_mail': (GMAIL_READ_SCOPE,),
            'email': (GMAIL_READ_SCOPE,),
            'contacts': GOOGLE_CONTACTS_SCOPES,
            'google_contacts': GOOGLE_CONTACTS_SCOPES,
        },
        'oauth': {
            'client_id_env': 'GOOGLE_CLIENT_ID',
            'client_secret_env': 'GOOGLE_CLIENT_SECRET',
            'auth_base': 'https://accounts.google.com/o/oauth2/v2/auth',
            'token_endpoint': 'https://oauth2.googleapis.com/token',
            'redirect_path': '/v2/integrations/google-calendar/callback',
            'query': {
                'response_type': 'code',
                'access_type': 'offline',
                'prompt': 'consent',
            },
        },
    },
}


def resolve_integration_provider(key: str) -> Optional[Tuple[str, Dict[str, Any]]]:
    """Resolve a provider key or capability to its connection provider."""
    normalized = key.strip().lower().replace('-', '_')
    for provider_key, provider in INTEGRATION_PROVIDERS.items():
        if normalized == provider_key or normalized in provider['capabilities']:
            return provider_key, provider
    return None


def oauth_scopes(provider: Dict[str, Any]) -> Tuple[str, ...]:
    """Derive one OAuth scope bundle from the provider's declared capabilities."""
    return tuple(
        dict.fromkeys(scope for required_scopes in provider['capabilities'].values() for scope in required_scopes)
    )


def oauth_authorization_query(provider: Dict[str, Any]) -> Dict[str, str]:
    """Build provider OAuth query parameters with the derived scope bundle."""
    query = dict(provider['oauth']['query'])
    query['scope'] = ' '.join(oauth_scopes(provider))
    return query
