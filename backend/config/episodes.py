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

``EPISODES_PERCENT`` (default 100) and
``EPISODES_UID_ALLOWLIST`` select the admitted cohort: a stable salted uid
bucket below the percentage, or a listed uid, is admitted. Invalid percentages
admit nobody beyond the allowlist.

Admission alone never spends money. Episode work (the per-moment listen update
and the finalizer's tail and reconciliation) also requires an inferred client
capability: the user's app called a ``/v1/episodes`` route within
``CLIENT_SEEN_TTL_SECONDS``, recorded as the Redis marker
``episodes:client_seen:{uid}`` (``utils/episodes/client_gate.py``). Old mobile
builds, the desktop app and web never call that API, so their users cost
nothing. The API itself stays available to every admitted uid, since it is what
sets the marker. The allowlist bypasses the percentage, not the marker.

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

from config.jev_decisions import percentage, uid_bucket

EPISODES_ENABLED_ENV = 'EPISODES_ENABLED'
EPISODES_PERCENT_ENV = 'EPISODES_PERCENT'
EPISODES_UID_ALLOWLIST_ENV = 'EPISODES_UID_ALLOWLIST'
EPISODES_CLIENT_CHANNELS_ENV = 'EPISODES_CLIENT_CHANNELS'
EPISODE_OUTPUT_LANGUAGE_PIN_ENV = 'EPISODE_OUTPUT_LANGUAGE_PIN'
EPISODE_HARD_CAP_ACROSS_CONVERSATIONS_ENV = 'EPISODE_HARD_CAP_ACROSS_CONVERSATIONS'
EPISODE_CARRY_ON_SESSION_END_ENV = 'EPISODE_CARRY_ON_SESSION_END'
EPISODE_MOMENT_OUTPUT_VALIDATOR_ENV = 'EPISODE_MOMENT_OUTPUT_VALIDATOR'
APP_CHANNEL_HEADER = 'X-Omi-App-Channel'
APP_CHANNELS = frozenset({'beta', 'store'})
_DEFAULT_CLIENT_CHANNELS = frozenset({'beta'})
_COHORT_SALT = 'episodes-v1'
_ON = frozenset({'true', 'on', '1', 'yes'})


def episodes_enabled() -> bool:
    """Unset or blank is on; only an explicit on-value keeps it on, anything else is off."""
    raw = os.getenv(EPISODES_ENABLED_ENV, '').strip().lower()
    return rollout_default_on(EPISODES_ENABLED_ENV, not raw or raw in _ON)


def episodes_enabled_for(uid: str) -> bool:
    """The kill switch first, then the cohort (allowlist or stable uid bucket).

    Admission only: callers that spend money also need ``client_gate.client_seen``.
    """
    if not uid or not episodes_enabled():
        return False
    allowlist = {item.strip() for item in os.getenv(EPISODES_UID_ALLOWLIST_ENV, '').split(',') if item.strip()}
    if uid in allowlist:
        return True
    return uid_bucket(uid, _COHORT_SALT) < percentage(EPISODES_PERCENT_ENV, default=100.0)


def app_channel(raw: str | None) -> str:
    """The request's ``X-Omi-App-Channel`` as a bounded label: ``beta``, ``store`` or ``unknown``."""
    value = (raw or '').strip().lower()
    return value if value in APP_CHANNELS else 'unknown'


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


def episode_carry_on_session_end_enabled() -> bool:
    """Whether a session-end buffer flushes after the bounded reconnect window."""
    return modes_default_on(EPISODE_CARRY_ON_SESSION_END_ENV)


def episode_moment_output_validator_enabled() -> bool:
    """Whether live moment output validation and its one bounded repair call are enabled."""
    return modes_default_on(EPISODE_MOMENT_OUTPUT_VALIDATOR_ENV)


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

# Jev answers P(same occasion); below this the user moved on. Deliberately low:
# the question is uncalibrated, so only a confident "moved on" closes, and no
# answer keeps the episode open (smart merge's measured cutoff is 0.35).
MOVED_ON_THRESHOLD = 0.2
JEV_LANE = 'episode_boundary'
JEV_TIMEOUT_SECONDS = 2.5
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
