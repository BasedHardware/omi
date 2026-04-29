# gstack Skills — Attribution Notice

## Source

- Repository: https://github.com/garrytan/gstack
- Vendored commit: e8893a18b18e32ebd63a21f6915337868249ebe1
- License: MIT (see LICENSE)
- Copyright: (c) 2026 Garry Tan

## What was vendored

The following skill directories were copied verbatim from the upstream commit above:

- `plan-ceo-review/SKILL.md`
- `plan-eng-review/SKILL.md`
- `review/SKILL.md` (+ `review/specialists/`)
- `ship/SKILL.md`
- `browse/SKILL.md`
- `qa/SKILL.md` (+ `qa/templates/`, `qa/references/`)
- `qa-only/SKILL.md`
- `setup-browser-cookies/SKILL.md`
- `retro/SKILL.md`

## Modifications

None — files are copied verbatim. The `nooto-gstack` Pi extension registers these skills
via the `resources_discover` event (pointing Pi at this directory), and also registers
the 9 slash commands via `pi.registerCommand`.

The upstream SKILL.md files contain gstack-specific preamble bash blocks that invoke
`~/.claude/skills/gstack/bin/gstack-*` binaries. These are not present in this environment.
All such calls use `2>/dev/null || true` fallbacks and fail gracefully — the substantive
skill instructions that follow are unaffected.

The `/browse` slash command is stubbed: gstack's browse skill relies on a Bun-compiled
binary not included here. Browser automation is available via the existing
`playwright-bridge` MCP tool registered by `nooto-mcp`.
