# Rule 17 — the wire-path fence

> **A settled wire path is SERVED by exactly one route module.** A file that
> both stands up an HTTP server and names a registered wire path in code must
> reach that path through the registered route module — it may not answer the
> path itself.

Status: **PROVISIONAL, HELD (round 3).** Landed 2026-08-08 with the W4
rebuild; it runs immediately, per §8, and continues to run at full strength
while held — holding is not disabling. Round 1 held on a file-wide escape
hatch (`fd38dc5e33` fixed it). Round 2 held on a construction-line hatch
check that was not comment-aware — a plain string containing the marker text
hatched it, no pre-existing hatch needed (`b9e0c9a915` fixed it). Round 3
holds on a narrower, lower-severity gap in that same fix: the comment-aware
predicate relies on `withoutComments()`, which is a plain regex with no
notion of string or template-literal boundaries, so text shaped like
`/* ... */` **inside a string value** is blanked exactly as if it were a
real comment. See **AUDIT-17 — round 3** below. The DOOR lane wrote the
original; a non-author (the coordinator) wrote both fixes, and said so
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
