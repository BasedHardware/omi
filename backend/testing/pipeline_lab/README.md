# Pipeline lab

## Start here

Run from `backend/`. Three commands cover most work:

```bash
python -m testing.pipeline_lab affected                       # which scenarios and stages your diff can change
python -m testing.pipeline_lab scenario run [NAME ...] --keep DIR   # run them (default: every committed scenario)
python -m testing.pipeline_lab view DIR                        # look at the result in a browser (loopback)
```

- **A pass** means every `expect` row of the scenario held on the conversations the real v3 code built, and
  on the answer the product's Home route gave (exit 0). `failed` (exit 1) is a check that did not hold, or
  `nondeterministic` when `--repeat` runs disagree; `error` (exit 2) is a run that could not finish.
- **The run directory** goes to `--keep DIR`, else a fresh temp dir (printed at the end); never into git.
  `view` takes it, a `scenario compare` directory, the lab store root, or one day-replay run, and opens
  the matching page. `python -m testing.pipeline_lab scenario summary DIR` prints the verdict as markdown
  for a pull request.
- Agents: read [AGENTS.md](AGENTS.md) before judging a change with the lab.

## What the lab is

Two tools share this package. **Scenarios** script one capture -> Finish -> Home story in a small JSON
file and run it through the real conversations v3 code on a local emulator in well under a minute.
**Day replays** replay one recorded day and cache every stage's output so people and agents can browse
the result next to what production produced that day. In a classic day replay, transcripts come from
STT cassettes when the overlay selects them (else the stored production transcripts), and conversation
boundaries and speakers are production's own, taken from the stored rows; the chain then runs the real
product code for discard, notes, memories, tasks, would-have-fired notifications, goals, the daily summary
and the chat index. A v3 day replay runs the real v3 builder, so its boundaries are the product's.
Engine code lives here. **Data and verdicts never do.**

## Privacy (hard rules)

The run store, corpus days, audio, snapshots, LLM call logs and verdicts hold
private data. They live outside Git under owner-only modes (dirs `0700`, files
`0600`), and the store refuses any root inside a git worktree. Never commit a
real uid, credential, name, conversation id, transcript, verdict, screenshot or a
path to private data. Tests use synthetic fixtures only. Replays run under the
synthetic uid `local-dev-user`.

## Layout

