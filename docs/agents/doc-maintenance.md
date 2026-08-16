# Maintaining agent docs

Read this before changing an `AGENTS.md`, adding a rule, or adding a check.

## Where a rule belongs

- **Root `AGENTS.md`** — cross-component rules and the index, nothing else. It loads in
  every session for every task, so every line is paid for constantly.
- **Component `AGENTS.md`** (`backend/`, `app/`, `desktop/macos/`, `.github/`,
  `web/admin/`, `omi/firmware/`) — that component's detail. Agents load the nearest one
  just-in-time.
- **`docs/agents/`** — reference an agent needs occasionally and can be pointed to, like
  this file or `fallback-telemetry.md`.
- **`CLAUDE.md`** — a pointer only, and there is exactly one, at the repo root. Never put
  a rule in it.

`.github/scripts/check_agents_md_lean.py` holds every `AGENTS.md` to a size ratchet.
The budget only ever shrinks: when a file gets smaller, lower it. Never raise a budget to
admit detail that has a component-guide home — that is the accretion the ratchet exists
to stop.

## How to write a rule

- **Write it mechanically.** A rule is only reliable if a weak agent can apply it without
  judgment. "Use good names" is a wish; "files ending `.g.dart` are generated, never edit
  them" is a rule.
- **Back it with a check.** Enforced rules don't drift; requested behavior does. Prefer a
  script with a clear failure message over another paragraph of prose.
- **Prefer replacing a line over adding one.** If a new rule overlaps an existing one,
  rewrite that one. Two rules covering the same ground will eventually disagree.
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
  `docs/product/invariants/`, including the invariant's guard test.
- **When a defect ships because guidance was misread or missing, tighten the guidance in
  the fix PR.** Make the rule mechanical enough that the same misreading cannot recur, or
  add the check that catches it.
