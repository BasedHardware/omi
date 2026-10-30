"""Durable album merge rules; request admission never waits for the debounce."""

from datetime import timedelta

ALBUM_DEBOUNCE_SECONDS = 1.2
ALBUM_MAX_WAIT_SECONDS = 3


def album_ready_at(row, now):
    first = row['created_at'] if row else now
    return min(now + timedelta(seconds=ALBUM_DEBOUNCE_SECONDS), first + timedelta(seconds=ALBUM_MAX_WAIT_SECONDS))


def merge_album(prior, current):
    if prior is None:
        return current
    # Telegram albums contain at most ten items. Keep a bounded encrypted payload.
    if len(prior['attachments']) + len(current['attachments']) > 10:
        raise ValueError('Album contains too many attachments')
    combined = dict(current)
    combined['received_at'] = min(prior['received_at'], current['received_at'])
    combined['quoted_text'] = current.get('quoted_text') or prior.get('quoted_text')
    combined['quoted_message_id'] = current.get('quoted_message_id') or prior.get('quoted_message_id')
    combined['forwarded'] = prior.get('forwarded', False) or current.get('forwarded', False)
    combined['attachments'] = [*prior['attachments'], *current['attachments']]
    combined['text'] = '\n'.join(t for t in (prior['text'], current['text']) if t)[:8000]
    return combined