| Path | Role |
|---|---|
| `contracts.py` | The single source for the store contract: typed records, the ordered `Stage` enum, item kinds, marks, `content_key`, time helpers. Stdlib only. |
| `store.py` | Private roots, id validation, atomic JSON writes, locked JSONL appends, corpus/run/cache/verdict readers and writers. |
| `keys.py` | Stage cache key: stage, input hashes, `backend/` tree hash, overlay hash, model config. |
| `ledger.py` | File-backed USD ledger with a hard cap; LLM, embeddings and STT all reserve on it. |
| `worktrees.py` | Pinned detached worktree per ref, tree-hash lookup, `python -I` arm runner. |
| `llm_proxy/` | LLM record/replay proxy with cap and per-call log; `fake_upstream.py` is a scripted gateway for tests and the smoke. |
| `registry.py`, `orchestrator.py` | Stage-driver and tool registry; the ordered, cached stage walk. |
| `cli.py`, `__main__.py` | The command line. |
| `seed/` | Snapshot reader, start state, emulator seed writer, synthetic snapshot, `corpus.py` (`corpus add-day`). |
| `stack/` | Lab environment: config, network guard, virtual clock, overlay, `runtime_env.py` (production overlay), `chain_smoke.py` (local-stack smoke). |
| `vector/`, `sinks/` | In-process vector index and embedders; capture-only side-effect sinks (pushes, webhooks, telemetry). |
| `chain/` | Ordered conversation driver, export, `entry.py` (process entry for the chain stages), `fake.py` (hermetic stand-in engine), `plugin.py`. |
| `day/`, `baseline/` | Day-level outputs; production normalization, pairing and status (the one implementation). |
| `timeline/`, `cassette/`, `lanes/` | Day timeline and lanes; STT cassettes (vendor prerecorded and Parakeet batch adapters); record/batch and sync replay; `lanes/plugin.py`. |
| `inspector/` | Stdlib server and static UI; `sample_run.py` (synthetic Lumen Bay day). |
| `v3/` | Conversations v3 replay: `feed.py` (recordings, arrival instants), `tasks.py` (loopback Cloud Tasks), `driver.py` (event loop), `product.py` + `run.py` + `entry.py` (real v3 code), `export.py` (contract rows, pairing by recording), `corpus.py` (add-day ingest), `select.py` (pipeline choice), `fake.py`, `smoke.py`, `prod_export.py` (read-only v3 exporter). |
| `scenario/` | Scripted capture -> Finish -> Home stories (see [Scenarios](#scenarios)): `spec.py` (file format, event plan), `checks.py` (expectations, outcomes), `ops.py` (events as product calls), `run.py` (one scenario in process), `budget.py` (operation counts, no-op writes, budgets), `home.py` (the Home routes, paging), `stack.py` (command, emulator bring-up, report), `scenarios/` (committed synthetic scenarios), `IMPORTER.md` (slice 2 design). |
| `ideal/` | Ideal days: `packet.py` (numbered lines), `schema.py` (validator), `score.py` (structure scoring), `runs.py` (score table and per-card diff across runs, no text), drafting passes. |
| `sample.py` | Minimal synthetic run, used only when the inspector plugin is absent. |

## Store

Run store at `$OMI_PIPELINE_LAB_ROOT` (default `/Volumes/Ephemeral/pipeline-lab`).
Verdicts are a record, so they live apart at `$OMI_PIPELINE_LAB_VERDICTS`
(default `~/.local/share/pipeline-lab/verdicts`).

```
corpus/<day_id>/day.json                          CorpusDay (date, timezone, snapshot label, coverage)
corpus/<day_id>/timeline.json                     islands, unknown gaps, lane per conversation, evaluability
corpus/<day_id>/baseline/conversations.jsonl      production conversations, ConversationRecord shape (id = production id)
corpus/<day_id>/baseline/raw_conversations.jsonl  the same rows in snapshot shape, lab uid; the chain replays these
corpus/<day_id>/baseline/memories.jsonl           production rows of the day (carry conversation_id)
corpus/<day_id>/baseline/action_items.jsonl
corpus/<day_id>/baseline/daily_summary.json       {title, overview, highlights}
corpus/<day_id>/start_state/                      meta.json + <entity>.jsonl: the account before the day (approximate)
corpus/<day_id>/audio/index.json                  [AudioIndexEntry]; path relative to audio/, start = UTC instant of byte 0
cache/<stage>/<kk>/<key>.json                     stage outputs; cache/llm, cache/stt_cassette, cache/embeddings
stt_records/<record_id>/                          record-stt ledger.json, vendor_log.jsonl, record.json
runs/<run_id>/run.json                            RunRecord (ref, commit, backend_tree, overlay, stages, extra.stt)
runs/<run_id>/conversations/<id>.json             ConversationRecord (+ replay block)
runs/<run_id>/day.json                            RunDay: daily_summary, goals, memory_delta, notifications, chat_index, recap
runs/<run_id>/baseline.json                       version 2: pairs, groups, field classes, digest (baseline/compare.py)
runs/<run_id>/baseline/conversations/<id>.json    production twin in the replay's shape
runs/<run_id>/chain.json, chain_entry.json        per-conversation chain status; the chain process summary
runs/<run_id>/ingest/<id>.json, index.json        replayed transcripts (transcribe stage)
runs/<run_id>/notifications.jsonl                 would-have-fired pushes (raw)
runs/<run_id>/sinks_egress.jsonl, sinks_telemetry.jsonl
runs/<run_id>/llm_calls.jsonl                     LlmCall (written by the proxy)
runs/<run_id>/vendor_log.jsonl                    what audio went to which vendor (+ outcome)
runs/<run_id>/decisions.jsonl                     serving pins, unpinned decisions, network refusals
runs/<run_id>/ledger.json, errors.log, chain_errors.log, processing_errors.log, <stage>.process.log
$VERDICTS/verdicts.jsonl                          Verdict, append-only; newest row per item wins; mark good|bad|clear
corpus/<day_id>/v3/recordings.jsonl               v3 days: the day's recordings (raw, lab uid); the v3 replay feeds these
corpus/<day_id>/v3/derived.jsonl, v3/meta.json    production's v3 conversations (raw) and day facts (live since, backfill runs)
corpus/<day_id>/baseline/v3_conversations.jsonl   production's v3 conversations in the contract shape: the v3 comparison target
runs/<run_id>/v3_driver.json, v3_tasks.jsonl      arrival plan and every event; every named task (enqueue, dedupe, due)
runs/<run_id>/v3_recordings.json                  where each replayed recording's speech went
```

A v3 conversation row adds `recordings` (source recording ids) and `v3` (`visible` on the phone's Home,
`home_hidden_reason`, `kind`, `tile_state`, notes state); its `structured` may carry `sections`,
`participants` and `gist`. Its id is derived from the uid, so pairing with production is by shared
recording (`baseline_id`, `baseline_ids`), never by id.

## Conversations v3

`run` replays a day through conversations v3 when the overlay turns `CONVERSATIONS_V3` on (the production
runtime env does) and the corpus day has v3 recordings; `model_config.pipeline: "classic" | "v3"` overrides.
Each recording is fed at its production arrival instant (`terminal_family_at`, else `record_sealed_at` + 60 s,
else `finished_at` + 60 s; stamps over 30 min late are ignored) as a fresh capture end through the product's
admission and durable finalization (`recording_short_path` wakes v3). Named Cloud Tasks run in process at
their virtual time (`service.reconcile`: outline, plan, commit, notes drain, created fanout) and the `*/5`
sweep runs while anything is pending. The lab writes the two app-capability markers the phone would
(`client_gate.note_client_seen`, `client_capability.note_capable`) so admission at stage `beta` is the
product's own decision, and removes them after the run. `model_config.v3` tunes it:
`{"arrival": "production"|"finish", "arrival_lag_seconds": 60, "tail_hours": 2, "sweeps": true}`.

Not replayed: on-open (foreground) notes and Retry, which need a user opening the app; listen's live
in-progress passes (the batch lane has no transcript until a recording seals); production's builder lease
state at the day start (`open_id`, outline cache).

Comparison: a replay conversation lists every production conversation that shares its recordings
(`baseline_ids`). A production row that pairs with no replay conversation but is listed there has status
`merged` (`merged_into` the replay id), not `missing`. The inspector shows pairing groups (`baseline/compare.py`
`strong_links`): a merge, split or regroup renders as one row group.

**Seeding.** The start state is written once per run before the first arrival. Conversations are
history, so each row is encoded with the product's harness seam (`encode_conversation_for_write`, the
stored shape) and written in batches of 200, not through the per-row processing upsert. Memories go
through the product's ledger commit, 200 per chunk, halved until a chunk fits Firestore's 1 MiB entity
limit. A focused goal is created in the background, then focused with `focus_goal`. A row that still
cannot be written is counted per kind and reason in the run warnings, never dropped silently; a blob
still sealed under the production key (`open_loop_extractions`) is cleared and counted (the product reads
an undecodable one as absent). The reset is a `recursive_delete` of the lab user. `chain_entry.json`
and the discard stage report phase timings (`environment`, `seed`, `seed_vectors`, `driver`, `export`,
`day`) and the seed's own per-kind timings.

**Typesense.** If the local Typesense is not listening, the run sets the product's kill switch
`TYPESENSE_CONVERSATION_INDEX_WRITES=off` (and a 1 s client timeout), records decision
`typesense_unavailable` and a run warning; otherwise every conversation write waits out the search
client's retries.

Segment `start`/`end` are seconds from the conversation's `started_at`. A verdict's
`conversation_id` is the production id when the item's conversation has one (the replay
id is kept as `replay_conversation_id`), so marks follow an item across runs.

