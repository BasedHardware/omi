"""Synthetic contracts for generated notes; no packet data or provider access."""

import json
from datetime import datetime, timezone

import pytest

from utils.summary_quality import (
    NOTE_QUALITY_RULES,
    clean_structured,
    episode_quality,
    safe_body,
    stable_title,
    title_or_fallback,
)


@pytest.fixture(scope='module', autouse=True)
def load_contract_dependencies():
    # Model/client module loading belongs to setup, outside the fast-unit call budget.
    from utils.episodes import composer, incremental  # noqa: F401
    from utils.llm import notes_output  # noqa: F401


@pytest.mark.parametrize('title', ['', '  ', None, '—', 'New moment', 'Launch plan missing from transcript'])
def test_missing_and_unsafe_titles_have_deterministic_nonempty_labels(title):
    assert title_or_fallback(title) == 'Discussion notes'
    assert title_or_fallback(title, index=3) == 'Discussion 3'


@pytest.mark.parametrize(
    'text',
    [
        'The transcript is missing.',
        'Audio gaps prevent a recap.',
        'Still processing the recording.',
        'A speaker discusses budgets.',
        'Episode notes of city life continue.',
        'The topic was not captured in the transcript.',
        'Our recording is unavailable.',
        'Pipeline failures prevent a recap.',
    ],
)
def test_mechanics_and_meta_narration_are_removed(text):
    assert safe_body(text) == ''


@pytest.mark.parametrize(
    'text',
    [
        'The pilot budget is $8,000; approval is due Friday.',
        'Build a transcript editor with search.',
        'Processing invoices costs $40 per month.',
        'An audio-gap detector needs unit tests.',
        'Riley proposed a transcription service.',
        'Fix pipeline failures before Friday.',
        'Investigate audio gaps in the mobile app.',
        'Audio gaps in the mobile app need investigation.',
    ],
)
def test_concrete_facts_and_product_discussion_survive(text):
    assert safe_body(text) == text


def test_filter_preserves_other_sentences_and_markdown():
    assert safe_body('- The budget is $8,000. Transcript is missing.\n  - Approval is due Friday.') == (
        '- The budget is $8,000.\n  - Approval is due Friday.'
    )


def test_structure_filter_does_not_invent_summary_for_empty_output():
    from utils.conversations.summary_delivery import present
    from utils.llm.notes_output import NotesOutput

    output = NotesOutput.model_validate(
        {
            'title': '—',
            'overview': 'Transcript is missing.',
            'sections': [
                {'heading': '', 'body_markdown': '- Audio gaps prevent a recap.'},
            ],
        }
    )
    assert output.title == 'Discussion notes'
    assert not present(output.to_structured())


def test_notes_output_parser_keeps_concrete_sections_and_repairs_empty_heading():
    from utils.llm.notes_output import NotesOutput

    output = NotesOutput.model_validate(
        {
            'title': None,
            'sections': [
                {'heading': 'Missing transcript', 'body_markdown': '- The pilot budget is $8,000.'},
            ],
        }
    )
    assert output.title
    assert output.sections[0].heading == 'Discussion 1'
    assert output.sections[0].body_markdown == '- The pilot budget is $8,000.'


def test_stability_is_independent_of_word_growth_repetition_and_proposed_rewording():
    assert stable_title('Pilot budget', 'Launch budget and approval') == ('Pilot budget', None)
    assert stable_title('Transcript is missing', 'Pilot budget') == ('Pilot budget', 'invalid_title_repaired')
    assert stable_title('', 'Pilot budget') == ('Pilot budget', 'initial_title')
    assert stable_title('Discussion notes', 'Pilot budget') == ('Pilot budget', 'invalid_title_repaired')


