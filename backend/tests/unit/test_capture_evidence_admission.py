"""CAPTURE_EVIDENCE_V1_DARK_WRITE (S1) admission.

S1 is admitted on every host that receives or consumes capture evidence
(listen receipts, sync upload claims, sync workers). Mobile release builds opt
in with a dart-define; code stays default off. Keeps this file import-light so
the fast-unit duration guard stays honest.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from config.capture_evidence import capture_evidence_dark_write_enabled

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / 'backend'
FLAG = 'CAPTURE_EVIDENCE_V1_DARK_WRITE'

S1_SERVICES = (
    'gke/backend-listen',
    'cloud_run/backend',
    'cloud_run/backend-sync',
    'cloud_run/backend-sync-backfill',
    'cloud_run/backend-integration',
)


def test_code_default_stays_off(monkeypatch):
    monkeypatch.delenv(FLAG, raising=False)
    assert capture_evidence_dark_write_enabled() is False


def test_composed_declarations_admit_s1_on_evidence_hosts():
    composed = yaml.safe_load((BACKEND / 'deploy/runtime_env.yaml').read_text(encoding='utf-8'))
    for environment in ('dev', 'prod'):
        env = composed['environments'][environment]
        scopes = {
            'gke/backend-listen': env['gke']['backend-listen']['env'],
            **{f'cloud_run/{name}': service['env'] for name, service in env['cloud_run']['services'].items()},
        }
        for scope in S1_SERVICES:
            entry = scopes[scope].get(FLAG)
            assert entry is not None, f'{environment}/{scope} must declare {FLAG}'
            assert (entry.get('value') or '').strip().lower() == 'true', f'{environment}/{scope} must admit S1'


def test_prod_listen_helm_values_admit_s1():
    text = (BACKEND / 'charts/backend-listen/prod_omi_backend_listen_values.yaml').read_text(encoding='utf-8')
    lines = [line.strip() for line in text.splitlines()]
    index = lines.index(f'- name: {FLAG}')
    assert lines[index + 1] == 'value: "true"'


def test_mobile_release_builds_send_s1():
    text = (ROOT / 'codemagic.yaml').read_text(encoding='utf-8')
    builds = [chunk for chunk in text.split('flutter build ')[1:] if chunk.startswith(('ipa', 'appbundle'))]
    assert builds, 'codemagic.yaml must define mobile release builds'
    for build in builds:
        command = build.split('$PROVENANCE_ARGS', 1)[0]
        assert f'--dart-define={FLAG}=true' in command, 'every mobile release build must opt in to S1'
