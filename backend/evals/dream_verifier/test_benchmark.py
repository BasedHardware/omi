"""Offline regressions. Run via backend/test.sh using a selected-file list."""

import asyncio
import copy
import json

import pytest

from evals.dream_verifier.audit import reconcile
from evals.dream_verifier.contracts import ROOT, Snapshot, canonical, digest, load_items, model_input, project
from evals.dream_verifier.detection import candidate_item, corpora, evaluate_detection, shortlists
from evals.dream_verifier.deterministic import local_check
from evals.dream_verifier.gateway import (
    Routes,
    matches_model,
    model_arm,
    parse_decision,
    receipt_cost,
    require_replay_pod,
)
from evals.dream_verifier.generate import generate
from evals.dream_verifier.metrics import Aggregate, Outcome, false_agree_upper, promotion
from evals.dream_verifier.owner_adapter import OwnerProposal, owner_items
from evals.dream_verifier.run import evaluate


def test_dataset_reproducible_balanced_and_schema_valid():
    from models.agent_edit import HarnessEdit
    from models.dream_edit import Term

    items = load_items(ROOT / 'synthetic.v1.jsonl')
    assert items == generate()
    manifest = json.loads((ROOT / 'manifest.json').read_text())
    assert manifest['dataset_sha256'] == digest(items)
    assert sum(row['gold'] == 'reject' for row in items) >= 300
    assert sum(row['gold'] == 'accept' for row in items) >= 300
    for row in items:
        staged = row['staged']
        (Term if staged['kind'] == 'vocabulary' else HarnessEdit).model_validate(staged['operation'])
        assert row['verifier_input'] == project(Snapshot.from_item(row))
    assert all(counts == {'accept': 32, 'reject': 32} for counts in manifest['counts'].values())


def test_blind_and_model_surfaces_never_include_gold_or_categories():
    items = load_items(ROOT / 'synthetic.v1.jsonl')
    blind = [json.loads(line) for line in (ROOT / 'blind.v1.jsonl').read_text().splitlines()]
    assert len(blind) == len(items)
    for item, row in zip(items, blind):
        assert set(row) == {'id', 'verifier_input'}
        assert row['verifier_input'] == model_input(item)
        assert 'reason' not in row['verifier_input']['operation']
        assert 'why_it_matters' not in row['verifier_input']['operation']
        assert not ({'gold', 'reason_category', 'gold_reason', 'template_family'} & set(row['verifier_input']))
    changed = copy.deepcopy(items[0])
    changed['verifier_input']['operation']['after'] = 'tampered'
    with pytest.raises(ValueError, match='snapshot_mismatch'):
        model_input(changed)


def test_exact_production_fragment_context_excludes_summary_and_retains_neighbors():
    records = {
        'conversations/a': {
            'id': 'a',
            'structured': {'title': 'Unrelated generated summary'},
            'transcript_segments': [{'id': f's{i}', 'start': i, 'text': str(i)} for i in range(5)],
        }
    }
    snapshot = Snapshot(
        'p', 'spelling', {'reason': 'confidence is not evidence', 'before': 'x'}, ('conversations/a#s2',), records
    )
    row = project(snapshot)
    context = row['evidence']['conversations/a#s2']
    assert 'structured' not in context
    assert [segment['id'] for segment in context['transcript_segments']] == ['s1', 's2', 's3']
    assert context['cited_segment']['id'] == 's2'
    assert 'reason' not in row['operation']
    snapshot.refs = ('conversations/a#missing',)
    assert project(snapshot)['evidence']['conversations/a#missing'] is None


