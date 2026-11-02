"""A held piece must use the provider named by its durable dispatch intent."""

from unittest.mock import Mock

import pytest

from utils.stt import pre_recorded as stt


@pytest.mark.parametrize('pinned', [False, True])
def test_url_dispatch_preserves_default_selection_or_uses_checkpointed_provider(monkeypatch, pinned):
    monkeypatch.delenv('OMI_STT_STUB', raising=False)
    selection = Mock(return_value=('modulate', 'en', 'velma-2'))
    monkeypatch.setattr(stt, 'get_prerecorded_service', selection)
    modulate, parakeet = Mock(), Mock()
    monkeypatch.setattr(stt, 'ModulatePrerecordedProvider', lambda: modulate)
    monkeypatch.setattr(stt, 'ParakeetPrerecordedProvider', lambda: parakeet)
    options = {'selected_service': ('parakeet', 'multi', 'parakeet')} if pinned else {}
    selected, unused = (parakeet, modulate) if pinned else (modulate, parakeet)
    assert stt.prerecorded('synthetic-url', language='multi', **options) is selected.transcribe_url.return_value
    selected.transcribe_url.assert_called_once_with(
        'synthetic-url',
        speakers_count=None,
        attempts=0,
        return_language=False,
        diarize=True,
        language='multi',
        keywords=None,
    )
    unused.transcribe_url.assert_not_called()
    if pinned:
        selection.assert_not_called()
    else:
        selection.assert_called_once_with('multi')
