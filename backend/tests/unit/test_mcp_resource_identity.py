"""The MCP discovery document must name THIS deployment, not upstream's (BACKLOG L48).

`/.well-known/oauth-protected-resource` is how an MCP client learns two things: which authorization
server to get a token from, and which resource that token is for. The two halves had opposite policies:

    authorization_servers   under AUTH_BACKEND=oidc, FAILS with 501 when OIDC_ISSUER is missing —
                            "a misconfiguration should surface, not silently mislead"
    resource                falls back to the code default, which is upstream's own endpoint
                            https://api.omi.me/v1/mcp/sse (database/mcp_oauth.py)

Measured on a live self-host, the served document therefore named OUR issuer and UPSTREAM's resource: a
client following it would have asked our Keycloak for a token audienced to Omi's cloud. Nothing was
wrong with the code — nobody had declared the variable, and the default is upstream's because upstream
wrote it. Both of our deployment targets declare it now.
"""

from __future__ import annotations

import pathlib
import re

import pytest

REPOSITORY = pathlib.Path(__file__).resolve().parents[3]
ONPREM = REPOSITORY / 'deploy' / 'onprem'


def test_the_document_reports_the_configured_resource(monkeypatch):
    from routers import mcp_sse

    monkeypatch.setenv('AUTH_BACKEND', 'oidc')
    monkeypatch.setenv('OIDC_ISSUER', 'https://auth.omi.internal/realms/omi')
    monkeypatch.setattr(mcp_sse, 'MCP_RESOURCE_URL', 'https://omi.internal/v1/mcp/sse')

    document = mcp_sse.oauth_protected_resource_metadata()

    assert document['resource'] == 'https://omi.internal/v1/mcp/sse'
    assert document['authorization_servers'] == ['https://auth.omi.internal/realms/omi']


def test_the_code_default_is_upstreams_endpoint():
    """Pins WHY the declaration has to exist. If upstream ever makes this default neutral, this test
    fails and the two env declarations become optional rather than load-bearing — which is a fact worth
    being told, not one to discover by reading."""
    from database.mcp_oauth import PRODUCTION_MCP_RESOURCE_URL

    assert 'omi.me' in PRODUCTION_MCP_RESOURCE_URL, PRODUCTION_MCP_RESOURCE_URL


# --- the two deployment targets -------------------------------------------------------------------
#
# STATIC CHECKS (they read the declarative config, they do not exercise it). The behaviour they stand in
# for is verified live on both targets before release — a rendered ConfigMap and a served document.


def test_the_compose_example_declares_it():
    text = (ONPREM / 'backend.env.prod.example').read_text(encoding='utf-8')

    assignments = [line for line in text.splitlines() if line.strip().startswith('MCP_RESOURCE_URL=')]

    assert len(assignments) == 1, 'compose must declare the resource identity exactly once'
    assert 'omi.me' not in assignments[0], 'the example must not point a self-host at upstream'
    assert '/v1/mcp/sse' in assignments[0]


def test_the_chart_declares_it_outside_the_auth_profile():
    """A firebase-backed self-host advertises upstream's URL just the same, so this cannot hang off
    `auth.enabled`."""
    text = (ONPREM / 'helm' / 'omi-oss' / 'templates' / 'backend-configmap.yaml').read_text(encoding='utf-8')

    (assignment,) = [line for line in text.splitlines() if line.strip().startswith('MCP_RESOURCE_URL:')]

    assert '{{ . }}/v1/mcp/sse' in assignment, 'the value must come from the enclosing hostname block'
    assert '{{- with (include "omi-oss.apiHostname" .) }}' in text, 'and that block must be apiHostname'
    assert text.index('MCP_RESOURCE_URL:') < text.index(
        '{{- if .Values.auth.enabled }}'
    ), 'it must not sit inside the auth profile'


@pytest.mark.parametrize('example', ['backend.env.prod.example'])
def test_the_declared_value_is_site_specific_and_therefore_gated(example):
    """It carries a <host> placeholder, which is only safe because ADR-0083 stops the boot on one —
    otherwise the fix would have replaced a wrong URL with a differently wrong URL."""
    from config.placeholder_values import MUST_BE_SUBSTITUTED

    text = (ONPREM / example).read_text(encoding='utf-8')
    (assignment,) = [line for line in text.splitlines() if line.strip().startswith('MCP_RESOURCE_URL=')]

    assert re.search(r'<[^>]+>', assignment), 'the example is site-specific; it should show a placeholder'
    assert 'MCP_RESOURCE_URL' in MUST_BE_SUBSTITUTED, 'a placeholder nobody checks is the L49 defect again'
