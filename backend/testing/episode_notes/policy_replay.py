"""DEV-only routing frontier from cached candidates; never generates or judges notes."""

from datetime import datetime
from statistics import mean

from testing.episode_notes.prompts import fixture_evidence_items
from utils.conversations.episode_selection import deterministic_episode_selection


def episode_route_signals(episode):
    items = deterministic_episode_selection(fixture_evidence_items(episode), finished_at=episode.evidence.finished_at)
    times = [datetime.fromisoformat(i.time) for i in items if i.source_kind == 'speech' and i.time]
    return {
        'words': sum(len(i.content.split()) for i in items if i.source_kind == 'speech'),
        'source_kinds': len({i.source_kind for i in items}),
        'speech_timestamp_span_seconds': (max(times) - min(times)).total_seconds() if len(times) > 1 else 0,
        'capture_seconds': (
            datetime.fromisoformat(episode.evidence.finished_at) - datetime.fromisoformat(episode.evidence.started_at)
        ).total_seconds(),
    }


def replay_policy(fixtures, c7, c6, predicate):
    if c7.get('split') != 'dev' or c6.get('split') != 'dev':
        raise ValueError('routing calibration is DEV only')
    if c7['reference_prompt_sha256'] != c6['reference_prompt_sha256']:
        raise ValueError('routing replay requires a shared reference contract')
    if c7['judge_prompt_sha256'] != c6['judge_prompt_sha256']:
        raise ValueError('routing replay requires a shared judge contract')
    episodes = [e for e in fixtures.episodes if e.split == 'dev']
    rows = {}
    for label, report in [('C7', c7), ('C6', c6)]:
        rows[label] = {
            (r['id'], r['judge_sample']): r for r in report['cases'] if r['arm'] == 'episode' and r['status'] == 'ok'
        }
    results = []
    for sample in (1, 2):
        chosen, routed = [], 0
        for episode in episodes:
            signals = episode_route_signals(episode)
            tier = 'C6' if predicate(episode.id, signals) else 'C7'
            row = rows[tier].get((episode.id, sample))
            if row is None:
                raise ValueError('missing candidate/judge for routed DEV episode')
            chosen.append(row)
            routed += tier == 'C6'
        results.append(
            {
                'judge_sample': sample,
                'n': len(chosen),
                'c6_count': routed,
                'c6_share': routed / len(chosen),
                'gap': mean(r['informativeness_gap'] for r in chosen),
                'unsupported': sum(r['unsupported_claims'] for r in chosen),
                'wrong': sum(r['wrong_provenance_claims'] for r in chosen),
                'unrelated': sum(r['unrelated_content_claims'] for r in chosen),
                'faith': sum(r['faithfulness_pass'] for r in chosen),
                'cost': {
                    key: (
                        mean(r['candidate_cost'][key] for r in chosen)
                        if all(r['candidate_cost'].get(key) is not None for r in chosen)
                        else None
                    )
                    for key in ('input_tokens', 'output_tokens', 'reasoning_tokens', 'latency_seconds', 'provider_cost')
                },
                'max_latency': max(r['candidate_cost']['latency_seconds'] for r in chosen),
                'over_115': sum(r['candidate_cost']['latency_seconds'] > 115 for r in chosen),
            }
        )
    return results
