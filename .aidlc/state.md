# AIDLC State

- **Phase**: specifying
- **Branch**: feat/auto-router-v2
- **PR**: (none — v1 PR #8343 is still open and pending merge; v2 will be a separate PR)
- **Worktree**: /Users/choguun/Documents/workspaces/cool-projects/omi-worktrees/auto-router-v2
- **Last action**: 2026-06-25T13:50:00Z
- **Next action**: Run /plan to break v2 spec into ordered tasks (after user review/approval of spec)
- **Notes**:
  - **v2 feature:** Auto-router v2 — Make it production-useful
  - **Built on:** v1 (17 commits, 142 backend + 15 desktop = 157 tests, all passing, PR #8343 ready for merge)
  - **v2 branched from:** `feat/auto-router-v1` (commit 9897edcb) — all v1 work preserved
  - **v2 focus:** Authentication + Observability metrics + ONE wired path (ChatProvider)
  - **v2 tasks (planned):**
    1. T-201: Add auth (`Depends(get_current_user_uid)`) to pick endpoint + tests
    2. T-202: Add metrics endpoint + pick history (in-memory ring buffer) + tests
    3. T-203: Wire `ChatProvider` to consult `AutoRouter` for "Auto" mode + Swift test
    4. T-204: Demo updates (show metrics endpoint, show auth requirement)
    5. T-205: Doc updates (developer guide, PR description for v2)
  - **5 Open Questions in spec** — most have clear recommendations locked
  - **Not modifying:** upstream `/v1/auto/model-pick`, upstream `AutoModelSelector.swift`, `ChatProvider.swift` core behavior (only a NEW helper function added alongside)
  - No push, no PR until user explicit approval per AGENTS.md

_Updated: 2026-06-25T13:50:00Z_
