"""A row with no notes keeps no title: the fallback label is for generated notes only.

2026-11-16 incident: the capture stub was stamped "Discussion notes" at creation.
Home then showed a finished row for a capture still waiting on its transcript, and
the batch projection refused to register the first-summary obligation because the
row "already had a title".
"""

from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from database import conversations as db
from tests.unit.test_batch_pipeline_live import incoming, recording
from tests.unit.test_conversation_persistence_transaction_expiry import _FakeFirestoreClient
from tests.unit.test_home_transcribing_hold import capture
from tests.unit.test_stale_empty_capture import placeholder
from utils.batch_pipeline.live_projection import replace_record
from utils.conversations import empty_capture, home_step, home_titles, summary_delivery, transcribing_hold
from utils.conversations.home_titles import display_title, is_fallback_title, notes_pending
from utils.summary_quality import title_or_fallback

NOW = datetime.now(timezone.utc)
FALLBACK = title_or_fallback('')
EMPTY_NOTES = {'title': '', 'overview': '', 'emoji': '🧠', 'category': 'other', 'action_items': [], 'events': []}


def stub(**changes):
    """The in-progress row a listen socket creates before any speech exists."""
    return {
        'id': 'c',
        'status': 'in_progress',
        'data_protection_level': 'standard',
        'created_at': NOW,
        'started_at': NOW,
        'finished_at': NOW,
        'transcript_segments': [],
        'structured': dict(EMPTY_NOTES),
        **changes,
    }


@pytest.fixture
def store(monkeypatch):
    def install(document):
        client = _FakeFirestoreClient(document)
        monkeypatch.setattr(db, 'db', client)
        monkeypatch.setattr(db, 'invalidate_people_stats_cache', lambda _: None)
        monkeypatch.setattr(db, '_sync_conversation_search_index', lambda *_: None)
        monkeypatch.setattr(db, '_delete_conversation_search_index', lambda *_: None)
        return client

    return install


def test_fallback_label_is_what_the_incident_rows_carry():
    assert FALLBACK == 'Discussion notes'
    # The reader's matcher must follow the writer's labels.
    assert is_fallback_title(FALLBACK) and is_fallback_title(title_or_fallback('', index=3))
    assert is_fallback_title(' discussion  3 ')
    # Other placeholders are wire labels or model junk, never this writer's output.
    assert not any(is_fallback_title(value) for value in ('Transcribing…', 'Untitled', '', None, 'Discussion notes Q3'))


@pytest.mark.parametrize(
    'structured,pending',
    [
        (EMPTY_NOTES, True),
        ({'title': FALLBACK}, True),
        ({'title': 'Transcribing…', 'sections': [{'heading': 'Discussion 1', 'body_markdown': ''}]}, True),
        (None, True),
        ({'title': 'Pilot budget'}, False),
        ({'title': '', 'overview': 'The pilot budget is $8,000.'}, False),
        ({'title': '', 'gist': 'Pilot budget approval'}, False),
        ({'title': '', 'sections': [{'heading': '', 'body_markdown': 'Approval is due Friday.'}]}, False),
        ({'title': '', 'action_items': [{'description': 'Send the budget'}]}, False),
        ({'title': '', 'events': [{'title': 'Budget review'}]}, False),
    ],
)
def test_notes_pending_means_nothing_was_generated(structured, pending):
    assert notes_pending(structured) is pending


@pytest.mark.parametrize('existing', [None, stub(structured={'title': ''})])
def test_capture_stub_is_written_untitled(store, existing):
    client = store(deepcopy(existing))
    db.upsert_conversation_with_lifecycle('u', stub())
    written = client.commits[0]
    assert written['structured']['title'] == ''
    assert 'title_change_reason' not in written and 'title_changed_at' not in written
    # The row a batch projection later meets is one it can still enroll.
    assert notes_pending(written['structured'])


def test_raw_completion_of_an_untitled_row_stays_untitled(store):
    client = store(stub(status='processing', structured={'title': ''}))
    assert db.persist_processing_result_with_lifecycle('u', stub(status='completed'))
    written = client.commits[0]
    assert written['structured']['title'] == ''
    assert 'title_change_reason' not in written


def test_empty_write_clears_a_placeholder_stamped_by_the_earlier_build(store):
    client = store(stub(structured={'title': FALLBACK}, title_change_reason='initial_title'))
    db.upsert_conversation_with_lifecycle('u', stub(structured={**EMPTY_NOTES, 'title': FALLBACK}))
    assert client.commits[0]['structured']['title'] == ''


