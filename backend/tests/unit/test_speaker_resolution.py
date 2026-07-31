"""Unit tests for LLM speaker-identity gating and its refutation pass.

Two things stand between a model's guess and a voiceprint enrolled against the
wrong person. The gate checks grounding a machine can settle -- a quote that is
not in the transcript, a name absent from its own quote, two names on one
speaker -- and produces suggestions only. A second, independent model call then
tries to refute each suggestion, and only the survivors are assigned and
enrolled, so these also pin down that a refusal, or a verifier that breaks,
leaves the pass at suggestion-only.
"""

import sys
from types import ModuleType, SimpleNamespace

import pytest

from utils.conversations.speaker_resolution import MAX_VERIFICATIONS_PER_CONVERSATION, verify_suggestions
from utils.speaker_resolution import (
    RejectionReason,
    ResolvedSpeaker,
    SpeakerClaim,
    is_valid_person_name,
    normalize_text,
    plan_speaker_resolution,
)


def segment(seg_id, text, speaker_id=None, is_user=False, person_id=None):
    return SimpleNamespace(id=seg_id, text=text, speaker_id=speaker_id, is_user=is_user, person_id=person_id)


def claim(speaker_id=1, name="Alex", quote="I'm Alex", confidence=0.9):
    return SpeakerClaim(
        speaker_id=speaker_id,
        person_name=name,
        evidence_quote=quote,
        confidence=confidence,
    )


def reasons(plan):
    return {rejected.reason for rejected in plan.rejected}


class TestNormalizeText:
    def test_strips_punctuation_case_and_accents(self):
        assert normalize_text("Hey, Álex!") == "hey alex"

    def test_collapses_whitespace(self):
        assert normalize_text("  I'm   Alex \n") == "im alex"

    def test_non_string_is_empty(self):
        assert normalize_text(None) == ""
        assert normalize_text(42) == ""


class TestIsValidPersonName:
    @pytest.mark.parametrize("name", ["Alex", "Mary Jane", "O'Brien"])
    def test_accepts_real_names(self, name):
        assert is_valid_person_name(name)

    @pytest.mark.parametrize("name", ["you", "They", "it"])
    def test_rejects_stopwords_shared_with_regex_detector(self, name):
        assert not is_valid_person_name(name)

    def test_rejects_stopword_inside_multiword_name(self):
        assert not is_valid_person_name("Alex you")

    @pytest.mark.parametrize("name", ["", "A", "   ", "123", None, 7, "x" * 41])
    def test_rejects_unusable_values(self, name):
        assert not is_valid_person_name(name)


class TestQuoteGrounding:
    def test_accepts_a_quote_found_verbatim(self):
        segments = [
            segment("s1", "Hi everyone", speaker_id=0, is_user=True),
            segment("s2", "I'm Alex, good to meet you", speaker_id=1),
        ]
        plan = plan_speaker_resolution([claim(quote="I'm Alex, good to meet you")], segments)
        assert [(s.speaker_id, s.person_name) for s in plan.suggestions] == [(1, "Alex")]
        assert plan.suggestions[0].segment_ids == ("s2",)

    def test_rejects_a_quote_absent_from_the_transcript(self):
        segments = [segment("s1", "good morning everyone", speaker_id=1)]
        plan = plan_speaker_resolution([claim(quote="I'm Alex")], segments)
        assert plan.is_empty
        assert reasons(plan) == {RejectionReason.QUOTE_NOT_IN_TRANSCRIPT}

    def test_rejects_a_quote_that_does_not_contain_the_name(self):
        segments = [segment("s1", "good morning everyone", speaker_id=1)]
        plan = plan_speaker_resolution([claim(quote="good morning everyone")], segments)
        assert plan.is_empty
        assert reasons(plan) == {RejectionReason.NAME_NOT_IN_QUOTE}

    def test_tolerates_punctuation_and_case_drift(self):
        segments = [segment("s1", "Hey — I'm Alex, by the way.", speaker_id=1)]
        plan = plan_speaker_resolution([claim(quote="hey i'm alex by the way")], segments)
        assert [s.person_name for s in plan.suggestions] == ["Alex"]

    def test_rejects_a_quote_stitched_across_two_segments(self):
        segments = [
            segment("s1", "so anyway", speaker_id=1),
            segment("s2", "I'm Alex", speaker_id=1),
        ]
        plan = plan_speaker_resolution([claim(quote="so anyway I'm Alex")], segments)
        assert plan.is_empty
        assert reasons(plan) == {RejectionReason.QUOTE_NOT_IN_TRANSCRIPT}

    def test_a_quote_from_another_speaker_still_only_suggests(self):
        segments = [
            segment("s1", "Thanks Alex, that helps", speaker_id=0, is_user=True),
            segment("s2", "No problem at all", speaker_id=1),
        ]
        plan = plan_speaker_resolution([claim(speaker_id=1, quote="Thanks Alex, that helps")], segments)
        assert [(s.speaker_id, s.person_name) for s in plan.suggestions] == [(1, "Alex")]

    def test_covers_every_segment_of_that_speaker(self):
        segments = [
            segment("s1", "I'm Alex", speaker_id=1),
            segment("s2", "and I work on the API", speaker_id=1),
            segment("s3", "got it", speaker_id=2),
        ]
        plan = plan_speaker_resolution([claim()], segments)
        assert plan.suggestions[0].segment_ids == ("s1", "s2")


