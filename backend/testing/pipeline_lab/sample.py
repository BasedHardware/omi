"""Minimal synthetic corpus day + run, used by ``sample-run`` when the inspector lane's
richer generator is not registered, and by the core tests. Obviously fictional content."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from testing.pipeline_lab.contracts import (
    ActionItem,
    Coverage,
    CorpusDay,
    ConversationRecord,
    Gap,
    LlmCall,
    MemoryItem,
    Notification,
    RunDay,
    RunRecord,
    RunStatus,
    Segment,
    StageRun,
    StageState,
    Structured,
    STAGES,
    utc_iso,
)
from testing.pipeline_lab.store import Store, new_run_id

SAMPLE_DAY_ID = 'sample-day'
_START = datetime(2026, 1, 15, 9, 0, tzinfo=timezone.utc)


def _conversation(index: int, *, title: str, task: str, memory: str, discarded: bool = False) -> ConversationRecord:
    start = _START + timedelta(hours=index * 2)
    return ConversationRecord(
        id=f'sample-c{index}',
        baseline_id=f'sample-b{index}',
        lane='record',
        started_at=utc_iso(start),
        finished_at=utc_iso(start + timedelta(minutes=12)),
        discarded=discarded,
        discard_reason='too short' if discarded else None,
        language='en',
        segments=[
            Segment(
                start=0.0, end=4.0, speaker='SPEAKER_00', speaker_name='Owner', is_user=True, text='Testing one two.'
            ),
            Segment(start=4.5, end=9.0, speaker='SPEAKER_01', speaker_name='Pat Example', text=f'Let us {task}.'),
        ],
        structured=(
            None if discarded else Structured(title=title, overview=f'A fictional chat about {title}.', emoji='🧪')
        ),
        action_items=[] if discarded else [ActionItem.make(task)],
        memories=[] if discarded else [MemoryItem.make(memory, category='interesting')],
        notifications=[],
        llm_call_ids=[f'llm-sample-{index}'],
    )


def write_sample(store: Store, day_id: str = SAMPLE_DAY_ID) -> dict:
    day = CorpusDay(
        day_id=day_id,
        date=_START.date().isoformat(),
        timezone='UTC',
        source_snapshot='synthetic',
        start_state_snapshot='synthetic',
        coverage=Coverage(
            audio_seconds=2160.0,
            conversations=3,
            with_audio=3,
            lanes={'record': 3},
            gaps=[Gap(start=utc_iso(_START + timedelta(hours=1)), end=utc_iso(_START + timedelta(hours=2)))],
        ),
        extra={'synthetic': True},
    )
    store.write_day(day)
    replay = [
        _conversation(0, title='Garden planning', task='water the tomatoes', memory='Likes heirloom tomatoes'),
        _conversation(1, title='Bike repair', task='buy a new inner tube', memory='Rides a blue bicycle'),
        _conversation(2, title='', task='', memory='', discarded=True),
    ]
    baseline = [
        _conversation(0, title='Garden plans', task='water the tomatoes', memory='Likes heirloom tomatoes'),
        _conversation(1, title='Bike repair', task='buy an inner tube', memory='Rides a blue bicycle'),
    ]
    for row in baseline:
        row.id = row.baseline_id or row.id
        row.baseline_id = None
    store.write_baseline(day_id, 'conversations.jsonl', baseline)
    store.write_baseline_daily_summary(day_id, {'headline': 'A fictional quiet day.'})
    run = RunRecord(
        run_id=new_run_id(day_id, 'sample'),
        day_id=day_id,
        ref='sample',
        backend_tree='0' * 40,
        status=RunStatus.COMPLETE.value,
        started_at=utc_iso(),
        finished_at=utc_iso(),
        spend_usd=0.0,
        timings={stage: 0.0 for stage in STAGES},
        stages={stage: StageRun(status=StageState.COMPLETE.value) for stage in STAGES},
        extra={'synthetic': True},
    )
    store.create_run(run)
    for row in replay:
        store.write_conversation(run.run_id, row)
    store.write_run_day(
        run.run_id,
        RunDay(
            daily_summary={'headline': 'A fictional day of gardening and bikes.'},
            notifications=[
                Notification(
                    at=utc_iso(_START + timedelta(hours=3)), title='Reminder', body='Water the tomatoes', trigger='task'
                )
            ],
        ),
    )
    store.append_llm_calls(
        run.run_id,
        [
            LlmCall(
                id=f'llm-sample-{i}',
                at=utc_iso(),
                stage='notes',
                conversation_id=f'sample-c{i}',
                feature='conversation_notes',
                model='fake-model',
                prompt={'messages': [{'role': 'user', 'content': 'Summarise.'}]},
                output='{"title": "..."}',
                tokens_in=100,
                tokens_out=20,
            )
            for i in range(3)
        ],
    )
    return {'day_id': day_id, 'run_id': run.run_id, 'conversations': len(replay), 'generator': 'core-minimal'}
