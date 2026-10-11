"""Deterministic synthetic checks for DEV-only ablations; no external conversations."""

from dataclasses import replace

import pytest

from config.episode_writer import EpisodeWriterSettings, episode_writer_settings
from testing.episode_notes.generation_experiments import apply_edits, verify_draft, extract_facts, fact_check
from testing.episode_notes.policy_replay import replay_policy
from testing.episode_notes.runner import evaluate, REFERENCE_PROMPT, JUDGE_PROMPT
from testing.episode_notes.schema import (
    EpisodeFixture,
    EvidenceBundle,
    Observation,
    ExpectedProperties,
    FixtureSet,
    LLMResult,
    LLMCallError,
)
from testing.episode_notes.selection_experiments import experiment_selection
from utils.conversations.episode_evidence import EvidenceItem


def fixture():
    episode = EpisodeFixture(
        id='synthetic-routing',
        stratum='synthetic',
        split='dev',
        evidence=EvidenceBundle(
            started_at='2026-01-01T10:00:00+00:00',
            finished_at='2026-01-01T10:30:00+00:00',
            transcript_segments=[Observation(id='speech:1', content='We approved the new launch date.')],
        ),
        expected=ExpectedProperties(must_cover=[]),
    )
    return FixtureSet(schema_version='episode_notes.v1', synthetic=True, episodes=[episode])


def items():
    return [
        EvidenceItem(id='speech:1', source_kind='speech', content='The revised launch date was approved'),
        EvidenceItem(id='screen:1', source_kind='screen_ocr', content='The revised launch date is shown'),
        EvidenceItem(id='device:1', source_kind='device_state', content='Capture finished'),
    ]


def test_edits_use_exact_unique_anchors_and_preserve_untouched_fields():
    note = {
        'title': 'Launch',
        'overview': 'Ari said approved. A screen showed the date.',
        'note_claims': [{'text': 'stale'}],
    }
    edited, count = apply_edits(
        note, [{'target': '/overview', 'text': 'Ari said approved.', 'replacement': 'Approval was inferred.'}]
    )
    assert edited['overview'] == 'Approval was inferred. A screen showed the date.'
    assert count == 1 and edited['title'] == note['title'] and edited['note_claims'] == []
    assert note['note_claims']  # Input stays untouched.


@pytest.mark.parametrize(
    'edit',
    [
        {'target': '/missing', 'text': 'Launch', 'replacement': ''},
        {'target': '/title', 'text': 'unsupported', 'replacement': ''},
        {'target': '/title', 'text': 'Launch', 'replacement': 'x' * 100},
    ],
)
def test_invalid_edits_cannot_rewrite_arbitrary_note_fields(edit):
    with pytest.raises(ValueError):
        apply_edits({'title': 'Launch'}, [edit])


def test_empty_helper_result_is_rejected():
    with pytest.raises(ValueError, match='empty_edit_result'):
        apply_edits({'overview': 'Approved'}, [{'target': '/overview', 'text': 'Approved', 'replacement': ''}])


def test_paid_invalid_repair_retains_its_receipt():
    with pytest.raises(LLMCallError) as error:
        verify_draft(
            LLMResult(content={'title': 'Launch'}),
            items(),
            llm=lambda *_: LLMResult(content={'edits': None}, provider_cost=0.001),
            cache_dir=None,
            model='openai/gpt-6-luna',
        )
    assert error.value.result.provider_cost == 0.001


def test_fact_extraction_requires_original_exact_quotes():
    selected, _ = extract_facts(
        items(),
        llm=lambda *_: {'facts': [{'id': 'speech:1', 'quote': 'launch date'}]},
        cache_dir=None,
        model='openai/gpt-6-luna',
    )
    assert [(i.id, i.content) for i in selected] == [('speech:1', 'launch date'), ('device:1', 'Capture finished')]
    with pytest.raises(LLMCallError, match='invalid_fact_quote'):
        extract_facts(
            items(),
            llm=lambda *_: {'facts': [{'id': 'speech:1', 'quote': 'Invented deadline'}]},
            cache_dir=None,
            model='openai/gpt-6-luna',
        )


@pytest.mark.parametrize('facts', [None, ['malformed']])
def test_malformed_fact_extraction_retains_paid_receipt(facts):
    with pytest.raises(LLMCallError, match='invalid_fact_extraction') as error:
        extract_facts(
            items(),
            llm=lambda *_: LLMResult(content={'facts': facts}, provider_cost=0.001),
            cache_dir=None,
            model='openai/gpt-6-luna',
        )
    assert error.value.result.provider_cost == 0.001


