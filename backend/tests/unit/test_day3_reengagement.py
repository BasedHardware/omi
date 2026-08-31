"""Unit tests for utils.email.day3_reengagement: eligibility, copy, candidate
selection, and the send orchestration.

No network, no real Firestore: candidate selection is exercised against
``tests.unit.fixtures.generic_firestore_fake.FakeFirestore`` and outbound mail
is exercised against a patched ``httpx.post``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import utils.email.day3_reengagement as day3_reengagement
from models.conversation_enums import ConversationStatus
import utils.email.lifecycle as lifecycle
from tests.unit.fixtures.generic_firestore_fake import FakeFirestore
from utils.experiments import TREATMENT, existing_assignment
from utils.product_telemetry import set_product_telemetry_client_for_tests

NOW = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)
BASE_SIGNUP_AT = NOW - timedelta(hours=80)  # comfortably inside the (72h, 96h] send window


class _FakePosthog:
    def __init__(self):
        self.events: list[dict] = []

    def capture(self, **event):
        self.events.append(event)


@pytest.fixture(autouse=True)
def _posthog(monkeypatch):
    monkeypatch.setenv('POSTHOG_PROJECT_API_KEY', 'fake-key')
    fake = _FakePosthog()
    set_product_telemetry_client_for_tests(fake)
    yield fake
    set_product_telemetry_client_for_tests(None)


@pytest.fixture
def _resend(monkeypatch):
    """A working Resend + signing configuration, with httpx.post patched out."""
    monkeypatch.setenv('RESEND_API_KEY', 'fake-resend-key')
    monkeypatch.setenv('LIFECYCLE_EMAIL_SIGNING_SECRET', 'test-lifecycle-signing-secret-do-not-use-in-prod')
    # The API that serves /email/unsubscribe. Absent, no send may proceed.
    monkeypatch.setenv('BASE_API_URL', 'https://api.example.test')

    calls: list[dict] = []

    class _FakeResponse:
        status_code = 200

    def fake_post(url, *, json, headers, timeout):
        calls.append({'url': url, 'json': json, 'headers': headers})
        return _FakeResponse()

    monkeypatch.setattr(lifecycle.httpx, 'post', fake_post)
    # `post` is exposed so a test can swap the transport mid-scenario (e.g.
    # fail one run, succeed the next) and put this one back.
    return SimpleNamespace(calls=calls, post=fake_post)


# --- evaluate_candidate: eligibility partition and precedence ------------


def _facts(**overrides) -> day3_reengagement.CandidateFacts:
    base = dict(
        uid='uid-elig',
        signup_at=BASE_SIGNUP_AT,
        signup_os='macos',
        email='user@example.com',
        day_zero_conversation_count=1,
        conversations_after_day_zero=0,
        opted_out=False,
        already_sent=False,
    )
    base.update(overrides)
    return day3_reengagement.CandidateFacts(**base)


def test_every_macos_signup_os_spelling_is_eligible():
    """`signup_os` is the raw client header lowercased, not a canonical value.

    Only the *coarse* bucket goes through `_normalize_platform`'s alias table,
    so every key that table maps to 'desktop' can land in `signup_os` verbatim.
    Matching one literal would silently drop real macOS users — the same class
    of miss as querying `signup_platform == 'macos'`, which matches nothing at
    all.
    """
    for spelling in ('macos', 'mac', 'mac os x', 'MacOS', 'Mac OS X'):
        decision = day3_reengagement.evaluate_candidate(_facts(signup_os=spelling), now=NOW)
        assert decision.eligible, f'{spelling!r} is a macOS signup and must be eligible'


def test_bare_desktop_signup_os_is_not_assumed_to_be_macos():
    """Windows clients sending the coarse string write 'desktop' too, so it
    cannot be attributed to macOS. Excluded rather than guessed at."""
    decision = day3_reengagement.evaluate_candidate(_facts(signup_os='desktop'), now=NOW)
    assert not decision.eligible
    assert decision.reason == 'not_macos'


def test_eligible_candidate_with_day_zero_output_gets_personalized_branch():
    decision = day3_reengagement.evaluate_candidate(_facts(day_zero_conversation_count=3), now=NOW)
    assert decision.eligible is True
    assert decision.has_day_zero_output is True


def test_eligible_candidate_with_no_day_zero_output_is_deliberately_included():
    """Rule 4 of the pre-registration: zero day-0 output does NOT disqualify a
    candidate, it only selects the generic-tips copy branch. This guards
    against someone 'fixing' it into an extra eligibility gate, which the
    pre-registration explicitly says is not the design."""
    decision = day3_reengagement.evaluate_candidate(_facts(day_zero_conversation_count=0), now=NOW)
    assert decision.eligible is True
    assert decision.has_day_zero_output is False


@pytest.mark.parametrize(
    'overrides, expected_reason',
    [
        ({'signup_os': 'windows'}, 'not_macos'),
        ({'signup_os': None}, 'not_macos'),
        ({'signup_os': ''}, 'not_macos'),
        ({'signup_at': None}, 'no_signup_timestamp'),
        ({'conversations_after_day_zero': 1}, 'returned'),
        ({'already_sent': True}, 'already_sent'),
        ({'opted_out': True}, 'opted_out'),
        ({'email': None}, 'no_email'),
        ({'email': ''}, 'no_email'),
    ],
)
def test_each_rejection_reason_fires_on_its_own(overrides, expected_reason):
    decision = day3_reengagement.evaluate_candidate(_facts(**overrides), now=NOW)
    assert decision.eligible is False
    assert decision.reason == expected_reason


def test_a_user_with_a_conversation_after_day_zero_is_not_eligible():
    decision = day3_reengagement.evaluate_candidate(_facts(conversations_after_day_zero=1), now=NOW)
    assert decision.eligible is False
    assert decision.reason == 'returned'


def test_rejection_reasons_partition_by_fixed_precedence():
    """A candidate failing several rules at once is attributed to exactly the
    first rule in precedence order, so funnel counts never overlap."""
    facts = _facts(
        signup_os='windows',
        conversations_after_day_zero=1,
        already_sent=True,
        opted_out=True,
        email=None,
    )
    assert day3_reengagement.evaluate_candidate(facts, now=NOW).reason == 'not_macos'

    facts = _facts(conversations_after_day_zero=1, already_sent=True, opted_out=True, email=None)
    assert day3_reengagement.evaluate_candidate(facts, now=NOW).reason == 'returned'

    facts = _facts(already_sent=True, opted_out=True, email=None)
    assert day3_reengagement.evaluate_candidate(facts, now=NOW).reason == 'already_sent'

    facts = _facts(opted_out=True, email=None)
    assert day3_reengagement.evaluate_candidate(facts, now=NOW).reason == 'opted_out'


@pytest.mark.parametrize(
    'hours_ago, expected_reason_if_rejected',
    [
        (71.98, 'too_early'),  # just under 72h
        (72.0, None),  # exactly 72h: age < 72h is false, so not too_early
        (95.98, None),  # just under 96h: not too_late
        (96.0, 'too_late'),  # exactly 96h: age >= 96h
        (100.0, 'too_late'),
    ],
)
def test_72h_96h_window_boundaries(hours_ago, expected_reason_if_rejected):
    facts = _facts(signup_at=NOW - timedelta(hours=hours_ago))
    decision = day3_reengagement.evaluate_candidate(facts, now=NOW)
    if expected_reason_if_rejected is None:
        assert decision.eligible is True
    else:
        assert decision.eligible is False
        assert decision.reason == expected_reason_if_rejected


# --- build_reengagement_email: copy, escaping, branch selection -----------


def test_copy_escapes_a_hostile_display_name():
    content = day3_reengagement.build_reengagement_email(
        display_name='<script>alert(1)</script>',
        has_day_zero_output=True,
        day_zero_conversation_count=2,
        unsubscribe='https://omi.me/email/unsubscribe?token=abc',
    )
    assert '<script>' not in content['html']
    assert '&lt;script&gt;' in content['html']


def test_copy_has_no_parameter_that_could_carry_conversation_content():
    import inspect

    params = set(inspect.signature(day3_reengagement.build_reengagement_email).parameters)
    assert params == {'display_name', 'has_day_zero_output', 'day_zero_conversation_count', 'unsubscribe'}


def test_generic_branch_copy_for_no_day_zero_output():
    content = day3_reengagement.build_reengagement_email(
        display_name='Robin',
        has_day_zero_output=False,
        day_zero_conversation_count=0,
        unsubscribe='https://omi.me/email/unsubscribe?token=abc',
    )
    assert content['subject'] == 'Getting the most out of Omi'
    assert 'background' in content['html']


def test_personalized_branch_copy_for_day_zero_output():
    content = day3_reengagement.build_reengagement_email(
        display_name='Robin',
        has_day_zero_output=True,
        day_zero_conversation_count=4,
        unsubscribe='https://omi.me/email/unsubscribe?token=abc',
    )
    assert content['subject'] == 'Omi captured something on your first day'
    assert '4' in content['html']


# --- collect_day3_candidates: Firestore-facing plumbing --------------------


def _user_doc(signup_os: str, *, hours_ago: float = 80, opted_out: bool = False) -> dict:
    return {
        'signup_platform': 'desktop',
        'signup_os': signup_os,
        'signup_platform_at': NOW - timedelta(hours=hours_ago),
        'email_preferences': {'lifecycle_opted_out': opted_out},
    }


def _fake_get_user_from_uid(monkeypatch, emails: dict[str, str | None]):
    def fake(uid: str):
        if uid not in emails or emails[uid] is None:
            return None
        return {'email': emails[uid], 'display_name': uid}

    monkeypatch.setattr(day3_reengagement, 'get_user_from_uid', fake)


def test_collect_day3_candidates_maps_signup_os_and_excludes_off_window_and_off_platform(monkeypatch):
    docs = {
        'users/uid-mac': _user_doc('macos'),
        'users/uid-win': _user_doc('windows'),
        # coarse bucket 'mobile' never matches the query's signup_os=='desktop' filter.
        'users/uid-mobile': {
            'signup_platform': 'mobile',
            'signup_os': 'ios',
            'signup_platform_at': NOW - timedelta(hours=80),
        },
        # inside the desktop bucket but outside the 72-96h window.
        'users/uid-too-recent': _user_doc('macos', hours_ago=10),
    }
    _fake_get_user_from_uid(monkeypatch, {'uid-mac': 'mac@example.com', 'uid-win': 'win@example.com'})

    candidates = day3_reengagement.collect_day3_candidates(now=NOW, firestore_client=FakeFirestore(docs=docs))
    by_uid = {c.uid: c for c in candidates}

    assert set(by_uid) == {'uid-mac', 'uid-win'}
    # Granular signup_os is carried through verbatim, so
    # evaluate_candidate's unmodified `!= 'macos'` check still does the real
    # platform narrowing -- a Windows desktop signup fails it like any other
    # non-macOS signup.
    assert by_uid['uid-mac'].signup_os == 'macos'
    assert by_uid['uid-win'].signup_os == 'windows'
    assert day3_reengagement.evaluate_candidate(by_uid['uid-win'], now=NOW).reason == 'not_macos'


def _conversation(created_at, *, discarded=False, status='completed'):
    """A conversation document as the pipeline writes it.

    `status` and `discarded` are explicit in every fixture because they decide
    whether a document counts: an `in_progress` stub (written on every listen
    session start and reconnect) and a discarded empty session must not read as
    user output, while every other status must.
    """
    return {'created_at': created_at, 'discarded': discarded, 'status': status}


def test_collect_day3_candidates_caps_day_zero_count_and_bools_the_after_day_zero_check(monkeypatch):
    signup_at = NOW - timedelta(hours=80)
    docs = {'users/uid-prolific': _user_doc('macos')}
    for i in range(15):
        docs[f'users/uid-prolific/conversations/conv-{i}'] = _conversation(signup_at + timedelta(minutes=i))
    _fake_get_user_from_uid(monkeypatch, {'uid-prolific': 'prolific@example.com'})

    candidates = day3_reengagement.collect_day3_candidates(now=NOW, firestore_client=FakeFirestore(docs=docs))
    facts = next(c for c in candidates if c.uid == 'uid-prolific')

    # 15 real day-0 conversations, capped at 11 (the copy never needs more).
    assert facts.day_zero_conversation_count == 11
    assert facts.conversations_after_day_zero == 0


def test_collect_day3_candidates_flags_a_user_who_returned_after_day_zero(monkeypatch):
    signup_at = NOW - timedelta(hours=80)
    docs = {
        'users/uid-returned': _user_doc('macos'),
        'users/uid-returned/conversations/conv-0': _conversation(signup_at + timedelta(hours=1)),
        # 30h after signup is after the 24h day-0 window.
        'users/uid-returned/conversations/conv-after': _conversation(signup_at + timedelta(hours=30)),
    }
    _fake_get_user_from_uid(monkeypatch, {'uid-returned': 'returned@example.com'})

    candidates = day3_reengagement.collect_day3_candidates(now=NOW, firestore_client=FakeFirestore(docs=docs))
    facts = next(c for c in candidates if c.uid == 'uid-returned')

    assert facts.conversations_after_day_zero == 1
    assert day3_reengagement.evaluate_candidate(facts, now=NOW).reason == 'returned'


def test_in_progress_stubs_and_discards_do_not_count_as_coming_back(monkeypatch):
    """The whole target cohort depends on this.

    The desktop listen socket writes an `in_progress` conversation on every
    session start and reconnect, so a Mac that is merely still switched on --
    launch-at-login, wake from sleep, socket reconnect -- produces documents
    with fresh `created_at` values and no content. Counting those as "the user
    came back" is the same launch-at-login contamination that disqualified
    `last_active_at`, and it would leave the experiment enrolling only users
    whose machines are off.
    """
    signup_at = NOW - timedelta(hours=80)
    after_day_zero = signup_at + timedelta(hours=30)
    docs = {
        'users/uid-idle': _user_doc('macos'),
        # A live-but-empty listen session, and an empty session that was
        # discarded at the end. Neither is user output.
        'users/uid-idle/conversations/conv-stub': _conversation(after_day_zero, status='in_progress'),
        'users/uid-idle/conversations/conv-discarded': _conversation(after_day_zero, discarded=True),
    }
    _fake_get_user_from_uid(monkeypatch, {'uid-idle': 'idle@example.com'})

    candidates = day3_reengagement.collect_day3_candidates(now=NOW, firestore_client=FakeFirestore(docs=docs))
    facts = next(c for c in candidates if c.uid == 'uid-idle')

    assert facts.conversations_after_day_zero == 0
    assert facts.day_zero_conversation_count == 0
    assert day3_reengagement.evaluate_candidate(facts, now=NOW).eligible


@pytest.mark.parametrize('status', ['processing', 'merging', 'completed', 'failed'])
def test_every_ended_status_counts_as_real_output(monkeypatch, status):
    """The mirror-image failure, and the more damaging one for this cohort.

    Tightening to `status == 'completed'` looks obviously safer and silently
    erases real conversations: `_store_deferred_conversation` persists a
    desktop capture for a freemium/Neo user with `deferred = True` and
    `status = processing`, and it stays that way until the user opens it. Those
    users are exactly who this experiment targets, so treating `processing` as
    "produced nothing, never came back" would mail the wrong branch to people
    who did come back.
    """
    signup_at = NOW - timedelta(hours=80)
    docs = {
        f'users/uid-{status}': _user_doc('macos'),
        f'users/uid-{status}/conversations/conv-day-zero': _conversation(signup_at + timedelta(hours=2), status=status),
        f'users/uid-{status}/conversations/conv-later': _conversation(signup_at + timedelta(hours=30), status=status),
    }
    _fake_get_user_from_uid(monkeypatch, {f'uid-{status}': 'user@example.com'})

    candidates = day3_reengagement.collect_day3_candidates(now=NOW, firestore_client=FakeFirestore(docs=docs))
    facts = next(c for c in candidates if c.uid == f'uid-{status}')

    assert facts.day_zero_conversation_count == 1, f'{status} is a real conversation, not a stub'
    assert facts.conversations_after_day_zero == 1
    assert day3_reengagement.evaluate_candidate(facts, now=NOW).reason == 'returned'


def test_the_only_status_that_does_not_count_is_the_listen_stub():
    """Pins the allow-list against the enum, so a new `ConversationStatus`
    forces a decision here instead of being silently excluded."""
    assert set(day3_reengagement.ENDED_CONVERSATION_STATUSES) == {status.value for status in ConversationStatus} - {
        ConversationStatus.in_progress.value
    }


def test_collect_day3_candidates_reads_opt_out_already_sent_and_email(monkeypatch):
    docs = {
        'users/uid-optout': _user_doc('macos', opted_out=True),
        'users/uid-sent': _user_doc('macos'),
        f'users/uid-sent/lifecycle_email_sends/{day3_reengagement.CAMPAIGN}': {'delivered': True},
        'users/uid-noemail': _user_doc('macos'),
    }
    _fake_get_user_from_uid(
        monkeypatch, {'uid-optout': 'a@example.com', 'uid-sent': 'b@example.com', 'uid-noemail': None}
    )

    candidates = day3_reengagement.collect_day3_candidates(now=NOW, firestore_client=FakeFirestore(docs=docs))
    by_uid = {c.uid: c for c in candidates}

    assert by_uid['uid-optout'].opted_out is True
    assert by_uid['uid-sent'].already_sent is True
    assert by_uid['uid-noemail'].email is None


# --- run_day3_reengagement: orchestration ----------------------------------


def _eligible_facts(uid: str, **overrides) -> day3_reengagement.CandidateFacts:
    base = dict(
        uid=uid,
        signup_at=BASE_SIGNUP_AT,
        signup_os='macos',
        email=f'{uid}@example.com',
        day_zero_conversation_count=2,
        conversations_after_day_zero=0,
        opted_out=False,
        already_sent=False,
    )
    base.update(overrides)
    return day3_reengagement.CandidateFacts(**base)


def test_closed_authority_performs_no_user_work(_resend):
    summary = day3_reengagement.run_day3_reengagement(
        candidates=[_eligible_facts('uid-closed')],
        now=NOW,
        authority=day3_reengagement.Day3Authority(enabled=False),
        display_name_for=lambda uid: None,
        firestore_client=FakeFirestore(),
    )
    assert summary.considered == 0
    assert summary.sent == 0
    assert _resend.calls == []


def test_failed_enrollment_prevents_a_send(_resend):
    class _RaisingFirestore(FakeFirestore):
        def collection(self, path):
            raise RuntimeError('firestore unavailable')

    summary = day3_reengagement.run_day3_reengagement(
        candidates=[_eligible_facts('uid-enroll-fails')],
        now=NOW,
        authority=day3_reengagement.Day3Authority(enabled=True),
        display_name_for=lambda uid: None,
        firestore_client=_RaisingFirestore(),
    )
    assert summary.sent == 0
    assert summary.failed == 1
    assert _resend.calls == []


def test_eligible_treatment_candidate_is_sent_with_working_unsubscribe(_resend):
    db = FakeFirestore(docs={'users/uid-happy': {}})
    summary = day3_reengagement.run_day3_reengagement(
        candidates=[_eligible_facts('uid-happy', day_zero_conversation_count=3)],
        now=NOW,
        authority=day3_reengagement.Day3Authority(enabled=True),
        display_name_for=lambda uid: 'Robin',
        firestore_client=db,
        treatment_share=1.0,
    )
    assert summary.sent == 1
    assert len(_resend.calls) == 1
    payload = _resend.calls[0]['json']
    assert payload['to'] == ['uid-happy@example.com']
    assert 'List-Unsubscribe' in payload['headers']
    assert 'Robin' in payload['html']
    assert '3' in payload['html']


def test_control_arm_candidate_is_enrolled_and_never_sent(_resend):
    db = FakeFirestore(docs={'users/uid-holdout': {}})
    summary = day3_reengagement.run_day3_reengagement(
        candidates=[_eligible_facts('uid-holdout')],
        now=NOW,
        authority=day3_reengagement.Day3Authority(enabled=True),
        display_name_for=lambda uid: None,
        firestore_client=db,
        treatment_share=0.0,
    )
    assert summary.enrolled_control == 1
    assert summary.sent == 0
    assert _resend.calls == []
    assignment = existing_assignment(day3_reengagement.EXPERIMENT_ID, 'uid-holdout', firestore_client=db)
    assert assignment is not None  # the holdout is still visible in the roster


def test_opt_out_between_selection_and_send_suppresses_the_email(_resend):
    """The candidate snapshot (evaluated at selection time) says not opted
    out; the live user doc says otherwise by send time. The send must be
    suppressed, the user must stay enrolled, and delivery must record
    'suppressed' -- this is the live re-check `send_lifecycle_email` performs
    on every send, independent of the selection-time snapshot."""
    db = FakeFirestore(docs={'users/uid-lateout': {'email_preferences': {'lifecycle_opted_out': True}}})
    summary = day3_reengagement.run_day3_reengagement(
        candidates=[_eligible_facts('uid-lateout', opted_out=False)],
        now=NOW,
        authority=day3_reengagement.Day3Authority(enabled=True),
        display_name_for=lambda uid: None,
        firestore_client=db,
        treatment_share=1.0,
    )
    assert summary.sent == 0
    assert summary.enrolled_treatment == 1
    assert summary.ineligible.get('opted_out_at_send') == 1
    assert _resend.calls == []

    assignment = existing_assignment(day3_reengagement.EXPERIMENT_ID, 'uid-lateout', firestore_client=db)
    assert assignment is not None
    assert assignment['variant'] == TREATMENT
    assert assignment['delivery']['outcome'] == 'suppressed'


def test_send_claim_blocks_a_second_send_after_a_crashed_first_attempt(_resend):
    """The claim ledger, not enrollment idempotency, is what is under test
    here: enrollment happens fresh (no prior assignment), but a claim already
    exists for this (uid, campaign) -- simulating a prior run that claimed
    the send slot and then crashed before finishing. The second run must not
    re-send."""
    db = FakeFirestore()
    day3_reengagement.claim_lifecycle_send('uid-crash-retry', day3_reengagement.CAMPAIGN, firestore_client=db)

    summary = day3_reengagement.run_day3_reengagement(
        candidates=[_eligible_facts('uid-crash-retry')],
        now=NOW,
        authority=day3_reengagement.Day3Authority(enabled=True),
        display_name_for=lambda uid: None,
        firestore_client=db,
        treatment_share=1.0,
    )
    assert summary.enrolled_treatment == 1
    assert summary.sent == 0
    assert summary.ineligible.get('send_already_claimed') == 1
    assert _resend.calls == []


def test_rerunning_with_the_same_candidate_does_not_double_send(_resend):
    """End-to-end idempotency across two job runs.

    The second run still re-enrolls (idempotently, same variant) and still
    reaches the claim -- the standing claim from the first run is what stops
    it. Deliberately *not* an early return on "already enrolled": see
    `test_a_treatment_user_whose_send_failed_is_retried_on_the_next_run`.
    """
    db = FakeFirestore(docs={'users/uid-two-runs': {}})
    facts = _eligible_facts('uid-two-runs')

    first = day3_reengagement.run_day3_reengagement(
        candidates=[facts],
        now=NOW,
        authority=day3_reengagement.Day3Authority(enabled=True),
        display_name_for=lambda uid: None,
        firestore_client=db,
        treatment_share=1.0,
    )
    second = day3_reengagement.run_day3_reengagement(
        candidates=[facts],
        now=NOW,
        authority=day3_reengagement.Day3Authority(enabled=True),
        display_name_for=lambda uid: None,
        firestore_client=db,
        treatment_share=1.0,
    )

    assert first.sent == 1
    assert second.sent == 0
    assert second.ineligible.get('already_enrolled') == 1
    assert second.ineligible.get('send_already_claimed') == 1, 'the ledger, not enrollment, is the lock'
    assert len(_resend.calls) == 1


def test_a_failure_before_the_provider_releases_the_claim(_resend, monkeypatch):
    """Nothing was sent, so holding the claim would be a permanent miss.

    `display_name_for` reaches Firebase Auth after the claim is taken. If that
    throws and the claim stands, the Cloud Run retry sees it, skips, and leaves
    a treatment user enrolled and never mailed — converting a transient blip
    into exactly the permanent non-delivery that removing the
    "already enrolled" early return was meant to fix.
    """
    db = FakeFirestore(docs={'users/uid-auth-blip': {}})
    facts = _eligible_facts('uid-auth-blip')

    def exploding_display_name(uid):
        raise RuntimeError('firebase auth unavailable')

    first = day3_reengagement.run_day3_reengagement(
        candidates=[facts],
        now=NOW,
        authority=day3_reengagement.Day3Authority(enabled=True),
        display_name_for=exploding_display_name,
        firestore_client=db,
        treatment_share=1.0,
    )
    assert first.failed == 1
    assert _resend.calls == []

    second = day3_reengagement.run_day3_reengagement(
        candidates=[facts],
        now=NOW,
        authority=day3_reengagement.Day3Authority(enabled=True),
        display_name_for=lambda uid: None,
        firestore_client=db,
        treatment_share=1.0,
    )

    assert second.sent == 1, 'a pre-provider failure must not become a permanent skip'
    assert len(_resend.calls) == 1


def test_an_unknown_delivery_outcome_keeps_the_claim(_resend, monkeypatch):
    """The opposite rule, and why the two cannot share one except clause.

    A read timeout means the request reached Resend and the response was never
    seen. The message may well have been delivered, so the claim must STAND: a
    duplicate unsolicited email is unrecoverable, a miss is not.
    """
    db = FakeFirestore(docs={'users/uid-timeout': {}})
    facts = _eligible_facts('uid-timeout')

    def read_timeout(url, *, json, headers, timeout):
        raise lifecycle.httpx.ReadTimeout('response never read')

    monkeypatch.setattr(lifecycle.httpx, 'post', read_timeout)
    first = day3_reengagement.run_day3_reengagement(
        candidates=[facts],
        now=NOW,
        authority=day3_reengagement.Day3Authority(enabled=True),
        display_name_for=lambda uid: None,
        firestore_client=db,
        treatment_share=1.0,
    )
    assert first.failed == 1

    monkeypatch.setattr(lifecycle.httpx, 'post', _resend.post)
    second = day3_reengagement.run_day3_reengagement(
        candidates=[facts],
        now=NOW,
        authority=day3_reengagement.Day3Authority(enabled=True),
        display_name_for=lambda uid: None,
        firestore_client=db,
        treatment_share=1.0,
    )

    assert second.sent == 0, 'an unknown outcome must not be retried into a possible duplicate'
    assert second.ineligible.get('send_already_claimed') == 1
    assert _resend.calls == []


def test_a_treatment_user_whose_send_failed_is_retried_on_the_next_run(_resend, monkeypatch):
    """Enrollment is the analysis lock; the claim ledger is the send-once lock.

    Conflating them looks like idempotency and is actually a permanent send
    failure: a treatment user whose first attempt died after enrolling would be
    skipped by every later run and never mailed, while still counting as
    treated -- silently diluting the very effect the experiment measures.
    """
    db = FakeFirestore(docs={'users/uid-retry': {}})
    facts = _eligible_facts('uid-retry')

    # First run: the provider is unreachable, which is a definitive
    # non-delivery, so the claim is released.
    def unreachable(url, *, json, headers, timeout):
        raise lifecycle.httpx.ConnectError('provider unreachable')

    monkeypatch.setattr(lifecycle.httpx, 'post', unreachable)
    first = day3_reengagement.run_day3_reengagement(
        candidates=[facts],
        now=NOW,
        authority=day3_reengagement.Day3Authority(enabled=True),
        display_name_for=lambda uid: None,
        firestore_client=db,
        treatment_share=1.0,
    )
    assert first.sent == 0
    assert first.failed == 1
    assert first.enrolled_treatment == 1

    # Second run: same user, provider healthy again. They must be mailed.
    monkeypatch.setattr(lifecycle.httpx, 'post', _resend.post)
    second = day3_reengagement.run_day3_reengagement(
        candidates=[facts],
        now=NOW,
        authority=day3_reengagement.Day3Authority(enabled=True),
        display_name_for=lambda uid: None,
        firestore_client=db,
        treatment_share=1.0,
    )

    assert second.sent == 1, 'a failed send must be retried, not permanently skipped'
    assert second.enrolled_treatment == 0, 'the arm assignment is unchanged, not re-counted'
    assert len(_resend.calls) == 1
