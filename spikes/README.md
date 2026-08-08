# Backend spike artifacts

This directory keeps disposable, non-runtime drafts on the shared integration
branch so the branch remains the single handoff source of truth.

Patch files here are evidence, not applied production code. A successor must
re-check the current ruling of record, apply a patch on the shared branch,
update it for the current APIs, run the full gates, and obtain review before
turning any draft into runtime code.

- `authorized-context/`: blocked on unpublished ADR-010 authority semantics.
- `mcp-final-reauthorization/`: incomplete protocol draft; its exact receipt
  shape is coupled to the unresolved authority decision.

