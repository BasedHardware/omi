"""Synthetic ownership/status cases through the real task writer and refresh transaction."""

from copy import deepcopy
from contextlib import asynccontextmanager
from datetime import timedelta
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from prometheus_client import CollectorRegistry, Counter

from config.action_item_extraction_policy import clearly_other_owner, clearly_status
from config.action_item_similarity import near_duplicate
from database.action_item_refresh_policy import RECEIPT, key
from tests.unit.test_action_item_refresh import NOW, UID, conv_path, item, seed_donor, task_path, world
from utils.conversations import (
    action_item_extraction as extraction,
    action_item_refresh as flow,
    process_conversation as pc,
)
from utils.conversations.processing_trigger import ProcessingTrigger as Trigger
from utils.conversations.transcript_for_llm import SpeakerMap
from utils.llm.conversation_notes_prompts import ACTION_ITEM_EXTRACTION_RULES, conversation_notes_static_instructions
from utils.llm import conversation_processing
from utils.llm.conversation_prompt_context import build_conversation_prompt_prefix
from utils.llm.known_spellings import render_known_spellings


@pytest.mark.parametrize(
    'name',
    ['Riley Chen', 'riley chen', 'Riley', 'User', 'The User', 'me', '', None, 'unknown', 'one speaker', 'Speaker 1'],
)
def test_owner_commitment_and_unknown_ownership_are_kept(name):
    assert not clearly_other_owner(name, 'Riley Chen')


@pytest.mark.parametrize('name', ['Morgan Vale', 'Casey Chen'])
def test_named_other_attendee_is_rejected(name):
    assert clearly_other_owner(name, 'Riley Chen')
    assert not clearly_other_owner(name, None)  # Missing account identity is uncertain.


@pytest.mark.parametrize('name', ['Dana Leigh', 'Dana L.', 'ＤＡＮＡ Leigh', 'dAnA Stone'])
def test_owner_surname_mismatch_and_initial_only_are_kept(name):
    assert not clearly_other_owner(name, 'Dana Lee')


@pytest.mark.parametrize('name', ["Dana's", 'Dana’s', 'Dana.', '(Dana)', '“Dana”', "Dana's,", 'Ｄａｎａ’s'])
def test_owner_given_name_possessive_and_punctuation_are_kept(name):
    assert not clearly_other_owner(name, 'Dana Lee')


@pytest.mark.parametrize('name', ['Morgan Lee', 'ＭＯＲＧＡＮ L.', 'Morgan’s'])
def test_different_first_name_is_dropped_even_when_surname_matches(name):
    assert clearly_other_owner(name, 'Dana Lee')


def test_drop_metrics_and_logs_separate_reasons_without_content(monkeypatch, caplog):
    metric = Counter(
        'synthetic_action_item_drop_total', 'Synthetic extraction drops', ['reason'], registry=CollectorRegistry()
    )
    monkeypatch.setattr(extraction, 'OMI_ACTION_ITEM_EXTRACTION_DROPPED_TOTAL', metric)
    monkeypatch.setattr(extraction, 'get_user_full_name', lambda uid: 'Dana Lee')
    own = SimpleNamespace(description='Send the download link', owner_name='Dana Leigh')
    items = [
        own,
        SimpleNamespace(description='Ask Dana for the download link', owner_name='Morgan Vale'),
        SimpleNamespace(description='Email Dana the proposal', owner_name='Casey Chen'),
        SimpleNamespace(description='User is testing the memory feature', owner_name='User'),
    ]
    with caplog.at_level('INFO', logger=extraction.__name__):
        assert extraction.filter_extracted_items(UID, items) == [own]
    counts = {
        sample.labels['reason']: sample.value
        for family in metric.collect()
        for sample in family.samples
        if sample.name.endswith('_total')
    }
    assert counts == {'other_owner': 2, 'status_statement': 1}
    assert [record.getMessage() for record in caplog.records] == [
        'event=action_item_extraction_dropped reason=other_owner count=2',
        'event=action_item_extraction_dropped reason=status_statement count=1',
    ]


@pytest.mark.parametrize(
    'description',
    [
        'User is testing the new memory feature.',
        'Morgan is working on the proposal.',
        'Riley Chen is currently reviewing the budget.',
    ],
)
def test_status_sentences_are_rejected(description):
    assert clearly_status(description)