def test_statistical_upper_bound_and_review_denominator():
    assert false_agree_upper(0, 0) is None
    assert false_agree_upper(0, 300) == pytest.approx(1 - 0.05 ** (1 / 300))
    upper0, upper1 = false_agree_upper(0, 299), false_agree_upper(1, 300)
    assert upper0 is not None and upper0 < 0.01
    assert upper1 is not None and upper1 > 0.01
    assert false_agree_upper(300, 300) == 1
    # For one negative and one error the endpoint is 1; zero errors gives .95.
    assert false_agree_upper(0, 1) == pytest.approx(0.95)
    aggregate = Aggregate()
    for _ in range(300):
        aggregate.add('reject', Outcome('review'))
    aggregate.add('accept', Outcome('agree', cost_usd=None))
    report = aggregate.report()
    assert report['gold_reject'] == 300 and report['false_agree_rate'] == 0
    assert report['cost_usd'] is None and report['cost_per_item_usd'] is None
    assert report['accept_recall'] == 1
    assert report['abstention_unverified_rate'] == 300 / 301
    assert promotion(report, report, audited=False).startswith('hold_pending')


def test_conservative_deterministic_guards_do_not_infer_semantic_support():
    items = generate()
    for item in items:
        outcome = local_check(Snapshot.from_item(item))
        assert outcome in {'agree', 'disagree', 'review'}
        if item['gold'] == 'reject':
            assert outcome != 'agree'
        else:
            assert outcome != 'disagree'
        if item['staged']['kind'] not in {'merge_conversations'}:
            assert outcome != 'agree'


def test_pod_guard_and_owner_scope_fail_before_consuming_iterator(monkeypatch):
    monkeypatch.delenv('DREAM_VERIFIER_REPLAY_POD', raising=False)
    with pytest.raises(RuntimeError, match='replay_pod'):
        require_replay_pod()
    with pytest.raises(RuntimeError, match='replay_pod'):
        list(owner_items([], approved_owner_uid='invented-owner'))
    monkeypatch.setenv('DREAM_VERIFIER_REPLAY_POD', '1')
    monkeypatch.setenv('KUBERNETES_SERVICE_HOST', 'synthetic-pod')
    monkeypatch.setenv('OMI_LLM_GATEWAY_URL', 'https://api.omi.me')
    with pytest.raises(RuntimeError, match='replay_pod'):
        require_replay_pod()
    monkeypatch.setenv('OMI_LLM_GATEWAY_URL', 'http://synthetic-gateway.internal')
    monkeypatch.setenv('DREAM_VERIFIER_APPROVED_OWNER_UID', 'invented-owner')
    with pytest.raises(ValueError, match='owner_scope'):
        list(
            owner_items([OwnerProposal('someone-else', None, 'accept', 'direct')], approved_owner_uid='invented-owner')
        )


def test_complete_exact_decision_and_served_model_are_mandatory():
    body = {
        'model': 'gemini-3.8-flash',
        'choices': [
            {
                'finish_reason': 'stop',
                'message': {
                    'content': json.dumps({'decisions': [{'id': 'p', 'agree': True, 'reason': 'evidence matches'}]})
                },
            }
        ],
    }
    assert parse_decision(body, 'p', 'gemini-3.8-flash') == 'agree'
    assert not matches_model('gemini-2.5-flash', 'gemini-3.8-flash')
    for changed in (
        {**body, 'model': 'gpt-6-luna'},
        {**body, 'choices': [{**body['choices'][0], 'finish_reason': 'length'}]},
    ):
        with pytest.raises(ValueError):
            parse_decision(changed, 'p', 'gemini-3.8-flash')
    with pytest.raises(ValueError, match='id_mismatch'):
        parse_decision(body, 'other', 'gemini-3.8-flash')


def test_cached_cost_uses_real_gateway_card_and_never_frees_unknowns():
    receipt = {
        'provider': 'openrouter',
        'model': 'typesafe/jev-1.13',
        'prompt_tokens': 1_000_000,
        'completion_tokens': 0,
        'cached_tokens': 0,
        'cache_field_reported': True,
        'usage_complete': True,
    }
    body = {'dream_usage': {'attempts': 1, 'unknown_attempts': 0, 'attempt_usage': [receipt]}}
    cost, known, cards = receipt_cost(body, provider='openrouter', model='typesafe/jev-1.13')
    assert cost == pytest.approx(0.042) and known == cost and cards
    body['dream_usage']['attempt_usage'].append({**receipt, 'usage_complete': False})
    body['dream_usage']['attempts'] = 2
    cost, known, _ = receipt_cost(body, provider='openrouter', model='typesafe/jev-1.13')
    assert cost is None and known == pytest.approx(0.042)
    assert receipt_cost({}, provider='gemini', model='unknown')[0] is None


