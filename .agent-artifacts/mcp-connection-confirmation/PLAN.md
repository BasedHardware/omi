# MCP connection confirmation

Replace the external-MCP OAuth callback's long, comma-separated tool catalog with
a compact, accessible confirmation that names the connected app and clearly tells
the user to close the browser and return to Omi. Preserve OAuth validation, tool
discovery, persistence and enablement. Do not add an unverified app deep link.

Verify the actual callback with synthetic state/provider/storage seams, including
HTML escaping and a large tool catalog. Exercise a local HTTP callback, inspect
the result at phone and desktop widths, and run the repository's selected backend,
type and preflight checks. Keep the PR draft until required verification passes.

Remove this kickoff-only plan from the final diff; retain the required UI evidence.
