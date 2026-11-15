"""Home aggregation must preserve the real episode/detail identities on the wire."""

from datetime import datetime, timezone

from utils.episodes import home_read

AT = datetime(2026, 11, 15, 9, tzinfo=timezone.utc)


def test_pending_episodes_keep_distinct_identities_and_all_member_steps(monkeypatch):
    monkeypatch.setattr(home_read, 'user_zone_provider', lambda _: lambda: 'UTC')
    monkeypatch.setattr(home_read.conversations, 'is_visible_conversation', lambda *a, **kw: True)
    monkeypatch.setattr(home_read, '_too_short_for_a_home_row', lambda _: False)
    monkeypatch.setattr(home_read.home_step_projection, 'classify', lambda row: row['home_step'])
    members = {
        f'capture-{index}': {
            'id': f'capture-{index}',
            'status': 'completed',
            'started_at': AT,
            'finished_at': AT,
            'home_step': step,
            'structured': {'title': 'Fixture'},
        }
        for index, step in enumerate(['writing_notes', 'transcribing', 'failed', 'ready'])
    }
    sources = [
        {
            'id': f'episode-{index}',
            'status': 'closed',
            'started_at': AT,
            'last_activity_at': AT,
            'conversation_ids': [cid],
        }
        for index, cid in enumerate(members)
    ]

    wires = [home_read.project_episode('fixture-owner', row, members=members, list_row=True) for row in sources]

    assert [wire['id'] for wire in wires] == [row['id'] for row in sources]
    assert [wire['conversation_ids'] for wire in wires] == [[cid] for cid in members]
    assert [wire['members'][0]['home_step'] for wire in wires] == ['writing_notes', 'transcribing', 'failed', 'ready']
    assert all(row['status'] == 'closed' for row in sources)
