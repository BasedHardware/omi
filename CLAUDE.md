# Omi — Agent Instructions
<!-- Official guidance for writing these files:
     CLAUDE.md: https://docs.anthropic.com/en/docs/claude-code/memory
     AGENTS.md: https://developers.openai.com/codex/guides/agents-md
     Format spec: https://agents.md -->

**Treat `AGENTS.md` as this repository's instruction file.** Every rule for every agent
(Claude Code, Codex, and any other) lives there. This file exists only because some tools
look for `CLAUDE.md` by name — it is the one such pointer in the repo.

- Start with the root [`AGENTS.md`](./AGENTS.md): cross-component rules plus an index.
- When working inside a directory, also read the **nearest `AGENTS.md` at or above it** —
  `backend/`, `app/`, `desktop/macos/`, `.github/`, `web/admin/`, `omi/firmware/`.
  Those carry the detail the root file deliberately omits.
- Add or change rules in the relevant `AGENTS.md`. **Never add instructions here** — this
  file stays a pointer so there is only ever one source of truth to maintain.

@AGENTS.md
