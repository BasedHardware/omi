"""Exercise the real notes prompt/parser with synthetic model responses only."""

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import google.auth.credentials  # noqa: F401
import pytest

from testing.import_isolation import stub_modules
from utils.conversations.meeting_participants import MeetingRoster, RosterEntry

START = datetime(2026, 10, 5, tzinfo=timezone.utc)


@pytest.fixture(scope='module', autouse=True)
def imports():
    with stub_modules({}):
        import utils.llm.conversation_processing  # noqa: F401

        yield


def run_notes(monkeypatch, *, enabled, payload, words=80, participants=1):
    from utils.llm import conversation_processing as notes
    from utils.llm.conversation_prompt_prefix import build_conversation_prompt_prefix

    names = ['Eddie Thai', 'Maya Chen', 'Ash Kalb', 'Priya Rao'][:participants]
    roster = MeetingRoster(
        tuple(
            [RosterEntry('David', None, None, 'owner', 'macos_calendar', None)]
            + [RosterEntry(name, None, None, 'human', 'macos_calendar', None) for name in names]
        ),
        'Planning',
        False,
    )
    ids = {'owner-turn', *(f'person-turn-{index}' for index in range(participants))}
    transcript = '[owner-turn 0] My name is David. We can plan the next release.\n'
    transcript += '\n'.join(
        f'[person-turn-{index} {index+1}] My name is {name}. '
        + ('We discussed testing and release planning. ' * (words // participants // 7))
        for index, name in enumerate(names)
    )
    prefix = build_conversation_prompt_prefix(
        conversation_id='synthetic',
        transcript=transcript,
        started_at=START,
        timezone_name='UTC',
        language_code='en',
        roster=roster,
        transcript_segment_ids=ids,
        speaker_map={key: None for key in range(participants + 1)},
    )
    calls = []

    class Model:
        def invoke(self, messages):
            calls.append(messages)
            return SimpleNamespace(content=json.dumps(payload, separators=(',', ':')))

    monkeypatch.setenv('SUMMARY_SPEAKER_LABELS_ENABLED', 'on' if enabled else 'off')
    monkeypatch.setattr(notes, 'get_llm', lambda *args, **kwargs: Model())
    monkeypatch.setattr(notes, 'shared_conversation_cache_supported', lambda: False)
    structured = notes.get_conversation_notes(
        prefix,
        started_at=START,
        language_code='en',
        output_language_code='en',
        tz='UTC',
        task_intelligence_capture=True,
        rich_context_enabled=True,
        roster=roster,
    )
    return structured, calls


def payloads(participants):
    names = ['Eddie Thai', 'Maya Chen', 'Ash Kalb', 'Priya Rao'][:participants]
    base = dict(
        title='Release planning',
        overview='The team discussed release planning.',
        participants=[dict(name=name, source='roster') for name in names],
    )
    labeled = json.loads(json.dumps(base))
    for index, person in enumerate(labeled['participants']):
        person['speaker_bindings'] = [
            dict(
                speaker_id=index + 1,
                confidence='high',
                evidence_segment_ids=[f'person-turn-{index}'],
                evidence_kind='self_introduction',
            )
        ]
    labeled['owner'] = dict(
        name='David',
        source='roster',
        speaker_bindings=[
            dict(
                speaker_id=0, confidence='high', evidence_segment_ids=['owner-turn'], evidence_kind='self_introduction'
            )
        ],
    )
    return base, labeled


def test_one_notes_call_retains_private_candidates_and_off_uses_original_schema(monkeypatch):
    base, labeled = payloads(1)
    on, calls = run_notes(monkeypatch, enabled=True, payload=labeled)
    assert len(calls) == 1
    assert len(on._summary_speaker_candidates) == 2
    assert on._summary_speaker_roster.entries[0].kind == 'owner'
    assert on._summary_speaker_candidates[0].bindings[0].speaker_id == 1
    assert 'speaker_bindings' not in on.model_dump_json()
    copied = on.model_copy(deep=True)
    assert len(copied._summary_speaker_candidates) == 2
    assert copied._summary_speaker_roster.entries[0].kind == 'owner'
    assert '_summary_speaker' not in copied.model_dump_json()
    off, off_calls = run_notes(monkeypatch, enabled=False, payload=base)
    assert len(off_calls) == 1
    assert not hasattr(off, '_summary_speaker_candidates')
    assert 'TRANSCRIPT IDENTITY EVIDENCE' not in str(off_calls[0])
    assert 'speaker_bindings' not in str(off_calls[0])
