"""Registered screen-tool regressions for multi-device observation intervals."""

from datetime import datetime, timedelta

import pytest


@pytest.fixture(scope='module')
def screen_tool():
    from testing.import_isolation import AutoMockModule, stub_modules

    # The screen reader is real; isolate unrelated import-time datastore/auth
    # dependencies without constructing cloud clients for this focused suite.
    names = [
        'database._client',
        'database.chat',
        'database.daily_summaries',
        'database.goals',
        'database.users',
        'database.vector_db',
        'database.x_posts',
        'database.person_aliases',
        'utils.memory.product_authorization',
        'utils.memory.default_read_rollout',
        'utils.mcp_server.handlers.action_items',
        'utils.mcp_server.handlers.conversations',
        'utils.mcp_server.handlers.memories',
        'utils.mcp_server.handlers.profile',
    ]
    stubs = {name: AutoMockModule(name) for name in names}
    stubs['utils.memory.product_authorization'].ProductAuthorizationContext = type(
        'ProductAuthorizationContext', (), {}
    )
    stubs['utils.memory.default_read_rollout'].MemoryReadDecision = type('MemoryReadDecision', (), {})
    with stub_modules(stubs):
        from utils.mcp_server import registry
        from utils.mcp_server.handlers import other

        yield registry, other


def row(seconds, device='a', app='Browser', **fields):
    return {
        'timestamp': (datetime(2026, 11, 1, 9) + timedelta(seconds=seconds)).isoformat(
            sep=' ', timespec='milliseconds'
        ),
        'appName': app,
        'windowTitle': 'Synthetic',
        **({'clientDeviceId': device} if device is not None else {}),
        **fields,
    }


@pytest.mark.parametrize(
    'rows, expected',
    [
        ([row(0), row(240)], {'Browser': 240}),
        ([row(0), row(240, 'b')], {'Browser': 0}),
        ([row(0), row(120, 'b', 'Editor'), row(240)], {'Browser': 240, 'Editor': 0}),
        ([row(0), row(30, 'b'), row(60), row(90, 'b')], {'Browser': 90}),
        ([row(0), row(0, 'b'), row(60), row(60, 'b')], {'Browser': 60}),
        ([row(0), row(20, 'b'), row(40, 'b'), row(60)], {'Browser': 60}),
        ([row(0), row(60), row(120, 'b'), row(180, 'b')], {'Browser': 120}),
        ([row(0), row(1.6), row(3, 'b'), row(4.6, 'b')], {'Browser': 2}),
        ([row(0), row(30, app='Editor'), row(60)], {'Browser': 0, 'Editor': 0}),
        ([row(0), row(301)], {'Browser': 0}),
        ([row(0), row(300)], {'Browser': 300}),
        ([row(0, deviceName='Shared name'), row(60, 'b', deviceName='Shared name')], {'Browser': 0}),
        ([row(0, None, deviceName='A'), row(60, None, deviceName='B')], {'Browser': 0}),
        ([row(0, None), row(60, None)], {'Browser': 60}),
        ([row(0, None), row(60)], {'Browser': 0}),
        ([row(0), row(0.6), row(1.2)], {'Browser': 0}),
        ([row(0), row(1.6), row(3.2)], {'Browser': 2}),
    ],
    ids=[
        'single-device',
        'isolated-devices',
        'interleaved-other-app',
        'partial-overlap',
        'identical-overlap',
        'nested-overlap',
        'disjoint-devices',
        'disjoint-fractional-credit',
        'same-device-app-switch',
        'over-gap-limit',
        'at-gap-limit',
        'device-id-beats-name',
        'fallback-device-names',
        'legacy-unknown',
        'unknown-is-not-named',
        'fractional-zero-credit',
        'fractional-whole-second-credit',
    ],
)
def test_registered_tool_observation_intervals(screen_tool, monkeypatch, rows, expected):
    registry, other = screen_tool
    monkeypatch.setattr(other.screen_activity_db, 'get_screen_activity', lambda *args, **kwargs: rows)

    for group_by in ('app', 'hour', 'day'):
        result = registry.execute_tool('synthetic-owner', 'get_screen_activity', {'group_by': group_by})
        buckets = result['buckets']
        if group_by == 'app':
            assert {bucket['app']: bucket['estimated_observation_seconds'] for bucket in buckets} == expected
        else:
            assert sum(bucket['estimated_observation_seconds'] for bucket in buckets) == sum(expected.values())
        assert sum(bucket['count'] for bucket in buckets) == len(rows)
        assert sum(title['count'] for bucket in buckets for title in bucket['top_titles']) == len(rows)
        assert result['coverage']['scanned_count'] == len(rows)
        assert result['coverage']['query_complete'] is True
        assert result['coverage']['capture_completeness'] == 'unknown'
        assert result['coverage']['complete_window'] is False
        assert 'next_cursor' not in result


@pytest.mark.parametrize('device, expected', [('a', 60), ('b', 0)])
def test_legacy_helper_seed_uses_its_own_device(screen_tool, device, expected):
    _, other = screen_tool
    buckets = other._screen_activity_buckets([row(60, device)], 'app', seed_row=row(0))
    assert buckets[0]['estimated_observation_seconds'] == expected


def test_time_bucket_unions_observations_across_apps(screen_tool, monkeypatch):
    registry, other = screen_tool
    rows = [row(0), row(30, 'b', 'Editor'), row(60), row(90, 'b', 'Editor')]
    monkeypatch.setattr(other.screen_activity_db, 'get_screen_activity', lambda *args, **kwargs: rows)
    for group_by, expected in [('app', 120), ('hour', 90), ('day', 90)]:
        result = registry.execute_tool('synthetic-owner', 'get_screen_activity', {'group_by': group_by})
        assert sum(bucket['estimated_observation_seconds'] for bucket in result['buckets']) == expected


def test_registered_tool_keeps_local_hour_metadata(screen_tool, monkeypatch):
    registry, other = screen_tool
    rows = [row(0), row(60)]
    monkeypatch.setattr(other.screen_activity_db, 'get_screen_activity', lambda *args, **kwargs: rows)
    result = registry.execute_tool(
        'synthetic-owner', 'get_screen_activity', {'group_by': 'hour', 'timezone': 'America/New_York'}
    )
    bucket = result['buckets'][0]
    assert bucket['hour'] == '2026-11-01T04:00:00-05:00'
    assert bucket['first_seen'] == '2026-11-01T04:00:00-05:00'
    assert bucket['last_seen'] == '2026-11-01T04:01:00-05:00'
    assert bucket['estimated_observation_seconds'] == 60
    assert result['coverage']['devices'][0]['device_id'] == 'a'
