"""Synthetic stand-ins for private fixtures; never load real conversation content."""

import json
import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

from testing.episode_notes import eval as cli
from testing.episode_notes.cache import validate_output_path
from testing.episode_notes.prompts import BASELINE_PROMPT, CANDIDATE_MODEL, CANDIDATE_PROMPT, candidate_request
from testing.episode_notes.runner import JUDGE_PROMPT, REFERENCE_PROMPT, evaluate, stored_note_map
from testing.episode_notes.schema import (
    EpisodeFixture,
    EvidenceBundle,
    ExpectedProperties,
    FixtureSet,
    Observation,
    load_fixtures,
)

ROOT = Path(__file__).resolve().parents[3]


def fixtures(synthetic=True, split='dev'):
    return FixtureSet(
        schema_version='episode_notes.v1',
        synthetic=synthetic,
        episodes=[
            EpisodeFixture(
                id='real-synthetic-standin',
                stratum='invented',
                split=split,
                evidence=EvidenceBundle(
                    started_at='2026-01-01T10:00:00+00:00',
                    finished_at='2026-01-01T10:05:00+00:00',
                    transcript_segments=[
                        Observation(id='speech:1', actor='Ari', content='The synthetic budget was approved.')
                    ],
                    roster=[Observation(id='roster:1', actor='Ari', content='Ari is on the synthetic roster.')],
                    screen_ocr=[Observation(id='screen:1', content='Synthetic document with budget details')],
                    prior_conversations=[Observation(id='prior:1', content='An earlier invented budget discussion.')],
                ),
                expected=ExpectedProperties(must_cover=['Synthetic budget']),
            )
        ],
    )


def fake(prompt, payload):
    if prompt == REFERENCE_PROMPT:
        assert 'expected' not in payload
        return {'narrative': 'Synthetic budget approved', 'claims': []}
    if prompt == JUDGE_PROMPT:
        return {
            'informativeness_gap': 0.1,
            'unsupported_claims': 0,
            'wrong_provenance_claims': 0,
            'unrelated_content_claims': 0,
            'vacuous': False,
            'property_failures': [],
            'reasons': [],
        }
    assert prompt in (CANDIDATE_PROMPT, BASELINE_PROMPT)
    return {'title': 'Synthetic budget approval', 'overview': 'Ari approved the synthetic budget.'}


def test_non_synthetic_loading_from_explicit_path(tmp_path):
    path = tmp_path / 'private-standin.json'
    path.write_text(fixtures(synthetic=False).model_dump_json())
    assert load_fixtures(path).synthetic is False


def test_non_synthetic_outputs_and_caches_refused_inside_worktrees(tmp_path):
    with pytest.raises(ValueError, match='outside every git worktree'):
        validate_output_path(ROOT / '.agent-briefs' / 'private-output.json', synthetic=False)
    alias = tmp_path / 'alias'
    alias.symlink_to(ROOT, target_is_directory=True)
    with pytest.raises(ValueError, match='outside every git worktree'):
        validate_output_path(alias / 'private-output.json', synthetic=False)
    with pytest.raises(ValueError, match='outside every git worktree'):
        evaluate(fixtures(synthetic=False), fake, cache_dir=ROOT / '.agent-briefs' / 'cache')
    validate_output_path(tmp_path / 'allowed.json', synthetic=False)
    validate_output_path(ROOT / '.agent-briefs' / 'synthetic.json', synthetic=True)


@pytest.mark.parametrize('arms', [('episode',), ('baseline',), ('episode', 'baseline')])
def test_arm_selection_and_same_reference(arms):
    calls = []

    def llm(prompt, payload):
        calls.append((prompt, payload))
        return fake(prompt, payload)

    report = evaluate(fixtures(), llm, arms=arms)
    assert set(report['arms']) == set(arms)
    assert [row['arm'] for row in report['cases']] == list(arms)
    assert sum(prompt == REFERENCE_PROMPT for prompt, _ in calls) == 1
    refs = [payload['reference'] for prompt, payload in calls if prompt == JUDGE_PROMPT]
    assert all(ref == refs[0] for ref in refs)
    if len(arms) == 2:
        assert report['paired']['episode_vs_baseline']['overall']['count'] == 1


