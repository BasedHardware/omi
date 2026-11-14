"""Original terminal receipts, never session capabilities or all-copy certificates."""

from database.jobstore.authority import AuthorityRefused
from database.privacy_fence.protocol import row_dict


def require_terminal(conn, upload):
    proof = row_dict(
        conn,
        'SELECT * FROM queue_upload_terminal_receipts WHERE namespace=%s AND unit_id=%s',
        (upload['namespace'], upload['unit_id']),
    )
    if (
        not proof
        or upload['phase'] != 'fenced'
        or any(
            proof[key] != upload[key]
            for key in (
                'namespace',
                'unit_id',
                'attempt_token',
                'owner_key',
                'admission_id',
                'effect_id',
                'original_deadline',
                'generation',
            )
        )
        or proof['status'] not in {200, 201, 404, 410, 412, 499}
        or (proof['generation'] is None and proof['status'] not in {412, 499})
        or conn.execute('SELECT 1 FROM privacy_effect_inflight WHERE effect_id=%s', (upload['effect_id'],)).fetchone()
    ):
        raise AuthorityRefused('durable original terminal-session receipt required')
    return proof
