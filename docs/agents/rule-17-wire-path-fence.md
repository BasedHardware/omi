# Rule 17 — the wire-path fence

> **A settled wire path is SERVED by exactly one route module.** A file that
> both stands up an HTTP server and names a registered wire path in code must
> reach that path through the registered route module — it may not answer the
> path itself.

Status: **PROVISIONAL**, landed 2026-08-08 with the W4 rebuild. It runs
immediately. Per the swarm protocol §8 a new fence stays provisional until
someone **who did not write it** has read the check against the English
statement above and audited its false positives. The DOOR lane wrote it, so the
DOOR lane cannot promote it. If it fires on another lane, that is a swarm-wide
blocker, never something to route around.

Implementation: `WIRE_PATH_REGISTRY` in the platform repo's
scripts/lint-import-graph.ts, which runs in `bun test` and in `make l0`.

Paths below that begin `platform/`, `apps/`, `integration/` or `scripts/` are in
the SIBLING `platform` repo and are written unquoted on purpose:
`check_agent_doc_references.py` verifies backticked repo paths against this tree
only, and a pointer it cannot check should not be dressed up as one it can.

## The defect that wrote the rule, and why rule 16 could not see it

Rule 16 keys on registered **port types**. A door that composes no registered
type is invisible to it *by construction* — and one existed.

integration/server/serve.ts is the backend `make stack` and HOW-TO-RUN.md
actually boot. It answered `GET /v1/memories` — the settled client recall route
— from a handler written in that file, over an `McpProtocolPorts` object written
in integration/server/compose.ts. It composed nothing registered, so rule 16 was
green the entire time. Measured on that door before the rebuild:

| | the registered route | the third door |
| --- | --- | --- |
| public item id | `mem1_<64 hex>`, reader-scoped opaque ref | `retrieval-node-v1:seed-0000`, the raw fixture row id |
| citation | `cit1_<64 hex>` | `citation-v1:retrieval-node-v1:seed-0000` |
| page shape | ratified 0.2.0+ | a 0.1.1-vintage hand-built envelope |
| `POST /v1/memories` | 404, fixed `not_found` body | **200 with the full read payload** |
| `GET /v1/memories/` | 404 | 200 |
| `?limit=5&limit=101` | 400 `bad_request` | 200 |
| bare key, no `Bearer ` | 401 | 200 |

Publishing storage row ids as public identities is the exact defect class the
wave-1 read-door collapse (rule 16) was built to kill, live again on the one
surface humans and agents form impressions from. The 690-test suite was green
throughout, because every existing assertion exercised the *registered* route
and this was a second implementation of the same wire.

The file's own header claimed "every byte of transport, envelope, and validation
is the code under test." That sentence was false.

Ruled by fable, W4, 2026-08-08: rebuild on the registered composition, and *"key
the fence on the wire path as well as the port type"*.

## What the check does

Matched on **comment-stripped** text, in non-test `.ts`/`.tsx` files. It fires
only when **both** halves are true:

1. the file constructs an HTTP server — `Bun.serve(`, `Deno.serve(`,
   `new Hono(`, `createServer(`; and
2. it names a registered wire path.

It is satisfied by being the registered route module itself, or by importing it
— directly, or through a server factory listed in the row's `boundVia`.

A file that only **calls** the path is a client, not a door, and is deliberately
not the defect class: apps/service/bin/boot-acceptance.ts fetches
`/v1/memories` throughout and can never hand anyone a divergent public id.

Staleness is a failure, on rule 16's precedent: if the row's `servedBy` file no
longer names the path, the fence has quietly stopped fencing and says so.

Escape hatch: `// wire-path-ok(<reason>)`, **file-scoped**, because the finding
is file-scoped — "this file stands up a server AND names a registered path" is a
statement about the file, so the justification belongs at that granularity.

## Why an import check rather than a behavioural one

