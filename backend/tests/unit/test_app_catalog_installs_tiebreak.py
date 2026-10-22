"""Unit tests for app catalog sorting and install count tie-breaking (#22772).

Regression tests for:
- When reviews are not loaded (rating_avg=0, rating_count=0, score=0.0) or when apps tie in score,
  sort_apps_by_installs must rank apps by install count descending instead of keeping them
  in oldest-first Firestore document order.
"""

from types import SimpleNamespace
import pytest

from models.app import App
from utils.apps import (
    sort_apps_by_installs,
    sort_apps_by_installs_only,
    group_apps_by_capability,
)


def _make_app(
    app_id: str,
    installs: int = 0,
    rating_avg: float = 0.0,
    rating_count: int = 0,
    capability: str = "chat",
) -> App:
    return App(
        id=app_id,
        name=f"App {app_id}",
        author="Author",
        description="Description",
        category="productivity",
        capabilities=[capability],
        image="https://example.com/icon.png",
        installs=installs,
        rating_avg=rating_avg,
        rating_count=rating_count,
    )


def test_sort_apps_by_installs_tiebreaks_by_install_count():
    """Unreviewed apps (all score 0.0) must sort by install count descending."""
    app_low = _make_app("app_low", installs=50)
    app_high = _make_app("app_high", installs=5000)
    app_mid = _make_app("app_mid", installs=500)
    app_zero = _make_app("app_zero", installs=0)

    # Initial order: low, high, mid, zero
    apps = [app_low, app_high, app_mid, app_zero]
    sorted_apps = sort_apps_by_installs(apps)

    sorted_ids = [a.id for a in sorted_apps]
    assert sorted_ids == ["app_high", "app_mid", "app_low", "app_zero"]


def test_sort_apps_by_installs_prefers_score_first_then_installs():
    """Higher review score takes precedence; equal scores tie-break by installs."""
    # app_reviewed has rating 5.0 with 10 reviews -> positive score
    app_reviewed_low_installs = _make_app("app_rev", installs=10, rating_avg=5.0, rating_count=10)
    # app_unreviewed has 100,000 installs but 0 reviews -> score 0.0
    app_unreviewed_huge_installs = _make_app("app_unreviewed_huge_installs", installs=100000, rating_avg=0.0, rating_count=0)

    # app_tie_1 and app_tie_2 have identical ratings and reviews -> identical score
    app_tie_high_installs = _make_app("app_tie_high", installs=2000, rating_avg=4.0, rating_count=5)
    app_tie_low_installs = _make_app("app_tie_low", installs=200, rating_avg=4.0, rating_count=5)

    apps = [app_unreviewed_huge_installs, app_tie_low_installs, app_reviewed_low_installs, app_tie_high_installs]
    sorted_apps = sort_apps_by_installs(apps)

    # Both reviewed apps with higher scores must come before unreviewed (score 0.0)
    assert sorted_apps[0].id == "app_rev"
    # Between the two tie apps with same score, app_tie_high (2000 installs) comes before app_tie_low (200 installs)
    assert sorted_apps[1].id == "app_tie_high"
    assert sorted_apps[2].id == "app_tie_low"
    assert sorted_apps[3].id == "app_unreviewed_huge_installs"


def test_sort_apps_by_installs_handles_none_installs_duck_typing():
    """Duck-typed objects or apps with None installs should be treated as 0 without raising TypeError."""
    app_none = SimpleNamespace(id="app_none", score=None, installs=None, rating_avg=0.0, rating_count=0)
    app_some = SimpleNamespace(id="app_some", score=None, installs=10, rating_avg=0.0, rating_count=0)

    sorted_apps = sort_apps_by_installs([app_none, app_some])
    assert [a.id for a in sorted_apps] == ["app_some", "app_none"]


def test_sort_apps_by_installs_only_handles_none():
    """sort_apps_by_installs_only handles None installs cleanly."""
    app_none = SimpleNamespace(id="app_none", installs=None)
    app_ten = SimpleNamespace(id="app_ten", installs=10)

    sorted_apps = sort_apps_by_installs_only([app_none, app_ten])
    assert [a.id for a in sorted_apps] == ["app_ten", "app_none"]


def test_group_apps_by_capability_orders_sections_by_installs_when_reviews_unloaded():
    """Catalog sections grouped by capability must be popularity-sorted when reviews are not loaded."""
    app1 = _make_app("chat_1", installs=10, capability="chat")
    app2 = _make_app("chat_2", installs=500, capability="chat")
    app3 = _make_app("chat_3", installs=150, capability="chat")

    capabilities = [{"id": "chat", "title": "Chat"}]
    grouped = group_apps_by_capability([app1, app2, app3], capabilities)

    chat_section = grouped["chat"]
    assert [a.id for a in chat_section] == ["chat_2", "chat_3", "chat_1"]
