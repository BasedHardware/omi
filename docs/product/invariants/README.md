# Product Invariant Registry

Named product rules that contributors and agents must not violate. Engineering
rules stay in [`AGENTS.md`](../../../AGENTS.md). Product north star:
[`PRODUCT.md`](../../../PRODUCT.md).

## Status

| Status | Meaning |
|--------|---------|
| `locked` | Binding. Has a hermetic guard test (or an explicit exception with owner + burn date). CI may require naming the ID in PRs that touch its path globs. |
| `proposed` | Written so drift is visible, but not yet CI-enforced. Promote only when a guard test exists. |

## Index

| ID | Title | Status | Doc |
|----|-------|--------|-----|
| INV-CHAT-1 | One shared transcript across surfaces | locked | [chat-continuity.md](./chat-continuity.md) |
| INV-MEM-1 | Exactly three product memory tiers | locked | [memory-tiers.md](./memory-tiers.md) |
| INV-AGENT-* | Agent control-plane contracts | locked | [agent-control-plane.md](./agent-control-plane.md) |
| INV-INT-1 | Integrations harness over heuristics | locked | [integrations.md](./integrations.md) |
| INV-UI-1 | No purple; neutral accents | locked | [brand-ui.md](./brand-ui.md) |

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

`proposed` → `locked` only when a hermetic guard test exists, or an explicit
documented exception lists an owner and burn date. Update this index in the
same PR.
