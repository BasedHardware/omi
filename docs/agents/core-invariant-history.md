# Why `core/`'s invariants exist — the incidents behind them

`core/AGENTS.md` is loaded into agent context every session, so it carries the *rule* and
its enforcement pointer only. The reasoning lives here. Read this when you are tempted to
weaken a rule, relax a check, or mark a failing invariant as a false positive — every one
of these was written after the permissive version of the same rule let a real defect
through.

## Rule 12 — snapshot honesty

Wrong `complete: true` is user data loss via `Projection.reconcile`, not a cosmetic
inaccuracy: a snapshot that claims completeness authorizes reconciliation to delete
everything absent from it.

Filtered sources are the NORM on this backend — 2 of the first 4 domains filter
server-side, one of them *after* the page limit. So the default assumption for any list
endpoint is that it may **not** back `complete: true`.

**History.** The permissive version of this rule let wave 4 certify a data-loss bug as
conformant via a mis-declared descriptor kind. The lesson that fixed it: declaring the
descriptor kind is a claim about the **backend**, not about your adapter, and it must cite
backend evidence — a repo-relative locator or a one-line proof of unfilteredness. A
descriptor asserting complete-capability without evidence fails the harness.

Two corollaries that came from the same incident: a 200 with an unexpected body returns
`null` rather than a complete empty snapshot, and a full page never claims completeness.

## Rule 14 — invariant tests declare their red-proof

**History.** Wave 5's alias-fold test passed with rekeying replaced by the identity
function. `reconcile` masked the bug, so the test's assertions proved a different
invariant than the one it named. It was found by mutation, not by reading — three review
passes had missed it.

That is why the reviewer must actually apply the named mutation rather than trust the
comment: a red-proof nobody executes is decoration.

**The canonical decorative shape is a row-count assertion.** Assert the *content* only a
working mechanism could produce, not how many rows survived. Counts survive almost every
mutation that matters.

## Rule 15 — a shared wire is tested against its real shape

**History.** Three defects in one night shared this exact shape, and none was catchable
from either side:

- a backend with 448 green tests that had never served a request;
- a bridge reporting itself active while serving nothing;
- an entitlement UI built against a reserved `/listen` frame no server emits, while the
  server emitted a different frame nobody consumed.

Each half was individually correct and individually green. A test that hand-authors the
counterpart's frame is testing its author's memory of the wire — which is precisely what
is already wrong when this bites.

**What the check does NOT do.** `scripts/check-wire-conformance.mjs` cannot prove a test
asserts anything useful about what it read; that is rule 14's job. It proves the
mechanical thing missing in all three cases above: the real shape exists as a corpus of
record, and something actually loads it.

Adding a wire that two components speak means adding a registry row. That is the whole
maintenance burden, and it is deliberate — a convention would be forgotten by the next
agent at 4am.
