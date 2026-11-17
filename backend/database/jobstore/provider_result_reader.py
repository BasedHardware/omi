"""Customer-role original result reader, reconstructible after worker exit.

Uses retained immutable SQL identity, never a live provider capability or a
new REGISTER. The resulting authority object has no START/COMPLETE methods.
"""

from types import SimpleNamespace

from database.jobstore.authority import AuthorityRefused, fingerprint
from database.jobstore.provider_handoff import ProviderHandoff
from database.jobstore.provider_upload import ProviderUpload
from database.jobstore.result_upload_rows import uri as upload_uri
from database.privacy_fence.protocol import row_dict


class ProviderResultReader:
    def __init__(self, handoff, storage_client, bucket, master_secret, *, lease_seconds):
        self.adapter = ProviderHandoff(handoff)
        self.storage, self.bucket, self.secret = storage_client, bucket, master_secret
        # Reuse the host's explicit artifact adapter setting; reads never
        # register effects, start sessions or consume this lease.
        self.lease_seconds = lease_seconds

    def load_result(self, item, uri, *, read_budget=None):
        units, handoff = self.adapter.units, self.adapter.handoff
        timeout = read_budget.timeout(2) if read_budget is not None else 2
        with units.pool.connection(timeout=timeout) as conn, conn.transaction():
            if read_budget is not None:
                # The extra original-source SQL snapshot is part of this same
                # caller budget, including waits for the owner/row guard.
                milliseconds = str(max(1, int(read_budget.timeout(2) * 1000)))
                conn.execute("SELECT set_config('statement_timeout',%s,true)", (milliseconds,))
                conn.execute("SELECT set_config('lock_timeout',%s,true)", (milliseconds,))
            job = units.terminal_provider_source(conn, item.segment_id)
            if job['result']['result_uri'] != uri:
                raise AuthorityRefused('original terminal result reference required')
            row = handoff._required_row(conn, job['recording_id'])
            handoff._guard(conn, row)
            upload = row_dict(
                conn,
                "SELECT * FROM queue_provider_uploads WHERE namespace=%s AND unit_id=%s AND phase='published'",
                (units.namespace, item.segment_id),
            )
            if (
                not upload
                or upload_uri(upload) != uri
                or upload['bucket'] != self.bucket
                or row['admission'] != job['admission']
                or str(upload['admission_id']) != job['admission']['admission_id']
                or str(job['attempt_admission_id']) != job['admission']['admission_id']
                or job['provider_effect_id'] is None
                or fingerprint(row['intent']['payload']['jobs'].get(item.segment_id)) != fingerprint(job['source'])
            ):
                raise AuthorityRefused('original published source/admission mismatch')
            ticket = SimpleNamespace(
                units=units,
                handoff=handoff,
                identity=item.segment_id,
                attempt=upload['attempt_token'],
                effect=str(job['provider_effect_id']),
                owner=job['owner_key'],
                source=job['source'],
                admission=job['admission'],
                conversation_ids=row['intent']['conversation_ids'],
            )
        # No SQL connection/owner guard crosses fresh A1/walk/A2, the actual
        # SDK read or its post-read authority check. No transcript cache.
        artifacts = ProviderUpload(ticket, self.storage, lease_seconds=self.lease_seconds).artifacts(
            self.bucket, self.secret
        )
        return artifacts.load_result(item, uri, read_budget=read_budget)
