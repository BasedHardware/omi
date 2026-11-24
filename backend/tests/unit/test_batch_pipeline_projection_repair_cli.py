"""Operator repair keeps prod silence skipping held off without explicit CLI admission."""

from types import SimpleNamespace
from unittest.mock import Mock
import sys

import pytest

from config.batch_pipeline import silence_read_skip_enabled
from scripts import batch_pipeline_projection_repair as repair


@pytest.mark.parametrize('inherited', [None, 'true', 'false', 'off', '0'])
@pytest.mark.parametrize('opt_in', [False, True])
def test_prod_repair_requires_cli_opt_in_even_with_inherited_true(monkeypatch, capsys, inherited, opt_in):
    key = 'BATCH_PIPELINE_SILENCE_READ_SKIP_ENABLED'
    monkeypatch.delenv(key, raising=False)
    if inherited is not None:
        monkeypatch.setenv(key, inherited)
    monkeypatch.delenv('FIRESTORE_EMULATOR_HOST', raising=False)
    monkeypatch.setenv('GCP_AGENT_TIER', 'prod-operator')
    monkeypatch.setenv('SYNTHETIC_OWNER', 'synthetic-owner')
    argv = ['repair', '--stage', 'prod', '--owner-env', 'SYNTHETIC_OWNER', '--apply', '--approve-plan-sha256', 'plan']
    if opt_in:
        argv.append('--enable-silence-read-skip')
    monkeypatch.setattr(sys, 'argv', argv)
    client, store = object(), object()
    monkeypatch.setattr(repair, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(repair, 'FirestoreStore', lambda namespace, **kwargs: store)
    monkeypatch.setattr(
        repair, 'plan_owner', lambda *a, **kw: {'units': ['unit'], 'plan_sha256': 'plan', 'unpinned_units': 0}
    )
    monkeypatch.setattr(repair, 'configure_rollout_runtime', lambda: None)
    monkeypatch.setattr(repair, 'artifacts_for', lambda _: SimpleNamespace(load_result=Mock(), fetch_audio=Mock()))
    admitted = []

    def projector(*args, **kwargs):
        admitted.append(silence_read_skip_enabled())
        return object()

    monkeypatch.setattr(repair, 'Projector', projector)
    monkeypatch.setattr(repair, 'apply_owner', lambda *a: {'completed': 1})
    repair.main()
    assert admitted == [opt_in]
    assert silence_read_skip_enabled() is opt_in
    assert 'synthetic-owner' not in capsys.readouterr().out
