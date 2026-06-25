# AIDLC State

- **Phase**: specifying
- **Branch**: feat/auto-router-v1
- **PR**: (none — not yet opened per AGENTS.md: "Never push or create PRs unless explicitly asked")
- **Worktree**: /Users/choguun/Documents/workspaces/cool-projects/omi-worktrees/auto-router-v1
- **Last action**: 2026-06-25T09:45:00Z
- **Next action**: Run /plan to break .aidlc/spec.md into ordered tasks (after user review/approval of spec)
- **Notes**:
  - Feature: Auto-router v1 — task-based model selection across Omi (5 task types: ptt_response, screenshot_understanding, screenshot_embedding, general_assistant, transcription)
  - Branched from upstream/main `ed0096b89`
  - **Upstream-overlap acknowledged in spec:** The maintainer's `/v1/auto/model-pick` (realtime-voice only, 2 providers, AA-backed) is the model. This MVP is a STANDALONE broader framework (5 task types vs 1, quality+latency+cost vs quality+speed, per-task weights, mock benchmarks). Does NOT extend or modify upstream's auto-router.
  - DeepWiki grounding used: backend module layout (`backend/routers/` + `backend/utils/` + `backend/tests/unit/`), chat page (RealtimeHubController has its own provider selection, no central router exists), PTT page (existing AutoModelSelector pattern)
  - 8 Open Questions in spec — most are minor (recommendations locked), Q1 (endpoint path), Q4 (package vs single files), Q5 (Swift class name) are architectural but have clear recommendations
  - Per user's brief: "smallest version that already looks strategic" + "first step toward model selection across Omni" + 7-day build plan
  - No push, no PR until user explicit approval per AGENTS.md

_Updated: 2026-06-25T09:45:00Z_
