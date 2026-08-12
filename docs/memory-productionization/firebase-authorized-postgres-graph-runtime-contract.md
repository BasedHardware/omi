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

Successful output contains the internal `GraphSnapshot` plus the exact
authorization-state digest for later generation binding. It contains no
cursor, product projection, synthesized text, page, citation, trace, or public
wire bytes. All transaction-time authority failures collapse to one
`authorization` denial; provider/persistence failures collapse to
`unavailable`.

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
   snapshot.

The same real suite reports 5 passed, 0 failed, and 282 expectations, then
passes the PostgreSQL/Postgres.js parity corpus under pinned Bun 1.3.14 and Node
24.19.0. The local harness stops the managed runtime and preserves the labelled
synthetic volume.

This contract does not complete or activate the product read. A later unit
must project reader-visible state, render, bind cursor/generation coordinates,
repeat live authority validation after any awaited product I/O, and only then
release item, absence, completeness, citation, or trace bytes. Product
projection materialization subject and public query-bearing recall remain
separately ratified decisions.