Every record keeps unknown keys in `extra` and writes them back, so a field one
lane adds survives another lane's round trip. Item `key`s come from
`contracts.content_key(kind, content)`: a hash of normalized text (NFKC,
casefold, collapsed whitespace, edge punctuation trimmed), so a verdict on a task
or memory still matches after a re-run that produces the same text.

## Scenarios

A scenario reproduces one capture -> Finish -> Home incident from a small JSON file, through the real v3
code. No deploy, no production data: the text is synthetic and the run uses the lab uid on a local emulator.

```bash
cd backend
python -m testing.pipeline_lab scenario check finish_after_reconnect_late_transcript   # validate, print the plan
<workspace>/bin/omi-heavy run -- python -m testing.pipeline_lab scenario run [NAME|FILE ...] \
    [--keep DIR] [--jobs N] [--repeat N] [--stt replay|record-local|record-vendor] [--json]
```

`run` with no names runs every committed scenario (`scenario/scenarios/*.json`). It needs `firebase`,
Java 21 (a Homebrew `openjdk@21` is used when present) and `redis-server`, runs each scenario in a fresh
process, prints a timeline, the resulting conversations and each check. Exit: 0 when every scenario passed
or failed as expected, 1 on a failure, an unexpected pass or a repeat that differs, 2 on an error.

