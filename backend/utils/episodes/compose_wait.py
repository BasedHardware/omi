"""Affirmative terminal evidence is distinct from an empty transcript still in flight."""

from datetime import datetime, timedelta
from typing import Any, Mapping

from config.episode_composition import anchored_wait_enabled, settled_terminal_enabled
from config.episodes import episode_compose_transcript_wait_seconds
from utils.episodes.policy import utc
from utils.batch_pipeline.empty_transcription import terminal as stt_terminal_empty
from utils.conversations.home_titles import summary_owed
from utils.conversations.summary_delivery import present


def empty_terminal_result(row: Mapping[str, Any]) -> bool:
    """The Home noise contract, independent of presentation feature switches.

    Summary exhaustion/below-floor decisions alone never settle transcription.
    A validated STT-empty receipt must cover the closed audio and current wait
    generation; renewed summary debt or a recovered summary receipt wins.
    Late speech is evaluated by the normal evidence/fingerprint path.
    """
    return bool(
        row.get('status') == 'completed'
        and stt_terminal_empty(row)
        and not any(
            str(s.get('text') or '').strip() for s in row.get('transcript_segments') or [] if isinstance(s, Mapping)
        )
        and not present(row.get('structured') or {})
        and not row.get('summary_output_present')
        and not row.get('summary_completed_at')
        and not summary_owed(row)
    )


def settled_terminal(row: Mapping[str, Any]) -> bool:
    return bool(settled_terminal_enabled() and row.get('status') == 'completed' and stt_terminal_empty(row))


def transcript_anchor(row: Mapping[str, Any]) -> datetime | None:
    return utc(row.get('home_transcription_pending_at')) or utc(row.get('episode_transcription_pending_at'))


def unstamped_audio_wait(row: Mapping[str, Any]) -> bool:
    # Old capture timestamps can predate a fresh upload by days. Only the
    # first-observation map can bound this otherwise unstamped registered work.
    return bool(
        settled_terminal_enabled()
        and anchored_wait_enabled()
        and (
            row.get('server_batch_audio_received') is True
            or any(row.get(key) is not None for key in ('server_batch_audio_start', 'server_batch_audio_end'))
        )
    )


OBSERVATIONS = 'compose_transcript_wait_observations'


def member_deadline(
    row: Mapping[str, Any],
    episode: Mapping[str, Any],
    cid: str,
    due: datetime,
    now: datetime,
    observations: dict[str, Any],
) -> datetime:
    """A blocker generation's first observation cannot be renewed by another member."""
    if not anchored_wait_enabled():
        return due
    pending = transcript_anchor(row)
    previous = (episode.get(OBSERVATIONS) or {}).get(cid)
    observed = None
    if isinstance(previous, Mapping) and utc(previous.get('pending_at')) == pending:
        observed = utc(previous.get('observed_at'))
    if previous is None and cid in (episode.get('compose_transcript_wait_members') or []):
        observed = utc(episode.get('compose_transcript_wait_started_at'))
    observed = observed or now
    observations[cid] = {'pending_at': pending, 'observed_at': observed}
    return min(due, observed + timedelta(seconds=episode_compose_transcript_wait_seconds()))


def stored_deadline(episode: Mapping[str, Any], legacy: datetime | None) -> datetime | None:
    if not anchored_wait_enabled() or legacy is None:
        return legacy
    observations = episode.get(OBSERVATIONS) or {}
    seconds = timedelta(seconds=episode_compose_transcript_wait_seconds())
    deadlines = [legacy]
    for cid in episode.get('compose_transcript_wait_members') or []:
        entry = observations.get(cid)
        if isinstance(entry, Mapping):
            deadlines.extend(at + seconds for key in ('observed_at', 'pending_at') if (at := utc(entry.get(key))))
    return min(deadlines)


def observation_updates(
    observations: Mapping[str, Any],
    waiting: list[str],
    now: datetime,
    *,
    current: Mapping[str, Any],
    due: datetime,
) -> dict[str, Any]:
    if not anchored_wait_enabled():
        return {'compose_transcript_wait_started_at': now}
    # A CAS retry must merge with the winning replica, not overwrite its earlier
    # first observation with this attempt's stale pre-CAS snapshot. Preserve
    # unrelated generations until their next evaluation too.
    merged = dict(current.get(OBSERVATIONS) or {})
    for cid, entry in observations.items():
        previous = merged.get(cid)
        observed = entry['observed_at']
        if isinstance(previous, Mapping) and utc(previous.get('pending_at')) == utc(entry.get('pending_at')):
            earlier = utc(previous.get('observed_at'))
            if earlier:
                observed = min(observed, earlier)
        merged[cid] = {**entry, 'observed_at': observed}
    seconds = timedelta(seconds=episode_compose_transcript_wait_seconds())
    caps = [merged[cid]['observed_at'] + seconds for cid in waiting if cid in merged]
    return {
        OBSERVATIONS: merged,
        'compose_transcript_wait_until': min([due, *caps]),
        'compose_transcript_wait_started_at': min(
            (merged[cid]['observed_at'] for cid in waiting if cid in merged), default=now
        ),
    }