def test_reference_and_arm_caches_resume_without_calls(tmp_path):
    calls = []

    def llm(prompt, payload):
        calls.append(prompt)
        return fake(prompt, payload)

    first = evaluate(fixtures(), llm, arms=('episode', 'baseline'), cache_dir=tmp_path)
    assert len(calls) == 5
    assert len(list(tmp_path.glob('reference-*.json'))) == 1
    calls.clear()
    resumed = evaluate(fixtures(), llm, arms=('episode', 'baseline'), cache_dir=tmp_path)
    assert resumed == first
    assert not calls
    # Expectations affect only scoring, never the all-evidence reference or generation.
    changed = fixtures()
    changed.episodes[0].expected.must_cover.append('Another synthetic property')
    evaluate(changed, llm, arms=('episode',), cache_dir=tmp_path)
    assert calls == [JUDGE_PROMPT]
    assert all((path.stat().st_mode & 0o777) == 0o600 for path in tmp_path.glob('*.json'))


def test_stored_fixture_mapping_and_all_arm_paired_report(tmp_path):
    stored = {
        'fixture_id': 'real-synthetic-standin',
        'conversation_id': 'fake-uuid',
        'title': 'Stored synthetic title',
        'overview': 'Stored synthetic overview',
        'sections_note': '- Synthetic stored detail.',
        'fetched_via': 'ignored metadata',
    }
    (tmp_path / 'fake-uuid.json').write_text(json.dumps(stored))
    note = stored_note_map(tmp_path)['real-synthetic-standin']
    assert 'conversation_id' not in note and 'fetched_via' not in note
    assert note['sections'][0]['body_markdown'] == stored['sections_note']
    calls = []

    def llm(prompt, payload):
        calls.append(prompt)
        return fake(prompt, payload)

    report = evaluate(fixtures(), llm, arms=('episode', 'baseline', 'stored'), stored_notes=tmp_path)
    assert len(calls) == 6  # one reference, two generated candidates, three judgments
    assert set(report['paired']) == {'episode_vs_baseline', 'episode_vs_stored'}
    stored_row = [row for row in report['cases'] if row['arm'] == 'stored'][0]
    assert not stored_row['generation_performed']
    assert stored_row['candidate_cost'] == {
        'input_tokens': None,
        'output_tokens': None,
        'latency_seconds': None,
        'cached_tokens': None,
        'claim_tokens': None,
        'reasoning_tokens': None,
        'provider_cost': None,
    }
    with pytest.raises(ValueError, match='requires --stored-notes'):
        evaluate(fixtures(), fake, arms=('stored',))


def test_held_out_requires_frozen_acknowledgement(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match='--frozen'):
        evaluate(fixtures(split='held_out'), fake, split='held_out')
    assert evaluate(fixtures(split='held_out'), fake, split='held_out', frozen=True)['frozen']
    path = tmp_path / 'synthetic-held.json'
    path.write_text(fixtures(split='held_out').model_dump_json())
    with pytest.raises(SystemExit) as exc:
        cli.main(['--fixtures', str(path), '--split', 'held_out', '--output', str(tmp_path / 'report.json')])
    assert exc.value.code == 2
    monkeypatch.setattr(cli, 'CompatibleEndpoint', lambda **kwargs: fake)
    cli.main(['--fixtures', str(path), '--split', 'held_out', '--frozen', '--output', str(tmp_path / 'report.json')])
    assert json.loads((tmp_path / 'report.json').read_text())['frozen']


def test_cli_refuses_private_output_before_endpoint_construction(tmp_path, monkeypatch):
    path = tmp_path / 'private-standin.json'
    path.write_text(fixtures(synthetic=False).model_dump_json())
    constructed = []
    monkeypatch.setattr(cli, 'CompatibleEndpoint', lambda **kw: constructed.append(kw))
    with pytest.raises(SystemExit) as exc:
        cli.main(['--fixtures', str(path), '--output', str(ROOT / '.agent-briefs' / 'forbidden.json')])
    assert exc.value.code == 2 and not constructed


def test_baseline_uses_production_prefix_and_background_builders():
    prompt, payload = candidate_request(fixtures().episodes[0], 'baseline')
    assert prompt == BASELINE_PROMPT
    for marker in (
        'CONVERSATION METADATA',
        'FULL TRANSCRIPT',
        'PARTICIPANTS',
        'BACKGROUND CONTEXT',
        'SCREEN ACTIVITY',
        'PRIOR MEETINGS',
    ):
        assert marker in payload['instructions']
    assert 'EPISODE EVIDENCE' not in payload['instructions']


def test_candidate_model_pinned_and_concurrency_bounded():
    with pytest.raises(ValueError, match='production'):
        evaluate(fixtures(), fake, candidate_model='unapproved-model')
    with pytest.raises(ValueError, match='concurrency'):
        evaluate(fixtures(), fake, concurrency=9)
    assert evaluate(fixtures(), fake, concurrency=2)['models']['candidate'] == CANDIDATE_MODEL