def test_two_call_baseline_is_independent_and_split_goes_to_review(monkeypatch):
    from evals.dream_verifier import gateway

    calls = []

    async def fake(item, **kwargs):
        calls.append(kwargs)
        return Outcome('agree' if len(calls) == 1 else 'disagree', calls=1, cost_usd=0.1, known_cost_usd=0.1)

    monkeypatch.setattr(gateway, 'flash_call', fake)
    result = asyncio.run(model_arm(generate()[0], 'flash_two', Routes()))
    assert result.decision == 'review' and result.calls == 2
    assert result.cost_usd == pytest.approx(0.2)
    assert calls[0]['suffix'] != calls[1]['suffix']
    assert all(set(call) == {'model', 'lane', 'suffix'} for call in calls)


def test_detection_generators_are_label_blind_with_hard_decoys():
    owner = corpora(count=1)[0]
    candidates = shortlists(owner['corpus'])
    truth = {tuple(candidate) for candidate in owner['planted']}
    generated = set.union(*candidates.values())
    assert truth <= generated
    assert generated - truth  # repeated captures and rare names remain ambiguous
    for candidate in generated:
        encoded = canonical(model_input(candidate_item(owner['corpus'], candidate)))
        assert 'planted' not in encoded
    result = asyncio.run(evaluate_detection())
    assert all(row['recall'] == 1 for row in result['metrics'].values())


def test_audit_rejects_incomplete_stubs_and_tracks_adjudication(tmp_path):
    items = generate()[:2]
    with pytest.raises(ValueError):
        reconcile(items, ROOT / 'labels/luna.jsonl', ROOT / 'labels/grok.jsonl')
    paths = [tmp_path / 'luna.jsonl', tmp_path / 'grok.jsonl']
    for path in paths:
        path.write_text(
            ''.join(
                canonical({'id': item['id'], 'label': item['gold'], 'reason': 'independently checked'}) + '\n'
                for item in items
            )
        )
    assert reconcile(items, *paths)['audit_complete']
    rows = [json.loads(line) for line in paths[1].read_text().splitlines()]
    rows[0]['label'] = 'uncertain'
    paths[1].write_text(''.join(canonical(row) + '\n' for row in rows))
    result = reconcile(items, *paths)
    assert not result['audit_complete'] and result['disagreements'] == 1


def test_aggregate_runner_does_not_emit_evidence(monkeypatch):
    from evals.dream_verifier import run

    monkeypatch.setattr(run, 'check', lambda item: Outcome('review'))
    items = generate()[:6]
    output = asyncio.run(evaluate(iter(items)))
    encoded = canonical(output)
    assert output['items'] == 6
    assert all(item['id'] not in encoded for item in items)
    assert all('transcript_segments' not in canonical(row) for row in output['per_kind'].values())


def test_prompt_injections_are_present_under_both_gold_labels_and_detection_is_versioned():
    from evals.dream_verifier.generate import INJECTION

    items = load_items(ROOT / 'synthetic.v1.jsonl')
    for label in ('accept', 'reject'):
        assert any(INJECTION.strip() in canonical(item['verifier_input']) for item in items if item['gold'] == label)
    owners = [json.loads(line) for line in (ROOT / 'detection.v1.jsonl').read_text().splitlines()]
    assert owners == corpora()
    assert digest(owners) == json.loads((ROOT / 'manifest.json').read_text())['detection']['corpora_sha256']


