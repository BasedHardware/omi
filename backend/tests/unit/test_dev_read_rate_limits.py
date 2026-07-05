"""Every Developer API read GET route must enforce a per-key read rate limit (issue #8713).

The dev read policies (dev:conversations_read, dev:action_items_read, dev:goals_read) already
exist in rate_limit_config, but the GET routes were declared with a bare scope dependency and
no rate limit, so a single API key could poll them unbounded. This guards that each read
dependency is wrapped with with_rate_limit and its intended policy.

routers.developer builds a typesense client at import, so it cannot be imported in a bare unit
test; this reads the source and asserts the wiring, matching the issue's acceptance criterion.
"""

from pathlib import Path

_DEV = Path(__file__).resolve().parents[2] / 'routers' / 'developer.py'


def _developer_source() -> str:
    return _DEV.read_text(encoding='utf-8')


def test_dev_read_routes_are_rate_limited():
    src = _developer_source()
    # No read GET route may use the bare scope dependency; each must be rate-limited.
    for dep in ('get_uid_with_conversations_read', 'get_uid_with_action_items_read', 'get_uid_with_goals_read'):
        assert f'Depends({dep})' not in src, f'{dep} is used as a dependency without a rate limit'


def test_dev_read_routes_use_intended_policies():
    src = _developer_source()
    assert 'with_rate_limit(get_uid_with_conversations_read, "dev:conversations_read")' in src
    assert 'with_rate_limit(get_uid_with_action_items_read, "dev:action_items_read")' in src
    assert 'with_rate_limit(get_uid_with_goals_read, "dev:goals_read")' in src
