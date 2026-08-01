"""Unit tests for acting on the speaker names the finalization pass only suggested.

The naming pass assigns a Person only when a second model fails to refute the
identification; everything short of that is persisted on the conversation as a
``speaker_label_suggestion`` and left for the user. These cover the two ways a
suggestion is settled -- accept and dismiss -- plus the enrolment attribution
that separates them from the pass's own writes, and the revocation a
reassignment away from an inferred Person has to trigger.

Attribution is the load-bearing detail: the pass enrols ``llm_inferred``, which
is excluded from embedding recovery, while a name the *user* tapped must enrol
``user_tagged`` so it is not. A test that accepted an inferred tag here would
let a user-confirmed voiceprint silently degrade.

``models.conversation`` and ``fastapi`` are imported at module scope rather than
inside the tests so their cost lands in collection, where the fast-unit CPU
guard does not measure it.
"""

import hashlib
import os
import uuid
from enum import Enum
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import BackgroundTasks, HTTPException

from models.conversation import SpeakerLabelSuggestion
from models.transcript_segment import TranscriptSegment
from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules

_BACKEND = Path(__file__).resolve().parents[2]

USER_TAGGED = 'user_tagged'
LLM_INFERRED = 'llm_inferred'


def _pkg(name):
    """AutoMockModule that also presents as a package (sets ``__path__``)."""
    mod = AutoMockModule(name)
    mod.__path__ = []
    return mod