def test_empty_write_keeps_a_stored_stand_in_and_a_user_title(store):
    client = store(stub(structured={'title': 'Recording · 2:14 AM', 'title_provenance': 'server_minimum'}))
    db.upsert_conversation_with_lifecycle('u', stub())
    assert client.commits[0]['structured']['title'] == 'Recording · 2:14 AM'

    client = store(stub(user_title='Budget sync', structured={'title': 'Budget sync'}))
    db.upsert_conversation_with_lifecycle('u', stub())
    assert client.commits[0]['structured']['title'] == 'Budget sync'


def test_empty_write_keeps_an_earlier_generated_title(store):
    client = store(stub(status='completed', structured={'title': 'Pilot budget', 'overview': 'Earlier notes'}))
    assert db.persist_processing_result_with_lifecycle('u', stub(status='completed'))
    assert client.commits[0]['structured']['title'] == 'Pilot budget'


def test_generated_notes_with_an_unusable_headline_still_get_the_fallback(store):
    client = store(stub(status='processing', structured={'title': ''}))
    notes = stub(status='completed', structured={**EMPTY_NOTES, 'overview': 'Approval is due Friday.'})
    assert db.persist_processing_result_with_lifecycle('u', notes)
    written = client.commits[0]
    assert written['structured']['title'] == FALLBACK
    assert written['title_change_reason'] == 'initial_title'


def test_projection_enrolls_a_row_that_only_carries_the_placeholder():
    stamped = recording(transcript_segments=[], structured={'title': FALLBACK, 'overview': ''})
    result, new = replace_record(stamped, incoming(), {'start': 100, 'end': 102})
    assert new
    assert result['summary_title_provenance'] == 'server_minimum'
    assert result['summary_due_at'] > result['summary_first_pending_at']
    assert summary_delivery.refusal(result) is None
    # The stored title is left for the notes writer, which repairs a placeholder.
    assert result['structured']['title'] == FALLBACK


@pytest.mark.parametrize(
    'structured',
    [{'title': 'Pilot budget'}, {'title': FALLBACK, 'overview': 'Approval is due Friday.'}],
)
def test_projection_still_leaves_titled_or_summarized_rows_alone(structured):
    result, _ = replace_record(recording(structured=structured), incoming(), {'start': 100, 'end': 102})
    assert 'summary_due_at' not in result and 'summary_first_pending_at' not in result


def test_home_presents_a_stamped_capture_as_transcribing_not_as_a_finished_row():
    row = capture(structured={'title': FALLBACK, 'overview': '', 'emoji': '', 'category': 'other'})
    before = deepcopy(row)
    assert transcribing_hold.applies(row)
    assert home_step.classify(row) == home_step.TRANSCRIBING
    wire = transcribing_hold.project(home_step.project(row), home_list=True)
    assert wire['structured']['title'] == 'Transcribing…'
    assert wire['status'] == 'processing' and wire['home_step'] == home_step.TRANSCRIBING
    assert row == before  # presentation only


def test_stamped_capture_keeps_the_bounded_wait():
    late = NOW - timedelta(days=3)
    row = capture(
        structured={'title': FALLBACK},
        created_at=late,
        home_transcription_pending_at=late,
        home_transcription_deadline_at=late + timedelta(hours=2),
    )
    assert home_step.classify(row) == home_step.FAILED
    assert transcribing_hold.project(row)['structured']['title'] == "Couldn't transcribe"


def test_processing_row_with_only_a_placeholder_is_transcribing():
    row = capture(status='processing', structured={'title': FALLBACK})
    assert home_step.classify(row) == home_step.TRANSCRIBING
    assert home_step.classify(capture(status='processing', structured={'title': 'Pilot budget'})) == (
        home_step.WRITING_NOTES
    )


def test_wire_serves_a_bare_placeholder_as_untitled_on_live_rows():
    row = stub(structured={**EMPTY_NOTES, 'title': FALLBACK}, record_lane_owner='batch_live_v1')
    before = deepcopy(row)
    wire = transcribing_hold.project(row)
    assert wire['structured']['title'] == '' and wire['status'] == 'in_progress'
    assert wire['structured']['emoji'] == '🧠'
    assert row == before


