"""SERVER_RECOVERY admission: one fenced attempt on stale content-bearing rows.

The admission predicate is evaluated twice — once on the sweep's stale read
for logging reasons, once authoritatively inside the outbox transaction
before any write. These tests pin the refusal vocabulary, the
no-write-on-refusal invariant, the one-attempt policy (no second revision
after dead_letter), and the recovery metadata persisted on the job.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from database import conversation_finalization_jobs as jobs
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.conversations.recovery import (
    RECOVERY_MAX_AUDIO_FILE_IDS,
    raw_transcript_bytes,
    recovery_audio_file_ids,
    structured_has_protected_content,
    structured_is_rich,
)


class _Ref:
    def __init__(self, doc_id: str, data: dict | None):
        self.id = doc_id
        self.data = data

    def get(self, transaction=None):
        del transaction
        return SimpleNamespace(exists=self.data is not None, id=self.id, to_dict=lambda: self.data)

    def collection(self, name: str):
        return SimpleNamespace(limit=lambda _count: SimpleNamespace(stream=lambda **_kw: iter([])))


class _Collection:
    def __init__(self, refs: dict[str, _Ref] | None = None):
        self.refs = refs or {}

    def document(self, doc_id: str):
        return self.refs.setdefault(doc_id, _Ref(doc_id, None))


class _Transaction:
    def __init__(self):
        self.updates: list[tuple[_Ref, dict]] = []
        self.sets: list[tuple[_Ref, dict]] = []

    def update(self, ref, data):
        self.updates.append((ref, data))

    def set(self, ref, data, **_kwargs):
        self.sets.append((ref, data))


NOW = datetime(2026, 7, 20, tzinfo=timezone.utc)
CUTOFF = NOW - timedelta(hours=2)
STALE_FINISHED = NOW - timedelta(hours=3)


def _recovery_conversation(data: dict | None = None) -> _Ref:
    return _Ref(
        'conversation-1',
        {
            'status': 'in_progress',
            'source': 'omi',
            'finished_at': STALE_FINISHED,
            'transcript_segments': [{'text': 'persisted'}],
            **(data or {}),
        },
    )


def _admit_finalization(_conversation_data: dict) -> jobs.FinalizationAdmission:
    return {
        'accepted': True,
        'terminal': False,
        'reason': 'accepted',
        'fanout_key': 'fanout-key',
    }


def _recover(conversation_ref: _Ref, *, cutoff=CUTOFF, jobs_collection=None):
    transaction = _Transaction()
    intent = jobs._create_or_get_finalization_intent_txn(
        transaction,
        conversation_ref,
        jobs_collection if jobs_collection is not None else _Collection(),
        'uid-1',
        'conversation-1',
        False,
        _admit_finalization,
        NOW,
        trigger=ProcessingTrigger.SERVER_RECOVERY,
        recovery_cutoff=cutoff,
    )
    return transaction, intent


def test_recovery_admits_stale_content_row_and_stamps_metadata():
    transaction, intent = _recover(_recovery_conversation({'audio_files': [{'id': 'b2'}, {'id': 'a1'}]}))

    assert intent['created'] is True
    assert intent['status'] == 'queued'
    assert len(transaction.sets) == 1
    job = transaction.sets[0][1]
    assert job['processing_trigger'] == 'server_recovery'
    assert job['selfheal_attempt'] == 1
    assert job['selfheal_transcript_bytes'] > 0
    assert job['selfheal_audio_file_ids'] == ['a1', 'b2']
    assert 'transcript' not in job and 'transcript_segments' not in job
    assert transaction.updates[0][1]['status'] == 'processing'
    assert transaction.updates[0][1]['finalization_job_id'] == intent['job_id']


def test_recovery_refuses_when_finished_at_raced_inside_the_cutoff():
    """The transaction's authoritative snapshot re-checks staleness after the scan."""
    transaction, intent = _recover(_recovery_conversation({'finished_at': NOW - timedelta(hours=1)}))

    assert intent['created'] is False
    assert intent['status'] == 'refused_not_stale'
    assert transaction.sets == []
    assert transaction.updates == []


def test_recovery_refuses_a_rich_structured_row():
    transaction, intent = _recover(_recovery_conversation({'structured': {'overview': 'finalized notes'}}))

    assert intent['status'] == 'refused_protected_content'
    assert transaction.sets == []
    assert transaction.updates == []


