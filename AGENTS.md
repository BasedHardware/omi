<!-- SINGLE SOURCE OF TRUTH for all agent instructions in this repo (Claude Code, Codex, and any other agent). -->
<!-- CLAUDE.md is a thin pointer to this file. Add or change rules HERE, never in CLAUDE.md. -->
<!-- Format spec: https://agents.md | Codex guidance: https://developers.openai.com/codex/guides/agents-md -->

# Omi Agent Guide

These rules apply to every AI agent working in this repository. This file is **high-level guidance plus an index** — component guides carry the detail; load them just-in-time for the area you are working in. `CLAUDE.md` just points here. A CI check (`.github/scripts/check_agents_md_lean.py`) keeps this file lean: add detail to the component guide, not here.

**Two audiences read this file.** Engineering standards (Definition of Done, testing, formatting) apply to everyone — maintainers and open-source contributors alike. Rules about this repo's `main` branch, production app bundles, deploys, and local machine workflows assume a maintainer environment; in a fork, follow your user's process for landing changes and skip those. Contributor flow: `docs/doc/developer/Contribution.mdx`.

## Read Next (just-in-time)

| Working on | Read first |
|---|---|
| Backend Python (`backend/`) | `backend/AGENTS.md` — setup, async/executors, WebSocket rules, service map, logging security, testing |
| Flutter app (`app/`) | `app/AGENTS.md` — build flavors, l10n, native bridge, tests, agent-flutter UI verification |
| Desktop macOS (`desktop/macos/`) | `desktop/macos/AGENTS.md` — build/run, named bundles, self-testing, release pipeline, changelog |
| Firmware (`omi/firmware/`) | `omi/firmware/AGENTS.md` — release workflow |
| Product behavior | `PRODUCT.md` + `docs/product/invariants/` — locked invariants and guard tests |
| Fallback/fail-open branches | `docs/agents/fallback-telemetry.md` — when to call `record_fallback` |
| App flows / E2E | `app/e2e/SKILL.md`, `desktop/macos/e2e/SKILL.md` |
| Cursor Cloud VM (Linux x86) | `.cursor/cloud-agent-environment.md` — hermetic E2E harness, known failures |

## Definition of Done

Every change must satisfy this checklist before it is committed or put in a PR. When in doubt about any other rule, satisfying this list is the priority.

1. **Behavior changed → a test changed.** Bug fixes include the regression test that would have caught the bug. New features test the core path and the main error path — no more.
2. **The component's test suite passes** (`backend/test.sh`, `app/test.sh`, or the component's documented equivalent), run locally before committing.
3. **You exercised the change yourself** — ran the real user-facing path, not just compiled or lint-passed. If you truly could not, say so explicitly instead of implying it works.
4. **Verification evidence is written down** — the commands you ran and what they showed, in the commit message or PR description.
5. **No orphaned deferrals** — new `TODO`/`FIXME`/`HACK` comments reference a tracking issue or are resolved before merge.
6. **Docs moved with the code** — setup, test commands, service boundaries, env vars, or agent-relevant behavior changes update the matching guide (this file, a component `AGENTS.md`, or `docs/doc/developer/`) in the same PR. Product-direction or invariant changes update `PRODUCT.md` / `docs/product/invariants/` in the same PR.
7. **Failure-class declaration** — before drafting a `fix:` PR body, run `scripts/pr-preflight --suggest` for its invariant citations and failure-class guidance; every `fix:` commit then declares `Failure-Class: FC-<slug> | new | none` and validates it with `scripts/failure-class`.
8. **PR contracts pass before opening the PR** — run `make preflight`; it executes the same deterministic check manifest CI runs (`.github/checks-manifest.yaml`). Draft the PR body and run `scripts/pr-preflight --pr-body-file /tmp/pr-body.md` (or `scripts/pr-preflight --suggest` for paste-ready invariant and failure-class guidance).

A deterministic diff-scoped check failing for the first time in CI is a manifest bug: fix the manifest instead of adding a one-off workflow step. Register new checks in `.github/checks-manifest.yaml` with both `local` and `ci` lanes.

## Bug Fixes: Repair the Failure-Class Boundary

The unit of work is the violated contract, not only the line where the symptom appeared. The declaration is the PR record for an ordinary instance fix; before fixing, inspect recent fixes in the same subsystem. Registry lifecycle transitions are separate PRs: dormant classes record `dormant_since`, and recurrence reopens them by setting `status: open` and removing it.

- Identify the authoritative owner, identity, state transition, or boundary contract that failed — don't add another observer, fallback boolean, or call-site exception when ownership is the real problem.
- If two or more recent fixes share the cause, add a reusable guard surface in the same PR: a typed state/policy model, behavioral contract test, fault harness, or narrow static checker.
- A regression test must execute production behavior through a controllable seam. Asserting that source strings occur in a certain order is a static tripwire, not behavioral coverage; label static checkers as such.
- Do not broaden a safe bug-fix PR into an unreviewable migration; land the enforceable guard now and track high-blast-radius follow-up explicitly.