@pytest.mark.parametrize(
    'changes',
    [
        {'user_title': FALLBACK},
        {'user_title': 'My chat', 'structured': {'title': FALLBACK, 'overview': ''}},
        {'structured': {'title': FALLBACK, 'overview': 'Approval is due Friday.'}},
        {'structured': {'title': 'Pilot budget'}},
        {'structured': {'title': ''}},
        {'structured': {'title': 'Transcribing…'}},
        {'structured': None},
    ],
)
def test_wire_rule_touches_nothing_else(changes):
    row = stub(**changes)
    assert home_titles.placeholder_title_wire(row) is row


@pytest.mark.parametrize('fallback', [FALLBACK, 'Discussion 3'])
def test_list_wire_labels_ready_captures_with_projection_receipt(fallback):
    row = capture(record_projection_revision=2, structured={'title': fallback, 'overview': ''})
    before = deepcopy(row)
    wire = transcribing_hold.project(home_step.project(row), home_list=True)
    assert wire['home_step'] == home_step.READY
    assert wire['structured']['title'] == 'Recording'
    assert wire['structured']['overview'] == ''
    assert wire['status'] == 'completed'
    assert row == before


def test_list_wire_does_not_label_a_ready_capture_without_a_receipt():
    row = capture(structured={'title': FALLBACK})
    row.pop('home_transcription_deadline_at', None)
    wire = transcribing_hold.project(home_step.project(row), home_list=True)
    assert wire['home_step'] == home_step.READY
    assert wire['structured']['title'] == ''


def test_list_wire_does_not_label_a_processing_capture_with_a_receipt():
    row = capture(status='processing', record_projection_revision=2, structured={'title': FALLBACK})
    wire = transcribing_hold.project(home_step.project(row), home_list=True)
    assert wire['home_step'] == home_step.TRANSCRIBING
    assert wire['structured']['title'] == ''


def test_list_wire_does_not_label_a_locked_capture():
    row = capture(record_projection_revision=2, is_locked=True, structured={'title': FALLBACK})
    wire = transcribing_hold.project(home_step.project(row), home_list=True)
    assert wire['structured']['title'] == ''


def test_other_reader_cannot_label_a_row_with_a_saved_ready_step():
    row = capture(record_projection_revision=2, home_step='ready', structured={'title': FALLBACK})
    assert transcribing_hold.project(row)['structured']['title'] == ''


def test_list_with_home_projection_off_ignores_a_saved_ready_step(monkeypatch):
    monkeypatch.setenv('HOME_STEP_PROJECTION', 'off')
    row = capture(record_projection_revision=2, home_step='ready', structured={'title': FALLBACK})
    assert transcribing_hold.project(home_step.project(row), home_list=True)['structured']['title'] == ''


def test_expired_empty_capture_is_noise_even_when_stamped():
    row = placeholder(structured={'title': FALLBACK, 'overview': ''})
    assert empty_capture.applies(row, now=NOW)
    assert home_step.classify(row) == home_step.NOISE
    assert transcribing_hold.project(row)['structured']['title'] == 'No summary'


def test_pending_write_is_sanitized_like_generated_notes_and_records_no_title_fallback(store, monkeypatch):
    from utils.observability import fallback

    recorded = []
    monkeypatch.setattr(fallback, 'record_fallback', lambda **labels: recorded.append(labels))
    client = store(stub(structured={'title': ''}))
    narrated = stub(structured={**EMPTY_NOTES, 'overview': 'The transcript is unavailable.', 'quality_flags': []})
    db.upsert_conversation_with_lifecycle('u', narrated)
    written = client.commits[0]['structured']
    assert written['title'] == '' and written['overview'] == ''
    assert 'quality_flags' not in written
    assert not [labels for labels in recorded if labels.get('to_mode') == 'deterministic_title']


@pytest.mark.parametrize(
    'title,preview,served',
    [
        (FALLBACK, '', ''),
        (FALLBACK, '   ', ''),
        ('Discussion 2', None, ''),
        (FALLBACK, 'Approval is due Friday.', FALLBACK),
        ('Pilot budget', '', 'Pilot budget'),
        ('', '', ''),
    ],
)
def test_home_card_title_rule(title, preview, served):
    assert display_title(title, preview) == served


@pytest.mark.parametrize('title', ['Transcribing…', 'Untitled'])
def test_expired_empty_capture_with_any_placeholder_is_noise(title):
    row = placeholder(structured={'title': title, 'overview': ''})
    assert empty_capture.applies(row, now=NOW)
    assert home_step.classify(row) == home_step.NOISE
    assert transcribing_hold.project(row)['structured']['title'] == 'No summary'