class TestConfidenceFloor:
    def test_confidence_below_the_floor_is_dropped(self):
        segments = [segment("s1", "I'm Alex", speaker_id=1)]
        plan = plan_speaker_resolution([claim(confidence=0.2)], segments)
        assert plan.is_empty
        assert reasons(plan) == {RejectionReason.LOW_CONFIDENCE}

    def test_confidence_at_the_floor_is_kept(self):
        segments = [segment("s1", "I'm Alex", speaker_id=1)]
        plan = plan_speaker_resolution([claim(confidence=0.5)], segments)
        assert [s.person_name for s in plan.suggestions] == ["Alex"]


class TestNothingIsEverAutoAssigned:
    def test_the_plan_offers_no_way_to_mark_a_claim_as_safe(self):
        segments = [segment("s1", "I'm Alex", speaker_id=1)]
        plan = plan_speaker_resolution([claim(confidence=1.0)], segments)
        assert not hasattr(plan, "assignments")
        assert len(plan.suggestions) == 1


class TestAmbiguity:
    def test_two_names_on_one_speaker_drops_both(self):
        segments = [
            segment("s1", "I'm Alex", speaker_id=1),
            segment("s2", "I'm Ben", speaker_id=1),
        ]
        plan = plan_speaker_resolution(
            [claim(speaker_id=1, name="Alex", quote="I'm Alex"), claim(speaker_id=1, name="Ben", quote="I'm Ben")],
            segments,
        )
        assert plan.is_empty
        assert reasons(plan) == {RejectionReason.AMBIGUOUS_SPEAKER}

    def test_one_name_on_two_speakers_drops_both(self):
        segments = [
            segment("s1", "I'm Alex", speaker_id=1),
            segment("s2", "I'm Alex", speaker_id=2),
        ]
        plan = plan_speaker_resolution(
            [claim(speaker_id=1, quote="I'm Alex"), claim(speaker_id=2, quote="I'm Alex")],
            segments,
        )
        assert plan.is_empty
        assert reasons(plan) == {RejectionReason.AMBIGUOUS_NAME}

    def test_an_ambiguous_speaker_does_not_poison_an_unrelated_one(self):
        segments = [
            segment("s1", "I'm Alex", speaker_id=1),
            segment("s2", "I'm Ben", speaker_id=1),
            segment("s3", "I'm Chris", speaker_id=2),
        ]
        plan = plan_speaker_resolution(
            [
                claim(speaker_id=1, name="Alex", quote="I'm Alex"),
                claim(speaker_id=1, name="Ben", quote="I'm Ben"),
                claim(speaker_id=2, name="Chris", quote="I'm Chris"),
            ],
            segments,
        )
        assert [(s.speaker_id, s.person_name) for s in plan.suggestions] == [(2, "Chris")]

    def test_duplicate_claims_for_one_speaker_keep_the_most_confident(self):
        segments = [
            segment("s1", "Thanks Alex", speaker_id=0, is_user=True),
            segment("s2", "I'm Alex", speaker_id=1),
        ]
        plan = plan_speaker_resolution(
            [
                claim(speaker_id=1, quote="Thanks Alex", confidence=0.6),
                claim(speaker_id=1, quote="I'm Alex", confidence=0.95),
            ],
            segments,
        )
        assert len(plan.suggestions) == 1
        assert plan.suggestions[0].evidence_quote == "I'm Alex"


