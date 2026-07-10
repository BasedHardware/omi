# Omi Desktop Experience Harness

`scripts/omi-harness` runs cursor-free desktop experience checks against the local
automation bridge. Use it to collect behavior, latency, logs, traces, and screenshots
while iterating on the macOS app.

## Lanes

- `bridge` — drives semantic navigation/actions and state assertions. This is the
  default lane and should stay cursor-free.
- `visual` — includes `bridge` behavior plus app-side PNG export from the running
  window. It does not use `screencapture` and does not move the cursor.
- `ui` — reserved for final Accessibility checks via `agent-swift`. Use sparingly
  for real user-facing affordances, menus, sheets, permissions, onboarding, and OS
  integration.

## Artifacts

Runs are written under `desktop/macos/.harness/runs/`, which is gitignored. Artifacts
can contain real user data from logs, state, screenshots, AX trees, memories, and
chat content. Do not attach or publish a run directory unless you have reviewed it.

## Usage

From the repo root, start the local dev harness and launch a named desktop
bundle against localhost services:

```bash
make dev-up
make desktop-run-local DESKTOP_APP_NAME=omi-harness-test
```

In another shell, run the experience harness from `desktop/macos`. Version 1
flows are legacy-compatible and require an explicit opt-in:

```bash
cd desktop/macos
python3 scripts/omi-harness run e2e/flows/harness-smoke.yaml \
  --allow-legacy-flow-version --lane visual
python3 scripts/omi-harness summarize latest
python3 scripts/omi-harness latest
python3 scripts/omi-harness compare <before-run> <after-run> --markdown
python3 scripts/omi-harness cleanup --keep 10
```

For process CPU/RSS sampling, pass a unique command-line match for the named
bundle process:

```bash
python3 scripts/omi-harness run e2e/flows/ask-omi-chat-power-benchmark.yaml \
  --allow-legacy-flow-version \
  --process-match "/Applications/omi-harness-test.app/Contents/MacOS/Omi Computer"
```

For `ui` lane AX assertions, pass the named bundle id:

```bash
python3 scripts/omi-harness run e2e/flows/harness-smoke.yaml \
  --allow-legacy-flow-version --lane ui --bundle-id com.omi.omi-harness-test
```

## Typed Steps

Supported step types:

- `bridge.navigate`
- `bridge.action`
- `visual.export`
- `visual.action_sequence`
- `state.expect`
- `trace.expect`
- `log.expect`
- `ax.expect`
- `power.sample`

Use `wait:` after bridge steps when a state or trace must settle before the next
step. Keep automated checks to facts the harness can measure directly: state,
traces, logs, timing, and AX text. The harness does not score screenshot quality;
the agent should open the PNGs listed in `summary.md` and judge layout, polish,
clipping, empty states, and visual regressions directly.

Before adding an AX step, inspect `./scripts/omi-ctl actions`. Action descriptors
include `surfaces`, `safety`, `sideEffects`, and `examples`; use a matching semantic
`bridge.action` first when `preferSemantic` is true, especially for read-only probes,
local captures, and deterministic visual fixtures.

Bridge routes return as soon as the app has accepted the command. Prefer `wait:`
for readiness checks so benchmark timing separates command latency from UI settle
latency. If a flow genuinely needs a fixed pause, pass `settleMs:` on
`bridge.navigate` payloads, `/conversation/open` payloads, or as an action param.

Use `visual.action_sequence` for fast animations. It posts the bridge action and
captures frames concurrently, which avoids missing transitions that finish before
a normal action response returns:

```yaml
- name: Capture Ask Omi Open Animation
  visual.action_sequence:
    action: open_ask_omi
    params:
      wait: false
    target: floating
    frames: 8
    interval_ms: 16
```

Use `power.sample` after a bridge step has opened the target UI state. It samples
the app process with `ps` and records average/peak CPU plus RSS in the run
summary. This is not a replacement for Instruments or `powermetrics`, but it is
cheap enough for agents to run repeatedly while optimizing idle UI power.

```yaml
- name: Sample Open Chat Idle Power
  power.sample:
    warmup_ms: 500
    duration_ms: 8000
    interval_ms: 250
    max_avg_cpu_percent: 5
```
