"""Local failure attribution is bounded, content-free and behavior-neutral."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from utils.stt import local_send_diagnostics as diagnostics


@pytest.mark.parametrize('phase', sorted(diagnostics.PHASES))
def test_local_send_failure_never_logs_exception_message_or_socket_content(caplog, phase):
    raw = SimpleNamespace(is_connection_dead=False, _closed=False, cap_dispatch_socket=True)
    counter = diagnostics.LOCAL_SEND_FAILURES.labels(provider='parakeet', phase=phase, exception_class='TypeError')
    before = counter._value.get()
    diagnostics.record_local_send_failure('parakeet', phase, raw, TypeError('secret transcript and private endpoint'))
    assert counter._value.get() == before + 1
    assert 'exception_class=TypeError' in caplog.text
    assert 'raw_dead=false raw_closed=false proxy=cap' in caplog.text
    assert 'secret transcript' not in caplog.text
    assert 'private endpoint' not in caplog.text


def test_unknown_labels_collapse_and_diagnostic_failure_never_raises(monkeypatch, caplog):
    class PrivateError(Exception):
        pass

    diagnostics.record_local_send_failure('private-provider', 'private-phase', object(), PrivateError('private'))
    assert 'provider=other phase=other exception_class=other' in caplog.text
    broken = Mock(side_effect=RuntimeError('metrics unavailable'))
    monkeypatch.setattr(diagnostics.LOCAL_SEND_FAILURES, 'labels', broken)
    diagnostics.record_local_send_failure('parakeet', 'raw_refused', object())
