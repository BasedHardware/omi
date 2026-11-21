"""Conservative transfer of transcript-only V3 claims across sync redirects."""

from datetime import datetime, timedelta

from utils.conversations.v3.policy import builder_eligible

MAX_DONORS = 8
MAX_CLAIMS = 64
MAX_CARD_SOURCES = 16
MAX_SEGMENTS = 4096


class CustodyBlocked(ValueError):
    """A bounded reason for keeping the original source and card in place."""


def _speech(row):
    segments = row.get('transcript_segments') or []
    if len(segments) > MAX_SEGMENTS:
        raise CustodyBlocked('speech_budget')
    origin = row.get('started_at')
    if not isinstance(origin, datetime) or origin.tzinfo is None:
        raise CustodyBlocked('speech_unavailable')
    try:
        return {
            (
                origin + timedelta(seconds=segment['start']),
                origin + timedelta(seconds=segment['end']),
                segment.get('id'),
                segment['text'].strip(),
            )
            for segment in segments
            if segment.get('text', '').strip()
        }
    except (TypeError, ValueError, KeyError, OverflowError, AttributeError):
        raise CustodyBlocked('speech_unavailable') from None


def _overlaps(left, right, start, end):
    return (left < end and right > start) or (left == right and start <= left <= end)


def transfer(survivor, donors, load_card):
    """Plan claim and card-link patches. All inputs come from the same transaction.

    A claim is an absolute interval. Moving it needs evidence that every line
    it could reserve on the survivor belongs to its existing card. A redirect
    alone cannot prove equivalent playback or equivalent speech.
    """
    if len(donors) > MAX_DONORS:
        raise CustodyBlocked('donor_budget')
    if sum(len(row.get('claims') or ()) for row in (survivor, *donors.values())) > MAX_CLAIMS:
        raise CustodyBlocked('claim_budget')
    claims = [(rid, claim) for rid, row in donors.items() for claim in row.get('claims') or ()]
    if not claims:
        return {}
    if not builder_eligible(survivor):
        raise CustodyBlocked('ineligible_survivor')
    stored = survivor.get('claims') or []
    for row in (survivor, *donors.values()):
        if not row.get('recording') or row.get('is_locked'):
            raise CustodyBlocked('ineligible_recording')
        if any(
            row.get(field)
            for field in (
                'audio_files',
                'deleted_spans',
                'v3_audio_erased',
                'v3_audio_purge_pending',
                'v3_backfill_run',
            )
        ):
            raise CustodyBlocked('audio_or_deletion_custody')

    def claim_key(claim):
        try:
            cid, start, end = (claim[field] for field in ('conversation_id', 'start', 'end'))
            if (
                not isinstance(cid, str)
                or not cid
                or '/' in cid
                or not isinstance(start, datetime)
                or not isinstance(end, datetime)
                or start.tzinfo is None
                or end.tzinfo is None
                or end < start
            ):
                raise ValueError
        except (TypeError, KeyError, ValueError):
            raise CustodyBlocked('invalid_claim') from None
        return cid, start, end

    merged = {claim_key(claim): claim for claim in stored}
    survivor_speech = _speech(survivor)
    donor_speech = {rid: _speech(row) for rid, row in donors.items()}
    cards = {}
    card_speech = {}
    patches = {}
    for rid, claim in claims:
        cid, start, end = claim_key(claim)
        if cid not in cards:
            card = load_card(cid)
            if (
                not card
                or not card.get('v3_derived')
                or any(
                    card.get(field)
                    for field in (
                        'deleted',
                        'is_locked',
                        'sync_merged_into',
                        'v3_claims_transferred_to',
                        'v3_backfill_run',
                    )
                )
            ):
                raise CustodyBlocked('card_unavailable')
            cards[cid] = card
            card_speech[cid] = _speech(card)
        card = cards[cid]
        sources = card.get('v3_recording_ids') or []
        if rid not in sources or len(sources) > MAX_CARD_SOURCES:
            raise CustodyBlocked('card_source_mismatch')
        if any(
            item.get('recording_id') in donors
            for field in ('recording_pieces', 'audio_files')
            for item in card.get(field) or ()
        ):
            raise CustodyBlocked('card_playback')
        if any(
            other != cid and (_overlaps(left, right, start, end) or _overlaps(start, end, left, right))
            for other, left, right in merged
        ):
            raise CustodyBlocked('competing_claim')
        covered = {line for line in survivor_speech if _overlaps(*line[:2], start, end)}
        original = {line for line in donor_speech[rid] if _overlaps(*line[:2], start, end)}
        card_start, card_end = card.get('started_at'), card.get('finished_at')
        if (
            not original
            or not original <= covered
            or not covered <= card_speech[cid]
            or not isinstance(card_end, datetime)
            or card_end.tzinfo is None
            or any(
                not (segment_id and start <= left <= right <= end and card_start <= left <= right <= card_end)
                for left, right, segment_id, _ in covered
            )
        ):
            raise CustodyBlocked('speech_mismatch')
        merged.setdefault((cid, start, end), claim)
        updated = patches.get(cid, {}).get('v3_recording_ids', sources)
        updated = list(dict.fromkeys(survivor['id'] if source == rid else source for source in updated))
        patches[cid] = {'v3_recording_ids': updated}

    patches[survivor['id']] = {'claims': list(merged.values())}
    patches.update({rid: {'claims': []} for rid, _ in claims})
    return patches