## Leave It Better Than You Found It

- If you touch a file and see a small related defect (dead code, an adjacent bug, a missing test for code you are modifying), fix it **in a separate commit in the same PR**.
- Only make an opportunistic fix you can verify; otherwise open a GitHub issue instead of touching it.
- Never expand beyond files you were already modifying or refactor working code for style alone. Deferring is wrong when the fix is in scope and verifiable; expanding scope is wrong everywhere else.

## Behavior

- Never ask for permission to access folders, run commands, search the web, or use tools. Just do it.
- Never ask for confirmation. Make decisions autonomously and proceed.
- You have full access to the user's computer — browser, desktop, all apps. Never ask the user to do something you can do yourself.

## Safety Rules

- Never kill, stop, or restart the production macOS apps (`/Applications/Omi.app` / `Omi Beta.app`, bundle ids `com.omi.computer-macos` and `com.omi.computer-macos.beta`). Dev commands target only dev or `omi-*` named test bundles.
- **Nothing lands on `main` until the user explicitly says so.** Land through PRs only (regular merge, never squash); never push directly to `main`; never push or open PRs unless explicitly asked — commit locally on a feature branch by default. A prior approval never carries over to later changes.
- **Exception — reverts merge right away.** A user request to revert a merged PR/commit is itself the approval to open and merge the revert PR.
- **Exception — verified + peer-approved changes may auto-merge.** If you actually exercised the real user-facing path **and** an independent agent review approved it, you may open and merge without a separate go-ahead — except for risky, wide-blast-radius, or hard-to-reverse changes (migrations, release/CI pipeline, schema, access control, data deletion), which always need explicit user sign-off.
- **Prefer testing locally first.** Default to a local build + run (desktop: named bundle) to verify a change before proposing to land it.

## Git

- **Setup (required before first commit):** `make setup` — fetches `origin/main`, fast-forwards when safe, installs repo Git hooks (including the auto-formatting pre-commit hook) with linked-worktree-safe paths.
- Before starting work: `git fetch origin && git pull --ff-only` on `main` — don't branch off stale state.
- Always work in a git worktree for code changes (`git worktree add`); commit to the current branch and never switch branches mid-task.
- Make individual commits per feature or testable surface, not per file or unrelated bulk changes.
- If push fails (remote ahead): `git pull --rebase && git push`.
- **RELEASE command:** branch from `main`, individual commits, push, open PR, merge without squash, switch back to `main` and pull. **RELEASEWITHBACKEND:** RELEASE + `gh workflow run gcp_backend.yml -f environment=prod -f branch=main`.

## Issues

- Open issues freely — one paragraph of symptom plus evidence (logs, IDs, links) is a complete issue. Tracking beats polish; iterate in comments.
- Issues state problems; PRs state solutions. Don't write implementation epics, acceptance-criteria matrices, SLOs, or rollout programs into an issue — that content hardens in the PR, where the Definition of Done already demands evidence.
- If an issue does prescribe implementation: scope it to one self-contained PR, verify every code claim against current code first (the fix may already exist), and any proposed check must run in an existing CI or deploy lane.
- Close incident issues on live evidence, not code merge; if live verification is deferred, name its owner in the closing comment.

## Cross-Component Guidelines

- **Product invariants:** read `PRODUCT.md` before changing product behavior. If your diff touches a locked invariant's path globs, name **every** matched invariant ID in the PR body (path-based, not intent-based; discover with `scripts/pr-preflight --suggest`) and update the invariant's guard test when behavior changes.
- **No in-repo compatibility layers:** migrate every in-tree caller in the same change; do not add deprecated aliases, duplicate adapters, or fallback paths to preserve a retired shape.
- **Compiler-first boundaries:** express ownership and mutation invariants with target dependencies, access control, and typed APIs before adding source scrapes or runtime assertions; behavioral tests still prove the permitted paths.
- **Never use purple** anywhere in UI (icons, accents, glows, gradients) — off-brand; use white/neutral. Enforced as a no-increase ratchet (`INV-UI-1`); see `docs/product/invariants/brand-ui.md`.
- **Fallback telemetry:** when a branch changes provider, mode, or correctness, or takes a fail-open path, call the shared `record_fallback`/`recordFallback` helper — never a new one-off counter. Full contract: `docs/agents/fallback-telemetry.md`.
- **Logging:** never log raw sensitive data; sanitize API responses and PII (backend: `utils.log_sanitizer`).
- **Deferred-work markers:** new `TODO`/`FIXME`/`HACK` must reference a tracking issue or be resolved before merge. Packages over 12 source files need a package-root `ARCHITECTURE.md`/`README.md` (`check_arch_guardrails.py` ratchet). Designated rollout scaffolding needs a `LIFECYCLE: permanent|one-time` header; one-time files also need `DELETE-AFTER: <issue URL or invariant ID>` (`check_lifecycle_headers.py`).
- **New guards:** explain in the PR why the guard is not a shared primitive, and cite the real merged PR or incident it would have caught; no real instance means the check does not land.

