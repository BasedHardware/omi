# Rule 17 — the wire-path fence

> **A settled wire path is SERVED by exactly one route module.** A file that
> both stands up an HTTP server and names a registered wire path in code must
> reach that path through the registered route module — it may not answer the
> path itself.

Status: **PROVISIONAL, HELD (round 9).** Landed 2026-08-08 with the W4
rebuild; it runs immediately, per §8, and continues to run at full strength
while held — holding is not disabling. Rounds 1–4 each found a working
bypass in a comment-marker escape hatch (file-wide scope; a bare substring
search; string-blindness in the shared comment stripper; no `${…}`
interpolation-depth tracking) and each fix left a smaller hole. **Round 5 is
a ruling, not a bypass:** the marker mechanism was replaced entirely with a
`WIRE_PATH_HATCHES` registry, keyed by `(file, line)` — see
**AUDIT-17 — round 5**. Round 6 found a gap in that replacement's own
granularity (two constructions on one physical line sharing a registry
key), fixed by making that shape an unconditional failure — see
**AUDIT-17 — round 6**. Round 7 found that the round-6 fix over-corrected:
the failure fired on ANY file combining two of the four server-construction
patterns on one line, including the ordinary, common
`Bun.serve({ fetch: new Hono().fetch })` idiom, whether or not the file
named the registered wire path at all — a false positive with tree-wide
blast radius, not a bypass, fixed by narrowing the *count* to
socket-binding patterns while keeping *detection* at all four — see
**AUDIT-17 — round 7**. Round 8 found that narrowing reopened round 6's own
class for the patterns it excluded: two independent, unbound `new Hono(`
routers sharing a line with an existing hatch are invisible to the
ambiguity check, because it now only counts socket binds — see
**AUDIT-17 — round 8**. Round 9 found that the round-8 fix restored round
6's protection but reintroduced round 7's shape at the root: the
"two constructions on one line" check still runs unconditionally, for
every file in the tree, independent of whether that file is relevant to
any registered wire path at all — so two unrelated, unbound routers
sharing a line, in a file with zero connection to `/v1/memories`, still
fail — see **AUDIT-17 — round 9**, including why this points at a fix
scoped to the root cause rather than the next per-pattern instance. The
DOOR lane wrote the original; a non-author (the
coordinator) wrote every fix and the round-5 replacement, and said so
explicitly rather than promoting their own work each time. If it fires on
another lane, that is a swarm-wide blocker, never something to route around,
regardless of held status.

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

**Escape hatch, current as of round 5 (`7a0602a844`): a row in
`WIRE_PATH_HATCHES`, keyed by `(file, 1-indexed line)`, not a comment.**
Everything below this paragraph through "Red-proofs" describes the mechanism
as it stood before round 5 and is kept as the historical record the audit
rounds refer back to — see **AUDIT-17 — round 5** for why the comment-marker
form was abandoned entirely rather than patched a fifth time, and
**AUDIT-17 — round 6** for the current mechanism's own audit. There is no
marker and no text is parsed to grant an exemption: `hatchedAt(index)` is
`WIRE_PATH_HATCHES.some((row) => row.file === shown && row.line === index + 1)`.
A row whose line no longer holds a server construction is itself a failure,
symmetric with a stale `servedBy` or `composedIn`. The construction site
keeps a short pointer comment that the checker deliberately does not read.

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

*(Superseded by round 2, below: both items were landed in `fd38dc5e33`, and
round 2 found a new defect in the mechanism that landed them.)*

## AUDIT-17 — round 2, non-author re-audit of `fd38dc5e33`, 2026-08-08

The coordinator landed a fix for round 1's finding — `fd38dc5e33`, "rule 17:
scope the escape hatch to the server, not the file" — and explicitly declined
to promote their own work: "I am not promoting rule 17 — I wrote this fix, so
that is not my call." This section is that re-audit, done in a fresh
`bin/omi-lane` worktree, not trusting the landing commit's own transcript for
any of the four claims it made.

**Every claim in `fd38dc5e33`'s commit message was independently
reproduced:**

- Mutation 8 (a second, unhatched `Bun.serve` added to the already-hatched
  integration/adversarial/live-server.ts, alongside the untouched
  legitimate probe) — re-applied by hand to the real file. **Fires**, naming
  `live-server.ts:71`. Reverted; `diff` against the pre-mutation file was
  empty.
- Unmounting the registered route from `serve.ts` while keeping the path
  string — re-applied by hand. **Fires**, naming the construction line
  (`serve.ts:115` under my exact mutation shape; the coordinator reported
  `:120` under theirs — the four-line delta is fully explained by which lines
  each of us deleted versus commented out, not a discrepancy in what fires).
  Reverted; `diff` against the pre-mutation file was empty.
- A server answering `/v1/memories-legacy-export` — constructed as a
  standalone fixture. **Correctly green.**
- Reverting the fence to file-wide (via a small patch to
  scripts/lint-import-graph.ts, not a `git checkout`, so the two new
  round-1 tests stayed in place) — **exactly one** of 12 tests goes red (the
  mechanised mutation-8 test); 11 pass. Reverted.

**The trailing-slash design call.** `/v1/memories/` deliberately still
counts as the registered path because it is the registered route's own
documented 404 case, and a rogue door answering it 200 is the same defect
class rule 17 exists to catch, not a collision to exempt. Verified directly:
a fixture serving `/v1/memories/` with a raw fixture id fires; a fixture
serving `/v1/memories-legacy-export` does not. Agreed — no pushback.