@pytest.mark.parametrize('mode', ['jev_veto', 'jev_per_source', 'jev_rank', 'jev_discussed', 'jev_choice'])
def test_selector_variants_only_remove_from_deterministic_pool(mode):
    def fake(_, payload):
        scores = {
            q: {'discussed': 0.1, 'background': 0.1, 'unrelated': 0.8} if question['type'] == 'choice' else 0.1
            for q, question in payload['questions'].items()
        }
        return {'scores': scores}

    selected, _, _ = experiment_selection(
        items(), fixture().episodes[0], mode=mode, cutoff=0.3, cache_dir=None, llm=fake
    )
    assert {i.id for i in selected} <= {i.id for i in items()}
    assert selected[0].source_kind == 'speech' and selected[-1].source_kind == 'device_state'


def test_oversize_fact_check_does_not_guess_from_truncated_evidence():
    enormous = [items()[0].model_copy(update={'content': 'x' * 30000})]
    draft = LLMResult(content={'title': 'Launch'})
    result, receipt, meta = fact_check(
        draft, enormous, llm=lambda *_: pytest.fail('must not call'), cache_dir=None, cutoff=0.3
    )
    assert result is draft and receipt is None and meta['fact_check_fallback'] == 'oversize'


def test_experimental_mode_cannot_run_held_out_even_when_frozen():
    with pytest.raises(ValueError, match='DEV only'):
        evaluate(fixture(), lambda *_: {}, split='held_out', frozen=True, experiment='verify')


def test_replay_refuses_mismatched_contract_and_missing_candidate():
    report = {'split': 'dev', 'reference_prompt_sha256': 'same', 'judge_prompt_sha256': 'same', 'cases': []}
    with pytest.raises(ValueError, match='missing candidate'):
        replay_policy(fixture(), report, report, lambda *_: False)
    with pytest.raises(ValueError, match='shared judge'):
        replay_policy(fixture(), report, {**report, 'judge_prompt_sha256': 'other'}, lambda *_: False)


def test_verify_cost_is_in_candidate_receipt_without_extra_writer():
    calls = []

    def fake(prompt, payload):
        calls.append(prompt)
        if prompt == REFERENCE_PROMPT:
            return {'narrative': 'approved', 'claims': []}
        if prompt == JUDGE_PROMPT:
            return {
                'informativeness_gap': 0,
                'unsupported_claims': 0,
                'wrong_provenance_claims': 0,
                'unrelated_content_claims': 0,
                'vacuous': False,
                'property_failures': [],
                'reasons': [],
            }
        if 'Check this draft' in prompt:
            return LLMResult(content={'edits': []}, provider_cost=0.002, latency_seconds=1)
        return LLMResult(
            content={'title': 'Launch', 'overview': 'Approval captured', 'note_claims': []},
            provider_cost=0.003,
            latency_seconds=2,
        )

    report = evaluate(fixture(), fake, settings=EpisodeWriterSettings(), experiment='verify')
    assert report['cases'][0]['candidate_cost']['provider_cost'] == pytest.approx(0.005)
    assert report['cases'][0]['candidate_cost']['latency_seconds'] == 3
    assert len(calls) == 4


def test_output_budget_is_keyed_and_only_applied_to_c6_then_one_c7_fallback():
    sample = fixture()
    sample.episodes[0].evidence.transcript_segments[0].content = 'speech ' * 1000
    sample.episodes[0].evidence.device_state = [Observation(id='device:1', content='recording')]
    writers = []

    def fake(prompt, payload):
        if prompt == REFERENCE_PROMPT:
            return {'narrative': 'synthetic', 'claims': []}
        if prompt == JUDGE_PROMPT:
            return {
                'informativeness_gap': 0,
                'unsupported_claims': 0,
                'wrong_provenance_claims': 0,
                'unrelated_content_claims': 0,
                'vacuous': False,
                'property_failures': [],
                'reasons': [],
            }
        options = payload['_request_options']
        writers.append(options)
        if options['effort'] == 'xhigh':
            assert options['max_tokens'] == 8000
            raise LLMCallError(
                'output_truncated',
                LLMResult(content={}, provider_cost=0.008, latency_seconds=80, finish_reason='length'),
            )
        assert 'max_tokens' not in options and options['effort'] == 'low'
        return LLMResult(
            content={'title': 'Synthetic launch', 'overview': 'Spoken plan captured', 'note_claims': []},
            provider_cost=0.002,
            latency_seconds=10,
        )

    report = evaluate(
        sample, fake, settings=EpisodeWriterSettings(tiered=True, tier_min_words=1000), candidate_max_tokens=8000
    )
    row = report['cases'][0]
    assert len(writers) == 2 and row['tier_fallback'] and row['status'] == 'ok'
    assert row['candidate_cost']['provider_cost'] == pytest.approx(0.010)
    assert row['candidate_cost']['latency_seconds'] == 90


def test_jev_router_is_one_typed_question_with_bounded_excerpt():
    from testing.episode_notes.jev_router import router_payload

    episode = fixture().episodes[0]
    episode.evidence.transcript_segments[0].content = 'speech ' * 10000
    payload = router_payload(episode)
    assert len(payload['questions']) == 1 and payload['questions']['careful_summary']['type'] == 'noul'
    assert len(payload['state']) < 24000 and '[excerpt gap]' in payload['state']