@pytest.mark.parametrize(
    'description',
    [
        'Test the new memory feature',
        'Work on the proposal',
        'Check Morgan is working on the proposal',
        'Send the link to Morgan',
        'Riley will test the feature',
        'Testing the feature',
    ],
)
def test_conservative_status_filter_keeps_requests_and_ambiguous_fragments(description):
    assert not clearly_status(description)


def _write(monkeypatch, trigger):
    monkeypatch.setattr(extraction, 'get_user_full_name', lambda uid: 'Riley Chen')
    metrics = MagicMock()
    monkeypatch.setattr(extraction, 'OMI_ACTION_ITEM_EXTRACTION_DROPPED_TOTAL', metrics)
    candidates = [
        SimpleNamespace(**item('Review the budget'), owner_name='Riley Chen'),  # own commitment
        SimpleNamespace(**item('Ask Riley for the download link'), owner_name='Morgan Vale'),
        SimpleNamespace(**item('Email Riley the contact information'), owner_name='Morgan Vale'),
        SimpleNamespace(**item('Send the download link to Morgan'), owner_name='Riley'),  # owner agreed
        SimpleNamespace(**item('User is testing the new memory feature'), owner_name='User'),
        SimpleNamespace(**item('Book the meeting room'), owner_name=None),
    ]
    conv = SimpleNamespace(
        id='survivor', is_locked=False, sync_content_revision=1, structured=SimpleNamespace(action_items=candidates)
    )
    pc._write_action_items(UID, conv, trigger)
    metrics.labels.assert_any_call(reason='other_owner')
    metrics.labels.assert_any_call(reason='status_statement')
    assert metrics.labels.return_value.inc.call_args_list[0].args == (2,)


@pytest.mark.parametrize('trigger', [Trigger.SMART_MERGE, Trigger.SYNC_UPDATE])
def test_writer_filters_owner_and_status_before_refresh(world, monkeypatch, trigger):
    _write(monkeypatch, trigger)
    rows = [r for p, r in world.store.rows.items() if p[-2] == 'action_items']
    assert {r['description'] for r in rows} == {
        'Send report',
        'Review the budget',
        'Send the download link to Morgan',
        'Book the meeting room',
    }


def test_first_processing_writer_uses_the_same_guards(monkeypatch):
    monkeypatch.setattr(pc.conversation_capture, 'canonical_conversation_fields', lambda *a: {})
    monkeypatch.setattr(pc, 'preserve_refresh_tasks', lambda *a: False)
    monkeypatch.setattr(pc.action_items_db, 'get_action_items_by_conversation', lambda *a, **k: [])
    monkeypatch.setattr(pc.action_items_db, 'delete_action_items_for_conversation', lambda *a: None)
    create = MagicMock(return_value=[])
    monkeypatch.setattr(pc.action_items_db, 'create_action_items_batch', create)
    monkeypatch.setattr(pc.action_items_db, 'get_action_items_by_ids', lambda *a: [])
    monkeypatch.setattr(pc, 'emit_product_event', lambda **k: None)
    monkeypatch.setattr(pc, 'upsert_action_item_vectors_batch', lambda *a: None)
    monkeypatch.setattr(pc, 'submit_with_context', lambda *a: None)
    _write(monkeypatch, Trigger.CAPTURE_END)
    assert [row['description'] for row in create.call_args.args[1]] == [
        'Review the budget',
        'Send the download link to Morgan',
        'Book the meeting room',
    ]


def test_direct_refresh_entry_filters_raw_extractions(world, monkeypatch):
    monkeypatch.setattr(extraction, 'get_user_full_name', lambda uid: 'Riley Chen')
    conv = SimpleNamespace(id='survivor', sync_content_revision=1)
    assert flow.preserve(
        UID,
        conv,
        [item('Ask Riley for link', owner_name='Morgan Vale'), item('User is testing the feature')],
        Trigger.SYNC_UPDATE,
        lambda *a: None,
    )
    assert len([p for p in world.store.rows if p[-2] == 'action_items']) == 1


@pytest.mark.parametrize('completed', [False, True])
def test_rewordings_are_not_inserted_or_completed_tasks_resurrected(world, completed):
    world.store.rows[task_path('original')].update(description='Send the budget report to Morgan', completed=completed)
    before = deepcopy(world.store.rows[task_path('original')])
    for _ in range(8):
        world.write(
            [
                'Email Morgan the budget report',
                'Share the budget report to Morgan',
                'Send Morgan the final budget report',
            ]
        )
    world.drain()
    assert world.store.rows[task_path('original')] == before
    assert len([p for p in world.store.rows if p[-2] == 'action_items']) == 1
    assert not world.external
    receipt = world.store.rows[conv_path('survivor')][RECEIPT]
    assert receipt['keys'][key('Email Morgan the budget report')] == ['original']