def test_recovery_refuses_title_only_and_user_title_rows_without_writes():
    """A real title or a user-authored title is protected even with no overview."""
    transaction, intent = _recover(_recovery_conversation({'structured': {'title': 'Useful user title'}}))
    assert intent['status'] == 'refused_protected_content'
    assert transaction.sets == []
    assert transaction.updates == []

    transaction, intent = _recover(_recovery_conversation({'user_title': 'Renamed by the user'}))
    assert intent['status'] == 'refused_protected_content'
    assert transaction.sets == []
    assert transaction.updates == []

    transaction, intent = _recover(_recovery_conversation({'structured': {'title': '  '}, 'user_title': '   '}))
    assert intent['status'] != 'refused_protected_content'


def test_recovery_refuses_any_existing_finalization_job_id():
    transaction, intent = _recover(_recovery_conversation({'finalization_job_id': 'job-dead-1'}))

    assert intent['status'] == 'refused_has_job'
    assert transaction.sets == []
    assert transaction.updates == []


def test_dead_lettered_job_never_mints_a_second_revision():
    """A row whose job already dead-lettered is refused, never re-admitted."""
    dead_job = _Ref('job-dead-1', {'status': 'dead_letter', 'finalization_revision': 1})
    jobs_collection = _Collection({'job-dead-1': dead_job})
    transaction, intent = _recover(
        _recovery_conversation({'finalization_job_id': 'job-dead-1', 'finalization_revision': 1}),
        jobs_collection=jobs_collection,
    )

    assert intent['status'] == 'refused_has_job'
    assert intent['job_id'] is None
    assert transaction.sets == []
    assert transaction.updates == []


def test_recovery_refuses_when_cutoff_is_absent():
    transaction, intent = _recover(_recovery_conversation(), cutoff=None)

    assert intent['status'] == 'refused_no_cutoff'
    assert transaction.sets == []


def test_recovery_refuses_oversized_audio_file_lists():
    audio_files = [{'id': f'f{i}'} for i in range(RECOVERY_MAX_AUDIO_FILE_IDS + 1)]
    transaction, intent = _recover(_recovery_conversation({'audio_files': audio_files}))

    assert intent['status'] == 'refused_oversized_audio_files'
    assert transaction.sets == []


def test_other_triggers_never_run_the_recovery_fence():
    """CAPTURE_END on the same stale row admits normally — the fence is trigger-scoped."""
    transaction = _Transaction()
    intent = jobs._create_or_get_finalization_intent_txn(
        transaction,
        _recovery_conversation({'structured': {'overview': 'already done'}}),
        _Collection(),
        'uid-1',
        'conversation-1',
        False,
        _admit_finalization,
        NOW,
        trigger=ProcessingTrigger.CAPTURE_END,
    )
    assert intent['created'] is True
    assert 'selfheal_attempt' not in transaction.sets[0][1]


def test_one_admission_then_rerun_is_refused_idempotently():
    """After the first attempt binds finalization_job_id, a re-scan refuses."""
    conversation_data = {
        'status': 'in_progress',
        'source': 'omi',
        'finished_at': STALE_FINISHED,
        'transcript_segments': [{'text': 'persisted'}],
    }
    conversation_ref = _Ref('conversation-1', conversation_data)
    first_txn, first_intent = _recover(conversation_ref)
    assert first_intent['created'] is True
    conversation_data.update(first_txn.updates[0][1])

    second_txn, second_intent = _recover(_Ref('conversation-1', dict(conversation_data)))

    assert second_intent['created'] is False
    assert second_intent['status'] == 'refused_status'
    assert second_txn.sets == []

    third_txn, third_intent = _recover(_Ref('conversation-1', dict(conversation_data, status='in_progress')))
    assert third_intent['status'] == 'refused_has_job'
    assert third_txn.sets == []


