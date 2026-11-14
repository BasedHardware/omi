"""Runtime contract for episodes: a live presentation and processing unit over conversations.

An episode groups temporally adjacent conversations ("moments" are the speech
stretches inside them) into one occasion. It is an overlay: no conversation is
rewritten, merged or deleted by this feature. Per-conversation processing,
smart merge and the finalization jobs keep their own contracts.

``EPISODES_ENABLED`` is the kill switch. Unset or blank means on; ``off`` (or
any value outside the on-set) means off, so a mistyped value stops the feature
rather than silently keeping it running. Off makes the episodes API report
``enabled: false``: released and current apps then show today's
per-conversation UI, and no episode state is read, written or computed.

Every nonempty owner is admitted while the kill switch is on. Admission alone
never spends money: episode work still requires the existing recent capable-client
marker.

``EPISODES_CLIENT_CHANNELS`` (default ``beta``) is the client cohort. The app
sends ``X-Omi-App-Channel: beta|store`` on every request (TestFlight and
non-production build profiles are ``beta``; anything else, including an
unknown install, is ``store``). An episodes API call from a channel outside the
list answers ``enabled: false`` and leaves no marker, so that client keeps
today's UI and its user costs nothing. A missing or unrecognised channel (old
builds, desktop, web) is never admitted. Expanding to store users is the config
flip ``beta,store``.

Pure module: stdlib only, flags read at the call boundary, never at import.
"""

from __future__ import annotations

import os

from config.refactor_modes import default_on as modes_default_on
from config.refactor_switches import default_on as rollout_default_on

from config.app_channel import APP_CHANNELS, app_channel
from config.jev_decisions import JEV_CLIENT_TIMEOUT_SECONDS, percentage, uid_bucket

EPISODES_ENABLED_ENV = 'EPISODES_ENABLED'
EPISODES_CLIENT_CHANNELS_ENV = 'EPISODES_CLIENT_CHANNELS'
EPISODE_OUTPUT_LANGUAGE_PIN_ENV = 'EPISODE_OUTPUT_LANGUAGE_PIN'
EPISODE_HARD_CAP_ACROSS_CONVERSATIONS_ENV = 'EPISODE_HARD_CAP_ACROSS_CONVERSATIONS'
HOME_HIDE_BELOW_FLOOR_ROWS_ENV = 'HOME_HIDE_BELOW_FLOOR_ROWS'
HOME_HIDE_EPISODE_MEMBERS_ENV = 'HOME_HIDE_EPISODE_MEMBERS'
HOME_NEUTRAL_MINIMUM_TITLES_ENV = 'HOME_NEUTRAL_MINIMUM_TITLES'
HOME_TRANSCRIPTION_PRESENTATION_GATE_ENV = 'HOME_TRANSCRIPTION_PRESENTATION_GATE'
HOME_STEP_PROJECTION_ENV = 'HOME_STEP_PROJECTION'
HOME_EMPTY_OUTPUT_NOISE_ENV = 'HOME_EMPTY_OUTPUT_NOISE'
HOME_PROCESSING_MAX_AGE_SECONDS_ENV = 'HOME_PROCESSING_MAX_AGE_SECONDS'
DEFAULT_HOME_PROCESSING_MAX_AGE_SECONDS = 21600
EPISODE_CARRY_ON_SESSION_END_ENV = 'EPISODE_CARRY_ON_SESSION_END'
EPISODE_MOMENT_OUTPUT_VALIDATOR_ENV = 'EPISODE_MOMENT_OUTPUT_VALIDATOR'
EPISODE_COMPOSER_THRIFT_ENV = 'EPISODE_COMPOSER_THRIFT'
EPISODE_COMPOSER_ENV = 'EPISODE_COMPOSER'
EPISODE_COMPOSE_SETTLE_ENABLED_ENV = 'EPISODE_COMPOSE_SETTLE_ENABLED'
EPISODE_COMPOSE_LATE_ATTACH_ENABLED_ENV = 'EPISODE_COMPOSE_LATE_ATTACH_ENABLED'


EPISODE_LATE_COMPOSE_AFTER_HOURS_ENV = 'EPISODE_LATE_COMPOSE_AFTER_HOURS'
EPISODE_LATE_COMPOSE_GRACE_HOURS_ENV = 'EPISODE_LATE_COMPOSE_GRACE_HOURS'
# A recording repaired or synced more than this long after capture is "late": it
# composes when its page is first opened, not at finalize.
DEFAULT_LATE_COMPOSE_AFTER_HOURS = 48.0
# The read-side safety net still composes a deferred episode after this long, so a
# client that never opens the page cannot leave notes unwritten forever.
DEFAULT_LATE_COMPOSE_GRACE_HOURS = 168.0
_DEFAULT_CLIENT_CHANNELS = frozenset({'beta'})
_ON = frozenset({'true', 'on', '1', 'yes'})


