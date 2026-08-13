# Route-free Firebase-authorized PostgreSQL graph runtime contract

Status: implemented and real-PostgreSQL qualified, inert by construction.

The production-shaped internal graph-read seam is
`drivers/postgres/firebase-authorized-graph-snapshot-runtime.ts`. It shares the
same fixed-query Firebase/PostgreSQL authorization constructor as the append
runtime but requests the `memories.read` capability. Its only operation is
`load(token, now)`.

After project-bound Firebase verification with revocation checking, the
runtime resolves the exact application credential/grant and coherent
account-control projection. It then invokes the authoritative graph snapshot
repository with the resulting sealed context. That repository opens its own
serializable transaction, locks and revalidates every authority coordinate,
and holds those locks through every awaited graph reconstruction query. A
preliminary authorization decision alone can therefore never release a graph
snapshot.

Successful output contains the internal `GraphSnapshot`, the exact
authorization-state digest, and the database transaction timestamp for later
generation binding. Its sealed context is retained only in a private WeakMap;
`projectFirebaseAuthorizedGraphSnapshotLoad` rejects structural lookalikes and
produces the branded application-default projection plus content-free identity,
grant, account-generation, and read-time coordinates. It does not fabricate an
MCP credential or grant. All transaction-time authority failures collapse to
one `authorization` denial; provider/persistence failures collapse to
`unavailable`.

The route-free product composition is
`drivers/postgres/firebase-authorized-memory-read-runtime.ts`. It loads and
projects before rendering, reloads after awaited rendering, runs the existing
application read core over two branded coherent projections, and performs one
last live Firebase/PostgreSQL load before returning canonical page JSON. Trace
output is buffered until that last fence. A changed authority, account
generation, graph generation, projection digest, or reader binding discards the
attempt; repeated drift returns one closed `invalidated` outcome. The runtime
returns no graph, projection, credential/grant object, attestation, citation
closure, or trace object and owns no route.

## Qualification

The pinned PostgreSQL 18.4 real-adapter test proves:

1. an active, separately persisted `memories.read` grant loads the exact
   account-local graph at sequence 6;
2. the returned authorization-generation coordinate is a lowercase SHA-256
   digest;
3. the graph owner is derived from the sealed context, never a load argument;
4. a new revoked read-grant revision becomes current after both preliminary
   authorization reads but immediately before graph reconstruction; and
5. the locked graph transaction returns a closed authorization denial and no
   snapshot;
6. `legacy`, `migrating`, `rolled_back_stranded`, unactivated `new`,
   `deletion_pending`, `deleted`, and conflicted account-control rows deny both
   the Firebase read and write runtimes before either can reach a third
   graph/ledger transaction; and
7. a transition from active to deleted immediately before the locked graph
   transaction denies and releases no snapshot.

The same real suite reports 8 passed, 0 failed, and 473 expectations, then
passes the PostgreSQL/Postgres.js parity corpus under pinned Bun 1.3.14 and Node
24.19.0. The local harness stops the managed runtime and preserves the labelled
synthetic volume.

The direct product runtime is implemented, real-PostgreSQL-qualified, and not
activated. Local focused and broad tests prove branded-authority refusal,
renderer/final-revalidation order, late-revocation silence, stable direct reads,
and unchanged QA behavior. A fresh `bun run test:postgres` on 2026-08-12 passed
9/9 real tests with 503 expectations, including a nonempty cited direct product
page over the separately granted application role, and passed the same
PostgreSQL/Postgres.js parity receipt under pinned Bun and Node. The managed
runtime returned to stopped state with its labelled synthetic volume preserved.
No persisted semantic projection is required. Any future persisted projection
remains a disposable derived view whose every support is authorized before
selection or ranking and revalidated before release. Public query-bearing
recall remains separately ratified.
