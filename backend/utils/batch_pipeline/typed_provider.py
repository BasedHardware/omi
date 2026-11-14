"""Original-claim driver using the production provider admission/call phases.

Explicit composition only: the default Cloud Tasks consumer remains on its
existing lane. No per-unit outbox, document mirror or funding policy is added.
Unsupported/failing work keeps its original PG attempt and custody. A caller
must retain that claim for recovery; lease expiry never authorizes another POST.
"""

from dataclasses import replace
import math
import time

from database.jobstore.authority import AuthorityRefused
from database.jobstore.result_upload_rows import ResultUploadRows, uri as upload_uri
from utils.batch_pipeline.contracts import WorkItem, WorkResult
from utils.batch_pipeline.provider_stt import ProviderSttStage, UnitOutcome, _Call, result_outcome
from utils.batch_pipeline.provider_stt_admission import SttRoute


class _OriginalAttempt:
    """Narrow phase protocol over the original SQL source, never a Store mirror."""

    def __init__(self, ticket):
        self.ticket = ticket
        # _prepare reads only the original intake's usage period through run.
        self.store = self

    def read(self, identity):
        ticket = self.ticket
        if identity != ticket.identity:
            raise AuthorityRefused('typed provider claim identity changed')
        with ticket.units.pool.connection() as conn, conn.transaction():
            job = ticket._job(conn)
            state = conn.execute(
                'SELECT state FROM privacy_effect_inflight WHERE effect_id=%s', (ticket.effect,)
            ).fetchone()
            if state != ('registered',):
                raise AuthorityRefused('original paid outcome unresolved; another POST forbidden')
            return dict(job['source'])

    def run(self, body):
        return body(self)

    def get(self, table, key):
        if table != 'intakes':
            raise AuthorityRefused('typed provider has no legacy queue store')
        with self.ticket.units.pool.connection() as conn, conn.transaction():
            job = self.ticket._job(conn)
            row = self.ticket.handoff._required_row(conn, job['recording_id'])
            self.ticket.handoff._guard(conn, row)
            return dict(row['intent']['payload']['intakes'].get(key, {}))

    def start(self, identity, token, now, service, **options):
        # The scheduled claim already minted the durable original attempt.
        # Actual START remains after allowance reservation, inside transcribe.
        source = self.read(identity)
        if (
            token != self.ticket.attempt
            or service != source['stt_route']['provider_service']
            or options.get('vendor_skipped')
        ):
            raise AuthorityRefused('typed provider requires its original non-silence vendor attempt')
        return {**source, 'provider_intent': {'token': token, 'service': service}}

    def hold(self, *args, **kwargs):
        raise AuthorityRefused('vendor hold needs its typed recovery adapter; original claim retained')

    def terminal(self, *args, **kwargs):
        raise AuthorityRefused('provider exhaustion needs its typed recovery adapter; original claim retained')


class TypedProviderStage(ProviderSttStage):
    """Run an already scheduled ordinary claim, with the real paid preflight.

    Reuses _prepare and _call_async, including both funding checks, inspection,
    health/cap reservation and original usage-period allowance. No legacy
    protocol settlement, timeout abandonment or recovery-object upload is used.
    """

    def __init__(self, adapter, identity, attempt, artifacts, *, effect_lease_seconds, partial_wait, health, **options):
        if health is None or not math.isfinite(partial_wait) or partial_wait <= 0:
            raise ValueError('explicit positive partial wait required')
        with adapter.units.pool.connection() as conn, conn.transaction():
            job = adapter.units._guarded_unit(conn, identity)
            route = ((job or {}).get('source') or {}).get('stt_route', {})
            if route.get('provider_reason') != 'unsupported_language' or route.get('provider_service') != 'modulate':
                raise AuthorityRefused('ordinary original provider cohort required')
        super().__init__(None, None, health=health, **options)
        # Preserve the actual served table/arming/failover selection. A mixed
        # vendor policy needs its own immutable attempt and projection adapter.
        if self._candidates(SttRoute(**route)) != ['modulate']:
            raise AuthorityRefused('typed failover routing is not qualified')
        ticket = adapter.fence_ticket(identity, attempt, lease_seconds=effect_lease_seconds)
        self.artifacts = artifacts(ticket)
        self.ticket, self.partial_wait = ticket, partial_wait
        self.protocol = _OriginalAttempt(ticket)

    def _attempt_token(self):
        return self.ticket.attempt

    def _guarded(self, segment_id, fn, *args):
        # Privacy/transport refusal retains SQL custody; never call the legacy
        # FS quarantine or supersede mutations from the parent driver's guard.
        return fn(*args)

    def _prepare(self, segment_id):
        # A publication may have won before a lost terminal COMMIT reply.
        # Resolve its original immutable URI without another paid send.
        rows = ResultUploadRows(self.ticket)
        with self.ticket.units.pool.connection() as conn, conn.transaction():
            rows.source(conn, pending=True)
            upload = rows.row(conn)
        if upload:
            if upload['phase'] != 'published' or not upload['generation']:
                raise AuthorityRefused('original upload outcome unresolved; retain custody')
            item = WorkItem(
                **{k: self.ticket.source[k] for k in WorkItem.__dataclass_fields__ if k in self.ticket.source}
            )
            uri = upload_uri(upload)
            payload = self.artifacts.load_result(item, uri)
            return self._complete(item, uri, result_outcome(payload))
        plan = super()._prepare(segment_id)
        if isinstance(plan, _Call):
            if plan.failure or not plan.inspected or not plan.inspected[2]:
                raise AuthorityRefused('typed inspection/silence disposition requires its custody adapter')
            return replace(plan, fence_ticket=self.ticket)
        return plan

    def _finish(self, plan, response, latency=None):
        if not isinstance(response, dict):
            raise AuthorityRefused('original paid outcome retained pending typed failure recovery')
        outcome = result_outcome(response)
        uri = self.artifacts.persist_result(plan.item, response)
        result = self._complete(plan.item, uri, outcome)
        from utils.batch_pipeline import vendor_route_metrics
        from utils.observability.reasons import VendorAttemptOutcome

        vendor_route_metrics.attempt(plan.service, VendorAttemptOutcome.OK, plan.item.duration_seconds)
        vendor_route_metrics.overflow_attempt(plan.route, plan.service, plan.item.duration_seconds)
        self._record_attempt(plan.service, VendorAttemptOutcome.OK, latency)
        return result

    def _complete(self, item, uri, outcome):
        accepted = self.ticket.complete(
            WorkResult(item.segment_id, uri, outcome).to_dict(), now=self.clock(), partial_wait=self.partial_wait
        )
        if not accepted:
            raise AuthorityRefused('original paid completion refused; custody retained')
        return UnitOutcome('done', 'processed')