class TestSpeakerEligibility:
    def test_unknown_speaker_id_is_rejected(self):
        segments = [segment("s1", "I'm Alex", speaker_id=1)]
        plan = plan_speaker_resolution([claim(speaker_id=9, quote="I'm Alex")], segments)
        assert plan.is_empty
        assert reasons(plan) == {RejectionReason.UNKNOWN_SPEAKER}

    def test_a_speaker_already_bound_to_a_person_is_left_alone(self):
        segments = [segment("s1", "I'm Alex", speaker_id=1, person_id="person-existing")]
        plan = plan_speaker_resolution([claim(quote="I'm Alex")], segments)
        assert plan.is_empty
        assert reasons(plan) == {RejectionReason.SPEAKER_ALREADY_RESOLVED}

    def test_the_users_own_speaker_is_left_alone(self):
        segments = [segment("s1", "I'm Alex", speaker_id=1, is_user=True)]
        plan = plan_speaker_resolution([claim(quote="I'm Alex")], segments)
        assert plan.is_empty
        assert reasons(plan) == {RejectionReason.SPEAKER_ALREADY_RESOLVED}

    def test_the_account_owners_name_is_never_claimed_for_another_speaker(self):
        segments = [segment("s1", "I'm Alex", speaker_id=1)]
        plan = plan_speaker_resolution([claim(quote="I'm Alex")], segments, user_name="alex")
        assert plan.is_empty
        assert reasons(plan) == {RejectionReason.NAME_IS_USER}

    def test_an_invalid_name_is_rejected(self):
        segments = [segment("s1", "I'm you", speaker_id=1)]
        plan = plan_speaker_resolution([claim(name="you", quote="I'm you")], segments)
        assert plan.is_empty
        assert reasons(plan) == {RejectionReason.INVALID_NAME}

    def test_segments_without_a_speaker_index_are_ignored(self):
        segments = [segment("s1", "I'm Alex", speaker_id=None)]
        plan = plan_speaker_resolution([claim(quote="I'm Alex")], segments)
        assert plan.is_empty


class TestDegenerateInput:
    def test_no_claims_is_an_empty_plan(self):
        assert plan_speaker_resolution([], [segment("s1", "hello", speaker_id=1)]).is_empty

    def test_no_segments_is_an_empty_plan(self):
        assert plan_speaker_resolution([claim()], []).is_empty

    def test_empty_quote_is_rejected(self):
        segments = [segment("s1", "I'm Alex", speaker_id=1)]
        plan = plan_speaker_resolution([claim(quote="")], segments)
        assert plan.is_empty
        assert reasons(plan) == {RejectionReason.QUOTE_NOT_IN_TRANSCRIPT}

    def test_segments_without_an_id_are_skipped(self):
        segments = [segment("", "I'm Alex", speaker_id=1)]
        plan = plan_speaker_resolution([claim(quote="I'm Alex")], segments)
        assert plan.is_empty

    def test_mapping_segments_are_supported(self):
        segments = [{'id': 's1', 'text': "I'm Alex", 'speaker_id': 1, 'is_user': False, 'person_id': None}]
        plan = plan_speaker_resolution([claim(quote="I'm Alex")], segments)
        assert [s.person_name for s in plan.suggestions] == ["Alex"]


def suggestion(speaker_id=1, name="Alex", quote="I'm Alex", confidence=0.9, segment_ids=("s1",)):
    return ResolvedSpeaker(
        speaker_id=speaker_id,
        person_name=name,
        evidence_quote=quote,
        confidence=confidence,
        segment_ids=segment_ids,
    )