@pytest.fixture(scope="module")
def router():
    """Load ``routers.conversations`` fresh against stubbed heavy dependencies.

    Mirrors the fixture in ``test_conversation_events_bounds``: the router builds
    typesense/pinecone/firebase clients at import time, so those have to be faked
    before it is exec'd. ``utils.speaker_identification`` is stubbed with the real
    attribution constants rather than an AutoMock, because the point of these tests
    is which constant reaches ``extract_speaker_samples``.
    """

    client_mod = ModuleType("database._client")
    client_mod.db = MagicMock(name="db")
    client_mod.get_firestore_client = lambda: client_mod.db

    def _document_id_from_seed(seed: str) -> str:
        seed_hash = hashlib.sha256(seed.encode("utf-8")).digest()
        return str(uuid.UUID(bytes=seed_hash[:16], version=4))

    client_mod.document_id_from_seed = _document_id_from_seed

    fa_auth = _pkg("firebase_admin.auth")
    fa_auth.InvalidIdTokenError = type("InvalidIdTokenError", (Exception,), {})

    endpoints = ModuleType("utils.other.endpoints")

    def _fake_get_current_user_uid():  # pragma: no cover - dependency stand-in
        return "test-uid"

    def _fake_with_rate_limit(dependency, _policy):  # pragma: no cover - returns wrapped dependency
        return dependency

    endpoints.get_current_user_uid = _fake_get_current_user_uid
    endpoints.with_rate_limit = _fake_with_rate_limit
    endpoints.get_user = MagicMock()

    class _MemorySystem(str, Enum):
        LEGACY = "legacy"
        CANONICAL = "canonical"

    memory_system = ModuleType("utils.memory.memory_system")
    setattr(memory_system, "MemorySystem", _MemorySystem)

    canonical_activation = ModuleType("utils.memory.canonical_activation")
    setattr(canonical_activation, "canonical_write_enabled", MagicMock(return_value=False))

    memory_service = ModuleType("utils.memory.memory_service")
    memory_service.MemoryService = MagicMock()

    surface_routing = ModuleType("utils.memory.surface_routing")
    surface_routing.pin_memory_system = MagicMock()

    request_validation = ModuleType("utils.request_validation")
    setattr(request_validation, "NonNegativeOffset", int)
    setattr(request_validation, "PositiveLimit", int)

    speaker_identification = ModuleType("utils.speaker_identification")
    setattr(speaker_identification, "SPEAKER_ATTRIBUTION_USER_TAGGED", USER_TAGGED)
    setattr(speaker_identification, "SPEAKER_ATTRIBUTION_LLM_INFERRED", LLM_INFERRED)
    setattr(speaker_identification, "extract_speaker_samples", MagicMock(name="extract_speaker_samples"))
    setattr(
        speaker_identification,
        "revoke_inferred_speaker_enrolment",
        MagicMock(name="revoke_inferred_speaker_enrolment"),
    )

    fakes = {
        "ulid": _pkg("ulid"),
        "pinecone": _pkg("pinecone"),
        "typesense": _pkg("typesense"),
        "database": _pkg("database"),
        "database._client": client_mod,
        "database.conversations": _pkg("database.conversations"),
        "database.action_items": _pkg("database.action_items"),
        "database.memories": _pkg("database.memories"),
        "database.redis_db": _pkg("database.redis_db"),
        "database.cache": _pkg("database.cache"),
        "database.apps": _pkg("database.apps"),
        "database.folders": _pkg("database.folders"),
        "database.trends": _pkg("database.trends"),
        "database.calendar_meetings": _pkg("database.calendar_meetings"),
        "database.tasks": _pkg("database.tasks"),
        "database.goals": _pkg("database.goals"),
        "database.llm_usage": _pkg("database.llm_usage"),
        "database.chat": _pkg("database.chat"),
        "database.notifications": _pkg("database.notifications"),
        "database.fair_use": _pkg("database.fair_use"),
        "database.webhook_health": _pkg("database.webhook_health"),
        "database.mem_db": _pkg("database.mem_db"),
        "utils.apps": _pkg("utils.apps"),
        "utils.conversations.merge_conversations": _pkg("utils.conversations.merge_conversations"),
        "database.users": _pkg("database.users"),
        "database.vector_db": _pkg("database.vector_db"),
        "firebase_admin": _pkg("firebase_admin"),
        "firebase_admin.messaging": _pkg("firebase_admin.messaging"),
        "firebase_admin.auth": fa_auth,
        "firebase_admin.credentials": _pkg("firebase_admin.credentials"),
        "firebase_admin.firestore": _pkg("firebase_admin.firestore"),
        "google": _pkg("google"),
        "google.cloud": _pkg("google.cloud"),
        "google.cloud.firestore": _pkg("google.cloud.firestore"),
        "google.cloud.firestore_v1": _pkg("google.cloud.firestore_v1"),
        "utils.other": _pkg("utils.other"),
        "utils.other.endpoints": endpoints,
        "utils.other.storage": _pkg("utils.other.storage"),
        "utils.conversations": _pkg("utils.conversations"),
        "utils.conversations.factory": _pkg("utils.conversations.factory"),
        "utils.conversations.render": _pkg("utils.conversations.render"),
        "utils.conversations.process_conversation": _pkg("utils.conversations.process_conversation"),
        "utils.conversations.search": _pkg("utils.conversations.search"),
        "utils.conversations.calendar_linking": _pkg("utils.conversations.calendar_linking"),
        "utils.conversations.calendar_utils": _pkg("utils.conversations.calendar_utils"),
        "utils.conversations.location": _pkg("utils.conversations.location"),
        "utils.conversations.analytics": _pkg("utils.conversations.analytics"),
        "utils.llm": _pkg("utils.llm"),
        "utils.llm.conversation_processing": _pkg("utils.llm.conversation_processing"),
        "utils.speaker_identification": speaker_identification,
        "utils.app_integrations": _pkg("utils.app_integrations"),
        "utils.memory": _pkg("utils.memory"),
        "utils.memory.memory_service": memory_service,
        "utils.memory.memory_system": memory_system,
        "utils.memory.canonical_activation": canonical_activation,
        "utils.memory.surface_routing": surface_routing,
        "utils.retrieval": _pkg("utils.retrieval"),
        "utils.retrieval.tools": _pkg("utils.retrieval.tools"),
        "utils.retrieval.tools.calendar_tools": _pkg("utils.retrieval.tools.calendar_tools"),
        "utils.retrieval.tools.google_utils": _pkg("utils.retrieval.tools.google_utils"),
        "utils.request_validation": request_validation,
    }

    with stub_modules(fakes):
        conv = load_module_fresh(
            "routers.conversations",
            os.path.join(str(_BACKEND), "routers", "conversations.py"),
        )
        yield conv


def segment(seg_id, speaker_id, person_id=None, is_user=False):
    return TranscriptSegment(
        id=seg_id,
        text='some words spoken here',
        speaker=f'SPEAKER_{speaker_id:02d}',
        is_user=is_user,
        person_id=person_id,
        start=0.0,
        end=8.0,
    )


def suggestion(speaker_id=1, name='Alex'):
    return SpeakerLabelSuggestion(
        speaker_id=speaker_id,
        person_name=name,
        evidence_quote="I'm Alex",
        confidence=0.6,
        segment_ids=['s1'],
    )


def conversation(segments, suggestions):
    return SimpleNamespace(id='c1', transcript_segments=segments, speaker_label_suggestions=suggestions)


