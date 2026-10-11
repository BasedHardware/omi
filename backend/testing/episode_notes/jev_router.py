"""One-question DEV router; calibration uses cached quality deltas, never fixture strata."""

import json

from testing.episode_notes.policy_replay import episode_route_signals
from testing.episode_notes.prompts import fixture_evidence_items


def router_payload(episode):
    speech = '\n'.join(i.content for i in fixture_evidence_items(episode) if i.source_kind == 'speech')
    context = [
        i.model_dump(exclude_none=True)
        for i in fixture_evidence_items(episode)
        if i.source_kind in {'roster', 'calendar', 'device_state'}
    ]
    state = json.dumps(
        {
            'start': episode.evidence.started_at,
            'end': episode.evidence.finished_at,
            'signals': episode_route_signals(episode),
            'speech_excerpt': speech[:6000] + ('\n[excerpt gap]\n' + speech[-6000:] if len(speech) > 6000 else ''),
            'participants_and_capture': json.dumps(context, ensure_ascii=False)[:2000],
        },
        ensure_ascii=False,
    )
    return {
        'state': state,
        'questions': {
            'careful_summary': {
                'type': 'noul',
                'instructions': 'Is this a substantive multi-party exchange where a careful summary materially matters to its owner?',
                'criteria': {
                    'true': 'Multiple people exchange connected substantive reasoning, decisions or commitments across the capture; careful synthesis can recover important details.',
                    'false': 'Few spoken facts, mostly incidental screens, isolated utterances or an owner monologue; extra synthesis would mostly add speculation or filler.',
                },
            }
        },
    }