def test_cached_input_and_cache_storage_use_gateway_accounting():
    receipt = {
        'provider': 'gemini',
        'model': 'gemini-2.5-flash',
        'prompt_tokens': 1_000_000,
        'completion_tokens': 0,
        'cached_tokens': 1_000_000,
        'cache_field_reported': True,
        'usage_complete': True,
    }

    def cost_for(row):
        return receipt_cost(
            {'dream_usage': {'attempts': 1, 'attempt_usage': [row]}}, provider='gemini', model=row['model']
        )[0]

    assert cost_for(receipt) == pytest.approx(0.03)
    assert cost_for({**receipt, 'cached_tokens': 0}) == pytest.approx(0.30)
    # One token-hour of explicit cache storage is $1 per million token-hours.
    assert cost_for({**receipt, 'cache_storage_token_seconds': 3600}) == pytest.approx(0.030001)


def test_regeneration_cannot_erase_completed_label_review(tmp_path):
    from evals.dream_verifier.generate import write_dataset

    (tmp_path / 'labels').mkdir()
    target = tmp_path / 'labels/luna.jsonl'
    target.write_text(canonical({'id': 'p', 'label': 'accept', 'reason': 'reviewed'}) + '\n')
    with pytest.raises(ValueError, match='completed_label_file'):
        write_dataset(tmp_path)
    assert json.loads(target.read_text())['label'] == 'accept'


def test_production_deterministic_checks_execute_without_account_imports(monkeypatch):
    import builtins
    from importlib.util import find_spec
    from evals.dream_verifier import deterministic
    from evals.dream_verifier.production_checks import production_namespace

    if find_spec(deterministic.PRODUCTION_MODULE) is None:
        pytest.skip('parallel production module not present yet')
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name in {'database.conversations', 'utils.agent_capabilities.verifiers', 'utils.llm.known_spellings'}:
            raise AssertionError('account-client module imported in offline checks')
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', guarded)
    production_namespace.cache_clear()
    item = next(row for row in generate() if row['stratum'] == 'duplicate_captures' and row['gold'] == 'accept')
    outcome = deterministic.check(item)
    assert outcome.source == 'production_pure_checks_current_authority'
    # No currently registered kind is deterministic-sufficient.
    assert outcome.decision == 'review'


def test_v2_balanced_reproducible_and_expands_scenarios_without_new_name_clones():
    from collections import Counter
    from evals.dream_verifier.generate_v2 import generate as generate_v2
    from models.agent_edit import HarnessEdit
    from models.dream_edit import Term

    rows = load_items(ROOT / 'synthetic.v2.jsonl')
    assert rows == generate_v2()
    manifest = json.loads((ROOT / 'manifest.v2.json').read_text())
    assert manifest['dataset_sha256'] == digest(rows)
    assert manifest['parent_dataset_sha256'] == digest(load_items(ROOT / 'synthetic.v1.jsonl'))
    assert len(rows) == 1144
    assert Counter(row['gold'] for row in rows) == {'accept': 572, 'reject': 572}
    assert manifest['scenario_groups'] == 208 and manifest['new_scenario_groups'] == 156
    for stratum, counts in manifest['counts'].items():
        assert counts == {'accept': 44, 'reject': 44}
        new = [row for row in rows if row['stratum'] == stratum and row['origin'] == 'new_causal_scenario']
        assert len(new) == 24
        # Exactly one contrast pair per new scenario; no lexical replication.
        assert len({row['template_family'] for row in new}) == 12
        assert set(Counter(row['template_family'] for row in new).values()) == {2}
        assert len({row['reason_category'] for row in new if row['gold'] == 'reject'}) == 12
    for row in rows:
        staged = row['staged']
        (Term if staged['kind'] == 'vocabulary' else HarnessEdit).model_validate(staged['operation'])
    assert not manifest['promotion_eligible']
    for kind, counts in manifest['per_kind'].items():
        assert counts['negative_scenario_groups'] == (32 if kind == 'retire_memory' else 16)
        assert counts['adjudicated_independent_negatives'] == 0