@pytest.mark.parametrize(
    'notes',
    [
        {'title': FALLBACK, 'overview': 'Approval is due Friday.'},
        {'title': FALLBACK, 'sections': [{'heading': 'Discussion 1', 'body_markdown': 'Budget is $8,000.'}]},
        {'title': 'Transcribing…', 'gist': 'Pilot budget approval'},
    ],
)
def test_placeholder_title_beside_real_notes_is_a_finished_row_not_a_transcription_wait(notes):
    """Generated notes with an unusable headline, on a batch capture whose transcript receipt has not landed."""
    row = capture(structured=notes)
    assert not transcribing_hold.applies(row)
    assert home_step.classify(row) == home_step.READY
    wire = transcribing_hold.project(home_step.project(row), home_list=True)
    assert wire['structured'] == notes and wire['status'] == 'completed'
    assert home_step.classify(capture(status='processing', structured=notes)) == home_step.WRITING_NOTES


@pytest.mark.parametrize(
    'structured,protected',
    [
        ({'title': FALLBACK}, False),
        ({'title': 'Discussion 3'}, False),
        ({'title': 'Transcribing…'}, False),
        ({'title': ''}, False),
        ({'title': 'Pilot budget'}, True),
        ({'title': FALLBACK, 'overview': 'Approval is due Friday.'}, True),
        ({'title': FALLBACK, 'overview': 'The transcript is unavailable.'}, True),
        # A gist is content the minimum would drop, so it protects the row.
        ({'title': FALLBACK, 'gist': 'Pilot budget approval'}, True),
        ({'title': FALLBACK, 'participants': [{'name': 'Alex'}]}, False),
        ({'title': FALLBACK, 'insights': [{'text': 'The budget is tight.'}]}, False),
        ({'title': FALLBACK, 'meeting_type': 'meeting'}, False),
        ({'title': FALLBACK, 'salience': 'highlight'}, False),
    ],
)
def test_protected_content_does_not_count_a_placeholder_as_a_title(structured, protected):
    """Recovery may replace a row that only carries the fallback label, never a real title."""
    from utils.conversations.recovery import structured_has_protected_content

    assert structured_has_protected_content(structured) is protected
    assert structured_has_protected_content(structured, user_title='My chat') is True


@pytest.mark.parametrize(
    'structured,replaceable',
    [
        ({'title': FALLBACK}, True),
        ({'title': 'Discussion 3'}, True),
        ({'title': 'Transcribing…'}, True),
        ({'title': ''}, True),
        ({'title': 'Recording · 3:00 PM', 'title_provenance': 'server_minimum'}, True),
        ({'title': 'Pilot budget'}, False),
        ({'title': FALLBACK, 'overview': 'Approval is due Friday.'}, False),
        ({'title': FALLBACK, 'gist': 'Pilot budget approval'}, False),
        ({'title': FALLBACK, 'sections': [{'heading': '', 'body_markdown': 'Approval is due Friday.'}]}, False),
        ({'title': FALLBACK, 'action_items': [{'description': 'Send the budget'}]}, False),
        # Enrichment-only fields are not part of the protected set: a row that
        # carries only those is still replaceable.
        ({'title': FALLBACK, 'participants': [{'name': 'Alex'}]}, True),
        ({'title': FALLBACK, 'insights': [{'text': 'The budget is tight.'}]}, True),
        ({'title': FALLBACK, 'meeting_type': 'meeting'}, True),
        ({'title': FALLBACK, 'salience': 'highlight'}, True),
        ({'title': FALLBACK, 'category': 'business'}, True),
        ({'title': FALLBACK, 'emoji': '🚀'}, True),
    ],
)
def test_stored_structure_is_replaceable_only_without_a_real_title_or_notes(structured, replaceable):
    """The recovery guard and the post-enrichment eligibility share this one rule."""
    from utils.conversations.recovery import stored_structure_is_replaceable

    assert stored_structure_is_replaceable(structured) is replaceable


def test_stored_structure_is_replaceable_reads_sections_on_the_model():
    """Both call sites pass a Structured model, not a dict; sections must still count."""
    from models.structured import Structured
    from utils.conversations.recovery import stored_structure_is_replaceable

    with_sections = Structured(title=FALLBACK, sections=[{'heading': 'Plan', 'body_markdown': 'Ship it Friday.'}])
    assert stored_structure_is_replaceable(with_sections) is False
    without_sections = Structured(title=FALLBACK)
    assert stored_structure_is_replaceable(without_sections) is True