@pytest.fixture
def stub_verifier(monkeypatch):
    """Stand in for ``utils.llm.speaker_verification`` without importing langchain.

    ``verify_suggestions`` imports the verifier lazily, so a module planted in
    ``sys.modules`` is what it will pick up. Yields a setter for the behaviour
    and a list recording every call, so the tests can assert both the verdict
    handling and that each suggestion really was put to the verifier.
    """
    module = ModuleType('utils.llm.speaker_verification')
    calls = []
    behaviour = {'fn': lambda **kwargs: SimpleNamespace(refuted=True, reason='default')}

    def verify_speaker_identification(segments, **kwargs):
        calls.append(kwargs)
        return behaviour['fn'](**kwargs)

    setattr(module, 'verify_speaker_identification', verify_speaker_identification)
    monkeypatch.setitem(sys.modules, 'utils.llm.speaker_verification', module)
    yield SimpleNamespace(calls=calls, behaviour=behaviour)


class TestVerifySuggestions:
    def test_an_unrefuted_suggestion_survives(self, stub_verifier):
        stub_verifier.behaviour['fn'] = lambda **kwargs: SimpleNamespace(refuted=False, reason='states own name')
        verified = verify_suggestions([segment("s1", "I'm Alex", speaker_id=1)], [suggestion()], None)
        assert [v.person_name for v in verified] == ["Alex"]

    def test_a_refuted_suggestion_is_dropped(self, stub_verifier):
        stub_verifier.behaviour['fn'] = lambda **kwargs: SimpleNamespace(refuted=True, reason='third party')
        verified = verify_suggestions([segment("s1", "I'm Alex", speaker_id=1)], [suggestion()], None)
        assert verified == []

    def test_a_verifier_exception_drops_that_suggestion(self, stub_verifier):
        def explode(**kwargs):
            raise RuntimeError('verifier down')

        stub_verifier.behaviour['fn'] = explode
        verified = verify_suggestions([segment("s1", "I'm Alex", speaker_id=1)], [suggestion()], None)
        assert verified == []

    def test_one_failure_does_not_refute_the_others(self, stub_verifier):
        def selective(**kwargs):
            if kwargs['speaker_id'] == 1:
                raise RuntimeError('verifier down')
            return SimpleNamespace(refuted=False, reason='addressed by name')

        stub_verifier.behaviour['fn'] = selective
        segments = [segment("s1", "I'm Alex", speaker_id=1), segment("s2", "I'm Ben", speaker_id=2)]
        verified = verify_suggestions(
            segments,
            [suggestion(speaker_id=1), suggestion(speaker_id=2, name="Ben", quote="I'm Ben", segment_ids=("s2",))],
            None,
        )
        assert [v.person_name for v in verified] == ["Ben"]

    def test_every_suggestion_is_put_to_the_verifier_with_its_evidence(self, stub_verifier):
        stub_verifier.behaviour['fn'] = lambda **kwargs: SimpleNamespace(refuted=False, reason='')
        segments = [segment("s1", "I'm Alex", speaker_id=1)]
        verify_suggestions(segments, [suggestion()], "Dana")
        assert stub_verifier.calls == [
            {'speaker_id': 1, 'person_name': "Alex", 'evidence_quote': "I'm Alex", 'user_name': "Dana"}
        ]


@pytest.fixture
def resolution_pass(monkeypatch):
    """Drive ``resolve_conversation_speakers`` with the I/O replaced.

    Stubs the two database modules it reaches for and captures the arguments
    ``apply_plan`` is handed, which is where the verified/unverified split
    becomes the difference between an enrolment and a suggestion.
    """
    module = sys.modules['utils.conversations.speaker_resolution']

    auth = ModuleType('database.auth')
    setattr(auth, 'get_user_name', lambda uid, use_default=True: 'Dana')
    users = ModuleType('database.users')
    setattr(users, 'get_people', lambda uid: [])
    monkeypatch.setitem(sys.modules, 'database.auth', auth)
    monkeypatch.setitem(sys.modules, 'database.users', users)

    captured = {}

    async def fake_apply_plan(uid, conversation_id, segments, assignments, suggestions, known):
        captured['assignments'] = list(assignments)
        captured['suggestions'] = list(suggestions)
        return module.SpeakerResolutionOutcome(
            assigned=[('person-1', resolved.person_name) for resolved in assignments],
            suggested=list(suggestions),
            enrolled=['person-1'] if assignments else [],
        )

    monkeypatch.setattr(module, 'apply_plan', fake_apply_plan)
    monkeypatch.setattr(
        module,
        'build_plan',
        lambda segments, user_name, known_names: module.ResolutionPlan(suggestions=(suggestion(),)),
    )
    return SimpleNamespace(captured=captured, module=module)


