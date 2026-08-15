# Control-acceptance harness

Sibling of `integration/dev-app.sh --accept` — a second mode, not an edit of
`--accept`. That path snapshots the WKWebView and counts host-observed HTTP,
which is how a dead Rewind bridge and a dead microphone control both produced
`status=PASS`. This path clicks the real controls in the built macOS shell
against the live local stack.

## Run

```bash
# stack must be local (4851 + canned 8788). Boots it with the demo persona if needed.
node integration/control-acceptance/run.mjs

# Rewind + omiScreenBridge only. Does not send Chat. Use when 4851 is already
# serving and is not paired with the canned gateway.
node integration/control-acceptance/run.mjs --screen-proof
```

Default Chat generation is the canned gateway on 8788. The runner refuses to
start a full run while 8791 is bound unless `OMI_CHAT_MODEL=real`. It refuses
`api.omi.me` and never launches `?rig=dev`.

It is wired as the second L3 step in `integration/lanes.mjs`. Measured
`--screen-proof` wall-clock on 2026-08-15 was `141827ms` (~2.4 min), including
the signed-app build. A full run is one shell launch with a 120s probe bound;
expect ~2–3 min when the binary is already built. The runner prints
`control-acceptance wall-clock=…ms`.

## How an agent reads the output

Every control prints one line:

```text
CONTROL <slug>=<verdict>
```

Slugs are frozen in `verdict.mjs` (`STEP_SLUGS`). Pass tokens live next to them
in `PASS_VERDICTS`. A verdict that starts with `skipped-` is host state this
harness does not own (TCC already granted or denied). Skips are listed on
`CONTROL-ACCEPTANCE skips:` and are **not** counted as passes.

Overall:

```text
CONTROL-ACCEPTANCE status=PASS|FAIL passed=N failed=N skipped=N
```

`status=PASS` only when every step passed or was a legitimate skip. A missing
step is `missing-step` and fails. `bridge-unreachable` on `screen` is the
2026-08-15 Rewind defect: the capture control posts to `omiScreenBridge` and
the shell never registered that channel.

`--screen-proof` records `skipped-not-requested` for every slug it does not
drive. Those are skips, not passes. A dead screen still fails the run.

Live red-proof, this worktree, 2026-08-15, `--screen-proof` against current
trunk (channel still unregistered):

```text
CONTROL screen=bridge-unreachable
CONTROL-ACCEPTANCE status=FAIL passed=1 failed=1 skipped=13
```

Green on `screen=reached-os` needs the host-bridge lane to register
`omiScreenBridge`. This harness does not stub that channel.

Do not treat the older `ACCEPTANCE … servedCount=… status=PASS` line as a
control result. That line is a different mode.

## How to add a control step

1. Add a frozen slug to `STEP_SLUGS` and a pass token to `PASS_VERDICTS`.
2. Drive the surface the way a user does inside `driver.js`: click the rendered
   control (or type into the real composer). Do not call a store method and
   call that a control test. The defect this harness exists to catch lived
   between the control and the host.
3. Record `{ slug, verdict }` once. Capture assertions observe that the OS
   permission API was *requested*, never that TCC granted it.
4. Extend `verdict.test.ts` with a red-proof: a mutation that should fail,
   and the skip-accounting case if the new step can skip.

The in-page driver is injected through the existing `OMI_PROBE_JS` hook. It
keeps progress in `sessionStorage` so a real `<a href>` navigation does not
reset the run. It does not edit `frontend/shells/**`.
