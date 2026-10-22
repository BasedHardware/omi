"""The episode prompt consumes L3's authority without a second model call."""

import sys
from types import ModuleType
from unittest.mock import Mock

from utils.episodes.output_language import resolved_invoke


def test_episode_language_comes_from_l3_only_for_serve(monkeypatch):
    authority = ModuleType('utils.llm.output_language')
    authority.resolve_output_language = Mock(return_value='English')
    monkeypatch.setitem(sys.modules, 'utils.llm.output_language', authority)
    invoke = Mock(return_value='fixture')
    monkeypatch.setenv('LIFECYCLE_V2_MODE', 'shadow')
    assert resolved_invoke('test-account', 'en', invoke) is invoke
    authority.resolve_output_language.assert_not_called()
    monkeypatch.setenv('LIFECYCLE_V2_MODE', 'serve')
    call = resolved_invoke('test-account', 'en', invoke)
    assert call('test-account', [('system', 'fixture prompt')]) == 'fixture'
    authority.resolve_output_language.assert_called_once_with('test-account', 'en')
    invoke.assert_called_once()
    assert invoke.call_args.args[1][-1] == ('system', 'Write all episode output in English.')