def episodes_enabled() -> bool:
    """Unset or blank is on; only an explicit on-value keeps it on, anything else is off."""
    raw = os.getenv(EPISODES_ENABLED_ENV, '').strip().lower()
    return rollout_default_on(EPISODES_ENABLED_ENV, not raw or raw in _ON)


def episodes_enabled_for(uid: str) -> bool:
    """All owners are admitted while the independent kill switch is on."""
    return bool(uid and episodes_enabled())


def episodes_client_channels() -> frozenset[str]:
    """Admitted client channels. Unset or blank is ``beta``; unrecognised entries are ignored."""
    raw = os.getenv(EPISODES_CLIENT_CHANNELS_ENV, '')
    if not raw.strip():
        return _DEFAULT_CLIENT_CHANNELS
    return frozenset(item.strip().lower() for item in raw.split(',')) & APP_CHANNELS


def episode_output_language_pinned() -> bool:
    """Whether the shared output-language prompt pin is enabled.

    The kill switch also covers provisional conversation topics, daily recaps, and
    proactive notification prompts so one setting rolls the prompt changes back.
    Unknown values stay on. Off restores each surface's legacy prompt wording and
    the former cohort-gated episode language behavior.
    """
    return modes_default_on(EPISODE_OUTPUT_LANGUAGE_PIN_ENV)


def episode_hard_cap_across_conversations_enabled() -> bool:
    """Whether the strict episode-wide hard cap runs on attachment and moment boundaries."""
    return modes_default_on(EPISODE_HARD_CAP_ACROSS_CONVERSATIONS_ENV)


def home_hide_episode_members_enabled() -> bool:
    """Hide only members covered by a client-held, extant episode projection."""
    return modes_default_on(HOME_HIDE_EPISODE_MEMBERS_ENV)


def home_neutral_minimum_titles_enabled() -> bool:
    """Replace provisional transcript-echo Home titles without changing storage."""
    return modes_default_on(HOME_NEUTRAL_MINIMUM_TITLES_ENV)


def home_step_projection_enabled() -> bool:
    """Default-on Home row contract field on list reads; off omits ``home_step``."""
    return modes_default_on(HOME_STEP_PROJECTION_ENV)


def home_empty_output_noise_enabled() -> bool:
    """Default-on: no-output terminal summaries are noise regardless of title provenance."""
    return modes_default_on(HOME_EMPTY_OUTPUT_NOISE_ENV)


def home_processing_max_age_seconds() -> int | None:
    """6h by default; None tells the reader to count invalid config and use 6h.

    Nonpositive values are invalid, never a way to disable the age bound.
    Normal finalization takes minutes; 6h leaves headroom over the 2h batch SLA.
    """
    try:
        seconds = int(os.getenv(HOME_PROCESSING_MAX_AGE_SECONDS_ENV, str(DEFAULT_HOME_PROCESSING_MAX_AGE_SECONDS)))
    except ValueError:
        return None
    return seconds if seconds > 0 else None


def home_transcription_presentation_gate_enabled() -> bool:
    """Default-on batch transcription presentation; off restores stored status/title."""
    return modes_default_on(HOME_TRANSCRIPTION_PRESENTATION_GATE_ENV)


def home_transcription_deadline_seconds() -> int:
    """New captures get 2h (batch timeliness SLA); invalid or nonpositive values use 2h."""
    try:
        seconds = int(os.getenv('HOME_TRANSCRIPTION_DEADLINE_SECONDS', '7200'))
    except ValueError:
        return 7200
    return seconds if seconds > 0 else 7200


def home_hide_below_floor_rows_enabled() -> bool:
    """Whether Home leaves out short captures under the notes floor."""
    return modes_default_on(HOME_HIDE_BELOW_FLOOR_ROWS_ENV)


def episode_carry_on_session_end_enabled() -> bool:
    """Whether a session-end buffer flushes after the bounded reconnect window."""
    return modes_default_on(EPISODE_CARRY_ON_SESSION_END_ENV)