@pytest.mark.parametrize(
    'overrides,reason',
    [
        ({'status': 'processing'}, 'status'),
        ({'deleted': True}, 'tombstoned'),
        ({'discarded': True}, 'tombstoned'),
        ({'deferred': True}, 'deferred'),
        ({'is_locked': True}, 'locked'),
        ({'processing_state': 'local_pending'}, 'local_pending'),
        ({'terminal_no_derived_effects': True}, 'terminal_no_derived'),
        ({'source': 'desktop'}, 'source'),
        ({'source': 'unknown_source'}, 'source'),
        ({'finished_at': None}, 'no_finished_at'),
        ({'finished_at': 'not-a-datetime'}, 'no_finished_at'),
        ({'transcript_segments': [], 'has_content': False, 'audio_files': []}, 'no_content'),
        ({'structured': {'overview': 'done'}}, 'protected_content'),
        ({'structured': {'title': 'done'}}, 'protected_content'),
        ({'user_title': 'mine'}, 'protected_content'),
        ({'finalization_job_id': 'job-9'}, 'has_job'),
    ],
)
def test_recovery_refusal_reasons_are_bounded_and_write_free(overrides, reason):
    transaction, intent = _recover(_recovery_conversation(overrides))

    assert intent['status'] == f'refused_{reason}'
    assert intent['job_id'] is None
    assert transaction.sets == []
    assert transaction.updates == []


def test_audio_only_row_without_transcript_is_admitted():
    transaction, intent = _recover(
        _recovery_conversation({'transcript_segments': [], 'has_content': False, 'audio_files': [{'id': 'clip-1'}]})
    )

    assert intent['created'] is True
    job = transaction.sets[0][1]
    assert job['selfheal_audio_file_ids'] == ['clip-1']
    assert job['selfheal_transcript_bytes'] == len(b'[]')


def test_undecodable_transcript_blob_counts_as_content_and_sized_in_bytes():
    blob = 'gzipped-not-json-###'
    transaction, intent = _recover(_recovery_conversation({'transcript_segments': blob}))

    assert intent['created'] is True
    job = transaction.sets[0][1]
    assert job['selfheal_transcript_bytes'] == len(blob.encode('utf-8'))


def test_structured_is_rich_boundaries():
    assert structured_is_rich(None) is False
    assert structured_is_rich({}) is False
    assert structured_is_rich({'title': 'deterministic title'}) is False
    assert structured_is_rich({'overview': ' '}) is False
    assert structured_is_rich({'overview': 'notes'}) is True
    assert structured_is_rich({'sections': [{'title': 'x'}]}) is True
    assert structured_is_rich({'action_items': [{'description': 'd'}]}) is True
    model = SimpleNamespace(overview='', sections=[], action_items=[object()], events=[])
    assert structured_is_rich(model) is True
    empty_model = SimpleNamespace(overview='', sections=[], action_items=[], events=[])
    assert structured_is_rich(empty_model) is False


def test_structured_has_protected_content_boundaries():
    assert structured_has_protected_content(None) is False
    assert structured_has_protected_content({}) is False
    assert structured_has_protected_content({'title': ''}, ' ') is False
    assert structured_has_protected_content({'title': 'A title'}) is True
    assert structured_has_protected_content({'overview': 'notes'}) is True
    assert structured_has_protected_content({'sections': [{'title': 'x'}]}) is True
    assert structured_has_protected_content({'action_items': [{'description': 'd'}]}) is True
    assert structured_has_protected_content({'events': [{'title': 'e'}]}) is True
    assert structured_has_protected_content({}, user_title='Renamed') is True
    assert structured_has_protected_content({'title': ' '}, user_title=None) is False
    model = SimpleNamespace(title='', overview='', sections=[], action_items=[], events=[])
    assert structured_has_protected_content(model) is False
    titled_model = SimpleNamespace(title='Done', overview='', sections=[], action_items=[], events=[])
    assert structured_has_protected_content(titled_model) is True


def test_raw_transcript_bytes_never_reads_text():
    assert raw_transcript_bytes({}) == 0
    assert raw_transcript_bytes({'transcript_segments': 'blob'}) == 4
    assert raw_transcript_bytes({'transcript_segments': [{'text': 'secret words'}]}) == len(
        b'[{"text": "secret words"}]'
    )


def test_recovery_audio_file_ids_sorted_and_bounded():
    assert recovery_audio_file_ids({'audio_files': [{'id': 'z'}, {'id': 'a'}]}) == ['a', 'z']
    assert recovery_audio_file_ids({}) == []
    assert recovery_audio_file_ids({'audio_files': [{'id': i} for i in range(RECOVERY_MAX_AUDIO_FILE_IDS + 1)]}) is None


