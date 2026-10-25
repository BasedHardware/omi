"""The open-loops daily pass: guards, ingestion, dedupe, ranking, persistence.

The model call is always faked; every deterministic rule (identity, linking,
cooldown, slots, once-per-day) is what these tests pin. Conversation rows
carry real protected ``open_loop_extractions`` blobs so the decode seam is
exercised, not stubbed.
"""

import json
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import database.conversations as conversations_db
import utils.open_loops.daily as daily
from database.open_loops import get_cards, get_cards_doc, get_loops
from tests.support.open_loops_store_fake import FakeFirestore
from utils.open_loops import store
from utils.open_loops.extraction import OPEN_LOOP_EXTRACTIONS_FIELD
from utils.open_loops.prompts import OPEN_LOOPS_DAILY_RULES

NOW = datetime(2026, 10, 26, 14, 0, tzinfo=timezone.utc)  # Monday
TODAY = NOW.date()
DATE_STR = '2026-10-26'
UID = 'u1'

_EXTRACTIONS = {
    'version': 1,
    'delegated_by_user': [
        {
            'who': 'Maya',
            'what': 'send the vendor write-up',
            'by_when': None,
            'evidence': 'I will send it over tomorrow',
            'work_related': True,
        }
    ],
    'commitments_by_others': [],
    'observed_issue_or_blocker': None,
}


def _row(row_id='c1', title='Pricing sync', extractions=_EXTRACTIONS, started='2026-10-26T10:00:00+00:00'):
    row = {
        'id': row_id,
        'created_at': started,
        'started_at': started,
        'finished_at': '2026-10-26T10:20:00+00:00',
        'structured': {'title': title, 'overview': 'Maya will send the vendor write-up.'},
    }
    if extractions is not None:
        row.update(
            conversations_db.encode_conversation_for_write(UID, {OPEN_LOOP_EXTRACTIONS_FIELD: extractions}, 'standard')
        )
    return row


def _loop(loop_id=None, **overrides):
    loop = {
        'id': loop_id or store.stable_key('owed_to_user', 'Maya', 'send the vendor write-up'),
        'stable_key': store.stable_key('owed_to_user', 'Maya', 'send the vendor write-up'),
        'kind': 'owed_to_user',
        'who': 'Maya',
        'what': 'send the vendor write-up',
        'by_when': None,
        'evidence': 'I will send it over tomorrow',
        'status': 'stale',
        'history': [{'date': '2026-10-20', 'status': 'opened', 'evidence': 'asked Maya'}],
        'times_surfaced': 1,
        'last_surfaced_at': '2026-10-20T09:00:00+00:00',  # six days ago: cooldown passed
        'created_at': '2026-10-20T09:00:00+00:00',
        'last_activity_at': '2026-10-20T09:00:00+00:00',
        'source_conversation_ids': ['c1'],
        'source_title': 'Pricing sync',
        'source_started_at': '2026-10-20T10:00:00+00:00',
        'work_related': True,
    }
    loop.update(overrides)
    return loop


class FakeLLM:
    def __init__(self, payload=None, error=None):
        self.payload = payload or {}
        self.error = error
        self.messages = None

    def invoke(self, messages):
        if self.error:
            raise self.error
        self.messages = messages
        return SimpleNamespace(content=json.dumps(self.payload))


def _model_says_maya_due_soon():
    key = store.stable_key('owed_to_user', 'Maya', 'send the vendor write-up')
    return {
        'loops': [
            {
                'loop_id': key,
                'kind': 'owed_to_user',
                'who': 'Maya',
                'what': 'send the vendor write-up',
                'status': 'due_soon',
                'due': '2026-10-27',
                'work_related': True,
                'evidence': 'Maya promised it for Tuesday',
                'source_conversation_ids': ['c1'],
            }
        ],
        'surface': [{'loop_id': key, 'why_now': 'due tomorrow', 'value': 5}],
    }


@pytest.fixture
def pass_env(monkeypatch):
    fake = FakeFirestore()
    rows = [_row()]
    tasks = [{'id': 't1', 'description': 'Book the dentist', 'created_at': NOW - timedelta(days=3), 'completed': False}]
    summary = {'id': 's1', 'headline': 'Vendor sync day', 'overview': 'Pricing talk with Maya.'}
    monkeypatch.setattr(daily.conversations_db, 'get_conversations', lambda uid, **kwargs: list(rows))
    monkeypatch.setattr(daily.action_items_db, 'get_action_items', lambda uid, **kwargs: list(tasks))
    monkeypatch.setattr(daily.daily_summaries_db, 'get_daily_summary_by_date', lambda uid, date_str: summary)
    return SimpleNamespace(fake=fake, rows=rows, tasks=tasks, summary=summary)


