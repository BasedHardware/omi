# AIDLC State

- **Phase**: implementing
- **Branch**: feat/auto-router-v1
- **PR**: (none — not yet opened per AGENTS.md: "Never push or create PRs unless explicitly asked")
- **Worktree**: /Users/choguun/Documents/workspaces/cool-projects/omi-worktrees/auto-router-v1
- **Last action**: 2026-06-25T10:05:00Z
- **Next action**: Run /implement T-001 (backend scoring engine — `score(model, task) -> float`)
- **Notes**:
  - Feature: Auto-router v1 — task-based model selection across Omi
  - Spring profile LOCKED: `0.18 / 0.88` (previous cycle, shipped as #8152)
  - Auto-router spec/plan architecture: 5 task types, quality+latency+cost scoring, per-task weights, daily refresh (24h TTL + asyncio.Lock + stale fallback), STANDALONE MVP (not extending upstream's `/v1/auto/model-pick`)
  - Plan structure: 8 vertical-slice tasks (T-001 scoring → T-008 PR polish), mostly linear dependency
  - **T-001 is the entry point** — pure function `score(model, task) -> float`, no I/O, all other tasks build on it
  - User confirmed at 2026-06-25T10:00:00Z: "yes, start plan" — full go-ahead
  - Branch history on top of upstream/main `ed0096b89`:
    1. `641574797` — spec
    2. `(?pending)` — plan + state update
  - DeepWiki grounding used: backend module layout, RealtimeHubController pattern, AutoModelSelector structure, asyncio.Lock + 24h TTL pattern from upstream's auto_model.py
  - No push, no PR until user explicit approval per AGENTS.md

_Updated: 2026-06-25T10:05:00Z_
