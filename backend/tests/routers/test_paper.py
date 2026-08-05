"""PAPER router — the thin layer between the request and ``build_edition``.

Building an edition is expensive: several model calls, an image generation and
a set of web searches. Both routes therefore run behind a per-UID rate limit,
and the tests below assert that wiring rather than trusting it, because a route
that quietly loses its limiter looks identical to one that has it.
"""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.paper import Edition, EditionTier, Yesterday
from routers import paper as paper_router
from utils.rate_limit_config import RATE_POLICIES


def _edition():
    return Edition(
        date='2026-06-11',
        issue_number=7,
        yesterday=Yesterday(headline='Billing Migration Closed', source_date='2026-06-10'),
    )


@pytest.mark.asyncio
async def test_get_paper_returns_the_built_edition():
    built = _edition()
    build_edition = AsyncMock(return_value=built)

    with patch.object(paper_router, 'build_edition', build_edition), patch.object(
        paper_router.daily_summaries_db, 'get_daily_summaries', MagicMock(return_value=[{}] * 7)
    ):
        result = await paper_router.get_paper(date=date(2026, 6, 11), tier=EditionTier.EDITION, uid='uid1')

    assert result is built
    build_edition.assert_awaited_once_with('uid1', date(2026, 6, 11), tier=EditionTier.EDITION, issue_number=7)


@pytest.mark.asyncio
async def test_render_returns_the_edition_as_html():
    build_edition = AsyncMock(return_value=_edition())

    with patch.object(paper_router, 'build_edition', build_edition), patch.object(
        paper_router.daily_summaries_db, 'get_daily_summaries', MagicMock(return_value=[{}])
    ), patch.object(paper_router.auth_db, 'get_user_name', MagicMock(return_value='Archit')):
        response = await paper_router.render_paper(date=date(2026, 6, 11), tier=EditionTier.EDITION, uid='uid1')

    assert response.status_code == 200
    body = response.body.decode()
    assert 'Billing Migration Closed' in body
    assert 'Archit' in body


def _uid_dependency(route):
    """The resolved dependency FastAPI will actually call for the ``uid`` argument."""
    for dependency in route.dependant.dependencies:
        if dependency.name == 'uid':
            return dependency.call
    return None


def _closed_over_policy(dependency) -> str | None:
    """The policy name captured by the ``with_rate_limit`` closure."""
    for cell in dependency.__closure__ or ():
        value = cell.cell_contents
        if isinstance(value, str) and value in RATE_POLICIES:
            return value
    return None


def test_both_paper_routes_enforce_the_paper_rate_limit():
    """Read off the resolved dependency graph, not the source text.

    The render route calls the same builder as the JSON route, so limiting only
    one would leave the expensive path wide open. Asserting the closed-over
    policy name also catches a route wired to some other, laxer policy.
    """
    assert paper_router.PAPER_RATE_POLICY in RATE_POLICIES

    routes = {route.path: route for route in paper_router.router.routes}
    assert set(routes) == {'/v1/paper/{date}', '/v1/paper/{date}/render'}

    for path, route in routes.items():
        dependency = _uid_dependency(route)
        assert dependency is not None, f'{path} has no uid dependency'
        assert 'with_rate_limit' in dependency.__qualname__, f'{path} is not rate limited'
        assert _closed_over_policy(dependency) == paper_router.PAPER_RATE_POLICY, f'{path} uses the wrong policy'


@pytest.mark.asyncio
async def test_issue_number_counts_through_the_requested_date():
    """A historic edition keeps the number it was published under.

    Deriving it from today's total made the masthead drift upward every time a
    new summary landed, so the same edition printed a different number tomorrow.
    """
    captured = {}

    def _fake_get(uid, limit=None, end_date=None, **kwargs):
        captured['end_date'] = end_date
        return [{}] * 3

    with patch.object(paper_router.daily_summaries_db, 'get_daily_summaries', _fake_get):
        number = paper_router._issue_number('uid1', date(2026, 6, 11))

    assert number == 3
    assert captured['end_date'] == '2026-06-11'


def test_issue_number_falls_back_rather_than_blocking_the_edition():
    with patch.object(
        paper_router.daily_summaries_db, 'get_daily_summaries', MagicMock(side_effect=RuntimeError('firestore down'))
    ):
        assert paper_router._issue_number('uid1', date(2026, 6, 11)) == 1


def test_reader_name_is_absent_rather_than_wrong_on_failure():
    with patch.object(paper_router.auth_db, 'get_user_name', MagicMock(side_effect=RuntimeError('no user'))):
        assert paper_router._reader_name('uid1') == ''