**Format.** Documented at the top of `scenario/spec.py`: origins, batch-lane recordings (audio span,
recording session, seal, batch transcript landing, scripted lines with speaker and `is_user`), stream gaps,
device-sync fragments with arrival instants, a Finish tap (fast finish on or off, provisional latency, more
taps of the same button with `again_at`), the account (`account`: cloud audio off takes the live lane;
`sync_off_at` turns sync off mid-run), Home history before the run (`seed`: visible, hidden-below-the-word-
floor, media, raw recording and discarded rows, in runs), an `env` overlay on top of this checkout's
production `backend-sync` profile, an operation `budget`, and `expect` rows. A row targets
`conversation_of` a label or `@finish` (`recordings`, `recordings_include`, `visible`, `on_home`,
`manual_end`, `hidden_reason`, `min_words`, `kind`, `titled`, `has_notes`, `home_titled`, `home_has_notes`,
`holders`), `no_hidden_with`, `recording` (its `fast_finish` outcome), `finish_response` (what tap N
answered: `outcome`, `titled`, `has_notes`, `discarded`, `recordings`) or `home_paging` (`visible_once`:
Home paged to its end shows every visible conversation once). Each row is optionally checked at an instant
(`at`) and named (`label`). Every field of one row must hold for the same conversation.
`expected_failure: {"reason", "checks": [labels], "strict": true}` marks a known bug; the fix PR deletes it.

