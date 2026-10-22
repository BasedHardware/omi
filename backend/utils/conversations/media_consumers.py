"""Read the V2 content-kind projection at V4 consumer boundaries."""

from config.refactor_modes import serving_for


def eligible_conversations(uid, rows):
    if not serving_for('MEDIA_NOISE_MODE', uid):
        return list(rows)
    return [row for row in rows if row.get('content_kind') not in ('media', 'noise')]
