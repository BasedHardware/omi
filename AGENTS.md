# Omi agent guide

Read the guide for the area you are changing. `CLAUDE.md` points here.

## Routes

| Working on | Read |
|---|---|
| Backend | `backend/AGENTS.md` |
| Flutter app | `app/AGENTS.md` |
| macOS desktop | `desktop/macos/AGENTS.md` |
| Windows/Linux desktop | `desktop/windows/AGENTS.md` |
| Web app / admin | `web/app/AGENTS.md` / `web/admin/AGENTS.md` |
| Firmware | `omi/firmware/AGENTS.md` |
| CI / deployment workflows | `.github/AGENTS.md` |
| Public documentation | `docs/AGENTS.md` |
| Product behavior / UI | `PRODUCT.md`, `product/invariants/`; macOS UI: `desktop/macos/docs/ux-contract.md` |
| Shared client behavior | `contracts/parity/README.md` |
| Released-client compatibility | `contracts/client-compat/` |
| Fallbacks / fail-open paths | `.github/agent-docs/fallback-telemetry.md` |
| Plan catalog | `.github/agent-docs/plan-catalog.md` |
| App E2E | `app/e2e/SKILL.md`, `desktop/macos/e2e/SKILL.md` |
| Cursor Cloud environment | `.cursor/cloud-agent-environment.md` |
| Contributions / PR requirements | `docs/doc/developer/Contribution.mdx` |
| Failure-class classification | `product/failure-classes.md`, `scripts/failure-class` |
| Formatting | `.github/agent-docs/formatting.md` |
| Agent documentation / new checks | `.github/agent-docs/doc-maintenance.md` |

## Repository conventions

- Use a task worktree based on current `origin/main`. `make setup` installs the repository hooks, including staged-file formatting. Keep Git identity in the user's configuration; temporary test identities use `git -c`.
- Upstream `main` changes land through PRs with merge commits, never squash or direct pushes.
- macOS development uses dev or `omi-*` named bundles. Do not stop or replace the production Omi or Omi Beta apps; bundle details and commands live in the macOS guide.
- Migrate in-tree callers together rather than preserving retired APIs with compatibility wrappers. Released clients follow the compatibility contracts above.
- Run the component's documented verification and `make preflight`. For PR metadata, start with `scripts/pr-preflight --suggest`, then validate the draft with `scripts/pr-preflight --pr-body-file <file>`. These tools identify required invariant citations and failure-class declarations.

Keep this file a router. Add repository-specific facts at their owning guide; omit generic agent behavior and duplicated procedures. Size budgets live in `.github/scripts/check_agents_md_lean.py`.