def episode_moment_output_validator_enabled() -> bool:
    """Whether live moment output validation and its one bounded repair call are enabled."""
    return modes_default_on(EPISODE_MOMENT_OUTPUT_VALIDATOR_ENV)


def episode_composer_enabled() -> bool:
    """Whether closed episodes get one whole-episode summary (``utils/episodes/composer.py``).

    Off keeps the live incremental notes as the final episode notes, as before.
    """
    return modes_default_on(EPISODE_COMPOSER_ENV)


def episode_compose_settle_enabled() -> bool:
    """Default-on cost control; off restores the original trigger and retry behavior."""
    return modes_default_on(EPISODE_COMPOSE_SETTLE_ENABLED_ENV)


def episode_compose_late_attach_enabled() -> bool:
    """Default-on: a member that joins an already-composed closed episode re-arms its compose.

    Its own switch, not ``EPISODE_COMPOSER_THRIFT``: turning the THRIFT cost
    controls off must not silently restore the class-7 gap where a late member's
    notes never reach the composed summary. Off restores the previous attach
    behavior, where only a member finalize or a Home read could notice the member.
    """
    return modes_default_on(EPISODE_COMPOSE_LATE_ATTACH_ENABLED_ENV)


def episode_compose_keep_paid_enabled() -> bool:
    """Default-on: keep paid composes instead of discarding them.

    On, a parse failure gets one repair retry over the bad output alone, a short
    episode may ship a title and lede with no chapters, a superseded result is
    stored and the episode marked pending, and paid failures stop at two per
    evidence. Off restores the previous discard-and-retry behavior and the
    four-failure cap.
    """
    return modes_default_on(EPISODE_COMPOSER_THRIFT_ENV)


def episode_single_member_compose_enabled() -> bool:
    """Default-on: a one-conversation episode is built from that conversation's notes in code.

    Off restores the paid composer for single-member episodes. The shortcut never
    calls a model, so it has no lease, backoff or settle window.
    """
    return modes_default_on(EPISODE_COMPOSER_THRIFT_ENV)


def episode_late_compose_enabled() -> bool:
    """Default-on: a late episode composes on its first open instead of at finalize.

    Off restores today's behavior: every closed episode composes as soon as its
    members finish, however old the capture is.
    """
    return modes_default_on(EPISODE_COMPOSER_THRIFT_ENV)


def _positive_hours(name: str, default: float) -> float:
    """A positive hour count; invalid, non-finite or nonpositive values use the default."""
    try:
        hours = float(os.getenv(name, str(default)))
    except ValueError:
        return default
    if hours != hours or hours in (float('inf'), float('-inf')) or hours <= 0:
        return default
    return hours


def episode_late_compose_after_hours() -> float:
    """48h by default: capture age at finalize above which a compose waits for the first open."""
    return _positive_hours(EPISODE_LATE_COMPOSE_AFTER_HOURS_ENV, DEFAULT_LATE_COMPOSE_AFTER_HOURS)


def episode_late_compose_grace_hours() -> float:
    """7 days by default: how long a deferred episode may wait before a read composes it anyway."""
    return _positive_hours(EPISODE_LATE_COMPOSE_GRACE_HOURS_ENV, DEFAULT_LATE_COMPOSE_GRACE_HOURS)


def client_channel_admitted(raw: str | None) -> bool:
    """A missing or unknown channel is never admitted."""
    channel = app_channel(raw)
    return channel != 'unknown' and channel in episodes_client_channels()


# --------------------------------------------------------------------------- client capability

# A capable app calls /v1/episodes at startup and every 30 s while a live surface
# is on screen; the marker it leaves lives this long without another call.
CLIENT_SEEN_TTL_SECONDS = 14 * 24 * 60 * 60
# The marker is rewritten at most this often per uid, so polling is not a write.
CLIENT_SEEN_REFRESH_SECONDS = 60 * 60

# --------------------------------------------------------------------------- live poll reads

# /v1/episodes/live answers the additive last-closed recap from a per-process
# cache for this long while a live episode is on screen (the recap changes only
# when an episode closes). When no live episode is on screen the read stays
# fresh: that is the recovery-navigation answer the recap exists for.
LAST_CLOSED_CACHE_SECONDS = 30

# --------------------------------------------------------------------------- moments

