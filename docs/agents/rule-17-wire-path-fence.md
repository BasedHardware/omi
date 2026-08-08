# Rule 17 — the wire-path fence

> **A settled wire path is SERVED by exactly one route module.** A file that
> both stands up an HTTP server and names a registered wire path in code must
> reach that path through the registered route module — it may not answer the
> path itself.

Status: **PROVISIONAL, HELD (round 6).** Landed 2026-08-08 with the W4
rebuild; it runs immediately, per §8, and continues to run at full strength
while held — holding is not disabling. Rounds 1–4 each found a working
bypass in a comment-marker escape hatch (file-wide scope; a bare substring
search; string-blindness in the shared comment stripper; no `${…}`
interpolation-depth tracking) and each fix left a smaller hole. **Round 5 is
a ruling, not a bypass:** the marker mechanism was replaced entirely with a
`WIRE_PATH_HATCHES` registry, keyed by `(file, line)` — see
**AUDIT-17 — round 5**. Round 6 re-audited that replacement and found a gap
in the new mechanism's own granularity: two server constructions on one
physical source line collapse onto a single registry key, so a hatch for a
legitimate construction also covers a rogue one sharing its line — see
**AUDIT-17 — round 6**. The DOOR lane wrote the original; a non-author (the
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
