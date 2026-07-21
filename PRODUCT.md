# Omi Product Principles

Short north star for humans and agents. Read this before proposing features or
landing PRs that change product behavior. Engineering standards live in
[`AGENTS.md`](AGENTS.md). Locked product rules live in
[`docs/product/invariants/`](docs/product/invariants/).

## Principles

1. **Memory-first.** Protect the core loop:
   **Capture → Understand → Remember → Retrieve → Act**.
   If Omi fails to capture or preserve memory, nothing else matters.

2. **Trust over cleverness.** Prefer reliable capture, sync, and retrieval over
   flashy features. Silent data loss and dual sources of truth are product bugs.

3. **One product mind.** Surfaces are input/output against one shared product
   experience — not separate products with their own histories.

4. **Harness over heuristics.** Where we integrate with surfaces we do not own,
   invest in durable harnesses and contracts, not brittle one-off automation.

5. **Taste floor.** Stay on-brand. Prefer deleting dual paths over
   feature-flagging them forever.

## Before you build

- Large or ambiguous features start as a GitHub issue
  ([Contribution guide](docs/doc/developer/Contribution.mdx)).
- Check the [invariant registry](docs/product/invariants/) for locked rules that
  apply to your change.
- A product rule without a guard surface is taste advice, not a locked
  invariant.
- Keep a new or changed product rule as a proposed design note until its
  behavior and guard have remained unchanged for seven days; only then may it
  be locked.

## Maintainer operating rule

When declining a PR for direction or taste, either cite an existing invariant
by ID or open a `proposed` invariant in `docs/product/invariants/` the same
week. Tribal “no” becomes written law.