def test_episode_moment_identity_preserves_title_and_filters_nested_points():
    old = {'title': 'Pilot budget', 'moments': [{'conversation_id': 'a', 'start_offset': 0, 'heading': 'Approval'}]}
    new = {
        'title': 'Renamed budget',
        'bullets': ['Transcript is missing.', 'Approval is due Friday.'],
        'moments': [
            {
                'conversation_id': 'a',
                'start_offset': 0,
                'heading': 'New approval wording',
                'points': [
                    {
                        'text': 'Approval is due Friday.',
                        'details': ['Audio gaps prevent a recap.', 'Riley will review.'],
                    },
                    {'text': 'Transcript is missing.'},
                ],
            },
            {'conversation_id': 'b', 'start_offset': 0, 'heading': ''},
        ],
    }
    result = episode_quality(old, new)
    assert result['title'] == 'Pilot budget'
    assert result['bullets'] == ['Approval is due Friday.']
    assert result['moments'][0]['heading'] == 'Approval'
    assert result['moments'][0]['points'] == [{'text': 'Approval is due Friday.', 'details': ['Riley will review.']}]
    assert result['moments'][1]['heading'] == 'Discussion 2'
    assert new['moments'][0]['heading'] == 'New approval wording'  # caller snapshot stays intact


def test_incremental_parser_and_apply_share_contract():
    from utils.episodes.state import apply_update, parse_update

    parsed = parse_update(
        json.dumps(
            {
                'title': 'New moment',
                'moment_heading': '—',
                'bullets': [
                    'Audio gaps prevent a recap.',
                    'The pilot budget is $8,000.',
                ],
            }
        ),
        known_item_ids=[],
    )
    assert parsed.moment_heading
    result = apply_update(
        {'title': 'Pilot budget'}, parsed, conversation_id='a', segment_offset=10, now=datetime.now(timezone.utc)
    )
    assert result['title'] == 'Pilot budget'
    assert result['bullets'] == ['The pilot budget is $8,000.']


def test_all_prompt_paths_carry_specificity_and_no_mechanics_contract():
    from utils.episodes import composer, incremental
    from utils.llm.conversation_notes_prompts import conversation_notes_static_instructions
    from utils.llm.notes_agent_prompt import instructions_for_run

    prompts = [
        composer.SYSTEM_PROMPT,
        incremental.PROMPT_PREFIX,
        incremental._moment_prompt('en'),
        conversation_notes_static_instructions('{}'),
        instructions_for_run(),
    ]
    for prompt in prompts:
        assert NOTE_QUALITY_RULES in prompt
        assert 'number with its referent' in prompt
        assert 'Do not invent names' in prompt
    assert 'actions in the third person' not in incremental.PROMPT_PREFIX


def test_composer_boundary_drift_keeps_visible_heading_and_identity_once():
    previous = {
        'title': 'Pilot budget',
        'moments': [
            {'id': 'stable', 'conversation_id': 'a', 'start_offset': 10, 'end_offset': 110, 'heading': 'Approval'},
        ],
    }
    proposal = {
        'title': 'Pilot spending',
        'moments': [
            {
                'id': 'fresh',
                'conversation_id': 'a',
                'start_offset': 15,
                'end_offset': 115,
                'heading': 'Approval rephrased',
            },
            {
                'id': 'fresh2',
                'conversation_id': 'a',
                'start_offset': 30,
                'end_offset': 100,
                'heading': 'A distinct chapter',
            },
        ],
    }
    moments = episode_quality(previous, proposal)['moments']
    assert moments[0]['id'] == 'stable' and moments[0]['heading'] == 'Approval'
    assert moments[1]['id'] == 'fresh2' and moments[1]['heading'] == 'A distinct chapter'


def test_episode_storage_discard_clears_titles_instead_of_restoring_seen_content():
    from database.episodes import _merge_state

    old = {
        'title': 'Pilot budget',
        'started_at': datetime.now(timezone.utc),
        'conversation_ids': ['a'],
        'moments': [{'conversation_id': 'a', 'start_offset': 0, 'heading': 'Approval'}],
    }
    result = _merge_state(old, {'discarded_conversation_ids': ['a']})
    assert result['title'] == '' and result['moments'] == []


def test_episode_storage_records_repair_but_freezes_valid_title():
    from database.episodes import _merge_state

    old = {'title': 'Missing transcript', 'started_at': datetime.now(timezone.utc)}
    result = _merge_state(old, {'title': 'Pilot budget'})
    assert result['title_change_reason'] == 'invalid_title_repaired' and result['title_changed_at']
    assert _merge_state(result, {'title': 'Reworded budget'})['title'] == 'Pilot budget'