def test_recovery_audio_file_ids_refuses_any_malformed_entry():
    """A fingerprint that silently dropped a malformed entry would let the
    verification tick claim it preserved files it never recorded."""
    assert recovery_audio_file_ids({'audio_files': [{'id': 'a'}, {'other': 1}]}) is None
    assert recovery_audio_file_ids({'audio_files': [{'id': 'a'}, 'clip-1']}) is None
    assert recovery_audio_file_ids({'audio_files': [{'id': ''}]}) is None
    assert recovery_audio_file_ids({'audio_files': [{'id': None}]}) is None
    assert recovery_audio_file_ids({'audio_files': 'clip-1'}) is None


def test_audio_only_row_admits_without_touching_the_transcript_decoder(monkeypatch):
    """Nonempty audio_files must satisfy content admission before the raw
    transcript decoder runs — the decoder logs the blob on failure, which can
    carry user text."""
    decoder = MagicMock(side_effect=AssertionError('decoder must not run for audio-only rows'))
    monkeypatch.setattr(jobs.conversations_db, 'raw_conversation_has_content', decoder)

    transaction, intent = _recover(
        _recovery_conversation({'transcript_segments': 'explodes', 'audio_files': [{'id': 'clip-1'}]})
    )

    assert intent['created'] is True
    decoder.assert_not_called()
    job = transaction.sets[0][1]
    assert job['selfheal_audio_file_ids'] == ['clip-1']


def test_recovery_minimum_structure_raises_before_persist_or_fanout(capsys):
    """A SERVER_RECOVERY run producing only the deterministic minimum must raise
    the typed error before the persist transaction and before derived-effect
    fanout — the durable row keeps its in-progress state and content."""
    import json
    import sys
    from unittest.mock import MagicMock, patch

    from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules
    from tests.unit.test_process_conversation_duplicate_capture import BACKEND_DIR, _STUBBED
    from models.conversation import Conversation
    from models.conversation_enums import ConversationSource, ConversationStatus
    from models.structured import Structured
    from models.transcript_segment import TranscriptSegment
    from utils.conversations.recovery import RecoveryStructureUnavailableError

    fakes: dict = {}
    for name in _STUBBED:
        module = AutoMockModule(name)
        if name == 'langchain_core' or name.startswith('langchain_core.'):
            module.__path__ = []
        fakes[name] = module
    fakes['database._client'].document_id_from_seed = lambda seed: seed

    conversation = Conversation(
        id='recovery-conv',
        created_at=STALE_FINISHED,
        started_at=STALE_FINISHED,
        finished_at=NOW,
        structured=Structured(),
        transcript_segments=[
            TranscriptSegment(
                id='seg-1',
                text='a captured line',
                speaker='SPEAKER_00',
                speaker_id=0,
                is_user=True,
                start=0.0,
                end=1.0,
            )
        ],
        source=ConversationSource.omi,
        status=ConversationStatus.processing,
    )
    persistence_observer = MagicMock()
    disposition_observer = MagicMock()

    with stub_modules(fakes):
        pc = load_module_fresh(
            'utils.conversations.process_conversation',
            str(BACKEND_DIR / 'utils' / 'conversations' / 'process_conversation.py'),
        )
        try:
            with (
                patch.object(pc, 'is_release_probe_uid', MagicMock(return_value=False)),
                patch.object(pc, 'should_skip_omi_paid_postprocessing', MagicMock(return_value=False)),
                patch.object(pc, '_enrich_meeting_context', MagicMock()),
                patch.object(pc, '_get_structured', MagicMock(return_value=(Structured(), False))),
                patch.object(pc, '_get_conversation_obj', MagicMock(return_value=conversation)),
                patch.object(pc, '_attach_client_projection', MagicMock()),
            ):
                with pytest.raises(RecoveryStructureUnavailableError):
                    pc.process_conversation(
                        'uid-recovery',
                        'en',
                        conversation,
                        persistence_observer=persistence_observer,
                        derived_effects_disposition_observer=disposition_observer,
                        trigger=ProcessingTrigger.SERVER_RECOVERY,
                    )
        finally:
            sys.modules.pop('utils.conversations.process_conversation', None)

    persistence_observer.assert_not_called()
    disposition_observer.assert_not_called()
    events = [json.loads(line) for line in capsys.readouterr().out.strip().splitlines()]
    assert [e for e in events if e.get('event') == 'selfheal_guard'] == [
        {
            'event': 'selfheal_guard',
            'outcome': 'refused',
            'reason': 'empty_structured',
            'uid': 'uid-recovery',
            'conversation_id': 'recovery-conv',
        }
    ]