# A moment ends when the live stream pauses for this long, when it grows past
# MOMENT_MAX_WORDS (a rollover), after MOMENT_MAX_SECONDS of steady speech (an
# interval), or when finalize/wrap-up consumes the remaining buffer. A session
# end preserves speech for one reconnect window before flushing the tail; a
# conversation change carries speech into the next same-episode moment.
MOMENT_PAUSE_SECONDS = 45
MOMENT_MAX_WORDS = 600
# Continuous talk never pauses for 45 s and rarely reaches 600 words quickly; without a
# time bound the live state went many minutes without an update.
MOMENT_MAX_SECONDS = 180
# The first moment of a live stretch comes early, so the row gets a title within a minute
# instead of reading "Listening now" until the first pause or interval.
FIRST_MOMENT_MIN_WORDS = 60
FIRST_MOMENT_MIN_SECONDS = 30
# Below this a moment is folded into the next one instead of costing a call.
MOMENT_MIN_WORDS = 25
# A single moment's new text is bounded; the head and tail are kept.
MOMENT_TEXT_MAX_CHARS = 6_000
# One live update per episode at most this often; a burst folds into the next.
MOMENT_MIN_INTERVAL_SECONDS = 60
# Recovered audio refreshes draft notes at most this often: the composer rewrites them at close.
RECOVERY_NOTES_MIN_INTERVAL_SECONDS = MOMENT_MAX_SECONDS

# --------------------------------------------------------------------------- close detection

# Below this gap a new conversation simply continues the episode (it is the
# live split itself, ``models/conversation_continuity.DEFAULT_GAP_SECONDS``).
from config.recorded_time_tolerances import (
    CONTINUE_GAP_SECONDS as CONTINUE_GAP_SECONDS,
    CLOSE_GAP_SECONDS as CLOSE_GAP_SECONDS,
    MAX_EPISODE_SECONDS as MAX_EPISODE_SECONDS,
    FALLBACK_CLOSE_GAP_SECONDS as FALLBACK_CLOSE_GAP_SECONDS,
)

# At or above this gap the episode is over without asking: the next speech opens
# a new episode (reason ``gap``), and a read that finds an episode this idle
# closes it (reason ``idle``). In between, Jev decides whether the user moved on.
# Hard cap on one episode's recorded span (David, 2026-10-29).
MAX_MOMENTS = 48
COMPOSER_MIN_SECTION_SECONDS = 60

# Jev answers P(same occasion); below this the user moved on. Deliberately low:
# the question is uncalibrated, so only a confident "moved on" closes, and no
# answer keeps the episode open (smart merge's measured cutoff is 0.35).
MOVED_ON_THRESHOLD = 0.2
JEV_LANE = 'episode_boundary'
JEV_TIMEOUT_SECONDS = 2.5

# --------------------------------------------------------------------------- episode join variant F

# Variant F settles an uncertain recorded-time join (a live owner 2 to 30 minutes after its last speech)
# with Jev over the previous member's transcript and the new speech, no summary or time features.
# The cohort is the Omi flag store rule ``episode_f_join`` (``utils/episodes/f_join.py``): ramp and
# kill it at runtime with ``scripts/omi_flags.py``. Without a rule the env ``EPISODE_F_JOIN_PERCENT``
# (default 0) buckets uids. ``EPISODE_F_JOIN_ENABLED`` (unset is on; off/false/0/no) overrides both.
EPISODE_F_JOIN_ENABLED_ENV = 'EPISODE_F_JOIN_ENABLED'
EPISODE_F_JOIN_PERCENT_ENV = 'EPISODE_F_JOIN_PERCENT'
F_JOIN_FLAG_KEY = 'episode_f_join'
F_JOIN_VARIANT = 'f'
F_JOIN_JEV_LANE = 'episode_boundary_f'
F_JOIN_PREVIOUS_CHARS = 12_000
F_JOIN_NEW_CHARS = 8_000
F_JOIN_PEOPLE_READ_LIMIT = 8
# The gateway's own provider deadline (JEV_GATEWAY_REQUEST_MS, 2.5 s) is authoritative; the client
# waits just past it so a slow provider surfaces as a gateway timeout. One attempt, as today.
F_JOIN_TIMEOUT_SECONDS = JEV_CLIENT_TIMEOUT_SECONDS
F_JOIN_SALT = 'episode-f-join-v1'


def f_join_enabled() -> bool:
    """Unset is on; an explicit on-value stays on; anything else (including a typo) turns F off."""
    raw = os.getenv(EPISODE_F_JOIN_ENABLED_ENV, '').strip().lower()
    return not raw or raw in _ON


def f_join_env_admitted(uid: str) -> bool:
    """The env fallback cohort: a stable salted uid bucket below the percent; invalid admits nobody."""
    return bool(uid) and uid_bucket(uid, F_JOIN_SALT) < percentage(EPISODE_F_JOIN_PERCENT_ENV, default=0.0)