async def run_claimed_provider(adapter, claim, artifacts, *, run_sync, effect_lease_seconds, partial_wait, **options):
    """Production driver seam for a scheduled claim; no scheduler policy chosen.

    Construction and all FS/GCS/PG/VAD work use the caller's managed executor;
    the paid HTTP request is awaited without holding that executor thread.
    """
    if await run_sync(_resolved_terminal, adapter, claim):
        return UnitOutcome('done', 'processed')
    stage = await run_sync(
        TypedProviderStage,
        adapter,
        claim['unit_id'],
        claim['attempt_token'],
        artifacts,
        effect_lease_seconds=effect_lease_seconds,
        partial_wait=partial_wait,
        **options,
    )
    return await stage.run_async(claim['unit_id'], run_sync)


def _resolved_terminal(adapter, claim):
    """A committed terminal row plus its original upload proves lost SQL reply.

    Missing rows/effects never stand in for a committed outcome. This path
    neither rereads transcript bytes nor mutates accepted custody.
    """
    with adapter.units.pool.connection() as conn, conn.transaction():
        job = adapter.units._guarded_unit(conn, claim['unit_id'])
        if not job or job['admission'] != claim['admission'] or job['source'] != claim['source']:
            raise AuthorityRefused('original claim source/admission changed')
        if job['state'] == 'pending':
            return False
        row = conn.execute(
            'SELECT phase,bucket,object_key,generation,admission_id FROM queue_provider_uploads '
            'WHERE namespace=%s AND unit_id=%s AND attempt_token=%s',
            (adapter.units.namespace, claim['unit_id'], claim['attempt_token']),
        ).fetchone()
        if (
            not row
            or row[0] != 'published'
            or not row[3]
            or (
                job['state'] != 'result_ready'
                or str(row[4]) != claim['admission']['admission_id']
                or job['result']['result_uri'] != f'gs://{row[1]}/{row[2]}#{row[3]}'
            )
        ):
            raise AuthorityRefused('original terminal outcome is not proved')
        return True


class TypedProviderRunner:
    """Default-off bounded dequeue; explicit existing scheduling inputs only.

    Returns recording identities for the customer-role grouped projection task.
    It creates no per-unit Cloud Tasks. The caller still owns durable discovery
    of admission intents, unresolved attempts and completed recording tasks.
    """

    def __init__(
        self,
        adapter,
        artifacts,
        *,
        count,
        backlog_share,
        lease_seconds,
        effect_lease_seconds,
        partial_wait,
        health,
        enabled=False,
        clock=time.time,
        **options,
    ):
        if (
            type(enabled) is not bool
            or type(count) is not int
            or type(backlog_share) is not int
            or not 0 <= backlog_share <= count <= 100
            or count < 1
            or not math.isfinite(lease_seconds)
            or lease_seconds <= 0
            or not math.isfinite(effect_lease_seconds)
            or effect_lease_seconds <= 0
            or not math.isfinite(partial_wait)
            or partial_wait <= 0
            or health is None
        ):
            raise ValueError('explicit bounded scheduling inputs required')
        self.adapter, self.artifacts, self.enabled = adapter, artifacts, enabled
        self.count, self.backlog_share, self.lease_seconds = count, backlog_share, lease_seconds
        self.effect_lease_seconds, self.partial_wait, self.clock = effect_lease_seconds, partial_wait, clock
        self.options = dict(health=health, clock=clock, **options)

    async def run_once(self, run_sync):
        if not self.enabled:
            return []
        claims = await run_sync(
            self.adapter.units.claim,
            self.count,
            now=self.clock(),
            lease_seconds=self.lease_seconds,
            backlog_share=self.backlog_share,
            ordinary_provider_only=True,
        )
        ready = []
        for claim in claims:
            outcome = await run_claimed_provider(
                self.adapter,
                claim,
                self.artifacts,
                run_sync=run_sync,
                effect_lease_seconds=self.effect_lease_seconds,
                partial_wait=self.partial_wait,
                **self.options,
            )
            if outcome.outcome == 'done' and await run_sync(self._sealed, claim['recording_id']):
                ready.append(claim['recording_id'])
        return list(dict.fromkeys(ready))

    def _sealed(self, identity):
        with self.adapter.units.pool.connection() as conn, conn.transaction():
            row = self.adapter.handoff._required_row(conn, identity)
            self.adapter.handoff._guard(conn, row)
            return row['phase'] == 'completed' and row['completion_hash'] is not None
