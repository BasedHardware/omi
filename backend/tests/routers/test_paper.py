"""PAPER router — the thin layer between the request and ``build_edition``."""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from models.paper import Edition, EditionTier, Lede
from routers import paper as paper_router


def _edition():
    return Edition(
        date='2026-06-11',
        issue_number=7,
        lede=Lede(headline='Billing Migration Closed', source_date='2026-06-11'),
    )


def test_get_paper_returns_the_built_edition():
    built = _edition()
    build_edition = MagicMock(return_value=built)

    with patch.object(paper_router, 'build_edition', build_edition), patch.object(
        paper_router.daily_summaries_db, 'get_summaries_count', MagicMock(return_value=7)
    ):
        result = paper_router.get_paper(date='2026-06-11', tier=EditionTier.EDITION, uid='uid1')

    assert result is built
    build_edition.assert_called_once_with('uid1', date(2026, 6, 11), tier=EditionTier.EDITION, issue_number=7)


def test_malformed_date_is_rejected_before_any_work():
    build_edition = MagicMock()

    with patch.object(paper_router, 'build_edition', build_edition):
        with pytest.raises(HTTPException) as exc:
            paper_router.get_paper(date='11-06-2026', tier=EditionTier.EDITION, uid='uid1')

    assert exc.value.status_code == 400
    build_edition.assert_not_called()


def test_render_returns_the_edition_as_html():
    built = _edition()
    render_html = MagicMock(return_value='<html>edition</html>')

    with patch.object(paper_router, 'build_edition', MagicMock(return_value=built)), patch.object(
        paper_router, 'render_html', render_html
    ), patch.object(paper_router.daily_summaries_db, 'get_summaries_count', MagicMock(return_value=7)), patch.object(
        paper_router, 'get_prompt_memories', MagicMock(return_value=('Ada', 'memories'))
    ):
        response = paper_router.render_paper(date='2026-06-11', tier=EditionTier.EDITION, uid='uid1')

    assert response.status_code == 200
    assert response.body == b'<html>edition</html>'
    render_html.assert_called_once_with(built, 'Ada')
