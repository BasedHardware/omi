"""A value that only LOOKS set must stop the boot, not the first request (BACKLOG L49/L48).

Measured on a live compose stack: OIDC_ISSUER was still `https://<host>:8443/realms/omi`, straight from
the example file. Nothing rejected it — the OIDC adapter refuses only an EMPTY issuer — so the backend
came up "configured" and every authenticated request was going to fail against an `iss` that cannot
exist. The MCP protected-resource document served that host too.

The tripwire at the bottom is labelled as such: it reads the committed example files rather than
exercising behaviour, and its job is to keep the hand-written variable list from rotting.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from config.placeholder_values import (
    MUST_BE_SUBSTITUTED,
    ConfigurationPlaceholderError,
    find_placeholders,
    validate_configuration_values,
)

REPOSITORY = pathlib.Path(__file__).resolve().parents[3]


@pytest.mark.parametrize(
    'value,expected',
    [
        ('https://<host>:8443/realms/omi', 'an unsubstituted <...> placeholder'),
        ('https://auth.changeme.net/realms/omi', 'the word "CHANGE_ME"'),
        ('https://change-me.example/realms/omi', 'the word "CHANGE_ME"'),
        ('https://your-keycloak/realms/omi', 'a "your-" placeholder'),
        ('https://auth.example.com/realms/omi', 'the documentation domain example.com'),
        ('TODO', 'a TODO marker'),
    ],
)
def test_a_value_that_was_meant_to_be_replaced_is_refused(value, expected):
    (problem,) = find_placeholders({'OIDC_ISSUER': value})

    assert problem.startswith('OIDC_ISSUER still contains')
    assert expected in problem


def test_the_offending_value_is_never_echoed():
    """It fires on the shape, so the value is normally harmless — but the one case where this check is
    surprising is a real secret that happens to contain 'changeme', and a process about to die loudly
    must not put that in the logs."""
    secret = 'sk-live-changeme-9f2b7c'

    (problem,) = find_placeholders({'OPENAI_BASE_URL': secret})

    assert secret not in problem
    assert 'CHANGE_ME' in problem, 'the pattern is named, the value is not'


def test_a_substituted_value_passes():
    assert find_placeholders({'OIDC_ISSUER': 'https://auth.omi.internal:8443/realms/omi'}) == []


def test_an_absent_variable_is_not_this_check_s_business():
    """Presence is a different question, owned by the adapter that needs the value. Reporting it here
    would make every optional profile fail to boot."""
    assert find_placeholders({}) == []
    assert find_placeholders({'OIDC_ISSUER': ''}) == []
    assert find_placeholders({'OIDC_ISSUER': '   '}) == []


def test_an_unsubstituted_secret_is_refused_even_though_it_is_not_on_the_list():
    """The finding that widened this check. Our examples ship ENCRYPTION_SECRET=CHANGE_ME, so an
    operator who misses one line runs with a key that is published in our repository. No list would
    have caught it in time, which is why CHANGE_ME is checked on every variable."""
    for name in ('ENCRYPTION_SECRET', 'OMI_LLM_GATEWAY_SERVICE_TOKEN', 'METRICS_SECRET', 'TYPESENSE_API_KEY'):
        (problem,) = find_placeholders({name: 'CHANGE_ME'})
        assert problem.startswith(f'{name} still contains the word "CHANGE_ME"')


def test_the_weaker_shapes_stay_scoped_to_the_listed_variables():
    """`<...>` can occur inside a chosen password and `example.com` inside a real hostname. Applying
    those everywhere would make the gate cry wolf, and a gate that cries wolf gets an escape hatch."""
    assert find_placeholders({'ENCRYPTION_SECRET': 'a<b>c'}) == []
    assert find_placeholders({'SOME_HOST': 'mail.example.com'}) == []
    assert find_placeholders({'OIDC_ISSUER': 'https://a<b>c/realms/omi'}) != []


def test_every_listed_variable_is_actually_checked():
    """Guards against a name being added to the tuple and silently misspelled."""
    for name in MUST_BE_SUBSTITUTED:
        assert find_placeholders({name: 'https://<host>/x'}), f'{name} is listed but not checked'


# --- ADMIN_KEY: declared empty is weaker than absent ------------------------------------------------


def test_an_empty_admin_key_is_refused():
    (problem,) = find_placeholders({'ADMIN_KEY': ''})

    assert 'ADMIN_KEY is declared EMPTY' in problem


def test_an_absent_admin_key_is_the_correct_configuration():
    """Unset is fail-closed: every admin route requires the header, and no string equals None."""
    assert find_placeholders({}) == []


def test_a_real_admin_key_passes():
    assert find_placeholders({'ADMIN_KEY': '2f6c1b9e4a7d'}) == []


# --- the boot gate ------------------------------------------------------------------------------


def test_the_boot_gate_raises_and_names_every_problem(monkeypatch):
    monkeypatch.setenv('OIDC_ISSUER', 'https://<host>:8443/realms/omi')
    monkeypatch.setenv('ADMIN_KEY', '')

    with pytest.raises(ConfigurationPlaceholderError) as raised:
        validate_configuration_values()

    message = str(raised.value)
    assert 'OIDC_ISSUER' in message and 'ADMIN_KEY' in message


def test_the_boot_gate_is_silent_on_a_substituted_environment(monkeypatch):
    monkeypatch.setenv('OIDC_ISSUER', 'https://auth.omi.internal:8443/realms/omi')
    monkeypatch.delenv('ADMIN_KEY', raising=False)

    validate_configuration_values()


# --- static tripwire ------------------------------------------------------------------------------


def test_every_placeholder_our_examples_ship_belongs_to_a_checked_variable():
    """STATIC CHECK (reads files, does not exercise behaviour).

    Scoped to the SITE_SPECIFIC shapes: CHANGE_ME is checked on every variable, so no list can go stale
    for it. These four are list-scoped, and the list is a fact about the committed example files —
    facts about files rot. An example that grows one of them for an unchecked variable reopens the gap
    this module exists to close, so it fails here, naming the file and line.
    """
    placeholder = re.compile(r'<[^>]*>|\byour[-_]|\bexample\.com\b|\bTODO\b', re.IGNORECASE)
    offenders = []

    for path in sorted((REPOSITORY / 'deploy' / 'onprem').glob('*.example')):
        for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
            stripped = line.strip()
            if not stripped or stripped.startswith('#') or '=' not in stripped:
                continue
            name, _, value = stripped.partition('=')
            if placeholder.search(value) and name not in MUST_BE_SUBSTITUTED:
                offenders.append(f'{path.name}:{number} {name}')

    assert not offenders, 'example files ship a placeholder for an unchecked variable:\n  ' + '\n  '.join(offenders)
