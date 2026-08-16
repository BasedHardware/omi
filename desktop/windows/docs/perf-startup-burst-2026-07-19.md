# Windows desktop — startup burst (system-wide launch lag) — 2026-07-19

User report: when the Omi app opens, the **whole computer** lags — the mouse cursor goes
slow/glitchy for a couple seconds, then recovers. System-wide cursor lag means Omi's startup
saturates a *shared* resource (all-core CPU, GPU/DWM compositor, or the main process's ability
to service window/compositor IPC), not just its own process.

Branch: `perf/win-startup-burst` (worktree `.worktrees/startlag`), from `origin/main` @ `3638622b49`.

## TL;DR

The burst is the main-window **`ready-to-show` handler running ~20 background-service starts +
3 auxiliary `BrowserWindow` creations (capture / insight-toast / glow) synchronously in ONE
tick at first paint**. That produced a ~1s main-thread stall and a 4→7 renderer-spawn storm at
the exact moment the window appears — stuttering the whole desktop.

Fix: `scheduleStartupSteps()` runs each step on its own timer tick (24ms gap) so the event loop
yields between steps and the window creations are staggered instead of simultaneous. Order
preserved, nothing dropped, no user-visible startup behavior change.

**Result (system-jitter probe = whole-machine scheduling lag = the cursor-stutter proxy):**

| Boot | GPU mode | worst system jitter |
|---|---|---|
| before, cold Vite | software (dev SwiftShader) | 243 ms |
| before, warm | software | 278 ms |
| before, warm | **hardware** | 203 ms |
| **after, warm** | software | **70 ms** |
| **after, warm** | software | **24 ms** |

4–10× reduction, from clearly-perceptible to imperceptible.

## How it was measured

Isolated dev instance only (worktree `startlag`: renderer `:5229`, CDP `9301`, profile
`omi-windows-sandbox-startlag`). The user's live app (`:5179`) was never touched.

Three signals, captured on the same boots:
- **`src/main/dev/startupProfiler.ts`** (new, env-gated `OMI_STARTUP_PROFILE=<path>`): samples
  `app.getAppMetrics()` per Electron process + a main-process **event-loop lag probe** (a
  self-rescheduling timer records how late it fires = main-thread blocking) + `timedStep()`
  per-operation attribution. Inert (zero cost) unless the env var is set — safe in packaged builds.
- **`scripts/jitter-probe.mjs`** (new): a standalone `node` process running a ~125Hz timer,
  recording per-bucket scheduling lag. A separate process starved of timely scheduling is a
  proxy for whole-system saturation (what makes the OS cursor feel slow). Run alongside the boot.
- Perf marks (`src/shared/perf.ts`) for phase timing.

## Findings

1. **`ready-to-show` synchronous burst (root cause).** Peak main-thread stall at first paint:
   **872 ms (software GPU) / 1081 ms (hardware GPU)**. Present under BOTH GPU modes, so this is
   *not* primarily a dev-only SwiftShader effect — packaged builds have the same synchronous
   main work + window storm. SwiftShader adds only ~27% extra jitter (203 → 278 ms) on top.
2. **Window-creation storm.** capture + insight-toast + glow were created back-to-back in the
   same tick; process count jumped 4→7 at first paint. Transparent/layered window creation churns
   the Windows DWM compositor — a direct cursor-stutter mechanism.
3. **Suspect "synchronous `loadIndex` of up to 5000 embedding rows" — DEBUNKED for real data.**
   This user has 7 `action_items` + 58 `staged_tasks` embeddings = ~65 rows, ~**3 ms** to read +
   build the index. The "5000" was a theoretical cap; not a real startup cost here. Left where it
   is (now staggered like the rest).

## The fix

- `src/main/startupScheduler.ts` — `scheduleStartupSteps(steps, gapMs=24)`: one step per timer
  tick, error-isolated (a throwing service start never blocks the others), order preserved. First
  step at delay 0 so capture (continuous recording) isn't needlessly delayed; the whole schedule
  completes within ~0.5 s of first paint.
- `src/main/index.ts` — the `ready-to-show` body is now a `scheduleStartupSteps([...])` call.
  The existing `setTimeout(4000/4000/6000)` deferrals (source-id prewarm, audio-mute warm,
  what's-new) are unchanged. The `powerMonitor`/global-shortcut wiring stays synchronous and
  outside the scheduler.
- Unit test: `src/main/startupScheduler.test.ts` (ordering, spacing, error isolation).

## Known residual (follow-up, NOT the reported symptom)

A single ~1 s main-thread stall still occurs ~2 s AFTER first paint (t≈18 s in dev), separate
from the now-small staggered steps (each ≤145 ms). Because it no longer coincides with the window
storm / other work, it does **not** produce system-wide lag anymore (post-fix jitter is 24–70 ms).
It is app-internal jank — most likely the main-window renderer's boot/hydration and, in dev, Vite
on-demand transform (packaged builds have pre-bundled renderers). Worth a separate look; out of
scope for the system-wide-lag fix.

## Dev vs packaged

The stagger helps BOTH (the root cause is GPU-mode-independent). The dev-only SwiftShader adds a
secondary ~27% jitter penalty; the user runs `pnpm dev`, so they get both benefits. The dev Vite
cold-transform also inflates *time-to-first-paint* (~13–18 s) but that is a dev-server artifact,
not part of the shipped burst.
