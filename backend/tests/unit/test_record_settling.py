"""Short batch-owned rows wait off Home for their audio, and never past the deadline."""

from datetime import datetime, timedelta, timezone

import pytest

from utils.conversations.fragment_visibility import SETTLING_MAX_HOLD_SECONDS, is_settling_fragment
from utils.episodes import visibility

FINISHED = datetime(2026, 11, 2, 11, 0, tzinfo=timezone.utc)
NOW = FINISHED.timestamp() + 60


def _row(seconds=45, **extra):
    return {
        'status': 'completed',
        'record_lane_owner': 'batch_live_v1',
        'started_at': FINISHED - timedelta(seconds=seconds),
        'finished_at': FINISHED,
        'structured': {'title': 'Brief Conversation Fragment', 'overview': 'A fragment.'},
        **extra,
    }


@pytest.fixture(autouse=True)
def _on_by_default(monkeypatch):
    monkeypatch.delenv('HOME_HIDE_BELOW_FLOOR_ROWS', raising=False)


def test_a_short_batch_owned_row_waits_for_its_audio():
    assert is_settling_fragment(_row(), now=NOW)


def test_a_server_minimum_row_waits_at_any_length():
    row = _row(seconds=344, structured={'title': 'Yeah.', 'title_provenance': 'server_minimum'})
    assert is_settling_fragment(row, now=NOW)


def test_a_long_row_with_model_notes_is_shown():
    assert not is_settling_fragment(_row(seconds=600), now=NOW)


@pytest.mark.parametrize(
    'settled', [{'record_projection_revision': 1}, {'record_upload_failed': True}, {'record_audio_partial': {'at': 1}}]
)
def test_settled_audio_releases_the_row(settled):
    assert not is_settling_fragment(_row(**settled), now=NOW)


def test_the_deadline_shows_a_stuck_row():
    assert is_settling_fragment(_row(), now=FINISHED.timestamp() + SETTLING_MAX_HOLD_SECONDS - 1)
    assert not is_settling_fragment(_row(), now=FINISHED.timestamp() + SETTLING_MAX_HOLD_SECONDS)


@pytest.mark.parametrize(
    'extra',
    [
        {'record_lane_owner': None},
        {'status': 'in_progress'},
        {'status': 'processing'},
        {'starred': True},
        {'sync_relevance_user_kept': True},
        {'finished_at': None},
    ],
)
def test_live_legacy_and_curated_rows_are_never_held(extra):
    assert not is_settling_fragment(_row(**extra), now=NOW)


def test_the_home_switch_turns_the_hold_off(monkeypatch):
    monkeypatch.setenv('HOME_HIDE_BELOW_FLOOR_ROWS', 'false')
    assert not is_settling_fragment(_row(), now=NOW)


def test_an_episode_of_only_settling_rows_stays_off_live_and_returns(monkeypatch):
    rows = {'c': _row(finished_at=datetime.now(timezone.utc))}
    monkeypatch.setattr(
        visibility.conversations, 'get_conversation_raw_snapshot', lambda _uid, cid, **_kwargs: rows[cid]
    )
    episode = {'conversation_ids': ['c']}
    rows['c']['started_at'] = rows['c']['finished_at'] - timedelta(seconds=45)
    assert visibility.visible_episode('u', episode) is None
    rows['c']['record_projection_revision'] = 1
    assert visibility.visible_episode('u', episode) is episode
    assert not visibility.hidden_member(_row())