## Formatting

The pre-commit hook (installed by `make setup`) auto-formats staged files. Verify: `test -x "$(git rev-parse --git-path hooks)/pre-commit" && echo OK`. Manual commands:

| Language | Manual command |
|----------|----------------|
| Dart (`app/`) | `dart format --line-length 120 <files>` |
| Python (`backend/`) | `black --line-length 120 --skip-string-normalization <files>` |
| ARB (`app/lib/l10n/`) | `jq --indent 4 '.' <file> > tmp && mv tmp <file>` |
| C/C++ (firmware) | `clang-format -i <files>` |
| Rust (`desktop/macos/Backend-Rust/`) | `rustfmt --edition 2021 <files>` |
| Swift (`desktop/macos/Desktop/`) | `desktop/macos/scripts/swift-format-wrapper.sh format -i <files>` |
| Web (`web/`) | `npx prettier --write <files>` |

Files ending in `.gen.dart` or `.g.dart` are auto-generated — don't format manually. Swift files under `Desktop/Sources/Generated/` are excluded from the formatter scope.

## Computer Control

Click at coordinates: `cliclick c:X,Y`. Mac screenshots: `screencapture -x /tmp/screen.png`. Native macOS app testing: `agent-swift` (see desktop guide). Browser automation: `playwright` MCP. Never try 3+ different click tools for the same action — pick one and commit. Prefer `cliclick` over `automac`/`mac-use-mcp` (multi-monitor coordinate bugs).

## Testing

- **Coverage grows by ratchet, not mandate:** every bug fix adds the regression test that would have caught it; new features test the core path and main error path — no more. A small test that stays meaningful in a year beats ten brittle ones.
- **Push gate budget:** `scripts/pre-push` is a bounded local acceptance gate, intentionally smaller than CI: cap broad backend selection at 40 files and use only the desktop debug compile. Do not add full suites, release compiles, or CI-only toolchain pins to it — push-time bloat breaks normal iteration. Use focused feedback while editing; CI remains the full test authority.
- **CI tests must be hermetic** (no live services, network, sleeps, or ordering dependence) — and hermetic tests must run in CI: put them where the component's runner discovers them. A test needing a live service stays out of CI; note in the PR how you ran it.
- Delete or fix a flaky/obsolete test you encounter — a suite people distrust is worse than a smaller suite.
- Component runners and prerequisites: see the component guides (`backend/AGENTS.md` → Testing, `app/AGENTS.md` → Test Strategy). High-risk backend workflows must be listed in `backend/testing/workflow_contracts.json` with contract tests.

## Deploys & Release Pipelines

- Desktop (daily candidate → qualified beta → manual stable): `desktop/macos/AGENTS.md` → Release Pipeline.
- Backend: `gh workflow run gcp_backend.yml -f environment=prod -f branch=main`. Runtime env contract: `backend/AGENTS.md` → Service Map.
- Firmware (Omi CV1): `omi/firmware/AGENTS.md`.

**Every gated surface has a break-glass hatch. A broken gate is never a reason to be stuck.** Each records a tracking issue; repeated use means the gate is the defect.

| Blocked on | Hatch |
|---|---|
| Desktop candidate won't cut (`Desktop Swift Build & Tests` red/flaky) | `desktop_auto_release.yml` with `release_mode=break_glass` |
| Backend deploy has no Release Eligibility proof | `gcp_backend.yml` with `skip_eligibility_proof=true`, `break_glass_confirm=deploy-without-proof`, `break_glass_reason` |

Hatches relax *evidence* requirements only. They never relax that code is merged to `main` first, and never reach stable/prod pointers without their own explicit confirm.

## Documentation Maintenance

- **This file is the single source of truth for cross-component agent rules; component `AGENTS.md` files own their component's detail.** `CLAUDE.md` files are pointers only.
- **Keep this file lean** — high-level rules and the index, short plain bullets. Detail goes in the component guide; `.github/scripts/check_agents_md_lean.py` enforces the budget. Prefer editing/replacing an existing line over adding new ones.
- **Write rules mechanically, and back them with checks.** A rule is only reliable if a weak agent can apply it without judgment. Prefer encoding a rule as a script or CI check with a clear failure message — enforced rules don't drift; requested behavior does.
- **New checks, probes, or validation scripts must be wired into an existing CI or deploy lane in the same PR.** On-demand scripts and scheduled jobs with no blocking audience are dead checks.
- **When a defect ships because guidance was misread or missing, tighten the guidance in the fix PR** — make the rule mechanical enough that the same misreading can't recur, or add a check that catches it.
- PR changes to setup, test commands, safety rules, service boundaries, or env vars update the matching guide in the same PR. Architecture / core-flow / API changes update Mintlify docs (`docs/doc/developer/`). Product direction or locked invariants update `PRODUCT.md` / `docs/product/invariants/` and guard tests.