**The `hatchedAt` walk-up-the-comment-block design call.** Confirmed correct
and necessary, not a quiet widening: the real hatch in `live-server.ts` is a
four-`//`-line block with the marker on the *first* line. A strict
`index - 1`-only check (rule 16's rule) would reject it. Verified: a marker
separated from the construction site by a blank line, or by any non-comment
line, is **not** honoured (fails closed) — confirmed by direct mutation, not
assumed from reading the code.

### New finding: the construction-line hatch check is not comment-aware — a real bypass, more severe than round 1's

The coordinator asked me to attack three specific shapes. The first two fail
closed (safe, if occasionally over-strict about formatting a legitimate
justification); the third is a real, unauthenticated bypass:

1. **Marker separated from the construction by a blank line.** Fixture:
   `// wire-path-ok(...)` then a blank line then `Bun.serve(...)` naming
   `/v1/memories` with a raw fixture id, no import of the registered route.
   **Fires** — the walk-up stops at the blank line and treats the site as
   unhatched. Safe direction (rejects a would-be-legitimate hatch; does not
   admit a rogue one).
2. **Marker inside the object literal, on a line below the construction
   line.** Same fixture shape, marker moved to a line inside the `{ ... }`
   after `Bun.serve({`. **Fires** — `hatchedAt` only looks at the
   construction line itself and lines *above* it; a marker below is never
   found. Safe direction, same as (1).
3. **Marker inside a plain string literal, not a `//` comment, on the
   construction line itself.** Fixture:
   ```
   const rogue = Bun.serve({ port: 0, banner: "wire-path-ok(fake, not a real comment)", fetch: (req) =>
     new URL(req.url).pathname === "/v1/memories"
       ? Response.json({ id: "raw-fixture-row-id" })
       : new Response("", { status: 404 }) });
   ```
   **Does not fire.** No import of the registered route; no actual
   justification; the string `"wire-path-ok(fake, not a real comment)"` is
   ordinary data, not a comment. Confirmed the marker needs no `//` prefix
   at all — a field named anything, containing that substring anywhere in
   its value, on the same physical line as the construction, is sufficient.
   Confirmed the reverse holds correctly: the identical string placed on its
   *own* line above the construction (not the construction line itself) does
   **not** hatch it, because that line does not start with `//`.

**Root cause.** `hatchedAt`'s two halves are asymmetric:

```ts
if ((rawLines[index] ?? "").includes(wirePathAllowMarker)) return true;   // (A) not comment-aware
for (let above = index - 1; above >= 0; above -= 1) {
  const line = (rawLines[above] ?? "").trim();
  const isComment = line.startsWith("//") || line.startsWith("*") || line.startsWith("/*");
  if (!isComment) return false;                                          // (B) comment-aware
  if (line.includes(wirePathAllowMarker)) return true;
}
```

(B), the walk-up loop, requires each line to *start with* a comment token
before it will even look for the marker — that half is sound, and is why
attacks 1 and 2 fail closed. (A), the construction-line check, is a bare
substring search over the *entire raw line*, with no requirement that the
matched text sit inside a `//` span on that line. A trailing
`// wire-path-ok(...)` on the construction line was clearly the intended
shape, but nothing in the code requires the comment token to be present —
only the marker text, anywhere on the line, including inside a string.

**Severity, relative to round 1's finding.** Worse, not equivalent: round
1's gap required a *pre-existing, legitimate* hatch elsewhere in the same
file to hide behind. This one requires nothing — any single rogue file,
never previously touched, can self-exempt on the first write, with a string
that reads as data (a "banner", a log line, a field nobody would think to
audit) rather than as a claimed justification a reviewer might question.

**Not new, and out of scope for this rule, but worth recording:** modifying
the *existing* hatched construction's own behavior (rather than adding a
second, separate construction) is not caught by any version of this fence,
round 1 or round 2 — I tested editing `live-server.ts`'s hatched probe's own
`fetch` handler in place, so it also answers `/v1/memories` with a raw
fixture id, and lint stayed green throughout. No purely syntactic checker
can verify that a hatch's prose reason still describes the code beneath it;
that is what PR review is for, and rule 16's `port-composition-ok` has the
identical property. Flagging it so nobody mistakes the fence for covering
this case, not proposing it as a new blocker.

### False-positive sweep, round 2

Reran the full server-construction grep; `live-server.ts` remains the only
file with a real (non-test, non-checker) hatch marker. `fd38dc5e33`'s new
`namesWirePath` boundary check verified directly: `/v1/memories-legacy-export`
green, `/v1/memories/` fires (by design, per above).

