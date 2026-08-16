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

# Same driver.js and verdict.mjs, iOS simulator WKWebView at omi-ui://local.
# Not an L3/L4 gate. Acquires a run-scoped simulator lease before leasing a
# stack; never attaches to a stranger's already-booted device. A missing
# screen bridge or a simulator without a real microphone tap is a real token
# (bridge-unreachable / empty-transcript / skipped-tcc-denied), never a new
# skip word. The iOS control probe wires the same synthetic-PCM Listen grant
# the evidence walk uses: a simulator never grants microphone TCC.
node integration/control-acceptance/run.mjs --ios
```

Default Chat generation is the canned gateway on 8788. The runner refuses to
start a full run while 8791 is bound unless `OMI_CHAT_MODEL=real`. It refuses
`api.omi.me` and never launches `?rig=dev`.

`--journey` drives the listen → conversation → memory → Home → chat-retrieval
chain in the same shell, same leased stack, no hop stubbed. It is **L4**, a
named tier above L3: a measured full control-acceptance run is already ~3 min,
and the journey adds listen-stop, formation wait, and a retrieval clause on
top. Do not fold it into L3.

L4 is a real gate (`409b7ae057`). The pass token is
`CONTROL chat.memory=retrieved-and-streamed`. `--seam-break` is the negative
control: endpoints stay healthy and the served request drops the identified
memory.

```bash
node integration/control-acceptance/run.mjs --journey
# red-proof the retrieval seam (endpoints stay healthy; the served request
# drops the identified memory):
node integration/control-acceptance/run.mjs --journey --seam-break
```

Journey hops live in `JOURNEY_STEP_SLUGS` so they cannot pass a full control walk that never drove them. A journey skip (including `skipped-tcc-denied`) fails the run: the chain did not happen.

The runner prints `control-acceptance mode=… wall-clock=…ms`. Measured `--screen-proof` wall-clock on 2026-08-15 was
`141827ms` (~2.4 min), including the signed-app build. A measured full run on
2026-08-15 was `control-acceptance wall-clock=196163ms` (~3.3 min), one shell
launch with a 180s probe bound; the in-page driver is capped at 100 probe
attempts by the macOS hook.

## How an agent reads the output

Every control prints one line:

```text
CONTROL <slug>=<verdict>
```

Slugs are frozen in `verdict.mjs` (`STEP_SLUGS` for the control walk,
`JOURNEY_STEP_SLUGS` for `--journey`). **Add slugs; never rename one.** Pass tokens live next to them in `PASS_VERDICTS`. Adding a pass token
is allowed; renaming `home` / `chat` / `mic` / `screen` is not.

| slug | pass token | meaning |
|---|---|---|
| `mic` | `transcript-rendered` | `data-consumer-semantic` reports `segments>0`, `data-consumer-transcript` is non-empty, and visible `.listen-transcript-row` text is non-empty, within the outcome deadline (40 ticks × 0.4s). |
| `screen` | `frame-rendered` | after the capture control is clicked, a selected timeline frame (demo seed or ingest) renders `<img class="screen-frame-image">` with a `data:image/png;base64,` src and nonzero `naturalWidth`. `.screen-frame-unavailable` is a fail (`frame-unavailable`). Live capture starting is not a prerequisite for reading a picture that is already on the stage. |
| `chat` | `streamed-and-persisted` | the assistant streamed and persisted, **and** the provenance clause holds (see below). |
| `conversation` | `row-rendered` | Conversations lists a `data-conversation-id` that was absent before listen. |
| `memory` | `card-rendered` | Memories shows a new `data-proposition-id` whose `.proposition-text` carries a transcript needle from this run. |
| `home.memory` | `row-rendered` | Home's spine contains that identified card's rendered text. |
| `chat.memory` | `retrieved-and-streamed` | chat streamed and persisted, provenance agrees, **and** the served gateway request contains the `memory_projection` payload of the record id captured on Memories. |

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

### Journey chat retrieval

`chat.memory=retrieved-and-streamed` is the provenance conjunction **plus** a
join on the memory written earlier in the same run, by id:

1. The driver records `data-proposition-id` of the new Memories card.
2. After the probe, the runner `GET /v1/memories` and looks up that id.
3. The canned (or real) gateway JSONL records the served `/v1/chat/completions`
   messages. Context items are `memory_projection` previews; `sourceId` is
   stripped on the wire, so the payload of the identified record is what must
   appear.

Searching the assistant text for a plausible sentence is not this clause.
`--seam-break` leaves listen/memory/chat endpoints healthy and drops that
record from the served items before judging. The journey must print
`CONTROL chat.memory=memory-not-retrieved` while `CONTROL mic=transcript-rendered`
and `CONTROL memory=card-rendered` still hold.

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

The in-page driver is injected through the existing `OMI_PROBE_JS` hook on
macOS. It keeps progress in `sessionStorage` so a real `<a href>` navigation
does not reset the run. `--ios` writes that same driver into the simulator
Documents directory and the Flutter host evaluates it
(`frontend/shells/ios/app/lib/control_probe.dart`). The driver still does not
edit `frontend/packages/surfaces/**`.
