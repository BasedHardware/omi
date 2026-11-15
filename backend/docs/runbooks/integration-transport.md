## Status and ownership

This is an **unqualified integration-only extension** of the merged integration
controller. It is not an operator deployment instruction. Its CLI deliberately
refuses `prepare --integration-only` before any provider write because no trusted
pipeline evidence adapter is registered. Publishing this source does not remove
that refusal. SCA-2015 owns pipeline evidence semantics and producers; SCA-2225
owns this transport boundary; SCA-2283 owns admission and execution.

The existing image-only consumer, listen and pusher routes remain Release's
routes. Their verified sequence and +20-minute consumer observation precede
integration. This extension does not replace those routes or claim that their
receiving revisions prove an integration generation. Root paging is independent
follow-up work; the accepted release reader remains in place.

## Protected source and candidate scope

The existing `gcp_backend.yml` production boundary recognizes an explicit
`service_images` value of `integration-canary=<immutable backend digest>`.
It requires an exact source SHA, normal eligibility, Firestore readiness,
production approval and the existing noncancelling prod-train lock. It neither
adds a public workflow nor changes its triggers, jobs, runners or budgets.
An unbound evidence adapter refuses at the early prepare step, before native
repair/probe or candidate mutation. This selector is not presently deployable.

Only integration is cloned from its actual retained Ready revision
`backend-integration-provfix-off1114`. The inverse must contain exactly the
ruled 200-row/10-second overrides. The candidate removes those two overrides,
proves the admitted source defaults are 100/20, and refuses an OCI image baking
either override. Existing literals and secret references are retained, with
only the already disposed quality, provider, backoff and source-stamp decisions.
Resources, scale, sidecars and service account are cloned. Other services have
no template update or traffic move in this profile.

`stage` persists one verified 25% CAS and a monotonic five-minute hold.
`complete` consumes that hold, performs one verified 100% CAS and the separate
20-minute CPU/request watch, then waits for post-wrap evidence. `guard` can
re-evaluate a persisted decision; unavailable evidence withdraws current
qualification rather than retaining a stale success. Continuations are bound
to the same workflow run/attempt, workflow SHA, monotonic clock and private
journal; this does not authorize replay in a new run or host. Uncertain writes
never authorize another PUT. Native failure/cancellation recovery retains the
saved revision, including its 200/10 settings. No separate lock authority is
introduced.

## SCA-2015 evidence contract and missing adapter

The internal adapter receives an exact `binding` containing project, region,
service, source, immutable image, receiving revision/UID, service generation,
configuration SHA256, workflow run/attempt, control SHA and actual verified
100% move time. The proposed adapter result exposes only `state`,
`binding_sha256` and immutable `artifact_digests` in the sanitized receipt.
`qualified` or `rollback` requires artifact identities; malformed or mismatched
decisions refuse. The interface is an internal implementation boundary, not a
trusted producer by itself. A caller assertion or issue attachment cannot bind it.

SCA-2015's 07:47 proposal identifies these existing workflow artifacts:

- `artifacts/integration-canary-receipt.json`
- `artifacts/backend-serving-release-vector.json`
- `artifacts/backend-cloud-run-candidate-release-vector.json`
- `artifacts/backend-deployment-composition.json`

Their originating workflow run/attempt and immutable artifact digests must be
authenticated by the established ingestion path. That path has **not been
established**. The private journal must never be uploaded. The adapter must
also bind the participating worker/shared-cursor committer source/image/config
vector. It must validate receiving revision/config verification, then a
positive shared full wrap, then the bounded recount, in that order, without
splicing across generations. Pre-roll capability checking is distinct from
post-roll proof: an actual recount is not required before the roll.

Pipeline's existing counts-only definitions and authorized read bounds remain
authoritative. Truncation, missing pages, unresolved owner-head depth, sampled
absence, read limits and producer errors cannot become zero or healthy. This
transport does not invent a census TTL, counter, new scan, or freshness rule.
The required post-wrap rising-population and existing fresh-progress semantics
must be supplied by that authenticated adapter; HTTP CPU/request success is
not a replacement. Offline tests simulate an adapter to test state and rollback,
and do not prove these production semantics.

The actual required dependencies are the trusted ingestion adapter and a bound
producer for shared full-wrap, bounded complete recount, the 30-minute
ready-undiscovered guard and existing fresh-progress guard. SCA-2015 owns
identifying those existing producer inputs; SCA-2225 owns their authenticated
transport mapping; SCA-2283 supplies actual receiving/committer identities and
the post-roll handoff. No qualified fresh-progress input or established trusted
adapter has been supplied. Those are the qualification blockers requiring
producer evidence or captain disposition, not a new delivery metric.

True upload-to-durable-transcript latency remains **UNMEASURED**. Under captain
ruling SCA-2283 `01a1ddc7-ad39-75e0-a8de-ad7088463568`, its absence is explicitly
not a blocker to the narrow 100/20 recovery-default restoration. No delivery
field or delivery-producer requirement is added to this adapter. Existing
admission-to-commit, request/CPU or audio measurements are not substituted for
delivery. The required wrap/recount/fresh-progress evidence is not relaxed.
No live acceptance, saving, clean-hour start, or five-day outcome is claimed.
