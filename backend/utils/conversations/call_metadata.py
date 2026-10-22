"""Project call identity from the wave-1 boundary authority, never window titles.

Old boundary payloads without positive call evidence abstain. In particular a
screen/chat roster or a calendar html page is not proof of a remote call.
"""

from datetime import timedelta
import re
from urllib.parse import urlsplit

from config.refactor_modes import serving_for, shadow_or_serve
from utils.conversations.lifecycle_clocks import utc
from utils.conversations.calls_metrics import observe

FLAG_ENV = 'CALLS_RECAP_MODE'
FLAG = FLAG_ENV
_PLATFORM_HOSTS = {
    'meet.google.com': 'google_meet',
    'zoom.us': 'zoom',
    'teams.microsoft.com': 'teams',
    'teams.live.com': 'teams',
    'webex.com': 'webex',
}


def meeting_platform(link):
    try:
        parsed = urlsplit(link or '')
        if parsed.scheme != 'https' or not parsed.path.strip('/'):
            return None
        host = (parsed.hostname or '').lower()
        platform = next(
            (name for domain, name in _PLATFORM_HOSTS.items() if host == domain or host.endswith('.' + domain)), None
        )
        patterns = {
            'google_meet': r'^/(?:[a-z]{3}-[a-z]{4}-[a-z]{3}|lookup/[^/]+)/*$',
            'zoom': r'^/(?:j/\d+|s/\d+|my/[^/]+|wc/join/\d+)/*$',
            'teams': r'^/(?:l/meetup-join/|meet/)',
            'webex': r'^/(?:meet/|webappng/|j\.php)',
        }
        return platform if platform and re.search(patterns[platform], parsed.path.casefold()) else None
    except ValueError:
        return None


def call_fields(signals, context=None):
    """Pure projection; extra signal fields can be added by the boundary owner.

    Calendar context is accepted only for the exact boundary event, with a real
    meeting link. Desktop/screen events require explicit control evidence; an
    app name or roster alone never qualifies. media_playback is ignored.
    """
    context = context or {}
    calls = []
    for signal in signals:
        kind = signal.kind
        if signal.confidence < 0.8:
            continue
        if kind == 'phone_call':
            calls.append((0, signal, 'phone'))
        elif kind == 'calendar_event':
            link = getattr(signal, 'meeting_link', None)
            if not link and signal.external_id and signal.external_id == context.get('calendar_event_id'):
                link = context.get('meeting_link')
            if platform := meeting_platform(link):
                calls.append((2, signal, platform))
        elif kind in ('desktop_meeting', 'screen_meeting') and getattr(signal, 'call_controls_detected', False) is True:
            platform = getattr(signal, 'call_platform', None) or 'unknown'
            # Never persist a client-supplied arbitrary string as a telemetry-like label.
            calls.append(
                (
                    1,
                    signal,
                    (
                        platform
                        if platform in {*_PLATFORM_HOSTS.values(), 'telegram', 'slack', 'discord', 'whatsapp'}
                        else 'unknown'
                    ),
                )
            )
    if not calls:
        return {
            'is_call': None,
            'call_platform': None,
            'calendar_event_id': None,
            'geolocation_scope': None,
            'other_participants_location': None,
        }
    calls.sort(key=lambda item: (item[0], item[1].started_at.isoformat(), item[1].external_id or ''))
    priority = calls[0][0]
    platforms = {p for rank, _, p in calls if rank == priority}
    platform = next(iter(platforms)) if len(platforms) == 1 else 'unknown'
    events = {s.external_id for _, s, p in calls if s.kind == 'calendar_event' and s.external_id and p == platform}
    event = next(iter(events)) if len(events) == 1 else None
    return {
        'is_call': True,
        'call_platform': platform,
        'calendar_event_id': event,
        'geolocation_scope': 'owner',
        'other_participants_location': 'remote',
    }


def apply_call_metadata(uid, conversation):
    if not shadow_or_serve(FLAG):
        return conversation
    try:
        from models.boundary_evidence import BoundarySignal
        from utils.episodes import boundary_store, boundaries

        start = utc(conversation.started_at)
        end = utc(conversation.finished_at) or start
        if start is None or end is None:
            return conversation
        external = getattr(conversation, 'external_data', None) or {}
        context = external.get('calendar_meeting_context')
        serving = serving_for(FLAG, uid)
        # V4 must not add inputs to the wave-1 authority outside its own cohort.
        # Shadow projects the same evidence locally without persisting it.
        if serving:
            boundaries.ingest_context(uid, context)
        # A persisted phone transport identity is positive boundary evidence too.
        phone = None
        if getattr(conversation, 'call_id', None):
            phone = BoundarySignal(kind='phone_call', started_at=start, ended_at=end, external_id=conversation.call_id)
            if serving:
                boundary_store.record(uid, [phone])
        # Ongoing stale signals cannot label unrelated conversations indefinitely.
        windows = boundary_store.windows(uid)
        keys = [
            key
            for key, window in windows.items()
            if (left := utc(window.get('started_at'))) is not None
            and left < end
            and (utc(window.get('ended_at')) or left + timedelta(hours=4)) > start
        ]
        signals = boundary_store.load(uid, keys)
        if phone is not None:
            signals.append(phone)
        if not serving and context:
            if local_context := boundaries.context_signal(context):
                signals.append(local_context)
        fields = call_fields(signals, context)
        # Expired evidence cannot clear a durable call, so compare the retained
        # projection rather than reporting absence as a metadata disagreement.
        if fields['is_call'] is None and getattr(conversation, 'is_call', None) is True:
            fields = {key: getattr(conversation, key, None) for key in fields}
        observe(
            'call_metadata',
            'agree' if all(getattr(conversation, k, None) == v for k, v in fields.items()) else 'disagree',
        )
        # Evidence expiry is absence, not a contradiction of a previously finalized call.
        if serving_for(FLAG, uid) and fields['is_call'] is True:
            for key, value in fields.items():
                setattr(conversation, key, value)
    except Exception:
        observe('call_metadata', 'error')
        if serving_for(FLAG, uid):
            from utils.observability.fallback import record_fallback

            record_fallback(
                component='conversation_finalization',
                from_mode='boundary_call_metadata',
                to_mode='existing_metadata',
                reason='dependency_unavailable',
                outcome='degraded',
            )
    return conversation
