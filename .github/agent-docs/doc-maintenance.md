# Maintaining agent docs

Read this before changing an `AGENTS.md`, adding a rule, or adding a check.

## Where a rule belongs

- **Root `AGENTS.md`** — cross-component rules and the index, nothing else. It loads in
  every session for every task, so every line is paid for constantly.
- **Component `AGENTS.md`** (`backend/`, `app/`, `desktop/macos/`, `.github/`,
  `web/admin/`, `omi/firmware/`) — that component's detail. Agents load the nearest one
  just-in-time.
- **`.github/agent-docs/`** — reference an agent needs occasionally and can be pointed to, like
  this file or `fallback-telemetry.md`.
- **`CLAUDE.md`** — a pointer only, and there is exactly one, at the repo root. Never put
  a rule in it.

`.github/scripts/check_agents_md_lean.py` holds every `AGENTS.md` to a size ratchet.
After substantial reductions, lower the budget with modest headroom for new routes
and repository-specific facts. Routine edits need not reset it to the exact file size.
Do not raise a budget to admit detail that has a component-guide home.

## How to write a rule

- **Prefer omission.** Keep repository-specific facts that agents cannot readily
  discover. Omit generic behavior, repeated procedures, and instructions already
  expressed by tools or the owning guide.
- **Give each fact one owner.** Link to it from the relevant route; replace or
  remove overlapping guidance instead of adding another rule.
- **Every referenced path must exist.** `check_agent_doc_references.py` enforces this, so
  a rename that orphans a pointer fails in CI rather than silently misleading an agent
  months later.

## Adding a check

- Register it in `.github/checks-manifest.yaml` with **both `local` and `ci` lanes**.
  Never hardcode a check into workflow YAML — a deterministic diff-scoped check failing
  for the first time in CI is a manifest bug.
- On-demand scripts and scheduled jobs with no blocking audience are dead checks. If
  nothing fails when it fails, it does not land.
- Cite the real merged PR or incident it would have caught. No real instance, no check.
- Explain in the PR why it is not a shared primitive already.

## Keeping docs and code together

- A PR changing setup, test commands, safety rules, service boundaries, or env vars
  updates the matching guide in the same PR.
- Architecture, core-flow, and API changes update the Mintlify docs under
  `docs/doc/developer/`.
- Product direction or locked invariants update `PRODUCT.md` and
  `product/invariants/`, including the invariant's guard test.
- After a failure, improve the responsible implementation, test, tool diagnostic,
  or documentation. Add a standing instruction only for a recurring information gap.
