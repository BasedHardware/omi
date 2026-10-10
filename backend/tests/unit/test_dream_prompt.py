"""Readable synthetic evidence and shared conservative budget contracts."""

import asyncio
import json
import re

import pytest

from config.dream_agent import Caps
from models.dream_agent import Triage, Cluster, Plan
from utils import dream_agent, dream_prompt, dream_transport, dream_metrics
from utils.llm.shaped_agent import Turn


def conversation():
    return {
        'structured': {
            'events': [],
            'sections': [{'source_segment_ids': ['hidden-id']}],
            'title': 'Robot design',
            'overview': 'A synthetic spelling discussion',
            'category': 'work',
        },
        'status': 'completed',
        'transcript_segments': [
            {
                'id': f'hidden-segment-{i}',
                'text': 'Qorby is a misspelling of Qorbi.' if i == 10 else f'Synthetic sentence {i}.',
                'speaker': 'SPEAKER_00',
                'speaker_id_scope': 'hidden-scope',
                'stt_provider': 'hidden-provider',
                'audio_capture_id': 'hidden-capture',
                'start': i,
                'end': i + 1,
            }
            for i in range(14)
        ],
    }


def test_late_transcript_defect_visible_without_storage_metadata():
    records = {'conversations/synthetic': conversation()}
    messages = dream_prompt.evidence_message(records, Triage, min(6000, 16000 // 3))
    projected = json.loads(messages[0]['content'])['records']
    assert list(projected) == list(records)
    value = projected['conversations/synthetic']
    assert 'Qorby is a misspelling of Qorbi.' in value
    assert all(word in value for word in ('Robot design', 'synthetic spelling discussion', 'category: work'))
    assert value.count('SPEAKER_00:') == 1
    assert not any(word in value for word in ('hidden-', 'stt_provider', 'start', 'completed', 'sections'))


def test_resolved_names_you_and_consecutive_speakers():
    records = {
        'conversations/c': {
            'transcript_segments': [
                {'speaker': 'SPEAKER_01', 'is_user': True, 'text': 'First.'},
                {'speaker': 'SPEAKER_02', 'is_user': True, 'text': 'Second.'},
                {'speaker': 'SPEAKER_03', 'person_id': 'robot', 'text': 'Third.'},
                {'speaker': 'SPEAKER_04', 'text': 'Fourth.'},
            ]
        },
        'entity/person:robot': {'name': 'Qorbi'},
    }
    assert dream_prompt.excerpts(records, chars=1000)['conversations/c'] == (
        'You: First. Second.\nQorbi: Third.\nSPEAKER_04: Fourth.'
    )


@pytest.mark.parametrize(
    'ref,row,expected',
    [
        ('memories/m', {'content': 'Robot fact', 'category': 'work'}, ['Robot fact', 'work']),
        ('memory_items/m', {'content': 'Robot fact'}, ['Robot fact']),
        (
            'action_items/a',
            {'description': 'Build robot', 'status': 'active', 'due_at': '2030-01-01'},
            ['Build robot', 'active', '2030-01-01'],
        ),
        ('people/p', {'name': 'Qorbi', 'aliases': ['Robot']}, ['Qorbi', 'Robot']),
        ('candidates/c', {'description': 'Follow up', 'status': 'pending'}, ['Follow up', 'pending']),
        (
            'entity/person:p',
            {'name': 'Qorbi', 'summary': 'Robot', 'facts': [{'text': 'Works on gears', 'id': 'hidden'}]},
            ['Qorbi', 'Robot', 'Works on gears'],
        ),
        (
            'screen/s',
            {'appName': 'Synthetic editor', 'windowTitle': 'Robot notes', 'ocrText': 'Gear designs'},
            ['Synthetic editor', 'Robot notes', 'Gear designs'],
        ),
    ],
)
def test_collection_text_fields_only(ref, row, expected):
    row.update(id='hidden', timestamp='hidden', provider='hidden')
    value = dream_prompt.excerpts({ref: row}, chars=1000)[ref]
    assert all(word in value for word in expected)
    assert 'hidden' not in value


def test_long_transcript_keeps_head_tail_exact_count_and_summary_fields():
    row = conversation()
    row['transcript_segments'] = [{'speaker': 'SPEAKER_00', 'text': 'HEAD ' + 'middle ' * 1000 + ' TAIL'}]
    row['structured']['title'] = 'Title ' * 1000
    value = dream_prompt.excerpts({'conversations/c': row}, chars=400)['conversations/c']
    assert len(value) <= 400
    assert 'overview:' in value and 'category:' in value and 'title:' in value
    body = value.split('\n')[-1]
    assert body.startswith('SPEAKER_00: HEAD') and body.endswith('TAIL')
    match = re.search(r'…\[(\d+) chars omitted\]…', body)
    assert match
    original = dream_prompt.transcript(row, {})
    assert len(original) == len(body) - len(match[0]) + int(match[1])


@pytest.mark.parametrize('words', ['Synthetic evidence ' * 4000, '合成ロボット 🤖 ' * 4000])
def test_twelve_large_records_budget_and_selection_share_payload(words):
    records = {}
    for i in range(12):
        row = conversation()
        row['transcript_segments'][-1]['text'] = words + 'Synthetic tail'
        records[f'conversations/{i}'] = row
    caps = Caps(tokens=16000)
    budget = min(6000, caps.tokens // 3)
    messages = dream_prompt.evidence_message(records, Triage, budget)
    assert dream_prompt.fits_triage(records, caps)
    assert len(json.loads(messages[0]['content'])['records']) == 12
    assert (
        dream_transport.input_ceiling(
            dream_prompt.mount(Triage, budget, dream_prompt.TRIAGE_INSTRUCTIONS).messages(messages),
            Triage.model_json_schema(),
        )
        + 768
        <= budget
    )
    assert dream_prompt.evidence_chars(messages) > 0
    assert not dream_prompt.fits_triage(records, Caps(tokens=100))


def test_two_lanes_remaining_budget_names_and_counts(monkeypatch, caplog):
    records = {'conversations/c': conversation(), 'entity/person:robot': {'name': 'Qorbi'}}
    records['conversations/c']['transcript_segments'][0]['person_id'] = 'robot'
    sink = {'tokens': 0}
    seen = []

    async def turn(uid, lane, mount, messages):
        seen.append((lane, mount.budget.tokens, messages))
        assert 'Qorbi:' in messages[-1]['content']
        value = Triage(clusters=[Cluster(refs=['conversations/c'], problem='spelling')]) if len(seen) == 1 else Plan()
        return Turn(value=value, tokens=100)

    _, tokens = asyncio.run(dream_agent.plan_pass('synthetic', records, Caps(tokens=16000), turn=turn, usage_sink=sink))
    assert tokens == 200
    assert [row[1] for row in seen] == [16000 // 3, 15900]
    assert sink['triage_evidence_chars'] == dream_prompt.evidence_chars(seen[0][2])
    assert sink['reasoning_evidence_chars'] == dream_prompt.evidence_chars(seen[1][2])
    with caplog.at_level('INFO', logger='utils.dream_metrics'):
        dream_metrics.record_pass({'status': 'complete', **sink})
    assert 'triage_evidence_chars=' in caplog.text and 'reasoning_evidence_chars=' in caplog.text
    assert 'Qorbi' not in caplog.text and 'synthetic' not in caplog.text