def test_paraphrase_alias_survives_edit_and_hard_delete(world):
    world.store.rows[task_path('original')]['description'] = 'Send the budget report to Morgan'
    world.write(['Email Morgan the budget report'])
    world.store.rows[task_path('original')]['description'] = 'My carefully edited task'
    world.write(['Email Morgan the budget report'])
    del world.store.rows[task_path('original')]
    world.write(['Email Morgan the budget report'])
    assert not [p for p in world.store.rows if p[-2] == 'action_items']


@pytest.mark.parametrize(
    'description',
    [
        'Send the budget report to Casey',
        'Review the budget report with Morgan',
        'Send the staffing report to Morgan',
        'Send the budget report to Morgan and Casey',
    ],
)
def test_distinct_tasks_with_shared_words_are_inserted(world, description):
    world.store.rows[task_path('original')]['description'] = 'Send the budget report to Morgan'
    world.write([description])
    assert len([p for p in world.store.rows if p[-2] == 'action_items']) == 2


@pytest.mark.parametrize(
    'left,right',
    [
        ('Send the final budget report to Morgan', 'Send the final budget report to Casey'),
        ('Send budget report 12 to Morgan', 'Send budget report 13 to Morgan'),
        ('Send access code AbC to Morgan', 'Send access code abc to Morgan'),
        ('Send the report before Friday', 'Send the report after Friday'),
        ('Send the report to Morgan', 'Do not send the report to Morgan'),
    ],
)
def test_similarity_guards_meaningful_differences(left, right):
    assert not near_duplicate(left, right)


def test_new_paraphrases_in_one_refresh_are_collapsed(world):
    world.write(['Send the budget report to Morgan', 'Email Morgan the budget report'])
    assert len([p for p in world.store.rows if p[-2] == 'action_items']) == 2


def test_donor_duplicate_hidden_and_completion_carried_atomically(world):
    seed_donor(world)
    world.store.rows[task_path('donor-duplicate')].update(completed=True, status='completed', completed_at=NOW)
    flow.transfer_donor(UID, 'donor', 'survivor')
    assert world.store.rows[task_path('donor-duplicate')]['deleted']
    target = world.store.rows[task_path('original')]
    assert target['completed'] and target['status'] == 'completed' and target['completed_at'] == NOW
    world.write(['Email the report'])
    assert len([p for p in world.store.rows if p[-2] == 'action_items']) == 3


@pytest.mark.parametrize(
    'extra',
    [
        {'source': 'manual'},
        {'updated_at': NOW + timedelta(minutes=1)},
        {'folder_id': 'curated'},
    ],
)
def test_donor_manual_and_edited_items_are_never_hidden(world, extra):
    seed_donor(world)
    world.store.rows[task_path('donor-duplicate')].update(extra)
    before = deepcopy(world.store.rows[task_path('donor-duplicate')])
    flow.transfer_donor(UID, 'donor', 'survivor')
    after = world.store.rows[task_path('donor-duplicate')]
    assert not after.get('deleted')
    for field, value in before.items():
        assert after[field] == ('survivor' if field == 'conversation_id' else value)


def test_completed_donor_does_not_complete_a_user_edited_alias_target(world):
    world.write(['Send report'])
    world.store.rows[task_path('original')]['description'] = 'Review the staffing plan'
    seed_donor(world)
    world.store.rows[task_path('donor-duplicate')].update(completed=True, completed_at=NOW)
    flow.transfer_donor(UID, 'donor', 'survivor')
    assert not world.store.rows[task_path('original')]['completed']


