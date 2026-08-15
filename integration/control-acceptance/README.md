# Control-acceptance harness

Sibling of `integration/dev-app.sh --accept` — a second mode, not an edit of
`--accept`. That path snapshots the WKWebView and counts host-observed HTTP,
which is how a dead Rewind bridge and a dead microphone control both produced
`status=PASS`. This path clicks the real controls in the built macOS shell
against the live local stack.

Pass tokens are **outcomes**, not plumbing. `mic=transcript-rendered` means
the Listen surface drew a non-empty transcript. `screen=frame-rendered` means
Rewind drew a decoded PNG. `chat=streamed-and-persisted` also requires the
rendered capability label, the `service.boot` event, and `OMI_CHAT_MODEL` to
agree. `reached-os` is not a pass.

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

It is **held out of L3** (`integration/lanes.mjs`): currently red on
`CONTROL screen=frame-unavailable`, a true positive about Rewind. Home's
former red is closed (`CONTROL home=ready`). Keep it as a real step or an
explained hold, never a silent absence; wire it in when the harness prints
`screen=frame-rendered`. Measured `--screen-proof` wall-clock on 2026-08-15 was
`141827ms` (~2.4 min), including the signed-app build. A measured full run on
2026-08-15 was `control-acceptance wall-clock=196163ms` (~3.3 min), one shell
launch with a 180s probe bound; the in-page driver is capped at 100 probe
attempts by the macOS hook. The runner prints
`control-acceptance wall-clock=…ms`.

## How an agent reads the output

Every control prints one line:

```text
CONTROL <slug>=<verdict>
```

Slugs are frozen in `verdict.mjs` (`STEP_SLUGS`). **Add slugs; never rename
one.** Pass tokens live next to them in `PASS_VERDICTS`. Adding a pass token
is allowed; renaming `home` / `chat` / `mic` / `screen` is not.

| slug | pass token | meaning |
|---|---|---|
| `mic` | `transcript-rendered` | `data-consumer-semantic` reports `segments>0`, `data-consumer-transcript` is non-empty, and visible `.listen-transcript-row` text is non-empty, within the outcome deadline (40 ticks × 0.4s). |
| `screen` | `frame-rendered` | after the capture control is clicked, a selected timeline frame (demo seed or ingest) renders `<img class="screen-frame-image">` with a `data:image/png;base64,` src and nonzero `naturalWidth`. `.screen-frame-unavailable` is a fail (`frame-unavailable`). Live capture starting is not a prerequisite for reading a picture that is already on the stage. |
| `chat` | `streamed-and-persisted` | the assistant streamed and persisted, **and** the provenance clause holds (see below). |

A verdict in `SKIP_VERDICTS` (`skipped-tcc-denied`, `skipped-not-requested`) is
host state this harness does not own, or a slug the current mode did not drive.
The only legitimate capture skip is `skipped-tcc-denied`. Skips are listed on
`CONTROL-ACCEPTANCE skips:` and are **not** counted as passes. Do not turn a
real failure into a skip. `skipped-already-granted` is not a skip; it fails.

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

### Chat provenance

A provenance claim is a conjunction of three witnesses — rendered label, boot
event, lane intent. Two agreeing without the third is how a stub ships for a
week. See `docs/chat-provenance.md`.

1. **Rendered label** from `.chat-agent-capability` (and the assistant text).
2. **`service.boot`** from `${OMI_DEV_STACK_RUNDIR:-/tmp/omi-dev-stack}/logs/service.jsonl`.
3. **Declared intent** `OMI_CHAT_MODEL=real` vs unset/`test`.

`OMI_CHAT_MODEL=real` must render the real-provider label (`External model
response (<model>)`) and the assistant text must **not** equal `Local test
gateway answered.` A default run must render `Local test gateway` and the
canned answer. The canned direction is a negative control, not an afterthought.
Mismatch is `provenance-mismatch` (or `canned-answer` / `boot-missing` /
`answer-mismatch`) and fails `chat`.

### What the mic assertion actually exercises

Headless L3 injects synthetic PCM and skips installing the microphone tap
(`ListenCapture.swift`: `shouldInstallTap = !evidenceAudioEnabled`). This
harness unsets `OMI_CONSUMER_EVIDENCE_PATH`, so on a machine where TCC is
already granted it clicks Start and waits for the **real tap** to advance the
default scripted STT adapter (one PCM frame → one segment). That is the path
nobody else verifies. A skip is only `skipped-tcc-denied`.

Do not treat the older `ACCEPTANCE … servedCount=… status=PASS` line as a
control result. That line is a different mode.

## How to add a control step

1. Add a frozen slug to `STEP_SLUGS` and a pass token to `PASS_VERDICTS`.
   Never rename an existing slug. Outcome verbs, not plumbing verbs.
2. Drive the surface the way a user does inside `driver.js`: click the rendered
   control (or type into the real composer). Do not call a store method and
   call that a control test. The defect this harness exists to catch lived
   between the control and the host.
3. Record `{ slug, verdict }` once. Capture assertions observe the **rendered
   outcome** (transcript rows, decoded `<img>`, capability chip). TCC prompts
   cannot be clicked: assert the request reached the OS only as a wait, never
   as a pass, and never that a grant was given. Skip only `skipped-tcc-denied`
   (or `skipped-not-requested` for a mode that does not drive the slug).
   Outcome deadlines record the inspect result (`empty-transcript`,
   `frame-unavailable`), not a generic `timeout`.
4. Extend `verdict.test.ts` with a red-proof quoted both directions: a stub
   that must fail (`empty-transcript`, `.screen-frame-unavailable`, canned
   gateway while declaring real) and the matching green outcome. A token that
   has never failed is decoration.
5. Put the assertion at the layer the user observes. Reading a helper that the
   JSX then ignores is the wrong altitude.

The in-page driver is injected through the existing `OMI_PROBE_JS` hook. It
keeps progress in `sessionStorage` so a real `<a href>` navigation does not
reset the run. It does not edit `frontend/shells/**`.
