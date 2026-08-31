# Product Invariant Registry

Named product rules that contributors and agents must not violate. Engineering
rules stay in [`AGENTS.md`](../../AGENTS.md). Product north star:
[`PRODUCT.md`](../../PRODUCT.md).

## Status

| Status | Meaning |
|--------|---------|
| `locked` | A machine-checked claim: every guard this doc names exists, any guard script it names is wired into the checks manifest, and PRs touching its path globs must name the ID (unless it opts out — see *Whole-tree globs*). |
| `proposed` | A design note. Binding on judgement, not on CI. A stable resting state, not a queue. |

**Status does not control enforcement.** A static guard runs because it is wired
into `.github/checks-manifest.yaml`, whatever the doc says. `locked` controls
exactly one thing: whether the PR-body citation is required. Several `proposed`
invariants already have guards running on every PR.

## Locking

There is no waiting period. An invariant may be **born locked** the moment its
claims hold, and `.github/scripts/check_product_invariants.py` verifies those
claims on every PR — not once at promotion, but continuously:

- every path named under *Guard tests* exists
- any `.github/scripts/check_*.py` named there is run by a checks-manifest entry
- the ID appears in the index below, and every index row has a doc

That audit is why the old seven-day soak is gone. The soak was a proxy for "does
this guard actually work", and elapsed time cannot answer that — a violation
attempt can. It also never once operated: in the registry's history no invariant
was ever promoted `proposed` → `locked`, and two were born locked six days after
the soak rule was written.

**Convention for static guards:** ship a test that proves the guard *fails* on a
violating input, and wire the guard script into that test's manifest triggers so
the proof re-runs whenever the guard changes (see `task-capture-authority` and
its `-tests` sibling). This is a floor against decorative guards, not a coverage
proof — the author writes both the check and the violation, and they co-evolve.
Treat these as anti-recurrence ratchets: each case is the shape of a defect that
shipped.

**Demotion is cheap.** If a statement changes, edit the doc and set `proposed`
in the same PR. That has happened, it cost one line, and it is the intended way
to handle a rule in flux — not delaying the lock.

## Index

| ID | Title | Status | Doc |
|----|-------|--------|-----|
| INV-CHAT-1 | One shared transcript across surfaces | locked | [chat-continuity.md](./chat-continuity.md) |
| INV-CHAT-2 | Chat launch placement and reading position | locked | [chat-scroll-placement.md](./chat-scroll-placement.md) |
| INV-MEM-1 | Exactly three product memory tiers | locked | [memory-tiers.md](./memory-tiers.md) |
| INV-MEM-2 | Vector hydration fail-closed | locked | [memory-vector-hydration.md](./memory-vector-hydration.md) |
| INV-MEM-3 | No legacy fallback after canonical selection | locked | [memory-canonical-fail-closed.md](./memory-canonical-fail-closed.md) |
| INV-MEM-4 | Canonical promotion is the sole Long-term authority | locked | [memory-promotion-authority.md](./memory-promotion-authority.md) |
| INV-MEM-5 | Universal memory and task authority | locked | [universal-memory-task-authority.md](./universal-memory-task-authority.md) |
| INV-MEM-6 | Intent-backed knowledge ledger | proposed | [intent-backed-knowledge-ledger.md](./intent-backed-knowledge-ledger.md) |
| INV-AGENT-* | Agent control-plane contracts | locked | [agent-control-plane.md](./agent-control-plane.md) |
| INV-INT-1 | Integrations harness over heuristics | locked | [integrations.md](./integrations.md) |
| INV-UI-1 | No purple; neutral accents | locked | [brand-ui.md](./brand-ui.md) |
| INV-AUTH-1 | Desktop Firebase session truth | locked | [auth-session.md](./auth-session.md) |
| INV-BETA-1 | Desktop Beta build identity | locked | [desktop-beta-identity.md](./desktop-beta-identity.md) |
| INV-DATA-1 | Production-family customer data-plane continuity | locked | [data-plane-continuity.md](./data-plane-continuity.md) |
| INV-NAV-1 | Feature parity across desktop shells | locked | [desktop-shell-feature-parity.md](./desktop-shell-feature-parity.md) |
| INV-TASK-1 | Complete dated task buckets with bounded No Deadline paging | locked | [task-dated-bucket-completeness.md](./task-dated-bucket-completeness.md) |
| INV-TASK-2 | Capture proposes only where a Suggested surface exists | locked | [task-capture-suggestion-only.md](./task-capture-suggestion-only.md) |
| INV-VOICE-1 | One desktop voice-turn lifecycle owner | locked | [desktop-voice-turns.md](./desktop-voice-turns.md) |
| INV-CUTOVER-1 | Whole-account cohort cutover authority | locked | [account-cohort-cutover.md](./account-cohort-cutover.md) |

## File template

Copy into a new `*.md` under this directory:

```markdown
# INV-XXX-N: Short title

**Status:** proposed | locked
**Statement:** One sentence.

## MUST NOT

- …

## Surfaces

- …

## Guard tests

- `path/to/test`

## Path globs

- `path/prefix/**`

## PR rule

Name this invariant ID in the PR body if you touch the path globs above.
```

## Whole-tree globs

A glob rooted at a whole application tree (`backend/**`, `desktop/macos/Desktop/Sources/**`,
`.github/workflows/**`, …) makes every PR in that tree pay the citation. That is
how a citation becomes ritual: paste the token, move on. Such an invariant must
let its guard carry the floor and opt out of naming, by writing "Do **not**
require naming" in its PR rule — the INV-UI-1 pattern. The audit enforces this.

## Why the citation exists

It is cheap to satisfy: the checker prints a paste-ready block. Its durable
value is not attention but **context routing** — the failure prints the matched
invariant's Statement and MUST NOTs, so the rule lands in front of whoever, or
whatever, is editing those files. Keep MUST NOTs specific for that reason.

For crown-jewel invariants, prefer a PR rule that asks for a *claim* rather than
a token ("state whether this preserves the existing authority or is the explicit
migration exception"). A claim can be wrong, and reviewed; a token cannot.