def run_resolution():
    import asyncio

    from utils.conversations.speaker_resolution import resolve_conversation_speakers

    conversation = SimpleNamespace(id='conv-1', transcript_segments=[segment("s1", "I'm Alex", speaker_id=1)])
    return asyncio.run(resolve_conversation_speakers('uid-1', conversation))


class TestResolutionPassEnrolsOnlyUnrefuted:
    def test_a_refuted_suggestion_is_never_assigned_or_enrolled(self, stub_verifier, resolution_pass):
        stub_verifier.behaviour['fn'] = lambda **kwargs: SimpleNamespace(refuted=True, reason='third party')
        outcome = run_resolution()
        assert resolution_pass.captured['assignments'] == []
        assert [s.person_name for s in resolution_pass.captured['suggestions']] == ["Alex"]
        assert outcome.assigned == []
        assert outcome.enrolled == []

    def test_an_unrefuted_suggestion_is_assigned_and_enrolled(self, stub_verifier, resolution_pass):
        stub_verifier.behaviour['fn'] = lambda **kwargs: SimpleNamespace(refuted=False, reason='states own name')
        outcome = run_resolution()
        assert [a.person_name for a in resolution_pass.captured['assignments']] == ["Alex"]
        assert resolution_pass.captured['suggestions'] == []
        assert outcome.enrolled == ['person-1']

    def test_a_broken_verifier_falls_back_to_suggestion_only(self, stub_verifier, resolution_pass):
        def explode(**kwargs):
            raise RuntimeError('verifier down')

        stub_verifier.behaviour['fn'] = explode
        outcome = run_resolution()
        assert resolution_pass.captured['assignments'] == []
        assert [s.person_name for s in resolution_pass.captured['suggestions']] == ["Alex"]
        assert outcome.enrolled == []


class TestVerificationBudget:
    """Enrolment is capped, so the calls that lead to it must be capped too."""

    def test_verification_is_bounded_per_conversation(self, stub_verifier):
        stub_verifier.behaviour['fn'] = lambda **kwargs: SimpleNamespace(refuted=False, reason='ok')
        many = [
            suggestion(speaker_id=i, name=f"Person{i}", confidence=0.9)
            for i in range(MAX_VERIFICATIONS_PER_CONVERSATION + 3)
        ]
        verified = verify_suggestions([segment("s1", "hello", speaker_id=1)], many, None)
        assert len(stub_verifier.calls) == MAX_VERIFICATIONS_PER_CONVERSATION
        assert len(verified) == MAX_VERIFICATIONS_PER_CONVERSATION

    def test_the_budget_is_spent_on_the_most_confident_first(self, stub_verifier):
        stub_verifier.behaviour['fn'] = lambda **kwargs: SimpleNamespace(refuted=False, reason='ok')
        weak = [suggestion(speaker_id=i, name=f"Weak{i}", confidence=0.51) for i in range(10)]
        strong = suggestion(speaker_id=99, name="Strong", confidence=0.99)
        verify_suggestions([segment("s1", "hello", speaker_id=1)], weak + [strong], None)
        assert 99 in [call['speaker_id'] for call in stub_verifier.calls]

    def test_suggestions_past_the_budget_are_not_verified(self, stub_verifier):
        stub_verifier.behaviour['fn'] = lambda **kwargs: SimpleNamespace(refuted=False, reason='ok')
        many = [
            suggestion(speaker_id=i, name=f"Person{i}", confidence=0.6)
            for i in range(MAX_VERIFICATIONS_PER_CONVERSATION + 2)
        ]
        verified = verify_suggestions([segment("s1", "hello", speaker_id=1)], many, None)
        verified_ids = {v.speaker_id for v in verified}
        assert len(verified_ids) == MAX_VERIFICATIONS_PER_CONVERSATION