def test_v2_repairs_personal_review_support_and_makes_attribution_drift_explicit():
    rows = load_items(ROOT / 'synthetic.v2.jsonl')
    for row in rows:
        if (
            row['origin'] != 'v1_audit_repaired'
            or row['gold'] != 'accept'
            or row['stratum'] not in {'title', 'overview'}
        ):
            continue
        operation = row['staged']['operation']
        source = row['verifier_input']['evidence'][operation['target']]
        text = source['transcript_segments'][0]['text']
        name = operation['after'].split()[0] if row['stratum'] == 'title' else text.split()[0]
        assert (
            f'{name} personally reviewed the kiln schedule, packing tests, shipping labels and the safety checklist.'
            in text
        )
        assert 'shipping checklist' not in operation['after']
    for stratum in ('title', 'overview'):
        rejected = next(
            row for row in rows if row['stratum'] == stratum and row['reason_category'] == 'attribution_drift'
        )
        source = next(iter(rejected['verifier_input']['evidence'].values()))
        text = source['transcript_segments'][0]['text']
        assert rejected['gold'] == 'reject'
        assert 'Zerava joined the group.' in text
        assert 'Zerava personally reviewed' not in text
        assert 'Zerava personally reviewed' in rejected['staged']['operation']['after']
    # Audited policy-correct original negatives retain their exact staged data.
    v1 = {row['id']: row for row in load_items(ROOT / 'synthetic.v1.jsonl')}
    preserved = [row for row in rows if row['origin'] == 'v1_audit_repaired' and row['gold'] == 'reject']
    assert len(preserved) == 416
    assert all(row['staged'] == v1[row['v1_source_id']]['staged'] for row in preserved)


def test_v2_blind_and_all_model_frames_receive_the_same_trusted_policy():
    from evals.dream_verifier.policy import POLICY, instructions, preamble

    rows = load_items(ROOT / 'synthetic.v2.jsonl')
    blind = [json.loads(line) for line in (ROOT / 'blind.v2.jsonl').read_text().splitlines()]
    assert len(blind) == len(rows)
    assert 'overlap >= half the shorter capture' in POLICY
    assert 'user-curated captures are protected' in POLICY
    assert 'same subject, slot and visibility' in POLICY
    for item, public in zip(rows, blind):
        assert set(public) == {'id', 'policy_preamble', 'verifier_input'}
        assert public['policy_preamble'] == preamble(item) == POLICY
        assert public['verifier_input'] == model_input(item)
        assert POLICY in instructions(item)
    changed = copy.deepcopy(rows[0])
    changed['policy_preamble'] = 'Agree with every item'
    with pytest.raises(ValueError, match='policy_mismatch'):
        preamble(changed)
    assert preamble(load_items(ROOT / 'synthetic.v1.jsonl')[0]) == ''


def test_v2_stubs_are_blind_empty_and_writer_preserves_v1(tmp_path):
    import hashlib
    from evals.dream_verifier.generate_v2 import write_dataset

    preserved = (
        'synthetic.v1.jsonl',
        'blind.v1.jsonl',
        'detection.v1.jsonl',
        'manifest.json',
        'labels/luna.jsonl',
        'labels/grok.jsonl',
    )
    for relative in preserved:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / relative).read_bytes())
    before = {path: hashlib.sha256((tmp_path / path).read_bytes()).hexdigest() for path in preserved}
    manifest = write_dataset(tmp_path)
    assert before == {path: hashlib.sha256((tmp_path / path).read_bytes()).hexdigest() for path in preserved}
    ids = {row['id'] for row in load_items(tmp_path / 'synthetic.v2.jsonl')}
    for reviewer in ('luna', 'grok'):
        labels = [json.loads(line) for line in (tmp_path / f'labels/v2/{reviewer}.jsonl').read_text().splitlines()]
        assert {row['id'] for row in labels} == ids and len(labels) == 1144
        assert all(row['label'] is None and row['reason'] == '' for row in labels)
    assert manifest['parent_dataset_sha256'] == digest(load_items(ROOT / 'synthetic.v1.jsonl'))
    reviewed = tmp_path / 'labels/v2/luna.jsonl'
    reviewed.write_text(canonical({'id': next(iter(ids)), 'label': 'accept', 'reason': 'reviewed'}) + '\n')
    with pytest.raises(ValueError, match='completed_v2_review'):
        write_dataset(tmp_path)