class _Recorder:
    """Fresh mocks for the collaborators a suggestion route touches."""

    def __init__(self, router):
        self.router = router
        self.background_tasks = BackgroundTasks()

    def __enter__(self):
        self.router.conversations_db.update_conversation_segments.reset_mock()
        self.router.conversations_db.update_conversation.reset_mock()
        self.router.users_db.get_or_create_person_by_name.reset_mock()
        return self

    def __exit__(self, *exc_info):
        return False

    @property
    def segment_writes(self):
        return self.router.conversations_db.update_conversation_segments.call_args_list

    @property
    def suggestion_writes(self):
        return self.router.conversations_db.update_conversation.call_args_list

    def tasks_for(self, func):
        return [task for task in self.background_tasks.tasks if task.func is func]


def run_accept(router, convo, existing_person=None):
    """Drive accept with resolve-or-create standing in for the real Firestore helper.

    ``get_or_create_person_by_name`` returns ``(person, created)``: an existing
    record comes back with ``created`` False, and an unseen name is coined here
    the way the helper would, so the test can assert on the id the route used.
    """
    recorder = _Recorder(router)
    with recorder, patch.object(router, "_get_valid_conversation_by_id", return_value={"id": "c1"}), patch.object(
        router, "deserialize_conversation", return_value=convo
    ):
        if existing_person is not None:
            router.users_db.get_or_create_person_by_name.return_value = (existing_person, False)
        else:
            router.users_db.get_or_create_person_by_name.return_value = ({'id': 'p-new', 'name': 'Alex'}, True)
        result = router.accept_speaker_label_suggestion('c1', 1, recorder.background_tasks, uid='u1')
    return recorder, result


class TestAcceptSuggestion:
    def test_assigns_every_segment_of_the_speaker_to_the_resolved_person(self, router):
        segments = [segment('s1', 1), segment('s2', 1), segment('s3', 2)]
        convo = conversation(segments, [suggestion()])

        recorder, result = run_accept(router, convo, existing_person={'id': 'p-alex', 'name': 'Alex'})

        assert [seg.person_id for seg in segments] == ['p-alex', 'p-alex', None]
        assert all(seg.is_user is False for seg in segments)
        assert result is convo
        assert len(recorder.segment_writes) == 1

    def test_reuses_the_existing_person_rather_than_coining_a_second(self, router):
        convo = conversation([segment('s1', 1)], [suggestion()])

        recorder, _ = run_accept(router, convo, existing_person={'id': 'p-alex', 'name': 'Alex'})

        router.users_db.get_or_create_person_by_name.assert_called_once_with('u1', 'Alex')
        assert recorder.router.users_db.get_or_create_person_by_name.return_value[1] is False

    def test_creates_a_person_when_the_name_is_new(self, router):
        convo = conversation([segment('s1', 1)], [suggestion()])

        recorder, _ = run_accept(router, convo, existing_person=None)

        recorder.router.users_db.get_or_create_person_by_name.assert_called_once_with('u1', 'Alex')
        assert convo.transcript_segments[0].person_id == 'p-new'

    def test_enrols_as_user_tagged_not_llm_inferred(self, router):
        """The whole point of accept: a tapped name is a confirmation, not an inference."""
        convo = conversation([segment('s1', 1), segment('s2', 1)], [suggestion()])

        recorder, _ = run_accept(router, convo, existing_person={'id': 'p-alex'})

        enrolments = recorder.tasks_for(router.extract_speaker_samples)
        assert len(enrolments) == 1
        assert enrolments[0].kwargs['attribution'] == USER_TAGGED
        assert enrolments[0].kwargs['attribution'] != LLM_INFERRED
        assert enrolments[0].kwargs['person_id'] == 'p-alex'
        assert enrolments[0].kwargs['segment_ids'] == ['s1', 's2']

    def test_removes_the_accepted_suggestion_and_persists_the_rest(self, router):
        convo = conversation([segment('s1', 1)], [suggestion(1, 'Alex'), suggestion(2, 'Sam')])

        recorder, _ = run_accept(router, convo, existing_person={'id': 'p-alex'})

        assert [item.speaker_id for item in convo.speaker_label_suggestions] == [2]
        written = recorder.suggestion_writes[0][0][2]['speaker_label_suggestions']
        assert [item['speaker_id'] for item in written] == [2]

    def test_speaker_without_a_suggestion_is_404_and_writes_nothing(self, router):
        convo = conversation([segment('s1', 1)], [suggestion(speaker_id=4)])
        recorder = _Recorder(router)
        with recorder, patch.object(router, "_get_valid_conversation_by_id", return_value={"id": "c1"}), patch.object(
            router, "deserialize_conversation", return_value=convo
        ):
            with pytest.raises(HTTPException) as excinfo:
                router.accept_speaker_label_suggestion('c1', 1, recorder.background_tasks, uid='u1')

        assert excinfo.value.status_code == 404
        assert recorder.segment_writes == []
        assert recorder.suggestion_writes == []
        assert recorder.background_tasks.tasks == []
        assert convo.transcript_segments[0].person_id is None


