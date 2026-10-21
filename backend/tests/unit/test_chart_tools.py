"""Regression tests for ``create_chart_tool`` chart-data attachment.

Covers the three runtime defects reported in the chart-tools bug report:

1. ``chart_data`` silently discarded when ``config`` has no ``'configurable'`` key
   (``config.get('configurable', {})`` returns a detached temporary dict).
2. ``TypeError: 'NoneType' object does not support item assignment`` when
   ``config`` carries ``'configurable': None`` (uninitialized LangChain runnable).
3. ``None`` / string-encoded numeric ``values`` leaking into the frontend wire schema.
"""

import contextvars
import math
from typing import Any, Dict, Optional

import pytest

from utils.retrieval.tools import chart_tools


def _call(**kwargs: Any) -> str:
    """Invoke the underlying tool function, bypassing LLM-schema coercion."""
    func = getattr(chart_tools.create_chart_tool, 'func', chart_tools.create_chart_tool)
    return func(**kwargs)


@pytest.fixture()
def agent_config():
    """Install a private agent-config context var for the duration of a test."""
    var: contextvars.ContextVar[Optional[Dict[str, Any]]] = contextvars.ContextVar(
        'test_agent_config', default=None
    )
    original = chart_tools.agent_config_context
    chart_tools.agent_config_context = var

    def _set(config: Optional[Dict[str, Any]]) -> None:
        var.set(config)

    try:
        yield _set
    finally:
        chart_tools.agent_config_context = original


def test_chart_data_bound_when_configurable_key_absent(agent_config):
    """A config dict without 'configurable' must still receive chart_data."""
    config: Dict[str, Any] = {'user_id': 'user-123'}
    agent_config(config)

    result = _call(
        chart_type='line',
        title='Sleep',
        labels=['Mon', 'Tue'],
        values=[7.2, 6.8],
        dataset_label='Sleep Hours',
    )

    assert 'Chart created' in result
    assert 'configurable' in config, 'configurable dict must be attached to the caller config'
    chart_data = config['configurable']['chart_data']
    assert chart_data['title'] == 'Sleep'
    assert chart_data['datasets'][0]['data_points'] == [
        {'label': 'Mon', 'value': 7.2},
        {'label': 'Tue', 'value': 6.8},
    ]


def test_chart_data_bound_when_configurable_is_none(agent_config):
    """'configurable': None must not raise TypeError on item assignment."""
    config: Dict[str, Any] = {'configurable': None}
    agent_config(config)

    result = _call(
        chart_type='bar',
        title='Steps',
        labels=['Mon'],
        values=[1000.0],
    )

    assert 'Chart created' in result
    assert isinstance(config['configurable'], dict)
    assert config['configurable']['chart_data']['chart_type'] == 'bar'


def test_existing_configurable_dict_is_mutated_in_place(agent_config):
    """A pre-existing configurable mapping is reused, not replaced."""
    existing: Dict[str, Any] = {'thread_id': 'thread-1'}
    config: Dict[str, Any] = {'configurable': existing}
    agent_config(config)

    _call(chart_type='line', title='Heart Rate', labels=['Mon'], values=[62.0])

    assert config['configurable'] is existing
    assert existing['chart_data']['title'] == 'Heart Rate'
    assert existing['thread_id'] == 'thread-1'


def test_none_and_string_values_are_coerced_to_floats(agent_config):
    """LLM-supplied None / numeric strings / non-finite floats become safe floats."""
    config: Dict[str, Any] = {}
    agent_config(config)

    _call(
        chart_type='line',
        title='Mixed',
        labels=['a', 'b', 'c', 'd', 'e'],
        values=[None, '7.2', 'not-a-number', float('nan'), float('inf')],
    )

    points = config['configurable']['chart_data']['datasets'][0]['data_points']
    values = [p['value'] for p in points]
    assert values[0] == 0.0
    assert values[1] == 7.2
    assert values[2] == 0.0
    assert values[3] == 0.0
    assert values[4] == 0.0
    assert all(isinstance(v, float) and math.isfinite(v) for v in values)


def test_none_labels_are_coerced_to_strings(agent_config):
    """A None label must serialize as a string, never as JSON null."""
    config: Dict[str, Any] = {}
    agent_config(config)

    _call(chart_type='bar', title='Labels', labels=[None, 42], values=[1.0, 2.0])  # type: ignore[list-item]

    points = config['configurable']['chart_data']['datasets'][0]['data_points']
    assert points[0]['label'] == ''
    assert points[1]['label'] == '42'


def test_missing_agent_config_does_not_raise(agent_config):
    """With no config in context the tool still reports success."""
    agent_config(None)

    result = _call(chart_type='line', title='No Config', labels=['Mon'], values=[1.0])

    assert 'Chart created' in result


def test_empty_config_dict_is_populated(agent_config):
    """An empty (falsy) config dict is still a valid attachment target."""
    config: Dict[str, Any] = {}
    agent_config(config)

    _call(chart_type='line', title='Empty', labels=['Mon'], values=[1.0])

    assert config['configurable']['chart_data']['title'] == 'Empty'


@pytest.mark.parametrize(
    ('kwargs', 'expected'),
    [
        ({'labels': ['Mon', 'Tue'], 'values': [1.0]}, 'same length'),
        ({'chart_type': 'pie', 'labels': ['Mon'], 'values': [1.0]}, "'line' or 'bar'"),
        ({'labels': [], 'values': []}, 'at least one data point'),
    ],
)
def test_validation_errors_are_preserved(agent_config, kwargs, expected):
    """Existing validation messages keep working and no chart_data is attached."""
    config: Dict[str, Any] = {}
    agent_config(config)

    params: Dict[str, Any] = {'chart_type': 'line', 'title': 'T', 'labels': ['Mon'], 'values': [1.0]}
    params.update(kwargs)

    result = _call(**params)

    assert result.startswith('Error:')
    assert expected in result
    assert 'configurable' not in config
