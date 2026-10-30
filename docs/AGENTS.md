# Public documentation site

This folder is the **public Mintlify site "Omi Developers"** at
[docs.omi.me](https://docs.omi.me), for builders — not the repo's internal wiki.
End-user how-tos belong in the help center (help.omi.me): link, never duplicate.
Unlisted MDX/MD under `docs/` is still a public URL; absence from `docs.json` is
not a secrecy control.

## Allowed on the site

Developer platform (apps, API, MCP, CLI, SDKs), hardware and DIY, how Omi works,
contribution setup, and developer-platform reference. Nothing else. Do not dump
a design note, runbook, invariant, flag table, or agent-only rule here — put it
next to the owning code (`backend/docs/`, `desktop/macos/docs/`,
`.github/agent-docs/`) and link it.

## Style

Plain, direct, second person. No hype, no emoji, short pages. No volatile facts
in hand-written prose: prices, review/turnaround promises, counts like "22+
integrations", STT/LLM vendor or model names, tool version pins, personal
social handles — link the owning source instead. Enforced by
`.github/scripts/check_docs_volatile_facts.py` (its allowlist needs a reason a
reviewer can check).

## Navigation, redirects, checks

- Tabs: Get started / Build / Hardware / How Omi works / Contribute / Reference.
  Every MDX page appears in `docs.json`; after moving or deleting a page, add a
  `redirects` entry and fix in-repo links in the same change.
- `check_docs_site.py` gates nav→file, orphans, internal links, image refs, and
  redirect consistency on every docs change. Generated pages (edit the generator
  or source, never the block): CLI commands ←
  `sdks/python-cli/tools/gen_commands_doc.py`; MCP tool inventory ←
  `scripts/generate_mcp_tools_doc.py`.

## Changelog

`doc/reference/changelog.mdx` covers developer-platform changes only (API, MCP,
SDK, CLI, firmware/BLE). A merged PR changing one of those surfaces adds a
one-line past-tense entry with the PR link atop the matching month. App release
notes never go there.
