"""Plain-sync repeat-only observations use accepted survivors, after commit only."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from utils.sync import intake_content_shadow as shadow
from utils.sync import absorption_metrics


@pytest.mark.parametrize(
    'speech,span', [(speech, span) for speech in sorted(shadow.SPEECH) for span in sorted(shadow.SPANS)]
)
def test_plain_merge_is_shadowed_once_after_commit(speech, span):
    start = datetime(2026, 11, 4, tzinfo=timezone.utc)
    old = {'recorded_start': start, 'recorded_end': start + timedelta(minutes=1), 'transcript_segments': []}
    new = deepcopy(old)
    if span == 'growth':
        new['recorded_end'] += timedelta(minutes=1)
    elif span == 'changed':
        new['recorded_start'] += timedelta(seconds=1)
    elif span == 'unknown':
        new.pop('recorded_end')
    payload = deepcopy(new)
    plan = SimpleNamespace(
        created=False,
        result=new,
        canonical='synthetic',
        matched={'synthetic': old},
        survivors=[] if speech == 'repeat_only' else [{'text': 'new'}],
        donor_updates={},
    )
    counter = shadow.INTAKE_CONTENT.labels(speech=speech, span=span)._value
    before = counter.get()
    absorption_metrics.capture_assignment_metrics(new, [plan])
    assert shadow.FIELD in new and shadow.FIELD not in payload
    assert counter.get() == before
    absorption_metrics.record_assignment_metrics(new)
    assert counter.get() == before + 1
    absorption_metrics.record_assignment_metrics(new)
    assert counter.get() == before + 1
    assert shadow.FIELD not in new
    assert shadow.INTAKE_CONTENT._labelnames == ('speech', 'span')


def test_live_and_created_plans_stay_out_of_plain_merge_denominator():
    row = {}
    for created, live in [(True, False), (False, True)]:
        shadow.capture(row, [SimpleNamespace(created=created, result={'sync_live_target': live})])
    assert shadow.FIELD not in row
