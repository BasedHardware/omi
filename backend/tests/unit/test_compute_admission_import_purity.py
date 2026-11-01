"""Admission must not load enabled-only dependencies in a flag-off process."""

from tests.unit.fixtures.cap_rollout import full_cap_dispatch_rollout  # noqa: F401

import os
from pathlib import Path
import subprocess
import sys
import textwrap


def test_flags_off_helpers_and_noop_wrappers_do_not_import_compute_dependencies():
    # A fresh interpreter exercises real imports even when other tests have
    # already loaded the dependency graph. No replacement modules/SDK stubs.
    script = textwrap.dedent("""
        import importlib.abc
        import sys

        blocked = (
            'database', 'utils.byok', 'utils.executors', 'utils.subscription',
            'utils.llm', 'utils.stt_cap_dispatch', 'config.rate_card',
            'config.plan_catalog', 'config.ladder_v1',
        )
        attempted = []

        class DisabledDependencyGuard(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if any(fullname == name or fullname.startswith(name + '.') for name in blocked):
                    attempted.append(fullname)
                    raise AssertionError('flag-off dependency import: ' + fullname)

        sys.meta_path.insert(0, DisabledDependencyGuard())
        from utils import generated_compute as generated, funded_processing as funded

        assert generated.generated_compute_allowed(None, 'chat_agent')
        generated.require_generated_compute(None, 'chat_agent')
        assert generated.current_generated_compute_allowed('chat_agent')
        generated.require_current_generated_compute('chat_agent')
        assert funded.processing_allowed('unknown')
        assert generated.current_compute_uid('explicit') == 'explicit'

        response = object()

        @generated.generated_compute_scoped
        @funded.scoped
        def unchanged(uid):
            return response

        with generated.generated_compute_scope('synthetic'):
            assert unchanged('synthetic') is response
        assert not attempted
        assert not any(
            loaded == name or loaded.startswith(name + '.')
            for loaded in sys.modules for name in blocked
        )
        """)
    env = {
        **os.environ,
        'STT_CAP_DISPATCH_ENFORCEMENT': 'false',
        'LADDER_V1_BUDGET_ENFORCEMENT_ENABLED': 'false',
    }
    result = subprocess.run(
        [sys.executable, '-c', script],
        cwd=Path(__file__).resolve().parents[2],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_enabled_non_byok_call_uses_real_budget_owner_without_importing_byok(monkeypatch):
    import builtins
    from unittest.mock import Mock

    from utils import funded_processing, generated_compute

    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    admission = Mock(return_value=False)
    monkeypatch.setattr(funded_processing, 'processing_allowed', admission)
    original = builtins.__import__

    def import_without_byok(name, globals=None, locals=None, fromlist=(), level=0):
        assert name != 'utils.byok' and not (name == 'utils' and 'byok' in (fromlist or ()))
        return original(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, '__import__', import_without_byok)
    client = object()
    assert not generated_compute.generated_compute_allowed(
        'synthetic', 'app_icon', allow_byok=False, firestore_client=client
    )
    admission.assert_called_once_with('synthetic', firestore_client=client)
