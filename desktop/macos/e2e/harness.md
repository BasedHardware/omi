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

```bash
cd desktop/macos
OMI_SKIP_STALE_BUNDLE_SCAN=1 OMI_APP_NAME=omi-harness-test OMI_AUTOMATION_PORT=47888 ./run.sh --yolo
```

In another shell:

```bash
python3 scripts/omi-harness run e2e/flows/harness-smoke.yaml --lane visual --port 47888
python3 scripts/omi-harness summarize latest
python3 scripts/omi-harness latest
python3 scripts/omi-harness compare <before-run> <after-run> --markdown
python3 scripts/omi-harness cleanup --keep 10
```

For `ui` lane AX assertions, pass the named bundle id:

```bash
python3 scripts/omi-harness run e2e/flows/harness-smoke.yaml \
  --lane ui --port 47888 --bundle-id com.omi.omi-harness-test
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

Use `wait:` after bridge steps when a state or trace must settle before the next
step. Keep automated checks to facts the harness can measure directly: state,
traces, logs, timing, and AX text. The harness does not score screenshot quality;
the agent should open the PNGs listed in `summary.md` and judge layout, polish,
clipping, empty states, and visual regressions directly.

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
