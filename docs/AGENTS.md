# Public documentation site

This folder is the **public Mintlify site** at [docs.omi.me](https://docs.omi.me).
It is not the repo's internal wiki.

Mintlify ignores non-MDX files such as this one. That does not hide pages:
**unlisted MDX or MD under `docs/` is still a public URL.** `llms.txt` indexes
nav pages; absence from `docs.json` is not a secrecy control.

## Allowed on the site

- How to use the app
- Hardware and DIY
- How to build on Omi: apps, API, MCP, CLI, SDK, firmware, contribution setup

## Forbidden

Do not add a page to `docs.json` unless it fits the allow list above.

Do not dump a design note, runbook, invariant, flag table, allowlist,
kill switch, writer mode, incident, epic, or agent-only rule here
"temporarily." Put it next to the owning code (`backend/docs/`,
`desktop/macos/docs/`, `.github/agent-docs/`, `product/invariants/`) or in a
private tracker.

BasedHardware/omi is public. Files in `backend/docs/` remain on GitHub. This
folder only controls what ships to docs.omi.me, not secrecy.

## Editing

- Read this file before adding anything under `docs/`.
- Contributor Cursor setup lives at `docs/doc/developer/Cursor.mdx` and points
  here. `.cursor/` is editor/agent configuration, not the public site.
- After moving a page, update in-repo links in the same change.