def test_explicit_empty_evidence_clear_keeps_no_old_title():
    from database.episodes import _merge_state

    old = {'title': 'Pilot budget', 'started_at': datetime.now(timezone.utc)}
    result = _merge_state(old, {'title': '', 'bullets': [], 'moments': []})
    assert result['title'] == '' and result['moments'] == []


@pytest.mark.parametrize('trusted', [False, True])
def test_episode_prompt_renderers_reuse_owner_authority_and_keep_unknown_speech(monkeypatch, trusted):
    from utils.episodes import composer, incremental
    from utils.conversations.transcript_for_llm import owner_safe_transcript_segments
    from utils.conversations.owner_attribution import speaker_role_map
    from zoneinfo import ZoneInfo

    monkeypatch.setenv('SPEAKER_ROLE_PROJECTION_ENABLED', 'true')
    monkeypatch.setenv('NOTES_PACKET_V2_MODE', 'off')
    segments = [
        {
            'text': 'I will approve the pilot budget.',
            'is_user': True,
            'speaker_id': 1,
            'speaker_id_scope': 'synthetic',
            'speaker_identity_status': 'user' if trusted else 'ambiguous',
            'speaker_match_source': 'conversation_voice' if trusted else 'carried',
            'start': 0,
            'end': 5,
        },
        {
            'text': 'I prefer a smaller pilot.',
            'is_user': False,
            'speaker_id': 2,
            'speaker_id_scope': 'synthetic',
            'speaker_identity_status': 'no_match',
            'start': 6,
            'end': 10,
        },
    ]
    roles = speaker_role_map(segments)
    assert (roles.for_segment(segments[0]).role == 'primary_user') is trusted
    safe, _ = owner_safe_transcript_segments(segments)
    assert bool(safe[0]['is_user']) is trusted and len(safe) == 2
    lines = composer.transcript_lines(
        {'started_at': datetime.now(timezone.utc), 'transcript_segments': segments}, 'Riley', ZoneInfo('UTC')
    )
    rendered = '\n'.join(text for _, text in lines)
    assert ('Riley:' in rendered) is trusted
    assert 'I prefer a smaller pilot.' in rendered
    live = incremental.render_moment(segments, owner_name='Riley').text
    assert ('Riley:' in live) is trusted
    assert 'I prefer a smaller pilot.' in live
    assert segments[0]['is_user'] is True  # prompt-only copy; persisted labels untouched


@pytest.mark.parametrize(
    'text',
    [
        'There is insufficient evidence to approve the claim.',
        'The review found a lack of evidence for the proposed treatment.',
        'Our pipeline has failures; Riley will fix it by Friday.',
        'The team discussed missing transcripts in the transcription product.',
        'No transcript editor was approved.',
        'The audio product processes recordings for $8 per month.',
        '証拠が不十分なため、承認は見送った。',
        '文字起こし製品の音声処理を改善する。',
    ],
)
def test_subject_matter_evidence_and_audio_products_are_preserved(text):
    assert safe_body(text) == text


def test_japanese_availability_backstop_and_generic_same_call_signal():
    from utils.llm.notes_output import NotesOutput
    from utils.episodes.state import parse_update

    japanese = '文字起こしがないため、会議の内容を要約できません。'
    assert safe_body(japanese) == ''
    assert safe_body('予算は8万円。' + japanese) == '予算は8万円。'
    for text in [japanese, '녹취 자료를 사용할 수 없어 요약할 수 없습니다.', 'No se puede resumir esta grabación.']:
        output = NotesOutput.model_validate(
            {
                'title': text,
                'overview': '予算は8万円。',
                'sections': [{'heading': '予算', 'body_markdown': text}],
                'quality_flags': [
                    {'field': 'title', 'kind': 'capture_availability'},
                    {'field': 'sections.0.body_markdown', 'kind': 'capture_availability'},
                ],
            }
        )
        assert output.title and output.title != text
        assert output.overview == '予算は8万円。' and not output.sections
        assert 'quality_flags' not in output.to_structured().model_dump()
        update = parse_update(
            json.dumps(
                {
                    'title': '予算',
                    'moment_heading': text,
                    'bullets': [text, '予算は8万円。'],
                    'quality_flags': [
                        {'field': 'moment_heading', 'kind': 'capture_availability'},
                        {'field': 'bullets.0', 'kind': 'capture_availability'},
                    ],
                }
            ),
            known_item_ids=[],
        )
        assert update.moment_heading and update.bullets == ['予算は8万円。']