def _seed_loops(pass_env, loops):
    for loop in loops:
        from database.open_loops import upsert_loop

        upsert_loop(UID, loop, firestore_client=pass_env.fake)


def _run(pass_env, llm, **kwargs):
    return daily.run_daily_pass(
        UID, date_str=DATE_STR, tz='UTC', now=NOW, firestore_client=pass_env.fake, llm=llm, **kwargs
    )


def test_kill_switch_skips_the_pass_and_writes_nothing(pass_env, monkeypatch):
    monkeypatch.setenv('OPEN_LOOPS_ENABLED', 'off')
    llm = FakeLLM()
    assert _run(pass_env, llm) == daily.SKIPPED_DISABLED
    assert llm.messages is None
    assert get_cards_doc(UID, DATE_STR, firestore_client=pass_env.fake) is None


def test_cards_doc_is_the_once_per_day_marker(pass_env):
    from database.open_loops import set_cards

    _seed_loops(pass_env, [_loop()])
    set_cards(UID, DATE_STR, [], firestore_client=pass_env.fake)
    llm = FakeLLM()
    assert _run(pass_env, llm) == daily.SKIPPED_ALREADY_RAN
    assert llm.messages is None  # no second model call for the same day


def test_no_extractions_and_no_open_loops_skips_the_model_call(pass_env):
    pass_env.rows.clear()
    llm = FakeLLM()
    assert _run(pass_env, llm) == daily.SKIPPED_NO_SIGNAL
    assert llm.messages is None
    assert (
        get_cards_doc(UID, DATE_STR, firestore_client=pass_env.fake) is None
    )  # nothing written, a later tick may retry


def test_open_loops_alone_still_justify_a_pass(pass_env):
    """Cost guard: no extractions but open loops carried — the pass still runs."""
    pass_env.rows.clear()
    _seed_loops(pass_env, [_loop()])
    assert _run(pass_env, FakeLLM(_model_says_maya_due_soon())) == daily.RAN
    assert get_cards(UID, DATE_STR, firestore_client=pass_env.fake) is not None


def test_prompt_reuses_the_recap_render_and_carries_the_state(pass_env):
    _seed_loops(pass_env, [_loop()])
    llm = FakeLLM(_model_says_maya_due_soon())
    _run(pass_env, llm)
    system, user = llm.messages[0]['content'], llm.messages[1]['content']
    assert system == OPEN_LOOPS_DAILY_RULES
    # the recap-style conversation render leads, for prompt-cache reuse
    assert user.index('Pricing sync') < user.index('INPUT (JSON):')
    payload = json.loads(user.split('INPUT (JSON):\n', 1)[1])
    assert payload['date'] == DATE_STR and payload['user_timezone'] == 'UTC'
    assert payload['loop_extractions'][0]['conversation_id'] == 'c1'
    assert payload['carried_loops'][0]['loop_id'] == _loop()['id']
    assert payload['open_tasks'][0]['task_id'] == 't1' and payload['open_tasks'][0]['age_days'] == 3
    assert payload['day_summary']['headline'] == 'Vendor sync day'


def test_carried_loops_capped_at_twenty_most_relevant(pass_env):
    loops = [
        _loop(
            loop_id=f'l{i:02d}',
            what=f'deliverable number {i}',
            stable_key=f'k{i}',
            status='opened',
            times_surfaced=0,
            last_surfaced_at=None,
        )
        for i in range(30)
    ]
    _seed_loops(pass_env, loops)
    llm = FakeLLM({'loops': [], 'surface': []})
    _run(pass_env, llm)
    payload = json.loads(llm.messages[1]['content'].split('INPUT (JSON):\n', 1)[1])
    assert len(payload['carried_loops']) == store.CARRIED_LOOPS_PROMPT_CAP


def test_carried_update_reuses_the_loop_id_and_appends_history():
    existing = [_loop()]
    key = existing[0]['id']
    writes, absorbed, id_map = daily.ingest_model_loops(
        _model_says_maya_due_soon()['loops'],
        existing,
        [],
        today=TODAY,
        conversation_meta={'c1': {'id': 'c1', 'title': 'Pricing sync', 'started_at': '2026-10-26T10:00:00+00:00'}},
        now=NOW,
    )
    assert absorbed == []
    assert [w['id'] for w in writes] == [key]
    assert id_map[key] == key
    loop = writes[0]
    assert loop['status'] == 'due_soon'
    assert loop['history'][-1]['status'] == 'due_soon'
    assert len(loop['history']) == 2
    assert loop['times_surfaced'] == 1  # counters survive updates