class TestDismissSuggestion:
    def test_removes_the_suggestion_without_assigning_anything(self, router):
        segments = [segment('s1', 1)]
        convo = conversation(segments, [suggestion(1, 'Alex'), suggestion(2, 'Sam')])
        recorder = _Recorder(router)
        with recorder, patch.object(router, "_get_valid_conversation_by_id", return_value={"id": "c1"}), patch.object(
            router, "deserialize_conversation", return_value=convo
        ):
            result = router.dismiss_speaker_label_suggestion('c1', 1, uid='u1')

        assert [item.speaker_id for item in convo.speaker_label_suggestions] == [2]
        assert recorder.suggestion_writes[0][0][2]['speaker_label_suggestions'][0]['speaker_id'] == 2
        assert recorder.segment_writes == []
        assert recorder.router.users_db.get_or_create_person_by_name.call_count == 0
        assert segments[0].person_id is None
        assert result is convo

    def test_speaker_without_a_suggestion_is_404(self, router):
        convo = conversation([segment('s1', 1)], [suggestion(speaker_id=4)])
        recorder = _Recorder(router)
        with recorder, patch.object(router, "_get_valid_conversation_by_id", return_value={"id": "c1"}), patch.object(
            router, "deserialize_conversation", return_value=convo
        ):
            with pytest.raises(HTTPException) as excinfo:
                router.dismiss_speaker_label_suggestion('c1', 1, uid='u1')

        assert excinfo.value.status_code == 404
        assert recorder.suggestion_writes == []
        assert [item.speaker_id for item in convo.speaker_label_suggestions] == [4]


def run_assign_speaker(router, convo, speaker_id, assign_type, value):
    recorder = _Recorder(router)
    with recorder, patch.object(router, "_get_valid_conversation_by_id", return_value={"id": "c1"}), patch.object(
        router, "deserialize_conversation", return_value=convo
    ):
        router.set_assignee_conversation_segment(
            'c1', speaker_id, recorder.background_tasks, assign_type, value=value, uid='u1'
        )
    return recorder


class TestRevokeContradictedInference:
    def test_reassigning_a_speaker_away_revokes_the_previous_person(self, router):
        """The user contradicted whatever named this speaker, so the voiceprint goes."""
        convo = conversation([segment('s1', 1, person_id='p-old'), segment('s2', 2)], [])

        recorder = run_assign_speaker(router, convo, 1, 'person_id', 'p-new')

        revocations = recorder.tasks_for(router.revoke_inferred_speaker_enrolment)
        assert [task.kwargs['person_id'] for task in revocations] == ['p-old']
        assert revocations[0].kwargs['uid'] == 'u1'

    def test_unassigning_a_speaker_to_the_user_also_revokes(self, router):
        convo = conversation([segment('s1', 1, person_id='p-old'), segment('s2', 2)], [])

        recorder = run_assign_speaker(router, convo, 1, 'is_user', 'true')

        revocations = recorder.tasks_for(router.revoke_inferred_speaker_enrolment)
        assert [task.kwargs['person_id'] for task in revocations] == ['p-old']

    def test_person_still_speaking_elsewhere_is_left_alone(self, router):
        """Losing one speaker is not a contradiction while the Person holds another."""
        convo = conversation(
            [segment('s1', 1, person_id='p-old'), segment('s2', 2, person_id='p-old')],
            [],
        )

        recorder = run_assign_speaker(router, convo, 1, 'person_id', 'p-new')

        assert recorder.tasks_for(router.revoke_inferred_speaker_enrolment) == []

    def test_reassigning_to_the_same_person_revokes_nothing(self, router):
        convo = conversation([segment('s1', 1, person_id='p-old'), segment('s2', 2)], [])

        recorder = run_assign_speaker(router, convo, 1, 'person_id', 'p-old')

        assert recorder.tasks_for(router.revoke_inferred_speaker_enrolment) == []

    def test_accepting_over_an_earlier_person_revokes_that_person(self, router):
        convo = conversation([segment('s1', 1, person_id='p-old'), segment('s2', 2)], [suggestion()])

        recorder, _ = run_accept(router, convo, existing_person={'id': 'p-alex'})

        revocations = recorder.tasks_for(router.revoke_inferred_speaker_enrolment)
        assert [task.kwargs['person_id'] for task in revocations] == ['p-old']
