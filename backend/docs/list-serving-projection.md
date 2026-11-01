# Conversation and action list serving projection, version 1

The Python Firestore `Commit` surface writes small metadata projections beside
conversation/action sources, plus a random per-owner/family version in the
**same atomic commit**. It performs no reads. Source masks, preconditions,
transforms, transaction IDs/retries, and public SDK result lengths remain intact.
Document deletion also deletes its projected row atomically. Nested conversation
corrections and account/entitlement changes invalidate the appropriate versions.
Masked root patches limited to the exact platform telemetry fields written by
`record_user_platform` do not invalidate lists or append version writes. This
keeps authentication telemetry from defeating conditional polls, including when
Redis is unavailable. Mixed patches, unknown fields, root replacement/create,
and root deletion retain conservative invalidation of both families.

Paths under `users/{uid}`:

| Path | Meaning |
| --- | --- |
| `conversation_list_rows/{source_id}` | Small source metadata mask, no transcript/title/text |
| `action_item_list_rows/{source_id}` | Small source metadata mask, no task description/evidence |
| `list_serving_versions/{conversations,action_items}` | Random opaque `version`, 32 characters |

These are migration rows, **not a complete replacement collection**. Updating a
legacy source only projects the fields that were written. There is no backfill,
coverage claim, source-query change, or automatic serving cutover in this PR.
Deleting a user still uses the existing recursive wipe, with final head cleanup
after all source collections even when the root user is already absent. A root
user delete removes heads rather than recreating them. Rows stay under the same
user and source deletes remove the matching projection; no content is copied.

## Optional unchanged-poll check

`GET /v1/conversations`, `/v1/action-items`, and `/v1/dev/user/action-items` can
use `If-None-Match` without a new parameter or client release. After existing
authentication/scope dependencies and input validation, a matching validator
returns 304 with one version lookup and no list query. A changed full response
uses the existing source reader and emits a version-backed ETag only if a second version
lookup confirms that no mutation crossed the read. Truncated pages and pages
with locked conversations never get a validator: lock recovery must still run
when allowance rolls over without a source write. User, route, exact query,
authentication, server release, and rollout epoch
scope the validator. No response data is cached by this protocol.

Requests without validators add **zero marker reads**. Action-item requests
retain their existing cache/body ETag path. A full, unlocked conversation page
receives a random initial `lp0` tag: it cannot match a version-backed `lp1` tag.
An HTTP cache that returns that initial tag gets another ordinary source response
before it receives a stable `lp1` tag. This also holds if a source mutation crossed
the initial response; `lp0` can never directly produce a 304. Clients that never
return validators retain the original source-read count. Existing action body
ETag clients also graduate on their next source read. A changed conditional GET
adds two marker reads. A missing head is initialized once with create-only semantics
under the existing transactional destructive-operation fence (three additional
cold-path authority/head reads), without scanning/backfilling source rows or
overwriting a concurrent writer. A deletion or destructive-operation denial
falls back to the source reader; its authorization dependencies still apply.
Malformed heads, a lost baseline race or unavailable Firestore use the old reader.
There is no Redis dependency for the version check; existing caches are unchanged.

## Deployment and ramp owner

The rollout lead owns activation; this lane does not change production config.

1. Writer is **on by default**. `OMI_LIST_PROJECTION_WRITER_ENABLED=false` is
   the kill switch. Never turn a writer off while any reader epoch remains
   active; clear the reader epoch across serving processes first.
2. Conditional reads initially require `OMI_LIST_VERSION_EPOCH` to be set,
   plus the artifact's `OMI_BACKEND_RELEASE_SHA`. Empty epoch preserves the
   previous response behavior and adds no marker reads. This gate is required
   because a mixed fleet can commit source mutations without version writes.
3. Before T2 activation (2026-10-23 20:00Z), the lead must verify that all
   source-writing Python services/jobs import `database._client` and run this
   writer SHA, and audit for direct/non-Python and non-atomic `BatchWrite`
   source writers. The production tree currently uses neither `BulkWriter`
   nor `BatchWrite` for these sources. Do not activate if one is found.
4. After that attestation and a staging synthetic-account canary, the lead
   sets a unique epoch on a reader-enabled backend revision at 5% traffic,
   then expands to 100% by T3 (2026-10-24 08:00Z) after two hours of clean
   parity/read-cost/latency gates. The staging canary requires ordinary
   source-body equality, conditional 304 with no list query, and fresh 200
   after update/delete/correction. Use aggregate metrics in production; this
   lane never authenticates as a production user. A missed ramp date is a blocker.
5. Any writer rollback, disabled writer, or uncovered mutation path requires
   reader epoch removal before the change; re-audit and use a **new** epoch
   before reactivation. Release changes also invalidate validators.

## Attribution and economics

`omi_list_version_checks_total{origin,outcome}` uses only the three fixed HTTP
origins above; outcomes are `untracked`, `changed`, and `not_modified`. SDK
marker reads retain the HTTP origin in
`omi_firestore_billed_reads_by_origin_total`. Count marker reads in the net
comparison, and retain caller #7/#10 coverage rather than treating a missing
caller as a saving. The reads loop owns measurement and any lever/config ramps.

The 50M/day sprint number is an **unverified ceiling**. First-PR fleet savings
are **unknown** until conditional-request share and residual source reads are
measured over equal full-day windows. One successful 100-row fake poll changes
from 100 source reads to 1 version read; this is a mechanism test, not fleet
billing evidence. An unchanged legacy poll remains a source query/cache hit.
The shipped client-tree audit found no explicit `If-None-Match` literals; HTTP
caches may still revalidate automatically. Measure actual conditional-request
adoption before attributing or expanding this reader, rather than assuming the
ceiling is reachable in the first PR.

Added writes include one lazy baseline head per active owner/family, plus at most
one small projected row per changed source row and
one version per owner/family per atomic commit (account changes touch both).
Even a content-only source write invalidates its family, so transcription
activity may reduce the unchanged share. Include these writes, storage/index
cost, marker reads and live p95 in the loop's net ledger. Stop reader expansion
if parity fails or net economics cannot meet the measured residual target.

## Large server commits

The Python SDK uses the server `Commit` API. Its old 500-write count limit was
[removed on March 29, 2023](https://docs.cloud.google.com/firestore/docs/release-notes).
The [10 MiB request and per-document transform limits](https://firebase.google.com/docs/firestore/quotas)
still apply. This contract does not split a source transaction or change its
atomicity to satisfy a legacy write-count assumption.

`tests/integration/test_list_projection_emulator.py` exercises 450- and 499-source
commits and recursive deletes for both families against a loopback-only demo
emulator, including the expanded 901/999-write requests and unchanged SDK result
length. Run it through `backend/test.sh` with an explicit one-file list,
`BACKEND_PYTEST_MARK_EXPR=integration`, and
`firebase emulators:exec --only firestore --project demo-fs-p1 --config backend/tests/integration/firebase-list-projection.json`.
