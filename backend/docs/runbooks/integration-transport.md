## Status and ownership

This is the integration-only extension of the merged integration controller.
Source review, exact-head green CI, canonical merge and current scoped release
admission are required before execution. SCA-2015 owns pipeline evidence
semantics and producers; SCA-2225 owns the controller boundary; SCA-2283 owns
admission, execution and rollback. Source publication alone qualifies none of
the post-roll proofs.

The default `post_wrap_guard: internal` remains fail-closed: its CLI refuses
before provider writes without an authenticated adapter. Captain ruling
SCA-2283 `01a1de4c-ad87-7cbc-a06e-9c04c19f1580` explicitly delegates this run's
post-wrap guard to Pipeline through `post_wrap_guard: external`. External mode
skips only the internal adapter, retaining all other controller checks.

The existing image-only consumer, listen and pusher routes remain Release's
routes. Their verified sequence and +20-minute consumer observation precede
integration. This extension does not replace those routes or claim that their
receiving revisions prove an integration generation. Root paging is independent
follow-up work; the accepted release reader remains in place.

## Protected source and candidate scope

The existing `gcp_backend.yml` production boundary recognizes an explicit
`service_images` value of `integration-canary=<immutable backend digest>`.
That selection defaults to the internal guard. The explicit external selection
is `integration-canary=<immutable backend digest>,post_wrap_guard=external`;
the existing input is parsed into the composite's `post_wrap_guard` input and
the controller's `--post-wrap-guard` prepare flag. Unknown modes and external
mode outside integration-only scope refuse. No omitted mode selects external.
It requires an exact source SHA, normal eligibility, Firestore readiness,
production approval and the existing noncancelling prod-train lock. It neither
adds a public workflow nor changes its triggers, jobs, runners or budgets.
An unbound internal adapter refuses at early prepare, before native
repair/probe or candidate mutation. External mode is an explicit captain-owned
delegation, never a caller-supplied assertion that a guard has passed.

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
20-minute CPU/request watch. Internal mode then waits for post-wrap evidence. `guard` can
re-evaluate a persisted decision; unavailable evidence withdraws current
qualification rather than retaining a stale success. Continuations are bound
to the same workflow run/attempt, workflow SHA, monotonic clock and private
journal; this does not authorize replay in a new run or host. Uncertain writes
never authorize another PUT. Native failure/cancellation recovery retains the
saved revision, including its 200/10 settings. No separate lock authority is
introduced.

External mode instead records `phase=external_guard_pending`,
`discovery.state=external_pending`, Pipeline as guard owner and Release as
rollback executor. Its sanitized `external_handoff` binds the actual receiving
revision/UID, source/digest/config hash, generation, run/attempt/control SHA,
verified 100% move time, verified 100/20 settings, provider-release false and
retained rollback identity. It does not claim a wrap, recount or healthy
post-wrap window. The four existing workflow artifacts remain the handoff.
The native HTTP/CPU windows and failure/cancellation recovery still run.

Pipeline's external guard is read-only, arms after a whole post-roll shared pass,
and posts `ROLLBACK` on SCA-2283 if the captain's permitted FreshGuard rule trips.
Release alone executes the saved 200/10 inverse. The controller's existing
rollback command requires its private same-run journal; it is not a durable
post-job rollback interface. That journal must not be exported. Before relying
on a guard after the ephemeral runner exits, Release must identify its approved
durable rollback handoff; this source does not invent cross-run lock or write
authority.

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

For internal mode, the required dependencies are the trusted ingestion adapter and a bound
producer for shared full-wrap, bounded complete recount, the 30-minute
ready-undiscovered guard and existing fresh-progress guard. SCA-2015 owns
identifying those existing producer inputs; SCA-2225 owns their authenticated
transport mapping; SCA-2283 supplies actual receiving/committer identities and
the post-roll handoff. No qualified fresh-progress input or established trusted
adapter has been supplied. Those are the qualification blockers requiring
producer evidence or captain disposition, not a new delivery metric. Under the
08:22 ruling those guard implementation dependencies belong to Pipeline's
external lane and do not silently turn external mode back into internal mode.

Captain ruling SCA-2283 `01a1de53-b889-73a6-9cad-177c8e123c1a`
permits the external guard to use FreshGuard alone when the separate stock
signal needs a new scan. Pipeline's 08:40 feasibility disposition selects that
permitted lane: no new scan or historical census substitutes for the absent
30-minute privacy-excluded stock baseline. This stated gap is not an unresolved
controller admission dependency for external mode.

The existing `FreshGuard.collect` rule is two consecutive >5% readings, with
stale (120 seconds), missing, unbound or zero-denominator evidence UNKNOWN.
After receiving revision/config verification, arming records the actual shared
cursor position and requires a complete circle back to that position with an
unchanged integration/worker committer vector. A timestamp-only wrap can finish
a pre-roll pass and is insufficient. Before arming, values and UNKNOWN are
observations only, not acceptance or rollback decisions. SCA-2015 owns the
external producer and its identity/completeness qualification; this controller
does not invent or assert that qualification.

True upload-to-durable-transcript latency remains **UNMEASURED**. Under captain
ruling SCA-2283 `01a1ddc7-ad39-75e0-a8de-ad7088463568`, its absence is explicitly
not a blocker to the narrow 100/20 recovery-default restoration. No delivery
field or delivery-producer requirement is added to this adapter. Existing
admission-to-commit, request/CPU or audio measurements are not substituted for
delivery. The external evidence scope follows the explicit FreshGuard-only
disposition above; default internal mode remains fail-closed.
No live acceptance, saving, clean-hour start, or five-day outcome is claimed.
