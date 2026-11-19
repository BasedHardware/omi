# Pipeline lab

Replays one recorded day through code as close to the production pipeline as
possible (conversation boundaries, speakers, transcript, notes, memories, tasks,
would-have-fired notifications, goals, daily summary, chat index), caches every
stage's output, and lets people and agents browse the result next to what
production produced that day. Engine code lives here. **Data and verdicts never do.**

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
runs/<run_id>/baseline.json                       pairs, status chips and changed fields (chain baseline/)
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
```

Segment `start`/`end` are seconds from the conversation's `started_at`. A verdict's
`conversation_id` is the production id when the item's conversation has one (the replay
id is kept as `replay_conversation_id`), so marks follow an item across runs.

Every record keeps unknown keys in `extra` and writes them back, so a field one
lane adds survives another lane's round trip. Item `key`s come from
`contracts.content_key(kind, content)`: a hash of normalized text (NFKC,
casefold, collapsed whitespace, edge punctuation trimmed), so a verdict on a task
or memory still matches after a re-run that produces the same text.

## Cache key

`keys.stage_key(stage, backend_tree=, inputs=, overlay=, model_config=, schema_version=)`
hashes exactly those fields. The **tree** hash of `backend/` (not the commit)
means refs with an identical backend share cache entries. The orchestrator feeds
each stage the corpus day hash and every earlier stage's output hash, so a change
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
python -m testing.pipeline_lab overlay from-runtime-env --out overlay.json
python -m testing.pipeline_lab serve [--port 8765] [--allow-login LOGIN]
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

`overlay from-runtime-env [--service backend-sync] [--owner-uid-env VAR] --out FILE`
builds an overlay from the ref's `deploy/runtime_env.yaml` production profile: the lab
clears the process env, so without it every flag takes its code default.

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

# 2. Production flags at the ref under test (owner uid only resolves partial cohorts; never written)
python -m testing.pipeline_lab overlay from-runtime-env --service backend-sync \
    --owner-uid-env OWNER_UID --out "$OMI_PIPELINE_LAB_ROOT/overlays/prod.json" --json

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
