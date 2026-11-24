"""Existing identify-card evidence for recurring voices, without new wire copy."""

import re
from types import SimpleNamespace

from config.batch_conversation_speakers import recurring_enabled_for
from utils.llm.known_spellings import trusted_people_spellings


def recurring_run(uid, conversation, segment_ids, profile_ids=None):
    if not uid:
        return False
    segments = conversation.get('transcript_segments') or []
    authority = [
        SimpleNamespace(speaker_id_scope=s.get('speaker_id_scope'), provider_speaker=s.get('provider_speaker'))
        for s in segments
    ]
    if not recurring_enabled_for(uid, authority):
        return False
    selected = [s for s in segments if s.get('id') in set(segment_ids)]
    ids = {s.get('recurring_voice_id') for s in selected}
    return (
        bool(selected)
        and len(ids) == 1
        and bool(next(iter(ids)))
        and (profile_ids is None or next(iter(ids)) in profile_ids)
    )


def mentioned_people(conversation, stored_people):
    text = ' '.join(s.get('text') or '' for s in (conversation.get('transcript_segments') or [])[:2000])[
        :64000
    ].casefold()
    result = []
    for person in stored_people[:200]:
        trusted = trusted_people_spellings([person])
        if not trusted:
            continue
        name = trusted[0]['name'].casefold()
        if re.search(r'(?<!\w)' + re.escape(name) + r'(?!\w)', text):
            result.append(person['id'])
    return result[:5]


def metric_origin(uid, conversation, segment_ids, fallback, profile_ids=None):
    # Derive recurring origin from committed segments, never the client request.
    if recurring_run(uid, conversation, segment_ids, profile_ids):
        return 'recurring'
    return fallback if fallback in {'auto_user', 'auto_person', 'unnamed'} else 'unnamed'


def current_ids(uid, conversations):
    from database import recurring_voices
    from utils.observability.fallback import record_fallback

    if not any(
        recurring_run(uid, c, [s['id']])
        for c in conversations
        for s in c.get('transcript_segments') or []
        if s.get('recurring_voice_id') and s.get('id')
    ):
        return set()
    try:
        return recurring_voices.suggestable_ids(uid)
    except Exception:
        record_fallback(
            component='stt_selection',
            from_mode='batch_final_pass',
            to_mode='legacy_speaker_matching',
            reason='unavailable',
            outcome='degraded',
        )
        return set()