def test_new_loop_gets_the_stable_key_identity_and_source_meta():
    entry = {
        'loop_id': 'maya-vendor-writeup',
        'kind': 'owed_to_user',
        'who': 'Maya',
        'what': 'send the vendor write-up',
        'status': 'opened',
        'due': None,
        'work_related': True,
        'evidence': 'asked Maya',
        'source_conversation_ids': ['c9'],
    }
    writes, absorbed, id_map = daily.ingest_model_loops(
        [entry],
        [],
        [],
        today=TODAY,
        conversation_meta={'c9': {'id': 'c9', 'title': 'Standup', 'started_at': '2026-10-26T09:00:00+00:00'}},
        now=NOW,
    )
    loop = writes[0]
    assert loop['id'] == store.stable_key('owed_to_user', 'Maya', 'send the vendor write-up')
    assert loop['source_title'] == 'Standup'
    assert id_map['maya-vendor-writeup'] == loop['id']


def test_task_loop_uses_the_task_identity_and_links():
    entry = {
        'loop_id': 'task-7',
        'from_task_id': '7',
        'kind': 'own_commitment',
        'who': None,
        'what': 'review the pull request',
        'status': 'stale',
        'due': None,
        'work_related': True,
        'evidence': 'no mention since Oct 20',
        'source_conversation_ids': [],
    }
    tasks = [{'task_id': '7', 'title': 'Review the pull request'}]
    writes, _, id_map = daily.ingest_model_loops([entry], [], tasks, today=TODAY, conversation_meta={}, now=NOW)
    loop = writes[0]
    assert loop['id'] == 'task-7' and loop['linked_task_id'] == '7'
    assert loop['kind'] == 'own_commitment'
    assert id_map['task-7'] == 'task-7'


def test_duplicate_wording_merges_and_reports_the_absorbed_doc():
    carried = _loop(loop_id='ol-carried', stable_key='old-key')
    entries = [
        {
            'loop_id': 'ol-carried',
            'kind': 'owed_to_user',
            'who': 'Maya',
            'what': 'send the vendor write-up',
            'status': 'stale',
            'due': None,
            'evidence': 'still nothing',
            'source_conversation_ids': [],
        },
        {
            'loop_id': 'new-dup',
            'kind': 'owed_to_user',
            'who': 'Maya',
            'what': 'send the vendor write-up please',
            'status': 'stale',
            'due': None,
            'evidence': 'same ask again',
            'source_conversation_ids': [],
        },
    ]
    writes, absorbed, id_map = daily.ingest_model_loops(
        entries, [carried], [], today=TODAY, conversation_meta={}, now=NOW
    )
    assert len(writes) == 1
    assert writes[0]['id'] == 'ol-carried'
    assert 'new-dup' not in [w['id'] for w in writes]
    assert id_map['new-dup'] == 'ol-carried'


def test_undecidable_statuses_are_skipped():
    entries = [{'loop_id': 'x', 'kind': 'owed_to_user', 'who': 'A', 'what': 'b', 'status': 'no_signal'}]
    writes, _, _ = daily.ingest_model_loops(entries, [], [], today=TODAY, conversation_meta={}, now=NOW)
    assert writes == []


def test_matching_task_links_never_drops_the_loop(pass_env):
    pass_env.tasks[:] = [
        {'id': 't9', 'description': 'Send Maya the vendor write-up brief', 'created_at': NOW, 'completed': False}
    ]
    payload = {
        'loops': [
            {
                'loop_id': 'fresh-1',
                'kind': 'own_commitment',
                'who': None,
                'what': 'send Maya the vendor write-up brief',
                'status': 'stale',
                'due': None,
                'work_related': True,
                'evidence': 'no mention since Oct 20',
                'source_conversation_ids': ['c1'],
            }
        ],
        'surface': [{'loop_id': 'fresh-1', 'why_now': 'stale', 'value': 4}],
    }
    assert _run(pass_env, FakeLLM(payload)) == daily.RAN
    loops = get_loops(UID, firestore_client=pass_env.fake)
    matching = [l for l in loops if 'vendor write-up' in str(l.get('what'))]
    assert len(matching) == 1
    assert matching[0]['linked_task_id'] == 't9'
    # linked, not dropped: the card still exists and asks about it
    cards = get_cards(UID, DATE_STR, firestore_client=pass_env.fake)
    assert cards and cards[0]['loop_id'] == matching[0]['id']