# Without a Jev answer, a source change or a gap this long still closes.

# --------------------------------------------------------------------------- compact state budget

MAX_BULLETS = 8
MAX_PEOPLE = 8
MAX_OPEN_QUESTIONS = 4
MAX_PROVISIONAL_ITEMS = 12
MAX_ITEM_CHARS = 200
MAX_TOPIC_CHARS = 80
MAX_HEADING_CHARS = 48
# The rendered state the model reads back; a few hundred tokens.
MAX_STATE_CHARS = 2_400

# Provisional reminders due within this window are "near-time".
NEAR_TIME_REMINDER_SECONDS = 2 * 60 * 60
# Token-overlap threshold for "a provisional item became a saved task".
PROVISIONAL_MATCH_THRESHOLD = 0.5

# --------------------------------------------------------------------------- model

INCREMENTAL_FEATURE = 'episode_incremental'
INCREMENTAL_PROMPT_VERSION = 'episode_incremental_v1'
INCREMENTAL_TIMEOUT_SECONDS = 20.0
INCREMENTAL_MAX_OUTPUT_TOKENS = 700
# Estimate only, for the per-moment cost metric: llm_gateway/config/cost_rate_cards.yaml
# openai.gpt-5-nano.2026-07-17. The gateway attempt ledger stays authoritative.
EST_INPUT_USD_PER_MTOK = 0.05
EST_OUTPUT_USD_PER_MTOK = 0.40

# Closed-episode composer: one strong call over member summaries plus the full transcript.
COMPOSER_FEATURE = 'episode_composer'
COMPOSER_VERSION = 'episode_composer_v2'
COMPOSER_TIMEOUT_SECONDS = 90.0
# About 60k tokens. With the 4h episode cap almost every episode fits whole; beyond it the
# densest 10-minute windows are kept in time order.
COMPOSER_MAX_TRANSCRIPT_CHARS = 240_000
COMPOSER_MAX_CHAPTERS = 8
# Read-side safety net: at most this many closed, uncomposed episodes queued per list read.
COMPOSER_MAX_SCHEDULED_PER_READ = 2
# A read-side caller re-queues the same episode at most this often per process.
COMPOSER_READ_THROTTLE_SECONDS = 600
# The per-conversation lookup runs once per Home row: cap the distinct episodes it queues per user
# per throttle window, per process.
COMPOSER_LOOKUP_SCHEDULES_PER_WINDOW = 4
# Every logical turn permits two 90s provider attempts plus 30s retry/processing
# headroom. The lease covers all permitted turns plus a final-write margin.
COMPOSER_MAX_PAID_TURNS = 2  # initial + optional repair; L9 extends this bound
COMPOSER_CALL_BUDGET_SECONDS = COMPOSER_TIMEOUT_SECONDS * 2 + 30
COMPOSER_LEASE_SECONDS = COMPOSER_MAX_PAID_TURNS * COMPOSER_CALL_BUDGET_SECONDS + 60
COMPOSER_SETTLE_SECONDS = 10 * 60
COMPOSER_MAX_SETTLE_SECONDS = 25 * 60
# After a failed paid attempt the read-side net backs off 10, 20, 40 min, then stops until
# the evidence changes (a member finalize still composes).
COMPOSER_RETRY_MINUTES = 10
COMPOSER_MAX_FAILURES = 4
# With EPISODE_COMPOSER_THRIFT on, one attempt plus one repair retry is the whole budget:
# a third paid failure on the same evidence cannot produce a different result.
COMPOSER_MAX_PAID_FAILURES = 2
# A short episode (at most this much recorded member time) may ship a title and lede with
# no chapters: the lede is the page, and a sectionless reply is not a failed compose.
COMPOSER_SHORT_EPISODE_SECONDS = 15 * 60
# Wire budget per composed paragraph (to_wire serves bullets up to this length).
COMPOSER_MAX_PARAGRAPH_CHARS = 1200
# A composed moment's points (each with a few supporting details) are the episode page's sections.
COMPOSER_MAX_POINTS = 6
COMPOSER_MAX_DETAILS = 4
COMPOSER_MAX_POINT_CHARS = 400

# Extra reads caused by Home projection, independent of page/member counts.
HOME_MEMBERSHIP_EPISODE_READ_LIMIT = 5
HOME_IDLE_CLOSES_PER_READ = 2
