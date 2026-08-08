# Rule 17 — the wire-path fence

> **A settled wire path is SERVED by exactly one route module.** A file that
> both stands up an HTTP server and names a registered wire path in code must
> reach that path through the registered route module — it may not answer the
> path itself.

Status: **PROVISIONAL, HELD.** Landed 2026-08-08 with the W4 rebuild; it runs
immediately, per §8, and continues to run at full strength while held —
holding is not disabling. AUDIT-17 (non-author, 2026-08-08) completed the §8
audit and found the fence sound on every case DOOR checked, but found the
escape hatch's file-wide scope exploitable rather than merely imprecise; see
**AUDIT-17** below for the finding, the mutation that demonstrates it, and
exactly what unblocks promotion. The DOOR lane wrote it, so the DOOR lane
cannot promote it. If it fires on another lane, that is a swarm-wide blocker,
never something to route around, regardless of held status.

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

5. **The comment-stripping exemption — resolved by AUDIT-17.** DOOR flagged
   this as unproven: no file in the tree named a registered wire path only in
   prose while also constructing a server. AUDIT-17 constructed exactly that
   fixture (a server, plus `/v1/memories` appearing only inside a `//`
   comment, with the server's real routes pointing elsewhere) and confirmed
   two things by experiment, not by reading the regex: lint stays green
   against the real checker, and the identical fixture **fails** lint when
   `withoutComments()` is bypassed for rule 17's block only. The exemption is
   load-bearing, not decorative. Mechanised in
   scripts/lint-import-graph.test.ts ("rule 17 does not fire when the file
   only names the path in a comment").

## AUDIT-17 — non-author audit, 2026-08-08

Per §8, this fence stayed PROVISIONAL until a non-author read it against the
English statement above and audited its false positives. AUDIT-17 did that
work in an isolated lane worktree (`bin/omi-lane start audit17 platform`),
hand-applying every mutation below to the real source and to disposable
fixtures, watching lint fire or fail to fire, then reverting. DOOR's own four
red-proofs (retired door, unmounted door, stale row, hatch-is-load-bearing)
were re-run by hand against the real files and confirmed to still hold; they
are now also mechanised in scripts/lint-import-graph.test.ts alongside the
comment-stripping proof above.

**Verdict: HOLD.** Everything the doc claims is true — the checker enforces
exactly the English statement for every case DOOR's audit covered, the
one hatch in the tree (integration/adversarial/live-server.ts) is a real
client-plus-unrelated-probe, not a hole, and DOOR's nine-row false-positive
audit is complete for the platform tree (independently re-derived by grepping
every non-test `.ts`/`.tsx` file for the four server-construction forms:
same seven server-constructing files, same verdicts). But AUDIT-17 found one
new gap serious enough to hold promotion on, plus one lower-severity one
worth recording:

**1. The escape hatch is FILE-scoped, and that is exploitable, not just
imprecise (holds promotion).** The doc defends file-scoping as deliberate:
"the finding is file-scoped." That is true of the finding that earns a hatch,
but the hatch itself is checked with `text.includes(wirePathAllowMarker)` —
anywhere in the file, unconditionally, forever. Demonstrated: starting from
the real integration/adversarial/live-server.ts (which legitimately carries
`// wire-path-ok(...)` on its free-port probe), AUDIT-17 edited the *same*
probe's `fetch` handler to actually answer `/v1/memories` with a raw fixture
id — the exact defect class rule 17 exists to catch — while leaving the
existing, unrelated hatch comment untouched elsewhere in the file. Lint
stayed green. Reverted after confirming (`git diff` against the pre-mutation
file showed byte-identical restoration). Contrast with rule 16's
`port-composition-ok`, which is checked per construction-site line
(`hatched(index)`, the line or the line above) — a rule 16 hatch cannot mask
a second, unrelated violation added later in the same file; a rule 17 hatch
can, permanently, for every future edit to that file. This is the same shape
as the two defects this program has already found in guards: a compensating
mechanism (the hatch) that is not as strong, on the axis that matters
(scope), as the check it compensates for.
  - **What would unblock promotion:** scope the hatch to the server
    construction site, the same way rule 16 scopes `port-composition-ok` —
    require the marker on or adjacent to the matched `Bun.serve(`/`new
    Hono(`/etc. line, not merely present anywhere in the file. Re-run this
    same mutation (real handler added to an already-hatched file) against the
    tightened check and confirm it now fires while `live-server.ts` itself
    stays green.

**2. Substring match with no path-boundary awareness (recorded, not
blocking).** `code.includes(row.wirePath)` is a plain substring test.
Constructed fixture: a server answering a *different*, unregistered path,
`/v1/memories-legacy-export`, that merely contains `/v1/memories` as a
substring, with no import of the registered route. Lint fired, naming that
file as if it served the registered path. This is a false positive in the
same family as rule 16's banned-English-word defect, but weaker: no file in
the tree today has a path that collides this way, and the fix at the call
site is one `// wire-path-ok(<reason>)`. Recorded as a known limit, not a
promotion blocker on its own — it does not let a real door through, unlike
finding 1.

**3. Confirmed, not new: the fragment-assembly gap is real.** Constructed
`const path = "/v1/" + "memories"` inside a `Bun.serve` fixture that answers
that path with a raw fixture id and imports nothing from the registered
route. Lint stayed green — a true false negative, exactly as the "Known
limits" section already discloses with a citation to documented precedent of
an agent doing this to a regex elsewhere in this program. Not new, but
independently re-verified rather than taken on faith.

**Blast radius if this HOLD is wrong** (i.e., if finding 1 should not have
blocked promotion): the fix is a small, additive change to one helper
function in scripts/lint-import-graph.ts (mirroring code that already
exists for rule 16), verified by the same mutation used to find the gap. It
does not touch what the fence catches today — every case DOOR audited and
every case AUDIT-17 re-verified keeps firing exactly as it does now. Nothing
downstream depends on the *current* hatch granularity: the only hatch in the
tree today (`live-server.ts`) sits on the file's only server-construction
site, so tightening the scope from file to construction-site does not change
its outcome.

**What would unblock promotion:** land the construction-site-scoped hatch
described in finding 1, re-run finding 1's mutation and confirm it now fires,
re-run all existing red-proofs (mechanised in
scripts/lint-import-graph.test.ts) and confirm they still pass, then a
non-author re-reads the diff. Finding 2 does not block promotion but should
be noted in the same pass since the fix (a boundary-aware match, e.g. requiring
the character after the match to be `/`, a quote, or end-of-string) is cheap
and adjacent.