def test_run_daily_pass_full_flow_writes_cards_and_updates_loops(pass_env):
    _seed_loops(pass_env, [_loop()])
    assert _run(pass_env, FakeLLM(_model_says_maya_due_soon())) == daily.RAN
    cards = get_cards(UID, DATE_STR, firestore_client=pass_env.fake)
    assert len(cards) == 1
    card = cards[0]
    assert card['state'] == 'pending' and card['actions'] == ['done', 'remind', 'drop']
    assert card['question'].endswith('?') and 'Maya' in card['question']
    assert 'Pricing sync' in card['context_line'] or 'conversation' in card['context_line']
    assert card['source_ref']
    loop = get_loops(UID, firestore_client=pass_env.fake)[0]
    assert loop['status'] == 'due_soon'
    assert loop['times_surfaced'] == 2  # one before, one now
    assert loop['last_surfaced_at'] == DATE_STR
    # history moved with the status decision; surfacing did not fake activity
    assert loop['history'][-1]['status'] == 'due_soon'


def test_low_value_candidates_never_fill_a_slot(pass_env):
    payload = _model_says_maya_due_soon()
    payload['surface'][0]['value'] = 2
    _seed_loops(pass_env, [_loop()])
    assert _run(pass_env, FakeLLM(payload)) == daily.RAN
    assert get_cards(UID, DATE_STR, firestore_client=pass_env.fake) == []


def test_recently_surfaced_loop_is_not_reasked(pass_env):
    """Cooldown: surfaced yesterday, status unchanged — the store-level
    ``surfaceable`` re-arm on due_soon is pinned in test_open_loops_store."""
    asked_yesterday = _loop(last_surfaced_at='2026-10-25T09:00:00+00:00')
    _seed_loops(pass_env, [asked_yesterday])
    payload = _model_says_maya_due_soon()
    payload['loops'][0]['status'] = 'stale'
    payload['surface'][0]['value'] = 5
    assert _run(pass_env, FakeLLM(payload)) == daily.RAN
    assert get_cards(UID, DATE_STR, firestore_client=pass_env.fake) == []


def test_resolved_loop_is_closed_and_never_surfaces(pass_env):
    _seed_loops(pass_env, [_loop()])
    payload = _model_says_maya_due_soon()
    payload['loops'][0]['status'] = 'resolved'
    payload['loops'][0]['evidence'] = 'Maya sent the write-up this morning'
    payload['surface'] = [{'loop_id': payload['loops'][0]['loop_id'], 'why_now': '', 'value': 5}]
    assert _run(pass_env, FakeLLM(payload)) == daily.RAN
    loop = get_loops(UID, firestore_client=pass_env.fake)[0]
    assert loop['status'] == 'resolved'
    assert get_cards(UID, DATE_STR, firestore_client=pass_env.fake) == []


def test_model_failure_raises_and_leaves_the_day_unmarked(pass_env):
    _seed_loops(pass_env, [_loop()])
    llm = FakeLLM(error=RuntimeError('gateway down'))
    with pytest.raises(RuntimeError):
        _run(pass_env, llm)
    # no cards marker: the next recap tick may retry the pass
    assert get_cards_doc(UID, DATE_STR, firestore_client=pass_env.fake) is None


def test_merge_donor_locked_and_discarded_rows_never_contribute():
    rows = [
        {'id': 'donor', 'sync_merged_into': 'target', 'structured': {'title': 'Donor'}},
        {'id': 'locked', 'is_locked': True, 'structured': {'title': 'Locked'}},
        {'id': 'discarded', 'discarded': True, 'structured': {'title': 'Discarded'}},
        {'id': 'kept', 'structured': {'title': 'Kept'}},
    ]
    assert [row['id'] for row in daily.eligible_day_rows(UID, rows)] == ['kept']


def test_day_extractions_decode_protected_rows_and_skip_the_rest(pass_env):
    pass_env.rows.append(_row('c2', title='Chatter', extractions=None))
    entries = daily.day_extractions(UID, daily.eligible_day_rows(UID, pass_env.rows))
    assert [entry['conversation_id'] for entry in entries] == ['c1']
    assert entries[0]['delegated_by_user'][0]['who'] == 'Maya'


def test_parse_model_output_tolerates_fences_and_rejects_prose():
    assert daily.parse_model_output('{"loops": []}') == {'loops': []}
    assert daily.parse_model_output('```json\n{"loops": []}\n```') == {'loops': []}
    assert daily.parse_model_output('sounds good!') is None
    assert daily.parse_model_output(SimpleNamespace(content='{"surface": []}')) == {'surface': []}