def test_same_call_signal_cannot_remove_tasks_or_whole_chapters():
    from utils.summary_quality import filter_output

    payload = {'title': 'Launch', 'action_items': [{'description': 'Review Friday'}], 'chapters': [{'title': 'Budget'}]}
    flags = [
        {'field': path, 'kind': 'capture_availability'}
        for path in ['action_items.0.description', 'chapters.0', '__class__']
    ]
    assert filter_output({**payload, 'quality_flags': flags}) == payload


def test_material_growth_replaces_titles_but_minor_changes_do_not():
    assert stable_title('Budget planning', 'Launch decision', previous_units=100, current_units=120) == (
        'Budget planning',
        None,
    )
    assert stable_title('Budget planning', 'Launch decision', previous_units=100, current_units=200) == (
        'Launch decision',
        'material_content_growth',
    )
    assert stable_title('Budget planning', 'Launch decision', previous_units=0, current_units=200) == (
        'Budget planning',
        None,
    )
    old = {'title': 'Budget planning', 'content_word_units': 100, 'title_content_units': 100}
    minor = episode_quality(old, {'title': 'New headline', 'content_word_units': 120})
    assert minor['title'] == old['title'] and minor['title_content_units'] == 100
    changed = episode_quality(minor, {'title': 'Launch decision', 'content_word_units': 200})
    assert changed['title'] == 'Launch decision' and changed['title_change_reason'] == 'material_content_growth'
    assert changed['title_content_units'] == 200
    edited = episode_quality(
        {**old, 'user_title': 'My headline'}, {'title': 'Launch decision', 'content_word_units': 200}
    )
    assert edited['title'] == 'My headline'


def test_growth_threshold_is_forty_percent_of_current_content_and_has_a_small_edit_floor():
    assert stable_title('Old', 'New', previous_units=60, current_units=100) == ('New', 'material_content_growth')
    assert stable_title('Old', 'New', previous_units=61, current_units=100) == ('Old', None)
    assert stable_title('Old', 'New', previous_units=1, current_units=2) == ('Old', None)


def test_matched_chapter_growth_allows_a_new_heading_with_an_audit_reason():
    old = {
        'title': 'Session',
        'moments': [{'id': 'm', 'conversation_id': 'c', 'start_offset': 0, 'end_offset': 60, 'heading': 'Budget'}],
    }
    proposed = {
        'title': 'Session',
        'moments': [
            {'id': 'm', 'conversation_id': 'c', 'start_offset': 0, 'end_offset': 100, 'heading': 'Launch decision'}
        ],
    }
    result = episode_quality(old, proposed)
    assert result['moments'][0]['heading'] == 'Launch decision'
    assert result['moments'][0]['title_change_reason'] == 'material_content_growth'
    assert result['moments'][0]['id'] == 'm'


def test_generic_signal_preserves_real_facts_in_a_mixed_non_english_section():
    from utils.llm.notes_output import NotesOutput

    availability = 'No se puede resumir esta grabación.'
    output = NotesOutput.model_validate(
        {
            'title': 'Presupuesto',
            'sections': [
                {
                    'heading': 'Plan',
                    'body_markdown': '- El presupuesto es de 8.000 euros.\n- '
                    + availability
                    + '\n- La aprobación vence el viernes.',
                }
            ],
            'quality_flags': [
                {'field': 'sections.0.body_markdown', 'kind': 'capture_availability', 'statement': availability}
            ],
        }
    )
    assert output.sections[0].body_markdown == '- El presupuesto es de 8.000 euros.\n- La aprobación vence el viernes.'
    invalid_span = NotesOutput.model_validate(
        {
            'title': 'Evidence',
            'overview': 'There is insufficient evidence to approve the claim.',
            'quality_flags': [{'field': 'overview', 'kind': 'capture_availability', 'statement': 'not an exact span'}],
        }
    )
    assert invalid_span.overview == 'There is insufficient evidence to approve the claim.'
