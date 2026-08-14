# Product Invariant Registry

Named product rules that contributors and agents must not violate. Engineering
rules stay in [`AGENTS.md`](../../../AGENTS.md). Product north star:
[`PRODUCT.md`](../../../PRODUCT.md).

## Status

| Status | Meaning |
|--------|---------|
| `locked` | Binding. Has a hermetic guard test (or an explicit exception with owner + burn date). CI may require naming the ID in PRs that touch its path globs. |
| `proposed` | Design note written so drift is visible, but not yet CI-enforced. |

## Index

| ID | Title | Status | Doc |
|----|-------|--------|-----|
| INV-CHAT-1 | One shared transcript across surfaces | locked | [chat-continuity.md](./chat-continuity.md) |
| INV-CHAT-2 | Chat launch placement and reading position | proposed | [chat-scroll-placement.md](./chat-scroll-placement.md) |
| INV-MEM-1 | Exactly three product memory tiers | locked | [memory-tiers.md](./memory-tiers.md) |
| INV-MEM-2 | Vector hydration fail-closed | locked | [memory-vector-hydration.md](./memory-vector-hydration.md) |
| INV-MEM-3 | No legacy fallback after canonical selection | locked | [memory-canonical-fail-closed.md](./memory-canonical-fail-closed.md) |
| INV-MEM-4 | Canonical promotion is the sole Long-term authority | proposed | [memory-promotion-authority.md](./memory-promotion-authority.md) |
| INV-MEM-5 | Universal memory and task authority | proposed | [universal-memory-task-authority.md](./universal-memory-task-authority.md) |
| INV-AGENT-* | Agent control-plane contracts | locked | [agent-control-plane.md](./agent-control-plane.md) |
| INV-INT-1 | Integrations harness over heuristics | locked | [integrations.md](./integrations.md) |
| INV-UI-1 | No purple; neutral accents | locked | [brand-ui.md](./brand-ui.md) |
| INV-AUTH-1 | Desktop Firebase session truth | locked | [auth-session.md](./auth-session.md) |
| INV-DATA-1 | Production-family customer data-plane continuity | proposed | [data-plane-continuity.md](./data-plane-continuity.md) |
| INV-NAV-1 | Feature parity across desktop shells | proposed | [desktop-shell-feature-parity.md](./desktop-shell-feature-parity.md) |
| INV-TASK-1 | Complete dated task buckets with bounded No Deadline paging | proposed | [task-dated-bucket-completeness.md](./task-dated-bucket-completeness.md) |
| INV-VOICE-1 | One desktop voice-turn lifecycle owner | locked | [desktop-voice-turns.md](./desktop-voice-turns.md) |
| INV-CUTOVER-1 | Whole-account cohort cutover authority | proposed | [account-cohort-cutover.md](./account-cohort-cutover.md) |

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

## Promotion

`proposed` → `locked` only when a hermetic guard test exists (or an explicit
documented exception lists an owner and burn date) and both the behavior and
guard have remained unchanged for seven days. Update this index in the same PR.
