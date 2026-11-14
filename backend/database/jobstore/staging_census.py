"""Original per-record staging keys; never infer remote absence from SQL."""

from database.jobstore.authority import AuthorityRefused


def recording_for(conn, namespace, identity):
    if set(identity) != {'tbl', 'key'} or identity['tbl'] != 'artifacts':
        raise AuthorityRefused('unqualified document cold cohort')
    row = conn.execute(
        'SELECT recording_id FROM queue_staging_copy_keys WHERE namespace=%s AND key=%s',
        (namespace, identity['key']),
    ).fetchone()
    if not row:
        raise AuthorityRefused('original staging key census required')
    return row[0]


def cold_paths(conn, namespace, recording):
    return [
        row[0]
        for row in conn.execute(
            'SELECT cold_path FROM queue_staging_copy_keys WHERE namespace=%s AND recording_id=%s ORDER BY key',
            (namespace, recording),
        ).fetchall()
    ]
