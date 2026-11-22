"""Home policy: positive wearer evidence may hide background; uncertainty may not."""

from utils.conversations.v3.word_floor import MIN_HOME_WORDS


def hydrate_recognition(uid, recordings, windows):
    from utils.speakers.evidence import get_evidence, project_labels

    ids = {line['conversation_id'] for w in windows if w['kind'] == 'background' for line in w['lines']}
    for rid in ids:
        row = recordings[rid]
        segments = row.get('transcript_segments') or []
        recognized = any(s.get('is_user') is True for s in segments)
        if not recognized:
            evidence = get_evidence(uid, rid)
            if evidence is not None:
                labels = project_labels(evidence, row.get('manual_speaker_assignments') or {})
                recognized = any(labels.get(s.get('id'), (False, None))[0] for s in segments)
        # Transient input, never a new identity decision or a persisted claim.
        row['_v3_wearer_recognized'] = recognized


def project(kind, recordings, recording_ids, *, words, finished, manual_end):
    uncertain = kind == 'background' and not any(
        recordings[rid].get('_v3_wearer_recognized')
        or any(s.get('is_user') is True for s in recordings[rid].get('transcript_segments') or [])
        for rid in recording_ids
    )
    if uncertain:
        kind = 'conversation'
    if kind == 'media':
        return kind, True, 'media'
    if kind == 'background':
        return kind, True, 'background_wearer_recognized'
    if finished and not manual_end and words < MIN_HOME_WORDS:
        return kind, True, 'below_word_minimum'
    return kind, False, 'wearer_recognition_uncertain' if uncertain else 'manual_end' if manual_end else 'conversation'
