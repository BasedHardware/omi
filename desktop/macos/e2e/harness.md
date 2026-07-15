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
- `ax.activate`
- `ax.expect`
- `power.sample`

`ax.activate` is UI-lane-only and activates a SwiftUI/AppKit control by its stable
accessibility identifier — never a coordinate. AX steps require a named
non-production bundle id (`com.omi.omi-*`); the harness refuses production and
unnamed bundle ids. `ax.expect` supports `identifiers_visible`, ordered
`focus_order` assertions over the interactive AX tree, and exact
`voiceover_labels` keyed by stable identifier. Use these only for static,
user-facing controls; expected labels must never contain user content.

```yaml
- name: Verify chat-first sidebar accessibility contract
  ax.expect:
    identifiers_visible:
      - chat-first-sidebar-chat
      - chat-first-sidebar-goals
    focus_order:
      - chat-first-sidebar-chat
      - chat-first-sidebar-goals
    voiceover_labels:
      chat-first-sidebar-chat: Chat
      chat-first-sidebar-goals: Goals

- name: Open Goals by stable accessibility identifier
  ax.activate:
    identifier: chat-first-sidebar-goals
  wait:
    state.chatFirstRoute: goals
```

Use `wait:` after bridge steps when a state or trace must settle before the next
step. Keep automated checks to facts the harness can measure directly: state,
traces, logs, timing, and AX text. The harness does not score screenshot quality;
the agent should open the PNGs listed in `summary.md` and judge layout, polish,
clipping, empty states, and visual regressions directly.

Before adding an AX step, inspect `./scripts/omi-ctl actions`. Action descriptors
include `surfaces`, `safety`, `sideEffects`, and `examples`; use a matching semantic
`bridge.action` first when `preferSemantic` is true, especially for read-only probes,
local captures, and deterministic visual fixtures.

Bridge navigation returns only after its requested destination is mounted; the
Chat-first shell additionally requires the exact route-visible acknowledgement.
Use `wait:` for data, traces, or other readiness checks that follow navigation.
If a flow genuinely needs a fixed pause, pass `settleMs:` on `bridge.navigate`
payloads, `/conversation/open` payloads, or as an action param.

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

## Chat-first local fixture flows

`chat-first-cohesive.yaml`, `chat-first-question-deferral.yaml`,
`chat-first-cold-start.yaml`, and `chat-first-capability-isolation.yaml` are
manual flows. They require the server-owned local fixture; the desktop bridge
never manufactures eligibility, goals, tasks, captures, prompts, question
options, or rollout state.

```bash
PROVIDER_MODE=offline make dev-up
make seed-memory-scenario SCENARIO=happy_path
make chat-first-e2e-fixture CHAT_FIRST_E2E_ACTION=prepare CHAT_FIRST_E2E_CASE=enabled
make desktop-run-local DESKTOP_APP_NAME=omi-chat-first-e2e DESKTOP_USER=omi-chat-first-e2e-enabled
```

Use `CHAT_FIRST_E2E_CASE=question` for the question-deferral flow. It begins
after a fixture-owned completed rich cold-start receipt, so the real
server-materialized question remains the actionable Chat tail.

The fixture helper authenticates through Firebase Auth emulator credentials and
checks the emulator-assigned UID against the harness manifest. Its read-back and
clock advance responses contain bounded state and counts only; never add a
desktop capability override or print fixture content from these flows.

`chat-first-capability-isolation.yaml` is a three-launch matrix: run the same
single-case flow once after preparing and launching each `ui_flag_off`,
`out_of_cohort`, and `unreachable_control` case in its own `omi-*` bundle and
automation port. The exact three command pairs live in the flow header. A
harness run cannot switch named bundles midway through a flow, so do not treat
one serial run as proof of all three accounts. Each run asserts the real
`legacy` shell can still open Chat. The separate behavioral tests named in that
flow own the byte-equivalent legacy tool manifest and the no-rich-block,
no-materialization, and no-proactive-work guarantees; do not add a bridge
fixture or client capability override merely to duplicate those assertions.
