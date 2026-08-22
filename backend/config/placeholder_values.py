"""Refuse configuration that LOOKS set and is not (BACKLOG L49).

The existing checks ask whether a variable is present. That is not the same question as whether its
value can work, and the gap is where a self-host breaks silently:

    OIDC_ISSUER=https://<host>:8443/realms/omi

is what ``backend.env.prod.example`` ships, with ``<host>`` meant to be substituted. Measured on a live
compose stack, it had not been: the backend booted "configured", ``utils/auth/adapters/oidc.py`` accepted
it (it rejects only an EMPTY issuer), and the failure waited for the first authenticated request, where
a real token's ``iss`` can never match that string. It also propagates — the MCP protected-resource
document advertises the issuer, so the discovery we serve named a host that does not exist.

Widening it produced the sharper finding. Our own examples ship ``ENCRYPTION_SECRET=CHANGE_ME``,
``OMI_LLM_GATEWAY_SERVICE_TOKEN=CHANGE_ME``, ``METRICS_SECRET=CHANGE_ME``,
``MEMORY_V3_CURSOR_SECRET=CHANGE_ME`` and ``TYPESENSE_API_KEY=CHANGE_ME``. An operator who copies a file
and misses one is not running with a weak secret: they are running with a PUBLISHED one, their data
encrypted under a key that is in our repository. So the unmistakable pattern is checked on EVERY
variable, not on a list somebody has to remember to extend.

Three shapes are refused here, all "declared, and the declaration is worse than absence":

  CHANGE_ME anywhere    on every variable -- no real value looks like that
  a site placeholder    ``<...>``, ``your-``, ``example.com``, ``TODO``, on the variables that must be
                        substituted per site (these shapes CAN appear inside a legitimate value)
  an empty ADMIN_KEY    unset is fail-closed -- every admin route requires the header, and no string
                        matches ``None``. Declared EMPTY it is not: the bare
                        ``secret_key != os.getenv('ADMIN_KEY')`` form used by memory_admin, apps,
                        notifications and updates then accepts an empty ``secret_key:`` header
                        (measured). Two routes already carry the hardened ``if not admin_key or ...``
                        form; the rest do not, and that divergence is upstream's. Refusing the empty
                        declaration is ours, and it is the whole exposure (BACKLOG L48).

Fail fast at boot, like ``validate_push_configuration`` and ``validate_vector_dimension``: a
configuration error should stop the process that cannot serve, not surface as a puzzling 401 an hour
later.
"""

from __future__ import annotations

import os
import re

# Variables whose value is site-specific and whose examples therefore ship a placeholder. Kept explicit
# rather than scanning every variable in the environment: a generated password may legitimately contain
# any of these substrings, and a config gate that cries wolf gets an escape hatch added to it.
#
# `tests/unit/test_placeholder_values.py` recomputes this from the committed *.example files and fails
# if one ships a placeholder for a variable that is not listed -- a hand-written list is a fact about
# those files, and facts about files rot.
MUST_BE_SUBSTITUTED = (
    'OIDC_ISSUER',
    'OIDC_JWKS_URL',
    'OIDC_AUDIENCE',
    'MCP_RESOURCE_URL',
    'MCP_AUTHORIZATION_SERVER_URL',
    'OPENAI_BASE_URL',
    'OMI_EMBEDDINGS_BASE_URL',
    'HOSTED_PARAKEET_API_URL',
    'HOSTED_TRANSLATION_API_URL',
    'HOSTED_SPEAKER_EMBEDDING_API_URL',
    'UNIFIEDPUSH_PUBLIC_BASE_URL',
    'UNIFIEDPUSH_INTERNAL_BASE_URL',
)

# Two tiers, because the patterns are not equally safe to apply everywhere.
#
# UNMISTAKABLE runs against EVERY variable. No real value is "CHANGE_ME", and the variables that matter
# most here are exactly the ones no list would have caught in time: our own examples ship
# ``ENCRYPTION_SECRET=CHANGE_ME``, ``OMI_LLM_GATEWAY_SERVICE_TOKEN=CHANGE_ME``,
# ``METRICS_SECRET=CHANGE_ME``, ``MEMORY_V3_CURSOR_SECRET=CHANGE_ME``, ``TYPESENSE_API_KEY=CHANGE_ME``.
# An operator who copies the file and misses one is not running with a weak secret, they are running
# with a PUBLISHED one -- their data encrypted under a key that is in our repository.
UNMISTAKABLE_PATTERNS: tuple[tuple[str, str], ...] = (('the word "CHANGE_ME"', r'(?i)change[-_]?me'),)

# SITE_SPECIFIC runs only against MUST_BE_SUBSTITUTED. These shapes CAN occur inside a legitimate value
# -- a chosen password may contain angle brackets, a real host may be a subdomain of a customer's
# example.net -- so applying them everywhere would make the gate cry wolf, and a gate that cries wolf
# gets an escape hatch added to it.
SITE_SPECIFIC_PATTERNS: tuple[tuple[str, str], ...] = (
    ('an unsubstituted <...> placeholder', r'<[^>]*>'),
    ('a "your-" placeholder', r'(?i)\byour[-_]'),
    ('the documentation domain example.com', r'(?i)\bexample\.com\b'),
    ('a TODO marker', r'\bTODO\b'),
)

# Kept for callers/tests that want the whole vocabulary in one place.
PLACEHOLDER_PATTERNS = UNMISTAKABLE_PATTERNS + SITE_SPECIFIC_PATTERNS


class ConfigurationPlaceholderError(RuntimeError):
    """A variable is set to something that was meant to be replaced."""


def find_placeholders(environment: dict[str, str] | None = None) -> list[str]:
    """Human-readable problems, one per offending variable. Empty means the environment is plausible."""
    env = environment if environment is not None else dict(os.environ)
    problems: list[str] = []

    for name, raw in sorted(env.items()):
        value = (raw or '').strip()
        if not value:
            continue  # absent is a different question, and other checks own it
        patterns = UNMISTAKABLE_PATTERNS
        if name in MUST_BE_SUBSTITUTED:
            patterns = patterns + SITE_SPECIFIC_PATTERNS
        for description, pattern in patterns:
            if re.search(pattern, value):
                problems.append(
                    f'{name} still contains {description} — substitute it for this deployment. '
                    f'A value that only LOOKS set fails at the first request that needs it, not here.'
                )
                break

    if 'ADMIN_KEY' in env and not (env.get('ADMIN_KEY') or '').strip():
        problems.append(
            'ADMIN_KEY is declared EMPTY, which is weaker than not declaring it: the admin routes that '
            'compare `secret_key != os.getenv("ADMIN_KEY")` then accept an empty secret_key header. '
            'Remove the line, or set a real key (openssl rand -hex 24).'
        )

    return problems


def validate_configuration_values() -> None:
    """Raise if the environment carries a value that was meant to be replaced. Called at boot."""
    problems = find_placeholders()
    if problems:
        raise ConfigurationPlaceholderError(
            'configuration values that were meant to be substituted are still in place:\n  ' + '\n  '.join(problems)
        )
