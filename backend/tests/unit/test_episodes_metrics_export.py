"""The shared listen/API exporter registers the bounded episode moment metrics."""

from utils.metrics import metrics_response


def test_shared_metrics_export_includes_episode_moment_families():
    exported = metrics_response().body.decode()

    assert '# HELP omi_episode_moment_updates_total ' in exported
    assert '# HELP omi_episode_moment_tokens_total ' in exported
    assert '# HELP omi_episode_moment_cost_usd_total ' in exported
    assert '# HELP omi_episode_moment_update_latency_seconds ' in exported
    assert 'uid=' not in exported