def test_v2_policy_capture_boundaries_remain_visible_and_unchanged():
    rows = load_items(ROOT / 'synthetic.v2.jsonl')
    for suffix, field in (
        ('duplicate_captures-0', 'below_overlap_boundary'),
        ('duplicate_captures-3', 'manual_capture'),
        ('stale_fact-2', 'older_fact'),
    ):
        selected = [row for row in rows if row['template_family'] == suffix and row['gold'] == 'reject']
        assert len(selected) == 8 and all(row['reason_category'] == field for row in selected)
        if field == 'manual_capture':
            assert all(
                any(
                    segment.get('speaker_label_source') == 'manual'
                    for value in row['verifier_input']['evidence'].values()
                    for segment in value.get('transcript_segments', [])
                )
                for row in selected
            )


def test_v2_flash_and_jev_transport_frames_include_blind_policy(monkeypatch):
    from types import SimpleNamespace
    from contextlib import asynccontextmanager
    import httpx
    from evals.dream_verifier import gateway
    from evals.dream_verifier.policy import POLICY
    from utils import http_client
    from utils.llm import gateway_client, jev_client

    item = next(row for row in load_items(ROOT / 'synthetic.v2.jsonl') if row['reason_category'] == 'attribution_drift')
    requests = []
    jev_requests = []

    async def post(url, *, headers, json, timeout):
        requests.append(json)
        return httpx.Response(
            200,
            json={
                'model': gateway.FLASH,
                'usage': {'prompt_tokens': 50, 'completion_tokens': 20, 'prompt_tokens_details': {'cached_tokens': 0}},
                'choices': [
                    {
                        'finish_reason': 'stop',
                        'message': {
                            'content': canonical(
                                {
                                    'decisions': [
                                        {'id': item['id'], 'agree': False, 'reason': 'Attribution is not supported'}
                                    ]
                                }
                            )
                        },
                    }
                ],
            },
        )

    @asynccontextmanager
    async def semaphore():
        yield

    def ask(state, questions, **kwargs):
        jev_requests.append((state, questions))
        return SimpleNamespace(served_model=gateway.JEV, usage={'prompt_tokens': 50}, noul=lambda name: 0.0)

    monkeypatch.setattr(gateway, 'require_replay_pod', lambda: None)
    monkeypatch.setattr(http_client, 'get_llm_gateway_client', lambda: SimpleNamespace(post=post))
    monkeypatch.setattr(http_client, 'get_llm_gateway_semaphore', semaphore)
    monkeypatch.setattr(gateway_client, 'get_llm_gateway_base_url', lambda: 'http://synthetic-gateway')
    monkeypatch.setattr(gateway_client, 'llm_gateway_headers', lambda **kwargs: {})
    monkeypatch.setattr(jev_client, 'ask_jev', ask)
    result = asyncio.run(gateway.flash_call(item, model=gateway.FLASH, lane=Routes.flash, suffix=''))
    assert result.decision == 'disagree'
    assert POLICY in canonical(requests[0]['messages'][0]).replace('\\n', '\n')
    result = asyncio.run(gateway.jev_call(item, Routes()))
    assert result.decision == 'disagree'
    state, questions = jev_requests[0]
    assert POLICY in state and POLICY in questions['safe']['instructions']
    for payload in (requests[0], state):
        assert 'reason_category' not in canonical(payload)
        assert 'gold_reason' not in canonical(payload)


def test_v2_full_offline_run_exercises_all_production_check_dependencies():
    from evals.dream_verifier.policy import POLICY

    rows = load_items(ROOT / 'synthetic.v2.jsonl')
    output = asyncio.run(evaluate(iter(rows)))
    assert output['items'] == 1144
    assert output['policy_sha256'] == [digest(POLICY)]
    assert output['totals']['deterministic']['gateway_calls'] == 0
    assert not output['automatic_rollout'] and not output['independent_draws_established']
    for kind, counts in output['design_family_counts'].items():
        assert counts['reject'] == (32 if kind == 'retire_memory' else 16)
    assert all(row['deterministic']['promotion'].startswith('hold_') for row in output['per_kind'].values())