One imprecision found, **confirmed pre-existing, not a round-2 regression**
(re-ran the identical fixture against the round-1 checker, commit
`5d788a2b02`, before `fd38dc5e33`'s hatch-scoping change — it also fired):
a file with two *unrelated* server constructions — one legitimately serving
something else entirely, one absent altogether, plus a plain client `fetch`
call to `/v1/memories` elsewhere in the file — fires, blaming the unrelated
server's construction line. Root cause: `standsUpAServer` and `namesWirePath`
are still file-wide conditions; only the *hatch* resolution became per-site
in `fd38dc5e33`. No file in the tree today has this shape (`live-server.ts`
has exactly one server construction, so it is not exposed to this). Recorded
as a known limit, not a blocker — nothing today depends on the current
behavior, and it errs toward flagging rather than missing a door.

### Verdict: HOLD (round 2)

**What would unblock promotion:** make the construction-line hatch check
(A) as comment-aware as the walk-up check (B) already is — for example,
require that the marker survive on the *comment-stripped* version of that
one line be *absent* while it is present on the raw line (i.e., the marker
occurs only inside text `withoutComments()` would blank), rather than a bare
`rawLines[index].includes(...)`. Re-run attack 3 against the tightened
check and confirm it now fires while the real `live-server.ts` hatch — a
genuine trailing-adjacent `//` block — still passes. Re-run all existing
red-proofs. A non-author re-reads the diff.

**Blast radius if this HOLD is wrong:** small, same shape as round 1 — the
fix is additive to one helper, does not change any case already audited as
firing correctly, and the tree's one real hatch is a `//` block, not a
string, so tightening this does not touch it.

**What is still open after this round, stated plainly:** the construction-
line string-literal bypass (blocking). The pre-existing multi-server
false-positive imprecision (not blocking, recorded). The
same-construction-behavior-drift gap (not this fence's job; recorded so
nobody assumes it is covered).

## AUDIT-17 — round 3, non-author re-audit of `b9e0c9a915`, 2026-08-08

The coordinator reproduced round 2's finding before fixing anything, landed
`b9e0c9a915` ("rule 17: the hatch marker must be in a comment, not a string
literal"), and disclosed — unprompted — that their first test for it was
itself wrong: the fixture placed the marker three lines below the
construction line, so it was never on the line `hatchedAt` searches; the
test passed for the wrong reason, and only the isolation proof (revert the
fence, expect exactly one red — it came back 14/14 green) caught it. They
rewrote the fixture and asked to have neither claim taken on trust. This
section is that independent re-verification, done in a fresh `bin/omi-lane`
worktree.

**Every claim in `b9e0c9a915`'s commit message was independently
reproduced, each against the real files or a standalone fixture, not the
landing commit's own test:**

- String-literal marker on the construction line (`banner: "wire-path-ok(fake)"`)
  → **fires** (was green under `fd38dc5e33`).
- A genuine trailing `// wire-path-ok(...)` comment on the construction line
  → **stays green.**
- The real four-line hatch in integration/adversarial/live-server.ts
  → **stays green** (confirmed on the clean tree; nothing touches it).
- Round 1's mutation 8 (second, unhatched server added to the already-hatched
  file) → **still fires**, naming the correct construction line. Reverted;
  diffed byte-identical.
- Reverting the construction-line check to the old bare substring test → the
  suite goes from 14 green to **exactly one red** — the new test written to
  close this exact bypass, and nothing else. Restored; 14/14 green.

**Whether `isCommentText` (derived from `withoutComments()`, replacing the
old `trimStart().startsWith("//")` walk-up predicate) is faithful to my
round-2 criterion or a widening: faithful, and an improvement.** My
criterion was stated for the construction line specifically; generalizing it
to the walk-up half means both halves now agree on the exact same
definition of "comment" — the one `withoutComments()` already uses
everywhere else in this checker — rather than two independently-maintained
heuristics that can drift, which is how this bug existed in the first
place. Verified this does not silently admit non-comment lines: a line
containing real code plus a trailing `//` comment is correctly still
rejected by the walk (its comment-stripped form is non-blank, so
`isCommentText` is false), matching the old behavior exactly. The one
behavioral difference found: a multi-line `/* ... */` block comment whose
continuation lines are not `*`-aligned is now correctly recognized as
comment text end-to-end, where the old line-prefix check would have stopped
partway through it. That is a widening, but in the safe direction — it
recognizes more *genuine* comments, not more non-comment text — verified by
construction (see below).

### New finding, round 3: `withoutComments()` has no notion of string or template boundaries, and the hatch check now inherits that

The coordinator asked me to try two shapes they had not tested. Both matter,
but for different reasons:

1. **A genuine trailing block comment, `/* wire-path-ok(...) */`, on the
   construction line.** Constructed as a standalone fixture. **Stays green**
   — a legitimate hatch in block-comment form is honoured, exactly as the
   trailing-`//` form is. Good: the fix does not accidentally favor one
   comment syntax over the other.
2. **A marker split across a template literal**
   (`` `${"wire-path-"}ok(fake)` ``). **Fires** — correct, and not really an
   attack on the hatch logic at all: the raw text never contains the
   contiguous substring `wire-path-ok(`, so it is not recognized as a
   marker by either the exploit path or the legitimate one. Nothing to fix
   here.

**A third shape, not on the coordinator's list, is a real bypass — narrower
than round 2's, but real:**

```ts
const rogue = Bun.serve({
  port: 0,
  banner: "/* wire-path-ok(fake, this is a string not a comment) */",
  fetch: (req) => new URL(req.url).pathname === "/v1/memories"
    ? Response.json({ id: "raw-fixture-row-id" })
    : new Response("", { status: 404 }),
});
```

**Stays green.** `withoutComments()` is `text.replace(/\/\*[\s\S]*?\*\//g, ...)`
— a plain regex over the raw source with no concept of string or
template-literal boundaries. It matches `/* ... */`-shaped text *anywhere it
appears literally*, including inside a quoted string, and blanks it exactly
as it would a real comment. Verified directly, isolated from the rest of the
checker:

```
RAW     : ...banner: "/* wire-path-ok(fake, this is a string not a comment) */"...
STRIPPED: ...banner: "                                                        "...
raw.includes(marker)      : true
stripped.includes(marker) : false
```

Both halves of the round-2 predicate (`raw.includes(marker) &&
!stripped.includes(marker)`) are satisfied — not because the marker is in a
real comment, but because `withoutComments()` cannot tell a string
containing comment-shaped text from an actual comment.

**Severity, relative to round 2.** Lower, not absent. Round 2's bypass
needed nothing but an ordinary string containing the marker text — the kind
of collision that could occur without any intent to evade. This one needs
the specific `/* */` delimiters wrapped around the marker *as literal string
content*, which is unusual enough to draw a reviewer's eye ("why does this
banner field contain comment syntax?") and implausible by accident. It is
closer to a deliberate-evasion shape than a collision shape — but this
program has documented precedent of deliberate evasion under pressure
(string-splitting a route to dodge a regex), so "a reviewer would probably
notice" is not the same guarantee a structural fence is supposed to provide,
and it is exactly the shape of adversarial probe this round's mandate asked
for.

**Root cause is broader than this one hatch.** `withoutComments()` is used
throughout this checker — the corpus-path check, the storage-provenance
identifier check, rule 16's port-registry content matching, and now rule
17's hatch — and every one of those uses inherits the same string-blindness.
For content-matching uses (does this file *mention* a forbidden path or
identifier), a string that looks like a comment can only cause a
**false negative** on detection, which is the same class as the already-
disclosed fragment-assembly gap and is treated as a known limit rather than
a blocker. Using the identical primitive to **grant an exemption** is a
different risk profile: a false negative there does not just fail to catch
one occurrence, it turns off the fence entirely for that construction site.
That distinction — detection missing something once versus a hatch
suppressing everything — is why this is flagged as blocking for the hatch
specifically, while the same underlying limitation is not reopened as a
blocker for rule 16 or the other checks that were not part of this audit's
mandate. (Worth noting, out of scope to fix here: rule 16's own hatch,
`(rawLines[index] ?? "").includes(portCompositionAllowMarker)`, never
adopted round 2's comment-awareness at all and remains fully open to round
2's plain-string bypass. Flagging for whoever next touches rule 16; not
re-auditing it under this mandate.)

### Verdict: HOLD (round 3)

**What would unblock promotion:** give the hatch check — construction line
and walk-up block alike — a definition of "comment" that understands string
and template-literal boundaries, so `/* */`-or-`//`-shaped text inside a
quoted value is never treated as live comment syntax. This does not require
rewriting `withoutComments()` for the whole checker; a small, self-contained
scanner used only by `hatchedAt` (track whether each character position is
inside a string/template literal before checking for comment-introducing
tokens) is sufficient and testable in isolation. Re-run this round's fixture
against the tightened check and confirm it now fires, confirm the real
`live-server.ts` hatch and the genuine block-comment case both still pass,
re-run all existing red-proofs, non-author re-reads.

**Blast radius if this HOLD is wrong:** small. The fix is additive and
narrowly scoped to the hatch predicate; it does not change any case already
verified as firing or passing correctly in rounds 1–3, and the tree's one
real hatch is an ordinary `//` block with no string literals near it, so
tightening this does not touch it.

**What is still open after this round:** the string/template-boundary
bypass on the hatch check (blocking). Everything recorded as open after
round 2 — the pre-existing multi-server false-positive imprecision, and the
same-construction-behavior-drift gap — remains open and unchanged; neither
was touched by `b9e0c9a915`. Additionally noted: rule 16's own hatch shares
round 2's now-fixed-for-rule-17 vulnerability and was not part of this
audit's mandate to fix.

## AUDIT-17 — round 4, non-author re-audit of `1d2d62eb80`, 2026-08-08

The coordinator reproduced round 3's finding before fixing it, landed
`1d2d62eb80` ("rule 17: the hatch needs two independent mechanisms to
agree"), and disclosed two things unprompted: my own round-3 repro fixture
did not reproduce my own finding (marker three lines off the line
`hatchedAt` searches — the same placement mistake I had flagged in round 2),
and their own first test for the walk-up half of their fix had an identical
defect (a broken, non-contiguous template block that passed for the wrong
reason). Both were caught by their isolation proof, not by inspection. This
section applies that same discipline to my own new fixtures below —
everything is instrumented and isolation-proofed, not just run once and
read as green or red.

**All eight red-proofs in `1d2d62eb80`'s commit message were independently
reproduced, each with a fixture I built myself:**

- Block-comment-in-string on the construction line → **fires** (was green
  under `b9e0c9a915`).
- Plain-string marker on the construction line → **still fires.**
- A template line contiguous with the construction, containing a fake
  `// wire-path-ok(...)` line → **fires** (this is round 3's own new-bypass
  finding, still closed).
- A genuine trailing line-comment hatch → **stays green.**
- A genuine trailing block-comment hatch → **stays green.**
- The real four-line hatch in live-server.ts → **stays green.**
- Dropping `commentMask` from the construction-line check → exactly **1 of
  18** tests goes red (the block-comment-in-string test, and only it).
  Restored; 18/18 green.
- Dropping `commentMask` from the walk-up check → exactly **1 of 18** tests
  goes red (the contiguous-template test, and only it). Restored; 18/18
  green.

**The disclosed regex-literal shape, tested as asked:** a regex literal
containing a quote (`/["']/`) placed before a genuine trailing
`// wire-path-ok(...)` comment on the same line opens a spurious string
state exactly as documented, and the fence **fires** — rejecting what was
meant as a legitimate hatch. Confirmed fail-closed, not a bypass, matching
the disclosed known imprecision precisely.

### New finding, round 4: `commentMask()` has no concept of `${…}` interpolation depth, and a single unmatched backtick inside one desyncs it

The coordinator asked me to try "a marker inside a `${}` interpolation
within a template." The straightforward version of that is not a bypass —
verified first:

```ts
const rogue = Bun.serve({ port: 0, banner: `x${"wire-path-ok(fake)"}y`, fetch: … });
```

**Fires**, correctly: `withoutComments()` never blanks this text in the
first place (there is no `/* */`-or-`//`-shaped substring anywhere in it),
so the round-2 predicate alone already rejects it regardless of
`commentMask`.

**A more devious version of the same shape is a real bypass.**
`commentMask()`'s handling of `"template"` mode has no notion of `${…}`
nesting at all — once it enters template mode at an opening backtick, it
scans character-by-character for the next literal backtick to exit,
treating everything in between (including a `${…}` interpolation's own
content) as undifferentiated template text. A *single, unmatched* backtick
appearing inside an interpolation — for instance, the opening backtick of a
tagged template literal used as the interpolation's value — is read by the
scanner as the *outer* template's closing backtick. That desyncs tracking:
the scanner falls back into `"code"` mode one backtick early, and if a real
`//` or `/*` immediately follows in the text (which, from the true parser's
perspective, is still inside the interpolation or the outer template's
body), the scanner recognizes it as a genuine comment and marks it in the
mask — comment-shaped text that was never a comment, now indistinguishable
from one that is.

Minimal, syntactically-invalid demonstration first (proves the mechanism
in isolation, instrumented directly against `commentMask`'s own output —
`inRealComment` returns `true` and the mask is `true` across the entire
marker span):

```ts
const rogue = Bun.serve({ port: 0, banner: `${x`}//wire-path-ok(fake)
` }, fetch: (req) => /* … */ });
```

That fixture fails to compile (`error TS1160: Unterminated template
literal`), so its practical severity would be capped by `pnpm verify`'s
build step even though the lint check itself is fooled. Pushed further to
close that gap — **this is fully valid, type-checking TypeScript, using
only a real standard-library global, and it still bypasses the fence**:

```ts
const rogue = Bun.serve({ port: 0, banner: `${String.raw`}//wire-path-ok(fake)
` }rest`, fetch: (req) =>
  new URL(req.url).pathname === "/v1/memories"
    ? Response.json({ id: "raw-fixture-row-id" })
    : new Response("", { status: 404 }) } as any);
