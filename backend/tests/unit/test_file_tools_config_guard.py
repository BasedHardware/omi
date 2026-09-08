"""Regression test: search_files_tool must not crash on a config missing 'configurable'.

utils.retrieval.tools.file_tools.search_files_tool reads the agent config with
`configurable = cfg.get('configurable'); uid = configurable.get('user_id')`. When the
'configurable' key is absent (but cfg is a dict), get returns None and None.get raises
AttributeError, which the `except (KeyError, TypeError)` did NOT catch, so it escaped uncaught and
broke the chat turn instead of returning the intended error string. The six sibling retrieval
tools all catch AttributeError here; file_tools was the lone omission. AttributeError is now caught.
"""

import utils.retrieval.tools.file_tools as mod


def test_missing_configurable_returns_error_not_crash():
    # cfg is a dict but has no 'configurable' key -> cfg.get('configurable') is None ->
    # None.get('user_id') is an AttributeError that must be caught and surfaced as an error string.
    result = mod.search_files_tool.func(question="x", config={"foo": "bar"})

    assert isinstance(result, str)
    assert result.startswith("Error: Configuration error")
