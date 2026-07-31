# Median-user simulation (E8)

Grounded in the real PostHog profile ([user-profile.json](./user-profile.json)):
the average omi user sends ~3 short chat messages / 30d, median **0** tool
calls per message, is mobile, and has ~37 tasks / 7 memories / no big screenshot
corpus. Prior experiments (E1–E7) were all power-user-shaped; this one runs the
actual common case.

## Setup
- DB: median desktop user — 4,500 screenshots, 7 memories, 31 open tasks (with
  the real 63%-near-duplicate task pathology). Local, 2026-07-22.
- 4 queries drawn from the real top features (task lookup, daily recap, memory
  recall, task dedup — the dominant tool mix by user reach: `search_memories`,
  `get_action_items`, `get_daily_recap`).
- One-shot CLI path (model = Opus, no streaming heartbeat).

## Result

| Query | wall | tools | cost | correct |
|---|---|---|---|---|
| What are my open tasks? | 35.4s | 2 | $0.196 | ✓ |
| What did I do yesterday? | 28.0s | 2 | $0.179 | ✓ |
| What do you remember about my preferences? | 35.6s | 5 | $0.092 | ✓ |
| How many distinct times did I note reviewing the subagent PR? | 27.5s | 3 | $0.185 | ✓ |

All answers correct against ground truth (incl. the dedup case).

## Finding

The **latency problem hits the average user, not just the churn tail.** A median
user asking a trivial "what are my open tasks?" waits ~30s. With median real
usage at 0 tool calls/message, the fact that these simple lookups still spend
2–5 tool calls + ~30s is dominated by (a) the ~2-turn ToolSearch tax per
conversation (SDK defers the MCP tool schemas — see query-config.mjs) and (b)
Opus in the one-shot path. This directly validates the tool-access program:
**trimming the tool pool to kill the ToolSearch tax and running the light path
on a faster model helps the median user on every query**, not only the p99
runaway loops.

## Caveats
- One-shot CLI uses Opus; the mobile persistent-session path uses Sonnet +
  streaming, so first-token is faster there — but the tool count and ToolSearch
  tax are identical, so the ~30s floor largely holds.
- Local numbers (Mac mini offline); consistent with prior local runs.