void rogue;
```

`bunx tsc --noEmit` reports zero errors on this file. The lint check exits
0. Instrumented directly: `namesWirePath` correctly reports `true`, the
server construction is correctly located, and `hatchedAt` returns `true`
for a construction that, at runtime, would answer `/v1/memories` with a raw
fixture id — the `Response.json(...)` branch is reachable and untouched by
any of this; only the hatch determination is fooled. (The `as any` cast
routes around Bun's server-options type, and `String.raw` is used purely as
a syntactically-valid tag function to produce the unmatched backtick — no
fictional declarations, no invalid syntax.)

**Severity relative to rounds 2 and 3.** Narrower than either, in the sense
that matters for accidental collision — nobody writes `` `${String.raw`}…`` ``
by accident, and it reads as bizarre on sight, more so than round 3's
`/* … */`-in-a-string. But it is not a syntax-error curiosity either: it
compiles cleanly, type-checks cleanly, and a determined author (human or
agent, and this program has documented precedent of the latter deliberately
evading a regex) could construct it. The underlying flaw is structural, not
a freak coincidence: `commentMask()` was built and described as a
"string/template-aware scanner," and it is *not* actually aware of
interpolation nesting — the one JS construct most likely to contain a
backtick it cannot account for.

**Recommended fix, scoped conservatively rather than chasing full `${…}`
depth-tracking.** A recursive-descent tokenizer that correctly nests
interpolations is a much larger, more failure-prone undertaking than
anything landed in rounds 1–3, and is exactly the kind of complexity this
fence has repeatedly and correctly avoided (see "Why an import check rather
than a behavioural one"). The narrower fix: treat any line — construction
line or walk-up block — that contains a backtick anywhere in its raw text
as **ineligible** for the hatch, full stop, rather than attempting to
resolve what is inside or outside a template. Template literals are rare in
this context by construction (route paths and hatch reasons are ordinary
string/comment text), and the real hatch in `live-server.ts` has no
backtick anywhere near it, so this costs nothing today and removes the
entire class rather than patching one more instance of it.

### Verdict: HOLD (round 4)

**What would unblock promotion:** land the conservative fix above (or an
equivalent that provably closes the whole class, not just this instance),
re-run this round's `String.raw` fixture against it and confirm it now
fires, confirm the real `live-server.ts` hatch and both genuine
trailing-comment forms (line and block) still pass, re-run all existing
red-proofs, non-author re-reads.

**Blast radius if this HOLD is wrong:** small, same shape as every prior
round — additive, does not touch any case already verified correct, and the
tree's one real hatch has no template literal anywhere near it.

**On the coordinator's question — was it too cautious not to fix rule 16's
identical round-2-class gap in this commit?** No. Rule 16 carries its own
`PROVISIONAL` status and its own false-positive audit trail
(`docs/agents/rule-16-port-registry.md`); folding an unaudited fix for a
different fence into a commit whose evidence is rule 17's would blur which
audit actually verified which change, which is exactly the kind of
attribution confusion this program's evidence discipline exists to prevent.
Filing it for rule 16's own promotion pass is correct, not overcautious —
if anything, doing otherwise would have been the shortcut.

**What is still open after four rounds:** the `${…}` interpolation-depth
bypass in `commentMask()` (blocking). Everything recorded as open after
round 3 — the pre-existing multi-server false-positive imprecision, the
same-construction-behavior-drift gap, and rule 16's unfixed round-2-class
hatch — remains open and unchanged. Convergence is visible across rounds
2–4 (accidental collision, then deliberate-but-plausible, then deliberate
and syntactically unusual), which is the shape the coordinator predicted;
it does not yet warrant treating the fence as sound, because each round has
found a real, working bypass, not a diminishing false alarm.

## AUDIT-17 — round 5, ruling: the comment marker is the wrong mechanism

After round 4, the coordinator asked the audit to rule on something bigger
than one more instance: rounds 2–4 were all the same question — *is this
marker really inside a comment?* — answered a little better each time and
broken again. The question itself does not have a bound short of a real
lexer, and the coordinator did not want to write one, correctly: a
`${…}`-depth-tracking tokenizer is a bigger, more failure-prone thing than
anything this fence had landed, and three consecutive bypasses in the same
place are an argument against more parsing, not for it.

**Ruling: replace the comment marker with a registry, `WIRE_PATH_HATCHES`,
keyed by `(file, line)` — not by file alone.** Reasoning:

- **No bound exists for "is this text really a comment," short of a real
  lexer.** Restricting hatches to whole-line-only comments was considered
  and rejected as a half-measure: it closes the same-line attacks (rounds
  2–3 and round 4's construction-line case) but the walk-up direction still
  needs to know whether the checker is currently inside an unclosed
  multi-line string/template from a prior line — exactly the stateful
  tracking problem round 4 exploited, just moved to a different question.
  There is no cheaper text-based fix that is not itself another round.
- **A registry removes the class instead of shrinking it.** With no marker
  text anywhere in the exemption path, there is nothing to smuggle in a
  string, a template, or an interpolation, because nothing is read from
  application code at all. Exempting a site becomes a visible diff in the
  one file every reviewer already watches, not a comment in application
  code that can be worded to look incidental.
- **The coordinator's first sketch mirrored `PORT_REGISTRY`'s shape — file
  path plus reason — and that specific symmetry is wrong for rule 17.**
  Rule 16's subject is "which module owns this port's composition," which
  is naturally a per-file question, and file-keying is correct for it. Rule
  17's subject is a specific HTTP server *instance*, and one file can
  legitimately hold several unrelated ones — `live-server.ts` already does,
  by design (its probe and its client-calling functions coexist on
  purpose). A file-keyed `WIRE_PATH_HATCHES` would silently **reopen round
  1**: the first legitimate row would again make the whole file a permanent
  blind spot for every server construction added to it later, just moved
  from a comment marker to a registry row.
- **Keying by `(file, line)` instead preserves per-construction-site
  granularity**, and the staleness discipline the checker already has twice
  over (`WIRE_PATH_REGISTRY.servedBy`, `PORT_REGISTRY.composedIn`) applies
  symmetrically: a row whose line no longer holds a server construction is
  itself a failure, not a silently-disabled fence.

**Cost, accepted rather than hidden:** the justification no longer lives
next to the code it justifies — the entire reason comment-form hatches were
chosen in the first place. A short, explicitly non-load-bearing pointer
comment at the construction site is the mitigation: it orients a reader
without being read by the checker, so it cannot be forged into granting
anything.

**Authority to rule on this:** this is the internal shape of a lint check's
escape hatch — it does not touch product behavior, user-facing copy, or a
wire contract, so it does not need fable. It is also cheap to reverse right
now, specifically because exactly one real hatch exists in the tree today;
that will not stay true indefinitely, which is itself a reason to make this
change now rather than after hatches accumulate under the comment form.

**Rule 16** was left with its own identical round-2-class gap (a bare
`rawLines[index].includes(marker)` check with no comment-awareness at all)
unfixed by this ruling, filed for rule 16's own promotion pass rather than
folded into rule 17's evidence — confirmed as the right call, not
overcautious: mixing an unaudited fix for a different, independently-tracked
fence into this evidence trail would blur which audit verified which
change.

Implemented and pushed as `7a0602a844`. See **AUDIT-17 — round 6** for its
independent re-audit.

## AUDIT-17 — round 6, non-author re-audit of `7a0602a844`, 2026-08-08

The coordinator reproduced the round-5 ruling as specified — including the
`(file, line)` correction to their own file-keyed sketch, credited
explicitly in the commit message rather than presented as their own idea —
and deleted the entire marker apparatus (`commentMask`, `markerInComment`,
`carriesTemplate`, `isCommentText`, the marker constant itself) along with
nine tests that exercised it, reasoning in the test file that a test for
deleted machinery is a claim about nothing, and that the three properties
that now matter (hatch honoured, stale row, second unhatched server) cannot
be fixture-tested without a test-only registry row becoming a permanent,
real exemption — a standing hole to test a fence. This section independently
re-verifies both the mechanical claims and that reasoning, then reports one
new finding in the replacement mechanism itself.

**All three hand-applied red-proofs in `7a0602a844`'s commit message
reproduced, each against the real files:**

- A second, unhatched `Bun.serve` added inside `freePort()` in the real
  integration/adversarial/live-server.ts, alongside the untouched,
  registry-hatched probe → **fires**, naming `live-server.ts:68` — exactly
  matching the commit message. Reverted; `diff` against the pre-mutation
  file was empty.
- The `WIRE_PATH_HATCHES` row's `line` moved from `67` to `65` (off the real
  construction) → **fires**, `stale WIRE_PATH_HATCHES row — no server is
  constructed here`. Restored.
- The row deleted entirely → the real, legitimate probe **fires**, naming
  `live-server.ts:67`. Restored; clean tree confirmed with `git status`.

**The deleted-test judgment is sound.** Read every one of the nine removed
tests against what they asserted: each named a specific marker/string/
template shape (`banner: "wire-path-ok(fake)"`, block-comment-in-string,
the interpolation desync, and their converses) that referenced functions —
`commentMask`, `carriesTemplate`, the marker constant — that no longer
exist in the file. A test asserting behavior of code that has been deleted
is not a regression guard for anything; keeping it would either fail to
compile (a false alarm forcing someone to delete it anyway) or silently
test nothing if left orphaned some other way. The reasoning for not
fixture-testing the three properties that do still matter is also sound and
not merely convenient: the checker's own registry, `WIRE_PATH_HATCHES`, is
declared once at module scope and read by every file the linter walks in
one pass — a test-only row added to make a fixture "hatched" would be a
**real, permanent exemption** for whatever `(file, line)` it names, active
every time the checker runs, not scoped to the test. That is a standing
hole, deliberately, to test the mechanism that closes standing holes.
Choosing hand-applied proof over that trade is correct.

### New finding, round 6: line-keying conflates "this line is exempt" with "this construction is exempt" — two constructions on one physical line share a key

`serverSites` — the list of exempt-able construction sites — is computed as:

```ts
const serverSites = codeLines
  .map((line, index) => (serverConstructionPatterns.some((p) => p.test(line)) ? index : -1))
  .filter((index) => index >= 0);
```

`.some(...)` records **whether** a line matches, once, regardless of how
many times it matches. Two independent `Bun.serve(...)` calls placed on the
same physical raw line produce exactly one entry in `serverSites`, for that
line index — and `hatchedAt` grants or denies the hatch per entry in
`serverSites`, not per regex match. A `WIRE_PATH_HATCHES` row naming that
line therefore covers **everything matched on it**, including a second,
unrelated, unhatched construction that happens to share the line.

Demonstrated against the real, already-hatched
integration/adversarial/live-server.ts (row: `line: 67`): rewrote the
probe's line to carry a second, genuine `Bun.serve(...)` call — serving
`/v1/memories` with a raw fixture id, semicolon-separated, same physical
line as the legitimate probe:

```ts
const probe = Bun.serve({ hostname: "127.0.0.1", port: 0, fetch: () => new Response("") }); const rogue = Bun.serve({ hostname: "127.0.0.1", port: 0, fetch: (req) => new URL(req.url).pathname === "/v1/memories" ? Response.json({ id: "raw-fixture-row-id" }) : new Response("", { status: 404 }) }); void rogue;
```

**Lint stays green.** Verified by instrumentation, not inference: the real
checker's own `serverConstructionPatterns` match this line twice
(`line67.match(/Bun\.serve\s*\(/g).length === 2`), but `serverSites`
contains exactly one entry, `66` (0-indexed) — `67` (1-indexed) — which
`WIRE_PATH_HATCHES`'s existing row for `live-server.ts:67` covers. Reverted;
`diff` against the pre-mutation file was empty.

**Severity.** Narrower than round 1 in one sense — it needs an existing,
legitimate hatch to piggyback on, same precondition as round 1 had — and it
additionally needs a specific, unusual formatting choice (two full server
constructions crammed onto one physical line) that a careful reviewer would
likely notice. But nobody writes two `Bun.serve(...)` configurations on one
line by accident, so this is squarely a deliberate-authorship shape, the
same class this program has documented precedent for (an agent
string-splitting a route to dodge a regex). And the underlying cause is
structural, not a coincidence: the registry's entire safety property rests
on "one line, one construction," and nothing in the checker enforces or
even checks that assumption.

**Recommended fix, in the same spirit as every prior round's fix — remove
the ambiguity, don't patch around it.** Count matches per line rather than
testing existence: if a line matches a server-construction pattern more
than once, that is **always** a failure, independent of any hatch —
"multiple HTTP server constructions on one line cannot be resolved
unambiguously by a line-keyed hatch; put each on its own line." This is
small, matches the registry's own "remove the class" philosophy exactly,
and costs nothing today: the tree's one real hatch has exactly one
construction on its line.

**False-positive sweep, round 6.** Reran the full server-construction grep;
`live-server.ts` remains the only file with a `WIRE_PATH_HATCHES` entry.
Nothing else in the tree has more than one server-construction match on a
single line, so this finding is not presently exploitable by accident
anywhere in the tree — consistent with its severity assessment above.

### Verdict: HOLD (round 6)

The round-5 ruling was right, and its implementation is faithful to the
specification, including the `(file, line)` correction — verified, not
assumed. Rounds 2, 3 and 4's bypass classes are genuinely unrepresentable
now, not smaller: there is no marker, so there is no text to be tricked
about. But the registry's own granularity has one uncovered edge, found by
testing the assumption the mechanism depends on rather than trusting that
removing text parsing removed every gap.

**What would unblock promotion:** land the per-line match-count check
described above (or an equivalent that provably closes the same class), 
re-run this round's two-constructions-on-one-line mutation against it and
confirm it now fires, confirm the real `live-server.ts` hatch and the three
existing hand-applied red-proofs all still pass, non-author re-reads.

**Blast radius if this HOLD is wrong:** small — a count check on an
already-computed value, additive, does not change any case already
verified correct across six rounds, and the tree's one real hatch already
satisfies "one construction per line."

**What is still open after six rounds:** the same-line multi-construction
gap in `WIRE_PATH_HATCHES` (blocking). Everything recorded as open after
round 4 that round 5 did not touch — the pre-existing multi-server
false-positive imprecision, the same-construction-behavior-drift gap, and
rule 16's unfixed round-2-class hatch — remains open and unchanged. Five
rounds have now found four working bypasses in a mechanism and one design
flaw in its replacement; none of the six were found by reading the code,
all six were found by mutating it and watching the result. That is this
program's own standing rule (§5: an assertion never seen red does not
count) applied to the guard itself, and it is why the fence is still held
rather than promoted on the strength of a design that is sound in
principle.

## AUDIT-17 — round 7, non-author re-audit of `185357b502`, 2026-08-08

The coordinator reproduced round 6's finding before fixing it — lint exit
0 against the real, already-hatched `live-server.ts`, matching what was
reported — then made two constructions on one line an unconditional
failure, independent of any hatch, on the reasoning that removing the
ambiguity beats patching around it, the same move that replaced the marker
with the registry. Two red-proofs in the commit message: the two-on-one-
line case now fires; the clean tree stays green. Both reproduced.

**This round's finding is a false positive, not a bypass — the first one
of that shape in seven rounds — and its blast radius is wider than
anything found so far, because it is not scoped to the wire path at all.**

`constructionsOn(line)` sums matches **across all four**
`serverConstructionPatterns` — `Bun.serve(`, `Deno.serve(`, `new Hono(`,
`createServer(` — indiscriminately:

```ts
const constructionsOn = (line: string): number =>
  serverConstructionPatterns.reduce(
    (total, pattern) => total + (line.match(new RegExp(pattern.source, "g")) ?? []).length,
    0,
  );
```

`new Hono(` constructs a router/app **value** — it does not open a socket
or listen for anything on its own; something else (`Bun.serve`,
`@hono/node-server`'s `serve()`, etc.) has to bind it before it is a
server at all. `Bun.serve({ fetch: new Hono().fetch })` — passing a fresh
Hono app's fetch handler straight into `Bun.serve` — is an ordinary,
common way to wire the two together, and it is **one** server, not two.
Written on one line, it matches both `Bun.serve(` and `new Hono(`, so
`constructionsOn` counts 2 and the round-6 check fires "two HTTP servers
are constructed on one line" against a file with exactly one.

Verified directly, with the fixture's irrelevance to the wire path
confirmed by construction rather than assumed:

```ts
const server = Bun.serve({ fetch: new Hono().fetch });
```

`grep -c "memories"` on this fixture returns 0 — no occurrence of the
wire path, the domain word, or anything wire-path-adjacent anywhere in it.
Lint fires anyway, naming line 1, with the exact "two HTTP servers"
message. This is **unconditional**: the check runs before, and independent
of, whatever `WIRE_PATH_REGISTRY`/`namesWirePath` would have found, so it
can fire on any file in the platform tree that happens to combine a
binder with a same-line Hono construction — not files near `/v1/memories`,
not files that stand up a door, any file at all. Confirmed the current
tree does not trip it today: `app.ts` and `app-facing.ts` both construct
`new Hono(` on their own line, not combined with a binder on the same
line — but that is incidental formatting, not a property the checker
enforces or that anyone writing ordinary code would know to preserve.

**Why this is a §8 "gate is the defect" case, precisely the shape the
mandate asked auditors to look for from round 1 onward:** the two
documented rule-16 defects that motivated this whole audit were "a guard
inspecting only keys while the banned thing sat in a value" and "a fence
banning an ordinary English word, firing on prose while catching no real
reference." This is the second shape exactly — a check that fires on
ordinary, working code because it cannot tell "two independent server
bindings" from "one binding whose argument happens to also match a
different pattern in the same list."

**Recommended fix, minimal and consistent with round 6's own reasoning
("remove the ambiguity, don't patch around it"):** the ambiguity round 6
is actually trying to close is specific to **binding** calls — the ones
that can independently open a socket: `Bun.serve(`, `Deno.serve(`,
`createServer(`. `new Hono(` never binds anything by itself and commonly
appears as an argument to one of the other three; it should not be summed
into the same count. Restrict `constructionsOn`'s "two or more is a
failure" check to matches within that three-pattern binder subset (still
summing multiple matches of the *same* binder pattern, which is the
actually-suspicious case — two independent `Bun.serve(` calls on one
line has no ordinary explanation). `new Hono(` stays exactly as it is for
`standsUpAServer`/site detection, which round 7 did not touch and has no
finding against.

**False-positive sweep, round 7.** No file in the tree today combines two
server-construction patterns on one line, so this is not presently firing
on trunk — but it is a live landmine for the next ordinary PR anywhere in
`platform/`, `apps/`, or `integration/` that writes this idiom, which
`app.ts`/`app-facing.ts` show is already in use in this codebase (just not
yet on a shared line with a binder).

### Verdict: HOLD (round 7)

Rounds 1–6's findings all stay closed; nothing here reopens any of them.
This is a new, narrower problem in the opposite direction from every prior
round: over-firing rather than under-firing, on ordinary code rather than
on a crafted bypass.

**What would unblock promotion:** scope the "two or more on one line"
check to the three binder patterns only, re-run this round's
`Bun.serve({ fetch: new Hono().fetch })` fixture against the tightened
check and confirm it stays green, confirm round 6's own two-`Bun.serve(`-
calls fixture still fires, re-run all existing red-proofs, non-author
re-reads.

**Blast radius if this HOLD is wrong:** small — narrowing which patterns
feed one counting function, additive to nothing, does not touch site
detection, hatch resolution, or staleness, and does not change any case
already verified correct across seven rounds.

**What is still open after seven rounds:** the unscoped binder-count false
positive (blocking). Everything recorded as open after round 4 that
rounds 5 and 6 did not touch — the pre-existing multi-server false-positive
imprecision, the same-construction-behavior-drift gap, and rule 16's
unfixed round-2-class hatch — remains open and unchanged. Seven rounds: six
real findings against the fence (four in the deleted marker mechanism, one
in the registry's granularity, one in this round's over-correction of that
fix) and one design ruling, none found by reading. The rate of new findings
has not gone to zero; the last two rounds were opposite-direction problems
in the exemption path's immediate neighborhood, which reads as the
mechanism settling, not as it being sound yet.

## AUDIT-17 — round 8, non-author re-audit of `d3389795f0`, 2026-08-08

The coordinator reproduced round 7's false positive before fixing it
(confirmed `grep -c memories` on the audit's own fixture returns 0, and
lint fired anyway), then split `serverConstructionPatterns` (unchanged,
still four — used for site *detection*) from a new `socketBindPatterns`
(three — `Bun.serve(`, `Deno.serve(`, `createServer(`, used only for the
*ambiguity count*), with an explicit converse test pinning that a
Hono-only door that never calls a binder still counts as a site.

**All four red-proofs in `d3389795f0`'s commit message reproduced, each
against the real files or a standalone fixture:**

- `Bun.serve({ fetch: new Hono().fetch })`, confirmed to contain zero
  occurrences of "memories" → **stays green** (round 7's false positive
  fixed).
- Two real `Bun.serve(` calls crammed onto the real, hatched
  `live-server.ts:67` (round 6's original mutation) → **still fires**,
  naming that line.
- A Hono-only door naming the path, never calling any binder → **still
  fires** — detection breadth is genuinely unchanged, not merely claimed.
- Reverting `constructionsOn` to sum all four patterns again (not just
  `socketBindPatterns`) → exactly **1 of 12** tests goes red — the
  round-7 false-positive test, and only it. Restored; 12/12 green.

**New finding, round 8: narrowing the count to `socketBindPatterns`
reopened round 6's exact class for the patterns it excluded.**
`serverSites` (site detection, used both to decide *what needs a hatch*
and to drive the ambiguity check's iteration) still uses `.some(...)`
across all four patterns — a boolean, not a count. The ambiguity check
now only counts `socketBindPatterns` matches, so two independent,
**unbound** `new Hono(` calls on one physical line are invisible to it:
`constructionsOn` returns 0 (no socket binds), so the check never
considers that line ambiguous, even though `serverSites` treats it as
exactly one site — same as any other line.

Demonstrated with a temporary, self-declared `WIRE_PATH_HATCHES` row
simulating a legitimate hatch on a Hono-only site (there is no real one
in the tree today, so this could not be shown against existing code the
way round 6's finding could):

```ts
const legit = new Hono(); const rogue = new Hono();
rogue.get("/v1/memories", () => new Response(JSON.stringify({ id: "raw-fixture-row-id" })));
```

With a hatch row registered for `legit`'s line (simulating "this Hono
instance is a fixture/test double, never bound, exempt for a stated
reason"), the same line's second, wholly independent `rogue` router —
naming the registered path and never reaching the registered route —
**is silently exempted by the same row.** Without the hatch row, the
identical file correctly fires. Reverted the temporary row; `diff`
against the pre-mutation checker was empty.

**Severity.** Structurally identical to round 6 — needs a pre-existing,
legitimate hatch to hide behind — but currently *more* latent than round
6 was: the one real hatch in the tree binds a socket (`Bun.serve`), so it
sits in the still-covered `socketBindPatterns` subset and this specific
gap is not reachable against any file in the tree today. It becomes live
the first time anyone legitimately hatches a Hono-only site.

**Recommended fix**, keeping round 7's real insight (a router nested
inside its own binder's call is not a second server) while restoring
round 6's actual guarantee (no two independent sites share a hatch key):
fail when `socketBindPatterns` matches 2+ times on a line (unchanged), OR
when there are zero socket binds on the line and `new Hono(` matches 2+
times (two independent, unbound routers — genuinely ambiguous, since
neither is any other one's argument). The one case this does not
resolve, and which is narrower still — a single real socket bind sharing
a line with a genuinely unrelated, independent router that is *not* that
bind's own argument — is a residual gap on the order of the already-
accepted same-construction-behavior-drift limitation, not something this
round's fix needs to chase to land.

### Verdict: HOLD (round 8)

Rounds 1–7 all stay closed; nothing here reopens any of them. This is
round 6's class, in the one place round 7's narrowing left uncovered —
not a new mechanism failure, a gap at the seam between two correct-in-
isolation fixes.

**What would unblock promotion:** land the two-part ambiguity condition
above, re-run this round's two-independent-Hono-routers fixture against
it and confirm it now fires (with a hatch row present) while a genuine
`Bun.serve({ fetch: new Hono().fetch })` and a genuine Hono-only door
each still pass, re-run all existing red-proofs, non-author re-reads.

**Blast radius if this HOLD is wrong:** small — additive to the ambiguity
check only, does not touch detection, hatch resolution, or staleness, and
does not change any case already verified correct across eight rounds.
Not reachable against any file in the tree today.

**What is still open after eight rounds:** the unbound-router-pair gap
in the ambiguity check (blocking). Everything recorded open after round 4
that rounds 5–7 did not touch — the pre-existing multi-server false-
positive imprecision, the same-construction-behavior-drift gap, and rule
16's unfixed round-2-class hatch — remains open and unchanged.

### What eight rounds on one fence actually say

The coordinator asked for this in their own words, and it is worth
recording plainly rather than only in the per-round log above: **every
one of the coordinator's seven claims of "this closes it" was wrong**,
in both directions, and none of the eight findings — four bypasses in the
deleted marker mechanism, one granularity gap in the registry that
replaced it, one over-correction of that fix into a false positive, one
narrowing of *that* fix that reopened the original class for a different
pattern subset — was found by reading a diff. Every one was found by
building the specific input the fix's own stated boundary implied should
be safe, and running it. That includes this round's: the round-7 fix's
own header comment already said "narrowing the count must not narrow
what counts as a site," which is the correct principle, applied one
pattern-subset short of everywhere it needed to hold.

The direction of the errors is itself informative. Rounds 1–4 were all
under-firing (the fence missed something it should have caught); round 6
was under-firing again after the marker was removed; round 7 was over-
firing (the fence caught something it shouldn't have); round 8 is under-
firing once more, but narrower and more localized than any of rounds
1–4. That is not a fence converging monotonically toward correctness — it
is a fence whose failure mode keeps changing shape as each specific
defect closes, which is exactly what "no bound short of a real lexer" and
"no bound short of exhaustively reasoning about every pattern
combination" predict, for the two different mechanisms (the marker, and
now the multi-pattern ambiguity count) that have each carried this
property in turn. The lesson is not "this author is unreliable" — every
individual fix was correct against the case that motivated it, verified
independently each time, and two of the eight findings were the author's
own self-caught mistakes reported before the audit even saw them. The
lesson is that **confidence about a hand-written guard's completeness is
not evidence**, regardless of who holds it or how carefully the previous
round was reasoned through, and this fence's own audit history is now the
clearest demonstration of that claim this program has produced: eight
rounds, eight times a stated boundary turned out to have an edge nobody
had constructed yet, zero of them caught by re-reading code that had
already been read carefully the round before.

*(This paragraph moves to the top of the document on promotion — see
**AUDIT-17 — round 9**'s closing note. Round 9 did not promote, so it
stays here for now.)*

## Correction to the historical record

`63578dbac1`'s commit message states "Suite 716 pass / 0 fail." The
coordinator caught this themselves, before the audit did, and asked that
it be corrected here since a pushed commit message cannot be amended
without a force-push: **the real number is 715.** The figure was written
from a pre-rebase run and not re-read after. Verified again independently
during round 9: 715 pass, 0 fail, on the merged trunk. Nothing about any
verdict changes — this is a correction to a number in a commit message,
not to a claim about behavior — but a record asserting a count it did not
observe is the small end of the exact class this whole program exists to
catch, and it does not stay uncorrected here.

## AUDIT-17 — round 9, non-author re-audit of `63578dbac1`

The coordinator reproduced round 8's finding before fixing it (confirmed
against a simulated hatch, since the tree has no real Hono-only hatch to
demonstrate it against), then made the ambiguity count context-sensitive:
count socket binds when any are present on the line, otherwise count
routers. This is exactly the fix the round-8 audit specified.

**All three red-proofs in `63578dbac1`'s commit message reproduced, each
against a standalone fixture:**

- Two unbound routers, one naming the path → **fires**, both the
  "two HTTP servers" ambiguity failure and the underlying unhatched-site
  failure, on the same line.
- `Bun.serve({ fetch: new Hono().fetch })` → **stays green** (round 7
  preserved).
- Reverting `ambiguousSiteCount` to counting binds only → exactly **1 of
  13** tests goes red — the round-8 test, and only it. Restored; 13/13
  green.

**The previously-disclosed residual (a real socket bind sharing a line
with a genuinely unrelated, independent router) was re-confirmed present,
not re-tested as new.** Simulated the same way round 8's finding was
simulated (a temporary `WIRE_PATH_HATCHES` row, since no real instance
exists in the tree): with a hatch on `Bun.serve({ fetch: new
Hono().fetch })`'s line, an independent second router sharing that line
and naming the path is still silently covered. This matches exactly what
round 8 named, and what `63578dbac1`'s own commit message restates as an
accepted limit rather than a fix target. Confirmed accurate, not
reopened.

### New finding, round 9: the ambiguity check's unconditional scope is the actual root cause, and it produced a second instance

Round 7's finding and this round's finding are different specific
triggers of the **same structural property**: the "two constructions on
one line" check runs before, and independent of, whether the file has any
relevance to a registered wire path at all. Round 7 fixed the *specific
pattern combination* that tripped it (`Bun.serve` + `new Hono`); it did
not change *where the check runs*. So the same shape recurs for the
pattern combination round 8 added:

```ts
const publicApp = new Hono(); const adminApp = new Hono();
export { publicApp, adminApp };
```

Confirmed zero occurrences of "memories" anywhere in this fixture before
running it. **Fires** — "two HTTP servers are constructed on one line" —
against a file that could never need a `WIRE_PATH_HATCHES` row in the
first place, because it never names a registered wire path.

**Severity, assessed honestly rather than by pattern-matching against
round 7.** The *triggering shape* here — two separate `const x = new
Hono();` declarations crammed onto one physical line via a semicolon —
is far less ordinary than round 7's natural single-expression idiom;
most formatters would never produce it, and nobody writes two unrelated
declarations on one line without a specific reason to. Judged purely on
"how likely is this exact fixture," it is closer to round 6's
unusual-but-deliberate territory than round 7's every-day one. But the
*mechanism* is identical to round 7's: unconditional, tree-wide,
zero-benefit noise on a file that could never trigger rule 17's actual
concern. The next pattern that gets added to `serverConstructionPatterns`
for some other framework will reopen the identical shape a third time,
because the fix each round has narrowed the *symptom* (which pattern
combination) rather than the *scope* (which files the check should even
run against).

**Recommended fix, aimed at the root rather than the next instance:**
gate the entire "two constructions on one line" loop on the file being
relevant to rule 17 at all — i.e., only run it for a file where
`namesWirePath(code, row.wirePath)` is true for some `WIRE_PATH_REGISTRY`
row. A file that never names a registered wire path can never legitimately
need a `WIRE_PATH_HATCHES` entry, so the ambiguity the check exists to
prevent cannot arise there; checking it anyway is pure false-positive risk
with no corresponding protection. Verified this does not lose round 6's
original protection: integration/adversarial/live-server.ts names
`/v1/memories` (as a client call), so it would still be in scope under
this gating, and the two-real-`Bun.serve(`-calls mutation would still
fire.

### Verdict: HOLD (round 9)

Rounds 1–8 all stay closed; nothing here reopens any of them, and the
round-8 residual was re-confirmed accurate rather than newly discovered.
This is round 7's structural cause, not yet addressed, producing a second
symptom through the code round 8 added to fix a different problem.

**What would unblock promotion:** gate the ambiguity check on file-level
wire-path relevance as described above (or an equivalent that provably
closes the same root, not just this instance), re-run this round's
two-independent-Hono-apps fixture and confirm it stays green, confirm
`live-server.ts`'s protection is unaffected, re-run all existing
red-proofs including round 8's and round 6's, non-author re-reads.

**Blast radius if this HOLD is wrong:** small — a single additional guard
condition on an existing loop, does not touch detection, hatch
resolution, or staleness, and does not change any case already verified
correct across nine rounds.

**What is still open after nine rounds:** the ambiguity check's unscoped
reach (blocking — this is round 7's root cause, not a new mechanism).
Everything recorded open after round 4 that rounds 5–8 did not touch — the
pre-existing multi-server false-positive imprecision, the same-
construction-behavior-drift gap, and rule 16's unfixed round-2-class
hatch — remains open and unchanged.

### On the coordinator's proposed promotion bar

> Promote when a round finds nothing reachable in the tree AND nothing
> new in kind — with every residual written down as an accepted limit,
> named and dated, rather than left implicit.

**The bar is right, with one addition this round argues for directly.**
The two-part test (not reachable today; not a new kind) is the correct
shape: it does not ask for proof of completeness, which nothing here can
give, and it matches how the rest of this document already treats
detection-side gaps (the "Known limits" section has carried undecided,
accepted items since before this audit existed). Round 8 would indeed
have cleared it — its finding needed a hatch that does not exist.

But round 9 is itself the argument for a third clause. Round 9's finding
is "the same kind" as round 7 by mechanism (unconditional scope) and "a
new kind" by trigger (a different pattern combination) — the bar as
stated does not say which one governs, and answering that honestly
required tracing round 7's fix back to what it actually changed (the
counted patterns) versus what it left alone (where the check runs) rather
than just diffing the two fixtures. A bar that can be satisfied by
patching the last reported trigger without asking whether a **structural
source** is still standing behind it would have promoted after round 7,
then round 8, then this round — three times, on a fence that kept
producing the same shape of finding from the same unaddressed root.

**Proposed addition:** *and no open finding traces to a structural cause
still capable of producing another instance in a different specific
form.* Concretely, before promoting: for each finding closed so far, ask
whether the fix addressed the mechanism that produced it or only the
trigger that revealed it. Round 5 addressed a mechanism (deleted the
marker apparatus entirely). Round 6 addressed a mechanism (line-keying).
Round 7 and round 8 each addressed a trigger (which patterns count,
twice) while leaving a mechanism — the check's unconditional scope —
untouched; that is precisely why round 9 exists. Under the three-part
bar, round 9's fix (gating on file relevance) closes a mechanism, not
another trigger, and a round that finds nothing reachable, nothing new in
kind, *and* no untouched structural source behind what was fixed is the
point at which the audit's own reasoning, not just its search, is
satisfied.

This is not a retroactive re-litigation of the fix already landed — the
registry replacement in round 5 and the line-count fix in round 6 were
both mechanism-level from the start, and neither has reopened. It is a
sharper version of the same bar, aimed at the one place in this fence's
history where the same failure shape was allowed to recur because a
symptom was patched twice before its cause was named once.
