"""The realm a deployment RUNS is chosen by the installer, not by the repository (ADR-0082, BACKLOG L47).

The Helm chart used to carry a committed copy of the DEV realm — `files/omi-realm.dev.json`, with the
`omi-test` client and `testuser` — and the template mounted it unconditionally. So the installation we
document as production (`helm/MANUAL-prod-k0s.md`) came up with a well-known credential. Measured on the
live k0s release on 2026-08-22, from inside the cluster:

    POST /realms/omi/protocol/openid-connect/token
         grant_type=password client_id=omi-test username=testuser password=testpass   ->  200

Compose already separated the two realms per environment; the chart had one slot and it held the wrong
one. The deeper reason is that the committed file was also the executed file, so "which realm is live"
was a property of the repo rather than of the installation — the same shape as every other env file,
solved the same way: commit examples, copy one into the runtime name, gitignore the runtime name.

STATIC CHECKS. They read the declarative config; they do not stand up a Keycloak. What they can hold is
the property that broke — no executable realm in the repository, and both consumers reading the runtime
name and refusing to proceed without it.
"""

from __future__ import annotations

import json
import pathlib
import subprocess

import pytest

REPOSITORY = pathlib.Path(__file__).resolve().parents[3]
ONPREM = REPOSITORY / 'deploy' / 'onprem'
CHART = ONPREM / 'helm' / 'omi-oss'

RUNTIME_NAMES = ('deploy/onprem/keycloak/omi-realm.json', 'deploy/onprem/helm/omi-oss/files/omi-realm.json')


def _tracked(path: str) -> bool:
    result = subprocess.run(
        ['git', 'ls-files', '--error-unmatch', path], cwd=REPOSITORY, capture_output=True, text=True
    )
    return result.returncode == 0


@pytest.mark.parametrize('path', RUNTIME_NAMES)
def test_no_runtime_realm_is_committed(path):
    """The file a deployment executes must not be in the repository. Committing it is what put the dev
    realm on the prod install."""
    assert not _tracked(path), f'{path} is tracked — the runtime realm must be gitignored (ADR-0082)'


def test_the_dev_realm_copy_is_gone_from_the_chart():
    assert not (CHART / 'files' / 'omi-realm.dev.json').exists(), 'the chart must not carry a realm of its own'


def test_both_examples_are_committed_and_differ_in_the_way_that_matters():
    """The whole point of two examples: one has test principals, the other must not. If they ever stop
    differing, choosing between them is theatre."""
    prod = json.loads((ONPREM / 'keycloak' / 'omi-realm.example.json').read_text(encoding='utf-8'))
    dev = json.loads((ONPREM / 'keycloak' / 'omi-realm.dev.example.json').read_text(encoding='utf-8'))

    dev_clients = {client['clientId'] for client in dev.get('clients', [])}
    prod_clients = {client['clientId'] for client in prod.get('clients', [])}
    dev_users = {user['username'] for user in dev.get('users', [])}
    prod_users = {user['username'] for user in prod.get('users', [])}

    assert 'omi-test' in dev_clients and 'testuser' in dev_users, 'the dev realm is the one WITH test principals'
    assert 'omi-test' not in prod_clients, 'the prod realm must not ship the test client'
    assert 'testuser' not in prod_users, 'the prod realm must not ship the test user'
    assert prod['realm'] == dev['realm'] == 'omi', 'both must seed the same realm name'


def test_the_chart_reads_the_runtime_name_and_refuses_without_it():
    text = (CHART / 'templates' / 'keycloak-realm-configmap.yaml').read_text(encoding='utf-8')

    assert '.Files.Get "files/omi-realm.json"' in text, 'the chart must read the runtime name'
    assert 'omi-realm.dev.json' not in text
    assert '{{-   fail ' in text, 'a missing realm must fail the render, not produce an empty ConfigMap'


@pytest.mark.parametrize('compose', ['compose.prod.yaml', 'compose.dev.yaml', 'compose.seed.yaml'])
def test_every_compose_mount_uses_the_runtime_name_and_refuses_to_invent_it(compose):
    """`create_host_path: false` is the compose-side equivalent of the chart's `fail`: without it Docker
    creates a DIRECTORY where the missing file should be, and Keycloak imports nothing — a silent success
    is exactly what this change is about."""
    text = (ONPREM / compose).read_text(encoding='utf-8')

    assert 'source: ./keycloak/omi-realm.json' in text, f'{compose} must mount the runtime name'
    assert 'omi-realm.example.json:' not in text and 'omi-realm.dev.example.json:' not in text
    mount = text[text.index('source: ./keycloak/omi-realm.json') :]
    assert 'create_host_path: false' in mount[:400], f'{compose} would silently create an empty directory'
