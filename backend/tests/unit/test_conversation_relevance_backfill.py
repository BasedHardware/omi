"""scripts/conversation_relevance_backfill.py: which stored rows it hides, and never more."""

from scripts.conversation_relevance_backfill import Summary, backfill_user, decision_record, verdict_for


def _row(text='Mm-hmm.', **fields):
    row = {
        'id': fields.pop('id', 'c1'),
        'source': 'omi',
        'status': 'completed',
        'discarded': False,
        'transcript_segments': [{'text': text, 'start': 0.0, 'end': 1.0}],
    }
    row.update(fields)
    return row


def test_legacy_review_row_is_stamped_without_reading_its_transcript():
    assert verdict_for(_row(text='Please call the doctor tomorrow.', sync_relevance='review')) == 'legacy_review'


def test_unassessed_filler_is_discarded_by_rule():
    assert verdict_for(_row()) == 'filler_only'
    assert verdict_for(_row(text="That's all.")) == 'no_content_words'


def test_non_audio_sources_are_never_judged_by_transcript_rules():
    """App imports, workflows, and camera captures keep content outside transcript_segments."""
    for source in ('external_integration', 'workflow', 'openglass', 'screenpipe', 'onboarding', None, 'unknown'):
        assert verdict_for(_row(source=source)) is None, source
        assert verdict_for(_row(text='', source=source)) is None, source


def test_an_empty_transcript_is_unknown_not_filler():
    assert verdict_for(_row(text='')) is None
    assert verdict_for({**_row(), 'transcript_segments': []}) is None


def test_content_the_rules_cannot_settle_is_left_alone():
    assert verdict_for(_row(text='Call mom before five.')) is None


def test_rows_already_assessed_or_hidden_are_left_alone():
    assert verdict_for(_row(relevance_decision={'verdict': 'keep'})) is None
    assert verdict_for(_row(discarded=True)) is None
    assert verdict_for(_row(deleted=True)) is None
    assert verdict_for(_row(status='processing')) is None


def test_user_curation_and_calendar_evidence_protect_a_row():
    for protected in (
        {'starred': True},
        {'user_title': 'Keep'},
        {'sync_relevance_user_kept': True},
        {'folder_user_set': True},
        {'visibility': 'shared'},
        {'has_photos': True},
        {'calendar_event': {'id': 'meeting'}},
        {'external_data': {'calendar_meeting_context': {'title': 'Standup'}}},
    ):
        assert verdict_for(_row(**protected)) is None, protected


def test_a_wake_word_is_never_discarded_by_rule():
    assert verdict_for(_row(text='Hey Omi.')) is None


def test_dry_run_counts_and_never_writes():
    writes = []
    summary = Summary(apply=False)
    backfill_user(
        'u', [_row(id='a'), _row(id='b', text='Buy milk.')], apply=False, discard=writes.append, summary=summary
    )

    assert writes == []
    assert summary.as_dict()['discards_by_rule'] == {'filler_only': 1}


def test_apply_writes_through_the_lifecycle_owner_and_counts_refusals():
    calls = []

    def discard(uid, conversation_id, record):
        calls.append((uid, conversation_id, record))
        return conversation_id == 'a'

    summary = Summary(apply=True)
    backfill_user('u', [_row(id='a'), _row(id='b')], apply=True, discard=discard, summary=summary)

    assert [call[1] for call in calls] == ['a', 'b']
    assert calls[0][2] == decision_record('filler_only')
    assert calls[0][2]['trigger'] == 'backfill'
    assert (summary.written, summary.refused) == (1, 1)