**Operation counts and budgets** (`scenario/budget.py`). Every run counts, from the first event to the end:
Firestore document reads, writes, deletes and no-op writes (a write that left the document unchanged:
Firestore answers it with the document's previous `update_time`), by top-level collection and by collection
path, and vendor calls (requests to the fake LLM gateway; fast-finish STT calls and cassette plays). The
counts are taken at the emulator client's GAPIC API, the client `database._client` hands the product, so
every SDK path is seen once; reads are counted as Firestore bills them. Each no-op write names its call
site. The lab's own reads (snapshots, flags, the driver's pending check) are shown under `by_scope.lab` and
never budgeted; Home route calls count under `home`. Reads through a real-time TTL cache (`dream_control`, a ten-second `time.monotonic` cache) depend on
host speed, so they are kept apart in `wall_clock_reads`: shown, never totalled, budgeted or compared. So are the account-document reads and writes of the detached AI
profile refresh (`utils/ai_profile_refresh.py`, `racy_ops`): its write is fenced against concurrent effects on
its source conversation, and whether it lands depends on thread timing inside one event. To find where a count comes from, run with `OMI_PIPELINE_LAB_WRITE_SITES=1`: `ops.write_sites` then names the
call site of every write (it walks the stack on each commit, so it is off by default). The counts are in `result.json` and the verdict row
(`ops`), a column of `scenario summary`, a line of the text report and a table under the verdict in the web
view, and they are compared between `--repeat` runs like every other result field. A scenario's `budget`
(`{"reads": N, "writes": N, "deletes": N, "noop_writes": N, "vendor_calls": {"stt": N, "llm": N}, "note"}`)
turns each key into a check labelled `budget_<key>` (`budget_vendor_stt`) that fails above the cap. Set a
committed scenario's budget from its measured counts plus a small margin; when it shows no-op writes, set
`noop_writes` to the current count and say where they come from in `note`, never higher to hide them. A change
that moves a scenario past its budget fails it: raise a budget only with the reason in the pull request; a new
no-op write site is a finding to report, not a cap to raise.
Read no-op sites against the lab clock: it does not move inside one event, so a write of a `now`-derived
value (a v3 lease renewal's `until`, `database/conversations_v3_leases.py` `renew`) repeats exactly in the
lab where production's would move.
The two tie rules (a tap at a seal's instant runs first; two recordings starting together are refused) are
explained there too. Events run at their scripted instants (`--clock tick` adds real elapsed time).

**Audio.** A recording or sync fragment may give `audio_file` (a PCM WAV, relative to the scenario file)
instead of `speech`. Its words come from an STT cassette for that exact audio, then pass through the lane
code a day replay runs: production's decode, the real `PipelineWorker` (windows, packing, validation) and
`projection_segments` for batch recordings; `retrieve_vad_segments` and `postprocess_words` for sync. VAD is
the local Silero model; speaker labels come from the cassette; speaker identification does not run.
`--stt` picks how words are found:

- `replay` (default): committed `synthetic` cassettes (`scenario/fixtures/stt_cassette/`) and the lab
  root's cache; a miss is an error naming the command that would record it. No network.
- `record-local`: local Parakeet (production's `parakeet-tdt-0.6b-v3` checkpoint on CPU, the product's
  decoding, 30 s windows). An optional extra in its own venv (`requirements-local-stt.txt`), never imported by
  the default lab. Measured word error rate on synthetic speech: 2.3% on 60 s, 7.2% on 10 min. Local
  cassettes are evidence for everything after the words, not for transcription quality.
- `record-vendor`: the vendor prerecorded adapter with a spend cap (`--stt-budget-usd`); needs credentials
  and an `stt` provider and model pin in the scenario.

Without an `stt` pin the run takes the best cassette recorded for the file: vendor, then local, then synthetic.

**What runs as product code.** Each run lists its stand-ins in words, from its own counters, in
`result.json` (`stand_in_notes`, `audio_steps`), `verdict.json`, the text report and the web view. In short:

| Step | Product code | Stand-in |
|---|---|---|
| Capture admission, recording rows | `triggers.mark_new`, `upsert_conversation_with_lifecycle` | none |
| Finish tap | `retrieve_in_progress_conversation` picks the branch; with nothing in progress, `finish.finish_live_window` | Capture in progress: the finalization job's capture close is written as its outcome at the seal; the job does not run. |
| Record admission, fast finish | `batch_pipeline.live._manual_finish_admitted` -> `promote_manual_end` -> `fast_finish.run` | `admit_recording` does not run; one unit over the whole recording, a privacy check that allows, funding open. STT returns the recording's lines: scripted, or the cassette words of an audio recording. |
| Batch transcript landing | `update_conversation_segments`, `triggers.committed_sync_assignment` | The projection transaction (`replace_record`, its manual-end promotion, receipts) does not run, nor does the native completion that writes the sync-content ledger and consumes a recording-scoped Finish intent. So a Finish after a batch transcript landed is answered `requested` in the lab (`_native_projection_state` reads no ledger: `pending`) where production cuts, and a recording-scoped intent (#26288 fallback) is never consumed: scenarios do not judge `manual_end` in those two shapes. |
| Account settings | `users.set_user_private_cloud_sync_enabled` (start, `sync_off_at`) | The fast-finish privacy check reads that setting through `users.get_user_private_cloud_sync_enabled` instead of the batch privacy fence's generation read; the in-transaction fence of the write is the product's. |
| Device-sync fragment | `mark_new`, `upsert_conversation_with_lifecycle`, `committed_sync_assignment` | `/v2/sync-local-files` intake and its job do not run. |
| Reconcile, planner, notes, Home | `service.reconcile`, `service.sweep`, loopback named Cloud Tasks, the Home routes | Every LLM answer is the lab's fake gateway: one conversation per stretch, a new one at a line containing `switching topics`. |

**Isolation, `--jobs`, `--repeat`.** Each scenario process (each repeat too) gets its own Firestore project
`demo-lab-<run id>` on one multi-project emulator, its own leased Redis database, its own blob root and
Typesense writes off, so `--jobs N` runs N at once on one stack. `--repeat N` runs each scenario N times and
compares the repeats with `determinism.compare_runs`; any difference makes it `nondeterministic`. Peers, in
order: `FIRESTORE_EMULATOR_HOST` + `OMI_PIPELINE_LAB_REDIS` when both are given; the host's shared stack
(`scenario stack up|down|status`, pid file under the lab root); else an emulator and `redis-server` started
for the run (with only `OMI_PIPELINE_LAB_REDIS` given, that Redis and a started emulator).

**Run directory.** `run.json` (ref, tree, jobs, repeat, isolation), `verdict.json` (outcome and per-check
expected and actual), and per scenario `scenario.json`, `result.json`, `home.json`, `v3_tasks.jsonl`,
`decisions.jsonl`, `repeat-<k>/`.

**`scenario compare BASE [HEAD|--worktree]`** runs the same scenarios against two backend trees (a ref runs
in a pinned worktree with this checkout's lab vendored in) and writes `base/`, `head/` and `compare.json`.
Exit 0 when nothing differs, 1 when an outcome or conversation differs.

**The web view** (`view DIR`, or `scenario view DIR`) is a stateless read-only page on loopback: the verdict
and checks, Home as the route returned it with a snapshot picker and a "Not on Home" group, a timeline of
recordings, seals, landings, sync arrivals, gaps, Finish and checkpoints, a detail drawer, the stand-ins, and
base/head for a compare. "On Home" means the server's Home routes returned the conversation
(`GET /v1/conversations` and `/v1/conversations/live`, as the app calls them for a v3 account); the phone's
own client-side filtering is not modelled.

**CI.** The advisory job "Pipeline Lab Scenarios" (`.github/workflows/backend-hermetic-e2e.yml`) runs every
committed scenario with `--jobs 4 --repeat 2 --stt replay` on every backend pull request and merge-queue run,
writes the summary to the job page and uploads the run directory (artifact `pipeline-lab-scenarios`):
download it and run `view` on it. Measured 2026-11-26 on the lab host with the job's arguments: the 13 committed scenarios run in about
130 s (the five before them: 35 s); `.github/ci-budget.yaml` budgets the job at a 5-minute p50.

**Committed scenarios** (`scenario/scenarios/`), each with a budget from its measured counts:

| Scenario | Covers | From |
|---|---|---|
| `finish_single_recording_fast`, `audio_single_recording_finish` | Finish while capturing, fast finish, scripted and audio words | SCA-4386 |
| `finish_after_reconnect_late_transcript`, `finish_after_long_reconnect_gap`, `finish_transcript_never_lands` | Finish after a reconnect; a predecessor transcript late or never | SCA-4385, #26304 |
| `finish_next_opens_before_close` | a pendant pause: the next recording opens before the current one closes, then Finish | SCA-4385 class |
| `finish_after_second_close` | A closes, B closes two minutes later, then Finish must finish B (`expected_failure`) | #26288 |
| `finish_on_visible_conversation` | Finish on a closed conversation already on Home: a 404, and Home keeps its title and notes | #26241, #26242 |
| `finish_double_tap` | two Finish taps: one conversation, one fast-finish STT call | #26208 |
| `finish_no_closed_recording` | Finish with nothing to finish does not cut the next recording | #26288 |
| `finish_cloud_audio_off` | cloud audio off (live lane): Finish finishes the recording with no STT call | #26296 |
| `finish_privacy_refused_fast_finish` | the owner turns sync off before fast finish: `privacy_blocked`, zero STT calls | #26344 |
| `home_paging_past_hidden_runs` | Home paged past runs of hidden rows shows every visible conversation once | #25721, #25725, #26193 |

Turning a production incident into a scenario: [scenario/IMPORTER.md](scenario/IMPORTER.md).

## affected

`python -m testing.pipeline_lab affected [BASE..HEAD | BASE]` (default: the merge base with `origin/main` to
the working tree) maps every changed path to the scenarios worth running and the earliest day-replay stage
it can change, and prints the commands. Scenarios are named by `SCENARIO_TABLE` first (v3 runtime, Finish,
fast finish, visibility, the Home routes, the manual-finish hook, the production profile, the scenario harness
and view: every scenario; audio fixtures, cassette and lane code: the audio scenarios), then by measured
reach: `scenario/reach.json` lists the backend files in which a function ran during each scenario. Refresh it
after adding a scenario or when a scenario's product path changes:

```bash
python -m testing.pipeline_lab scenario run --trace-calls --keep DIR
python -m testing.pipeline_lab scenario reach DIR      # rewrites scenario/reach.json
```

An unmeasured scenario is named for any file the scenario runner imports. Stages come from import closures
of each stage's driver, an explicit table, and a run-everything default for unmapped backend paths; paths
outside `backend/` reach nothing.

## Stage cache

A day replay caches each stage's output under the stage key (below). The ingest-lane stages key only the
code they run, so an unrelated change still hits. `discard` through `chat_index` are one unit: production
runs them in one `process_conversation` per conversation and the day stages after it on the same emulator
state, so the lab caches, restores and re-runs them together; `--from-stage notes` re-runs from `discard`.
Every run reports hit or miss, seconds and LLM calls per stage. `--llm-mode refresh` never takes a stored stage.

## Cache key

`keys.stage_key(stage, backend_tree=, inputs=, overlay=, model_config=, schema_version=)`
hashes exactly those fields. The **tree** hash of `backend/` (not the commit)
means refs with an identical backend share cache entries. The orchestrator feeds
each stage the corpus day hash, the selected pipeline (`classic` or `v3`) and every
earlier stage's output hash, so a change
upstream invalidates exactly the stages whose inputs changed. The commit sha,
run id, paths and wall clock are not inputs. Per-item keys inside a stage come
from `StageContext.item_key(item, inputs)`.

## Plugging in a stage (other lanes)

Add `testing/pipeline_lab/<your dir>/plugin.py`:

```python
def register(registry):
    registry.add_stage(NotesDriver())             # .stage = 'notes'; .run(ctx) -> StageResult
    registry.add_tool('corpus-add-day', add_day)  # add_day(ToolContext) -> dict | int
```

A driver may also define `schema_version`, `cacheable = False` (its effect is
emulator state that a cached manifest cannot restore), `inputs(ctx)` (extra key
inputs) and `restore(ctx, output)`. `ctx.run_arm(module, args)` runs product code
from the run's pinned worktree with the overlay env, and `ctx.env` already
carries `OMI_LLM_GATEWAY_URL` when the proxy is on. Missing plugins are skipped;
a plugin that fails to import is an error. `$OMI_PIPELINE_LAB_PLUGINS` adds more
modules (comma separated).

## LLM proxy

Point the backend's `OMI_LLM_GATEWAY_URL` at the proxy (`run --llm-upstream URL`
starts one per run). It keys each POST on method, path, the JSON body minus
`user`/`prompt_cache_key`/`safety_identifier`/`metadata`, and the feature and
Anthropic version headers. It serves hits byte for byte (SSE included), forwards
misses after reserving the worst case on the run ledger, and appends one
`llm_calls.jsonl` row per request. Modes: `record` (default), `replay` (miss =
HTTP 409, nothing sent) and `refresh` (always forward, overwrite). At the cap it
answers HTTP 402 `spend_cap_reached` with `x-should-retry: false`, so the SDKs
do not retry, and the run stops with exit 4.

Prices are estimates from a table (`--llm-prices FILE`, USD per million tokens:
`{"default_in", "default_out", "cached_factor", "by_model": {"substr": [in, out]}}`);
the gateway's rate card is authoritative.

Attribution (`llm_proxy/tagging.py`):

- per request, safe under fan-out: in the arm process call
  `install_httpx_tagging(proxy_url)` once, then wrap work in
  `with lab_tag('notes', conversation_id):`. Requests to the proxy carry
  `X-Pipeline-Lab-Stage` / `X-Pipeline-Lab-Conversation`. Wrap executor
  submissions in `carry_context(fn)`, since context vars do not cross
  `ThreadPoolExecutor.submit`.
- proxy-wide fallback, serial runs only: `set_session_tag(proxy_url, stage, conversation_id)`.

The proxy strips both headers before forwarding upstream.

## Command line

Run from `backend/`. Wrap heavy commands (`run`, `record-stt`) in the workspace's
`bin/omi-heavy run --`; do not wrap `serve` or `llm-proxy`.

```bash
python -m testing.pipeline_lab sample-run --json
python -m testing.pipeline_lab corpus list|show <day>|add-day ...
python -m testing.pipeline_lab run --day <day> --ref <ref> [--overlay overlay.json] \
    [--from-stage notes] [--stages a,b] [--budget-usd 5] [--llm-upstream URL] [--llm-mode record|replay|refresh]
python -m testing.pipeline_lab runs [--day <day>]
python -m testing.pipeline_lab show <run> [--conversation <id>] [--calls]
python -m testing.pipeline_lab verdicts list|export|add ...
python -m testing.pipeline_lab worktree ensure|tree-hash <ref>
python -m testing.pipeline_lab llm-proxy --run <run> --upstream URL [--port N]
python -m testing.pipeline_lab stages | doctor
python -m testing.pipeline_lab corpus add-day --snapshot DIR --date YYYY-MM-DD --timezone TZ [--audio-dir DIR]
python -m testing.pipeline_lab record-stt --day <day> --adapter prerecorded|parakeet_batch [--provider P] --model M --budget-usd N
python -m testing.pipeline_lab overlay from-runtime-env [--runtime-env ARM/backend/deploy/runtime_env.yaml] [--owner-uid-file F] --out overlay.json
python -m testing.pipeline_lab serve [--port 8765] [--allow-login LOGIN]
python -m testing.pipeline_lab view PATH [--port N]   # scenario run/compare dir, store root, or runs/<run id>
```

`run` also takes `--in-place` (run this checkout's backend unpinned, in a fresh process),
`--engine product|fake` (fake = hermetic plumbing check, no emulator) and
`--allow-lock-mismatch` (a lock drift between harness and arm otherwise fails closed).
Stages before `--from-stage` are restored from cache or skipped; `--from-stage discard`
starts from the stored production transcripts.

`make pipeline-lab ARGS="runs --json"` runs the same CLI from the repo root.
Every command takes `--json`. Exit codes: 0 ok, 2 refusal or error, 3 transport,
4 spend stop. A command whose engine is not registered fails with
`tool not registered: <name>`; a run with a stage that has no driver fails
before creating the run with `stage driver not registered: <stages>` (or skips
it with `--allow-missing`).

Overlay file (one schema): `{"name", "env": {...}, "model_config": {...}, "serving": {"NAME": true},
"gates": {"module:function": value}, "strict": false}`. Cohorts are pinned only through
`serving` (raw `*_SERVE_PERCENT` / `*_SERVE_UID_SHA256S` env is refused). Env values whose
names look secret are redacted in `run.json`. `model_config.stt` picks the cassettes the
`transcribe` stage plays: `{"adapter": "prerecorded"|"parakeet_batch", "provider", "model",
"language", "vocabulary", "sync_mode": "span"|"exact"}`.

`overlay from-runtime-env [--service backend-sync] [--owner-uid-file F] --out FILE`
builds an overlay from the ref's `deploy/runtime_env.yaml` production profile: the lab
clears the process env, so without it every flag takes its code default. `backend-sync` is
the default service because it runs the v3 reconcile task (outline, notes, derived effects).
Every serve decision is pinned (cohorts through the owner uid when given; the rest are
uid-independent), and uid allow-lists carry the owner's membership over to the lab uid; the
owner uid never reaches the overlay. Read the uid from a 0600 file, never the environment.

## Worktrees

`worktree ensure <ref>` creates or reuses a detached checkout
`pipeline-lab-<sha12>` under `$OMI_PIPELINE_LAB_WORKTREES` (default
`$OMI_WORKTREES/omi`, else `/Volumes/Ephemeral/scratch/worktrees/omi`), using the
`git` on PATH. It refuses anything under `~/workspace`, and before every use it
checks that HEAD is the pinned sha and `backend/` is unmodified. Arms run on the
harness interpreter. `check_lockfile` fails closed when the arm's dependency lock
differs from the harness's.

## Tests and smoke

```bash
cd backend
for f in tests/unit/test_pipeline_lab_*.py; do python -m pytest "$f" -q; done   # one process per file, as CI
testing/pipeline_lab/stack/run_chain_smoke.sh   # LOCAL-STACK SMOKE: emulator + redis on 8295/6391, synthetic day
FS_PORT=8296 REDIS_PORT=6392 SMOKE_MODULE=testing.pipeline_lab.v3.smoke \
  testing/pipeline_lab/stack/run_chain_smoke.sh [--ref SHA]   # the same for a synthetic v3 day
```

`test_pipeline_lab_integration_e2e.py` drives the CLI end to end on a synthetic snapshot with
the fake engine; the smoke runs the real product chain against a Firestore emulator.

## Runbook: replay a real day (lead, on the lab host)

Private paths are environment variables; nothing below goes in git.

```bash
export OMI_PIPELINE_LAB_ROOT=/Volumes/Ephemeral/pipeline-lab          # 0700, outside git
export OMI_PIPELINE_LAB_VERDICTS=~/.local/share/pipeline-lab/verdicts
export SNAPSHOT_DIR=...      # a fetch-owner-audio snapshot taken at or after the day
export AUDIO_DIR=...         # optional: <conversation_id>.<ext> clips of that day
export DAY=YYYY-MM-DD TZ=America/Los_Angeles
HEAVY=<workspace>/bin/omi-heavy
cd backend

# 1. Corpus day (local files only, never the network)
python -m testing.pipeline_lab corpus add-day --snapshot "$SNAPSHOT_DIR" --date "$DAY" --timezone "$TZ" \
    --audio-dir "$AUDIO_DIR" --json

#    A v3 export beside the snapshot (v3/prod_export.py, read-only, owner guard injected by path) adds the
#    day's recordings and production's v3 conversations; runs then replay v3 under the production overlay.

# 2. Production flags at the ref under test (owner uid from a 0600 file: cohorts and allow-lists; never written)
python -m testing.pipeline_lab worktree ensure "$REF" --json      # pinned arm; its runtime env is the source
python -m testing.pipeline_lab overlay from-runtime-env --runtime-env "$ARM/backend/deploy/runtime_env.yaml" \
    --owner-uid-file "$UID_FILE" --out "$OMI_PIPELINE_LAB_ROOT/overlays/prod.json" --json

# 3. Local stack: Firestore + Auth emulators, Redis, Typesense (dev-up ports 8085/9099/6380/8108)
make dev-up            # or point FIRESTORE_EMULATOR_HOST / OMI_PIPELINE_LAB_REDIS / _TYPESENSE elsewhere

# 4. Run with a budget against the real gateway (proxy cap; exit 4 at the cap). The gateway credential
#    comes from your env only; the product inside the lab holds a placeholder.
export OMI_PIPELINE_LAB_UPSTREAM_TOKEN=...   # e.g. from the dev gateway's service token reference
$HEAVY run -- python -m testing.pipeline_lab run --day "$DAY" --ref <branch|sha> \
    --overlay "$OMI_PIPELINE_LAB_ROOT/overlays/prod.json" --from-stage discard \
    --llm-upstream "$OMI_LLM_GATEWAY_URL" --budget-usd 5 --json
#    re-run after a change: same command; unchanged calls are served from cache/llm
#    replayed transcripts: record-stt first (billable, capped), then add model_config.stt to the overlay

# 5. Inspector over the tailnet (loopback bind; tailscale serve, never funnel)
python -m testing.pipeline_lab serve --port 8765 --allow-login "$TAILNET_LOGIN" &   # stop it by PID when done
tailscale serve --bg --https=8765 http://127.0.0.1:8765
```