def test_eval_imports_never_reach_database_clients():
    code = '''import importlib.abc, sys
class Guard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'database' or fullname.startswith('database.'):
            raise RuntimeError('offline eval imported a database module')
sys.meta_path.insert(0, Guard())
import testing.episode_notes.eval
'''
    completed = subprocess.run(
        [sys.executable, '-c', code], cwd=ROOT / 'backend', env=os.environ.copy(), capture_output=True, text=True
    )
    assert completed.returncode == 0, completed.stderr


def test_candidate_pin_matches_production_route_without_importing_clients():
    tree = ast.parse((ROOT / 'backend/utils/llm/model_config.py').read_text())
    assignments = {
        node.targets[0].id: node.value
        for node in tree.body
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
    }
    assert CANDIDATE_MODEL == 'openai/' + ast.literal_eval(assignments['LUNA_MODEL'])
    profile = next(
        node.value
        for node in tree.body
        if isinstance(node, ast.AnnAssign) and getattr(node.target, 'id', None) == '_TWO_TIER_MODEL_PROFILE'
    )
    route = next(value for key, value in zip(profile.keys, profile.values) if ast.literal_eval(key) == 'conv_structure')
    assert isinstance(route.elts[0], ast.Name) and route.elts[0].id == 'LUNA_MODEL'
    assert ast.literal_eval(route.elts[1]) == 'openai'


def test_supported_unrelated_content_metric_per_arm_stratum_and_pair(tmp_path):
    bundle = fixtures()
    bundle.episodes[0].evidence.screen_ocr.append(
        Observation(id='screen:unrelated', content='An unrelated document lists a synthetic recipe.')
    )
    stored = tmp_path / 'stored'
    stored.mkdir()
    (stored / 'standin.json').write_text(json.dumps({'fixture_id': bundle.episodes[0].id, 'title': 'stored'}))

    def fake(prompt, payload):
        if prompt == REFERENCE_PROMPT:
            return {'narrative': 'Synthetic episode', 'claims': []}
        if prompt in (CANDIDATE_PROMPT, BASELINE_PROMPT):
            return {'title': 'episode' if prompt == CANDIDATE_PROMPT else 'baseline'}
        assert prompt == JUDGE_PROMPT
        assert 'ALL visible fields' in prompt
        assert 'source-supported but unrelated claims count' in prompt
        return {
            'informativeness_gap': 0.1,
            'unsupported_claims': 0,
            'wrong_provenance_claims': 0,
            'unrelated_content_claims': {'episode': 1, 'baseline': 2, 'stored': 3}[payload['candidate']['title']],
            'vacuous': False,
            'property_failures': [],
            'reasons': ['Synthetic supported but unrelated detail'],
        }

    report = evaluate(bundle, fake, arms=('episode', 'baseline', 'stored'), stored_notes=stored)
    for arm, count in [('episode', 1), ('baseline', 2), ('stored', 3)]:
        assert report['arms'][arm]['overall']['unrelated_content_claims'] == count
        assert report['arms'][arm]['strata']['invented']['unrelated_content_claims'] == count
        assert report['arms'][arm]['overall']['faithfulness_pass'] == 1
    for arm, delta in [('baseline', -1), ('stored', -2)]:
        paired = report['paired'][f'episode_vs_{arm}']
        assert paired['overall']['mean_episode_minus_comparator']['unrelated_content_claims'] == delta
        assert paired['strata']['invented']['mean_episode_minus_comparator']['unrelated_content_claims'] == delta


def test_external_legacy_fixture_tags_are_discarded_without_relaxing_schema(tmp_path):
    data = fixtures(synthetic=False).model_dump()
    data['episodes'][0]['evidence']['screen_ocr'][0]['sensitivity'] = 'private'
    data['episodes'][0]['expected']['private_claims'] = ['Synthetic legacy expectation']
    path = tmp_path / 'external-standin.json'
    path.write_text(json.dumps(data))
    result = load_fixtures(path)
    assert not result.synthetic
    evidence = result.episodes[0].evidence.model_dump()
    assert 'sensitivity' not in evidence['screen_ocr'][0]
    assert 'private_claims' not in result.episodes[0].expected.model_dump()
    data['episodes'][0]['evidence']['screen_ocr'][0]['unknown_metadata'] = True
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='extra_forbidden'):
        load_fixtures(path)