def test_desktop_candidate_capture_also_filters_ownership_and_status(monkeypatch):
    monkeypatch.setattr(extraction, 'get_user_full_name', lambda uid: 'Riley Chen')
    monkeypatch.setattr(pc, '_proposes_task_candidates', lambda conv: True)
    monkeypatch.setattr(pc.conversation_capture, 'prepare_wake_word_capture_gate', lambda *a: None)
    capture = MagicMock()
    monkeypatch.setattr(pc.conversation_capture, 'process_conversation_before_legacy', capture)
    monkeypatch.setattr(pc, 'emit_product_event', lambda **k: None)
    conv = SimpleNamespace(
        id='synthetic-desktop',
        structured=SimpleNamespace(
            action_items=[
                SimpleNamespace(description='Ask Riley for the link', owner_name='Morgan Vale'),
                SimpleNamespace(description='User is testing the new feature', owner_name='User'),
                SimpleNamespace(description='Send the link to Morgan', owner_name='Riley Chen'),
            ]
        ),
    )
    pc._save_action_items(UID, conv)
    assert [candidate.description for candidate in capture.call_args.args[1].structured.action_items] == [
        'Send the link to Morgan'
    ]


@pytest.mark.parametrize('rich', [False, True])
@pytest.mark.parametrize('spellings_enabled', [False, True])
def test_notes_task_suffix_identifies_owner_and_carries_rules_without_changing_shared_bytes(
    monkeypatch, rich, spellings_enabled
):
    monkeypatch.setenv('OMI_SHAPED_AGENT_MODE', 'on')
    speakers = SpeakerMap({0: 'User'}, owner_name='Riley Chen')
    spellings = render_known_spellings([{'spelling': 'Quorbi', 'aliases': ['Qorby']}], []) if spellings_enabled else ''
    kwargs = dict(
        conversation_id='synthetic',
        transcript='[s1 0] I will send the link.',
        started_at=NOW,
        timezone_name='UTC',
        language_code='en',
        uid=UID,
    )
    prefix = build_conversation_prompt_prefix(speaker_map=speakers, known_spellings=spellings, **kwargs)
    plain = build_conversation_prompt_prefix(speaker_map=dict(speakers), known_spellings=spellings, **kwargs)
    baseline = build_conversation_prompt_prefix(speaker_map=dict(speakers), **kwargs)
    assert prefix.account_owner_name == 'Riley Chen'
    assert prefix.known_spellings == spellings
    assert prefix.context == plain.context
    assert prefix.shaped_context == plain.shaped_context
    assert prefix.messages(cache_enabled=True) == plain.messages(cache_enabled=True)
    assert prefix.context == baseline.context
    assert prefix.shaped_context == baseline.shaped_context
    assert prefix.cache_key == baseline.cache_key
    assert prefix.cache_eligible == baseline.cache_eligible
    assert prefix.messages(cache_enabled=True)[:2] == baseline.messages(cache_enabled=True)
    if spellings:
        assert prefix.messages(cache_enabled=True)[2] == {'role': 'system', 'content': spellings}
    assert ACTION_ITEM_EXTRACTION_RULES not in conversation_notes_static_instructions('')

    captured = []

    class Model:
        async def ainvoke(self, messages):
            captured.extend(messages)
            return SimpleNamespace(
                content=json.dumps(
                    {
                        'title': 'Link follow-up',
                        'overview': 'A link will be sent.',
                        'emoji': '💬',
                        'category': 'work',
                        'sections': [],
                        'action_items': [],
                        'events': [],
                    }
                )
            )

    @asynccontextmanager
    async def isolated_model(model):
        yield model

    monkeypatch.setattr(conversation_processing, 'get_llm', lambda *a, **k: Model())
    monkeypatch.setattr(conversation_processing, 'isolated_notes_model', isolated_model)
    conversation_processing.get_conversation_notes(
        prefix,
        uid=UID,
        started_at=NOW,
        language_code='en',
        output_language_code='en',
        tz='UTC',
        task_intelligence_capture=True,
        rich_context_enabled=rich,
    )
    system, user = captured[:2]
    assert system['role'] == 'system' and user['role'] == 'user'
    system_text = '\n'.join(block['text'] for block in system['content'])
    assert 'Riley Chen' not in system_text
    assert system_text.count(ACTION_ITEM_EXTRACTION_RULES) == 1
    assert conversation_processing.notes_mount().instructions.startswith(conversation_notes_static_instructions(''))
    assert 'only tasks the account owner' in system_text
    assert 'Exclude observations and status statements' in system_text
    suffix = json.loads(user['content'])
    assert suffix['account_owner_name'] == 'Riley Chen'
    assert 'action_item_rules' not in suffix
    if spellings:
        assert suffix['known_spellings'] == spellings
        assert spellings not in suffix['capture_evidence']
        assert spellings not in system_text
    else:
        assert 'known_spellings' not in suffix
