"""EXP-001: the day-3 re-engagement email, and the experiment around it.

Contract: ``backend/docs/experiments/EXP-001-day3-reengagement.md``. That file
is pre-registered and this module must not drift from it — in particular the
eligibility predicate and the 50/50 standing split.

The shape here is deliberately boring: pure decision functions that take plain
data, and one orchestration function that does the I/O. The reason is that the
interesting failures of a batch mailer are all decision failures — mailing
somebody twice, mailing somebody who opted out, mailing the wrong cohort — and
those are only cheap to test when the decision does not need Firestore.

## The ordering that matters

Enroll **before** sending, and treat a failed enrollment as a hard stop.

An unsent treatment email is one lost data point. A sent-but-unenrolled email
is a user who got the treatment while counting as control for the life of the
experiment, which biases the result in the direction that makes the email look
worse and cannot be detected afterwards. The asymmetry is total, so the order
is not negotiable.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Iterable, Optional

from google.cloud.firestore_v1 import FieldFilter

from database._client import db
from database.auth import get_user_from_uid
from database.conversations import conversations_collection
from database.firestore_index_registry import (
    DAY3_REENGAGEMENT_DAY_ZERO_CONVERSATIONS_QUERY,
    DAY3_REENGAGEMENT_RETURNED_CONVERSATIONS_QUERY,
    DAY3_REENGAGEMENT_SIGNUP_COHORT_QUERY,
)
from models.conversation_enums import ConversationStatus
from utils.email.lifecycle import (
    LifecycleEmailDeliveryUnknown,
    LifecycleEmailNotConfigured,
    LifecycleEmailSuppressed,
    claim_lifecycle_send,
    is_lifecycle_opted_out,
    release_lifecycle_send,
    send_lifecycle_email,
    unsubscribe_url,
)
from utils.experiments import TREATMENT, enroll, record_delivery

logger = logging.getLogger(__name__)

EXPERIMENT_ID = 'EXP-001-day3-reengagement'
CAMPAIGN = 'day3_reengagement'
PRE_REGISTRATION = 'backend/docs/experiments/EXP-001-day3-reengagement.md'

ENABLED_ENV = 'DAY3_REENGAGEMENT_EMAIL_ENABLED'
KILL_SWITCH_ENV = 'DAY3_REENGAGEMENT_EMAIL_KILL_SWITCH'

# Day 0 is the 24h from first authenticated request. The send window is 72-96h
# after that, so exactly one signup-day cohort is eligible per daily run and a
# missed run does not silently double up the next day.
DAY_ZERO_HOURS = 24
SEND_WINDOW_START_HOURS = 72
SEND_WINDOW_END_HOURS = 96

MAX_USERS_PER_RUN = 500

# `signup_os` is the `X-App-Platform` header lowercased, NOT a canonical value:
# `_normalize_platform` in `database/users.py` only canonicalizes the *coarse*
# bucket ('desktop'/'mobile'/'web'), and every key its alias table maps to
# 'desktop' can therefore land here verbatim. So an `== 'macos'` test silently
# drops real macOS users whose client sent 'mac' or 'Mac OS X'.
#
# A literal 'desktop' is deliberately excluded: that value is also what a
# Windows client sending the coarse string writes, so it cannot be attributed
# to macOS. Those users are counted as `not_macos` rather than guessed at.
MACOS_SIGNUP_OS_VALUES = frozenset({'macos', 'mac', 'mac os x'})

# A conversation counts as user output once its session has ended, whatever the
# enrichment did next. Everything except `in_progress`, which is the stub the
# desktop listen socket writes on every session start and reconnect.
#
# Spelled as an explicit allow-list rather than `!= 'in_progress'` because
# Firestore serves an `in` filter from the same composite index as the
# surrounding equality and range, and `!=` does not. Derived from
# `ConversationStatus` so a new status is a visible decision here, not a silent
# omission.
ENDED_CONVERSATION_STATUSES = tuple(
    status.value for status in ConversationStatus if status is not ConversationStatus.in_progress
)


@dataclass(frozen=True)
class Day3Authority:
    """Both switches default closed: a deployed job is dark until opened."""

    enabled: bool = False
    kill_switch_active: bool = False

    @property
    def may_send(self) -> bool:
        return self.enabled and not self.kill_switch_active


def authority_from_environment() -> Day3Authority:
    truthy = {'1', 'true', 'yes', 'on'}
    return Day3Authority(
        enabled=os.getenv(ENABLED_ENV, 'false').casefold() in truthy,
        kill_switch_active=os.getenv(KILL_SWITCH_ENV, 'false').casefold() in truthy,
    )


@dataclass(frozen=True)
class CandidateFacts:
    """Everything the eligibility decision needs, as plain data."""

    uid: str
    signup_at: Optional[datetime]
    signup_os: Optional[str]
    email: Optional[str]
    day_zero_conversation_count: int
    conversations_after_day_zero: int
    opted_out: bool
    already_sent: bool


@dataclass(frozen=True)
class EligibilityDecision:
    eligible: bool
    reason: str
    has_day_zero_output: bool = False


def evaluate_candidate(facts: CandidateFacts, *, now: datetime) -> EligibilityDecision:
    """Apply the pre-registered predicate. Pure; order matters for the funnel.

    Reasons are returned in a fixed precedence so the funnel counts are a
    partition rather than an overlapping tally — each candidate is attributed
    to exactly the first rule it fails.
    """
    if (facts.signup_os or '').casefold() not in MACOS_SIGNUP_OS_VALUES:
        return EligibilityDecision(False, 'not_macos')
    if facts.signup_at is None:
        return EligibilityDecision(False, 'no_signup_timestamp')

    age = now - facts.signup_at
    if age < timedelta(hours=SEND_WINDOW_START_HOURS):
        return EligibilityDecision(False, 'too_early')
    if age >= timedelta(hours=SEND_WINDOW_END_HOURS):
        return EligibilityDecision(False, 'too_late')

    # Rule 3 of the pre-registration: a VALUE signal, not `last_active_at` and
    # not `App Launched` — both are kept warm by launch-at-login and would
    # exclude precisely the disengaged-but-still-running users this targets.
    if facts.conversations_after_day_zero > 0:
        return EligibilityDecision(False, 'returned')

    if facts.already_sent:
        return EligibilityDecision(False, 'already_sent')
    if facts.opted_out:
        return EligibilityDecision(False, 'opted_out')
    if not facts.email:
        return EligibilityDecision(False, 'no_email')

    return EligibilityDecision(True, 'eligible', has_day_zero_output=facts.day_zero_conversation_count > 0)


def build_reengagement_email(
    *, display_name: Optional[str], has_day_zero_output: bool, day_zero_conversation_count: int, unsubscribe: str
) -> dict[str, str]:
    """Two branches, one arm. See the pre-registration for why they are pooled.

    Copy is intentionally plain and short. Everything user-supplied is escaped;
    no conversation content is interpolated — a count is a count, and putting a
    transcript-derived title into an email is a privacy decision nobody has
    made.
    """
    greeting = f'Hi {_escape(display_name)},' if display_name else 'Hi,'
    if has_day_zero_output:
        subject = 'Omi captured something on your first day'
        body = (
            f'<p>{greeting}</p>'
            f'<p>Omi picked up <strong>{day_zero_conversation_count}</strong> '
            f'{"conversation" if day_zero_conversation_count == 1 else "conversations"} '
            'on your first day, and they are still waiting for you.</p>'
            '<p>Most of what Omi is useful for shows up after a few days of running — '
            'it needs enough context to start connecting things.</p>'
            '<p><a href="https://omi.me/app">Open Omi</a></p>'
        )
    else:
        subject = 'Getting the most out of Omi'
        body = (
            f'<p>{greeting}</p>'
            '<p>You installed Omi a few days ago. It works best running quietly in the '
            'background — the useful part is what it notices while you are busy.</p>'
            '<p>Two things that help most:</p>'
            '<ul>'
            '<li>Leave monitoring on for a full working day.</li>'
            '<li>Allow notifications, so Omi can tell you when it finds something.</li>'
            '</ul>'
            '<p><a href="https://omi.me/app">Open Omi</a></p>'
        )
    footer = (
        f'<hr><p style="color:#888;font-size:12px">'
        f'You are receiving this because you created an Omi account. '
        f'<a href="{_escape(unsubscribe)}">Unsubscribe</a>.</p>'
    )
    return {'subject': subject, 'html': f'{body}{footer}'}


def _escape(value: Optional[str]) -> str:
    if not value:
        return ''
    return (
        value.replace('&', '&amp;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
        .replace('"', '&quot;')
        .replace("'", '&#39;')
    )


_LIFECYCLE_SEND_LEDGER_COLLECTION = 'lifecycle_email_sends'


def _has_existing_send(uid: str, client: Any) -> bool:
    """Whether ``CAMPAIGN`` was already claimed/sent for ``uid``.

    Reads the same ``users/{uid}/lifecycle_email_sends/{campaign}`` document
    ``claim_lifecycle_send``/``release_lifecycle_send`` (``utils.email.lifecycle``)
    write, without claiming it. This is the pre-filter that keeps a user who
    was already mailed out of a later day's candidate set; it is not the
    double-send guard itself — that atomicity comes from ``claim_lifecycle_send``
    at send time, unaffected by this read.

    Fails closed: an unreadable ledger is treated as "already sent", because a
    duplicate lifecycle send is worse than a skipped candidate.
    """
    try:
        snapshot = (
            client.collection('users')
            .document(uid)
            .collection(_LIFECYCLE_SEND_LEDGER_COLLECTION)
            .document(CAMPAIGN)
            .get()
        )
    except Exception:
        logger.exception('day3 re-engagement: send-ledger read failed uid=%s', uid)
        return True
    return bool(getattr(snapshot, 'exists', False))


def _conversation_signals(uid: str, signup_at: Optional[datetime], *, client: Any) -> tuple[int, bool]:
    """Day-0 output count (capped) and whether the user returned after day 0.

    ## What counts as a conversation here

    Both probes require ``discarded == False`` and a status in
    ``ENDED_CONVERSATION_STATUSES`` — that is, anything except ``in_progress``.
    Both halves are load-bearing, and both directions of getting it wrong hurt.

    **Too loose.** The desktop listen socket writes an ``in_progress``
    conversation document on every session start and reconnect, so a Mac that
    is merely *running* — launch-at-login, wake from sleep, socket reconnect —
    mints documents with fresh ``created_at`` values and no content. Counting
    those would make "has the user come back?" true for every install still
    switched on, which is exactly the contamination that disqualified
    ``last_active_at`` as the eligibility signal.

    **Too strict.** ``status == 'completed'`` looks like the obvious tightening
    and silently deletes real output: ``_store_deferred_conversation`` persists
    a desktop conversation for a freemium/Neo user with ``deferred = True`` and
    ``status = processing``, and it stays there until the user opens it. Those
    are recorded conversations that are permanently not ``completed``, and they
    belong to precisely the new-macOS-user cohort this experiment targets —
    requiring ``completed`` would report those users as having produced nothing
    and never returned.

    Note this is deliberately *not* ``get_conversations``' default, which
    filters ``discarded`` only and leaves ``in_progress`` stubs in.

    The "after day 0" check uses ``limit(1)``: it is a boolean, so streaming
    the whole set would be pure waste. The day-0 count is capped at 11 because
    the copy only ever reports "N conversations" for small N.

    Without a ``signup_at`` neither can be windowed; both come back
    zero/False and ``evaluate_candidate`` rejects on ``no_signup_timestamp``
    before either value is ever read.
    """
    if signup_at is None:
        return 0, False

    day_zero_end = signup_at + timedelta(hours=DAY_ZERO_HOURS)
    conversations_ref = client.collection('users').document(uid).collection(conversations_collection)
    real_conversation = {'discarded': False, 'statuses': list(ENDED_CONVERSATION_STATUSES)}

    # Built through the registered specs rather than chained by hand. Beyond
    # keeping the declared index and the served query in one place, the
    # coverage checker is AST-only: a hand-chained `.where()` on a collection
    # named by an imported constant has no resolvable collection group, so it
    # cannot be matched to its spec and lands as an unsupported shape.
    day_zero_query = DAY3_REENGAGEMENT_DAY_ZERO_CONVERSATIONS_QUERY.build(
        conversations_ref,
        {**real_conversation, 'start': signup_at, 'end': day_zero_end},
        field_filter_factory=FieldFilter,
    ).limit(11)
    day_zero_count = sum(1 for _ in day_zero_query.stream())

    after_query = DAY3_REENGAGEMENT_RETURNED_CONVERSATIONS_QUERY.build(
        conversations_ref,
        {**real_conversation, 'start': day_zero_end},
        field_filter_factory=FieldFilter,
    ).limit(1)
    returned = any(True for _ in after_query.stream())

    return day_zero_count, returned


def collect_day3_candidates(
    *,
    now: datetime,
    firestore_client: Any | None = None,
    limit: int = MAX_USERS_PER_RUN,
) -> list[CandidateFacts]:
    """The Firestore I/O ``run_day3_reengagement`` needs: one day's signup cohort,
    resolved into plain ``CandidateFacts``.

    ## Two fields, and why the obvious query matches nothing

    ``record_user_platform`` (``database/users.py``) writes **two** platform
    fields with different granularity: ``signup_platform`` gets the *coarse*
    bucket — ``'desktop'`` for both macOS and Windows — and ``signup_os`` keeps
    the granular OS string. So the obvious query, ``signup_platform ==
    'macos'``, matches zero documents forever and silently: the experiment
    would enroll nobody and nothing would say why.

    The Firestore filter therefore uses the value actually written
    (``'desktop'``), which is as narrow as an indexed equality can get here,
    and the macOS narrowing happens in ``evaluate_candidate`` against
    ``signup_os``. A Windows signup is fetched and then rejected as
    ``'not_macos'`` — slightly wasteful per run, but bounded by the same page
    limit and honest about where the decision lives.

    Note that ``signup_os`` is **not** canonicalized (see
    ``MACOS_SIGNUP_OS_VALUES``): only the coarse bucket goes through the alias
    table, so the raw header value lands here verbatim and matching a single
    literal would drop real macOS users.
    """
    client = firestore_client or db
    window_start = now - timedelta(hours=SEND_WINDOW_END_HOURS)
    window_end = now - timedelta(hours=SEND_WINDOW_START_HOURS)

    query = (
        DAY3_REENGAGEMENT_SIGNUP_COHORT_QUERY.build(
            client.collection('users'),
            {'signup_platform': 'desktop', 'start': window_start, 'end': window_end},
            field_filter_factory=FieldFilter,
        )
        .order_by('signup_platform_at')
        .limit(limit)
    )

    candidates: list[CandidateFacts] = []
    for snapshot in query.stream():
        uid = snapshot.id
        data = snapshot.to_dict() or {}
        signup_at = data.get('signup_platform_at')

        day_zero_count, returned_after_day_zero = _conversation_signals(uid, signup_at, client=client)
        auth_user = get_user_from_uid(uid) or {}

        candidates.append(
            CandidateFacts(
                uid=uid,
                signup_at=signup_at,
                signup_os=data.get('signup_os'),
                email=auth_user.get('email'),
                day_zero_conversation_count=day_zero_count,
                conversations_after_day_zero=1 if returned_after_day_zero else 0,
                opted_out=is_lifecycle_opted_out(uid, firestore_client=client),
                already_sent=_has_existing_send(uid, client),
            )
        )
    return candidates


@dataclass
class RunSummary:
    """Content-free receipt. Counts only — never uids, never email addresses."""

    considered: int = 0
    enrolled_treatment: int = 0
    enrolled_control: int = 0
    sent: int = 0
    failed: int = 0
    ineligible: dict[str, int] = field(default_factory=dict)

    def note_ineligible(self, reason: str) -> None:
        self.ineligible[reason] = self.ineligible.get(reason, 0) + 1


def run_day3_reengagement(
    *,
    candidates: Iterable[CandidateFacts],
    now: datetime,
    authority: Day3Authority,
    display_name_for: Callable[[str], Optional[str]],
    firestore_client: Any | None = None,
    treatment_share: float = 0.5,
) -> RunSummary:
    """Enroll every eligible candidate and send to the treatment arm."""
    summary = RunSummary()
    if not authority.may_send:
        logger.info('day3 re-engagement: closed by authority; no user work performed')
        return summary

    for facts in candidates:
        summary.considered += 1
        decision = evaluate_candidate(facts, now=now)
        if not decision.eligible:
            summary.note_ineligible(decision.reason)
            continue

        # Enroll first. A send without an enrollment silently corrupts the
        # control arm; an enrollment without a send is one lost data point.
        enrollment = enroll(
            experiment_id=EXPERIMENT_ID,
            uid=facts.uid,
            treatment_share=treatment_share,
            eligibility={
                'has_day_zero_output': decision.has_day_zero_output,
                'day_zero_conversation_count': facts.day_zero_conversation_count,
                'signup_os': facts.signup_os,
            },
            source=CAMPAIGN,
            firestore_client=firestore_client,
        )
        if enrollment is None:
            summary.failed += 1
            continue

        if enrollment.newly_enrolled:
            if enrollment.variant == TREATMENT:
                summary.enrolled_treatment += 1
            else:
                summary.enrolled_control += 1
        else:
            summary.note_ineligible('already_enrolled')

        if enrollment.variant != TREATMENT:
            # The holdout is enrolled and then deliberately left alone. Its
            # visibility in analysis comes from the enrollment event, not from
            # anything the user does.
            continue

        # The claim ledger is the send-once lock; enrollment is the *analysis*
        # lock, and the two must not be conflated. Returning early on
        # `not newly_enrolled` would look like idempotency and actually be a
        # permanent send failure: a treatment user whose first attempt died
        # between enrolling and delivering (a provider blip, a killed job, a
        # released claim after a definitive rejection) would be skipped by
        # every later run and never mailed, while still counting as treated.
        # `claim_lifecycle_send`'s atomic create() is what prevents duplicates
        # here, and it works whether or not this is the first attempt.
        if not claim_lifecycle_send(facts.uid, CAMPAIGN, firestore_client=firestore_client):
            summary.note_ineligible('send_already_claimed')
            continue

        try:
            # Inside the try: `unsubscribe_url` raises when the signing secret
            # or BASE_API_URL is missing, and that must release the claim it
            # would otherwise strand.
            content = build_reengagement_email(
                display_name=display_name_for(facts.uid),
                has_day_zero_output=decision.has_day_zero_output,
                day_zero_conversation_count=facts.day_zero_conversation_count,
                unsubscribe=unsubscribe_url(facts.uid),
            )
            send_lifecycle_email(
                uid=facts.uid,
                campaign=CAMPAIGN,
                to_email=facts.email or '',
                subject=content['subject'],
                html=content['html'],
                firestore_client=firestore_client,
            )
        except LifecycleEmailSuppressed:
            # Opted out between selection and send. Correct outcome, not an
            # error: the user stays enrolled and is analyzed as treatment
            # (intention-to-treat).
            release_lifecycle_send(facts.uid, CAMPAIGN, firestore_client=firestore_client)
            record_delivery(
                experiment_id=EXPERIMENT_ID, uid=facts.uid, outcome='suppressed', firestore_client=firestore_client
            )
            summary.note_ineligible('opted_out_at_send')
            continue
        except LifecycleEmailNotConfigured:
            release_lifecycle_send(facts.uid, CAMPAIGN, firestore_client=firestore_client)
            logger.error('day3 re-engagement: email not configured; aborting run')
            raise
        except LifecycleEmailDeliveryUnknown:
            # The request reached the provider and the response was never read,
            # so the claim must STAND: a duplicate is worse than a miss.
            summary.failed += 1
            record_delivery(
                experiment_id=EXPERIMENT_ID, uid=facts.uid, outcome='unknown', firestore_client=firestore_client
            )
            logger.exception('day3 re-engagement: delivery status unknown')
        except Exception:
            # Everything else here happened *before* the provider was reached —
            # `display_name_for` hitting Firebase Auth, template building, a
            # transport error raised as anything other than the unknown-status
            # case above. Nothing was sent, so holding the claim would convert a
            # transient blip into a permanent non-delivery: the retry would see
            # the claim, skip, and leave a treatment user enrolled and unmailed
            # forever. Releasing is what makes the Cloud Run retry able to
            # recover, which is the whole reason the loop no longer stops at
            # "already enrolled".
            release_lifecycle_send(facts.uid, CAMPAIGN, firestore_client=firestore_client)
            summary.failed += 1
            record_delivery(
                experiment_id=EXPERIMENT_ID, uid=facts.uid, outcome='failed', firestore_client=firestore_client
            )
            logger.exception('day3 re-engagement: send failed before reaching the provider')
            continue

        record_delivery(
            experiment_id=EXPERIMENT_ID,
            uid=facts.uid,
            outcome='sent',
            detail={'has_day_zero_output': decision.has_day_zero_output},
            firestore_client=firestore_client,
        )
        summary.sent += 1

    logger.info(
        'day3 re-engagement: considered=%s treatment=%s control=%s sent=%s failed=%s ineligible=%s',
        summary.considered,
        summary.enrolled_treatment,
        summary.enrolled_control,
        summary.sent,
        summary.failed,
        sorted(summary.ineligible.items()),
    )
    return summary