A behavioural pin is a second implementation plus a checker chasing an
open-ended surface — rule 16's rejected alternative restated one layer up, and
W4 rejected it again for this exact door. The undersampling was not
speculative: 690 green tests, route-hardening asserting GET-only on the real
route, and the booted server answering `DELETE /v1/memories` with 200.

Whether the doors actually agree is an assertion, not a fence question, and it
lives in platform/integration/adversarial/cross-door-identity.test.ts (live
wire) and platform/apps/service/composition/cross-door-identity.test.ts
(in-process).

## False-positive audit

Every non-test `.ts` in the platform tree that constructs an HTTP server, and
whether it names the registered path:

| file | server form | names `/v1/memories` in code | verdict |
| --- | --- | --- | --- |
| integration/server/serve.ts | `Bun.serve(` | yes | passes — imports apps/service/routes/memories |
| apps/service/bin/dev-server.ts | `Bun.serve(` | yes, in a printed `curl` hint | passes — imports ../app-facing |
| integration/adversarial/live-server.ts | `Bun.serve(` | yes, as a CLIENT | **the one hatch** — see below |
| apps/service/app-facing.ts | `new Hono(` | no | not triggered |
| apps/service/app.ts | `new Hono(` | no | not triggered |
| apps/qa/server.ts | `Bun.serve(` | no | not triggered |
| integration/control/fence-server.ts | `Bun.serve(` | no | not triggered |
| apps/service/bin/boot-acceptance.ts | none | yes | not triggered — a client |
| apps/service/routes/memories.ts | none | yes | the registered route itself |

**One hatch in the whole tree.** integration/adversarial/live-server.ts calls
`Bun.serve` to open and immediately stop a throwaway socket for free-port
discovery — it answers a constant empty body to every request — and separately
`fetch`es `/v1/memories` as a client. Both halves are true of the file and
neither is a door. The reason is inline at the probe.

## Known limits — stated so nobody over-trusts it

- **The server-construction list is syntactic and finite.** A door built on a
  framework not in that list — `express()`, `serve()` from a helper, a
  hand-rolled `net` listener — is invisible. The list covers every server form
  in the tree today (audited above); it is not a general HTTP oracle.
- **It cannot see a path assembled from parts.** `"/v1/" + "memories"` passes.
  There is documented precedent in this program of an agent string-splitting a
  route to dodge a regex, so this gap is real, not hypothetical.
- **It does not run over `core-foundation`.** The linter walks the `platform`
  tree only. `core/packages/dev-recall-stub/src/create_dev_recall_stub_server.ts`
  serves this path in THIS repo and is out of the fence's reach entirely; it is
  a declared stub, not a claimant to being the real backend, but a reader should
  know the fence does not cover it.
- **Registration is opt-in**, like rule 16's. A wire path gets a row when it is
  settled and served, not when it is first typed.

## Red-proofs (applied and observed failing)

1. **The retired door.** Restored the pre-rebuild integration/server/serve.ts
   over the new one (`git checkout HEAD~1 --`). Lint failed naming that file and
   that path. Restored; green.
2. **The rebuilt door, unmounted.** Deleted the `registerMemoryRoutes` import
   and its call from the new serve.ts, leaving the path constant in place. Lint
   failed on the same file. Restored; green.
3. **Stale row.** Pointed `servedBy` at apps/service/routes/qa.ts, which does
   not name the path. Lint failed with the stale-row message. Restored; green.
4. **The hatch is load-bearing, not decorative.** Renamed the marker in
   live-server.ts so it no longer matched. Lint failed on that file — which is
   also the evidence that the audited false positive is real and that the
   exemption is doing work rather than sitting next to a check that would pass
   anyway. Restored; green.

Not claimed: the comment-stripping half has **no** applied red-proof here. No
file in the tree today names a registered wire path only in prose while also
constructing a server, so the exemption is currently unexercised. It is
inherited from rule 16's shape rather than independently demonstrated, and an
auditor should treat it as unproven.
