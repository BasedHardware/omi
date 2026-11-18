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

Core (this lane):

| File | Role |
|---|---|
| `contracts.py` | Typed records for the store contract, the ordered `Stage` enum, item kinds, stable `content_key` hashing. Stdlib only. |
| `store.py` | Private roots, atomic JSON writes, locked JSONL appends, corpus/run/cache/verdict readers and writers. |
| `keys.py` | Stage cache key: stage, input hashes, `backend/` tree hash, overlay hash, model config. |
| `ledger.py` | File-backed USD ledger with a hard cap; reserve before every billable attempt. |
| `worktrees.py` | Pinned detached worktree per ref, tree-hash lookup, `python -I` arm runner. |
| `llm_proxy/` | Local LLM record/replay proxy with cap and per-call log (`server.py`, `wire.py`, `tagging.py`). |
| `registry.py` | Stage-driver and tool registry other lanes plug into. |
| `orchestrator.py` | Walks the stages in order, consults the stage cache, records timings and status. |
| `cli.py`, `__main__.py` | The command line. |
| `sample.py` | Minimal synthetic day and run (`sample-run` fallback). |

Other lanes own `stack/`, `seed/`, `vector/`, `sinks/`, `chain/`, `day/`,
`baseline/` (chain), `timeline/`, `cassette/`, `lanes/` (ingest), `streaming/`
and `inspector/`.

## Store

Run store at `$OMI_PIPELINE_LAB_ROOT` (default `/Volumes/Ephemeral/pipeline-lab`).
Verdicts are a record, so they live apart at `$OMI_PIPELINE_LAB_VERDICTS`
(default `~/.local/share/pipeline-lab/verdicts`).

```
corpus/<day_id>/day.json                 CorpusDay
corpus/<day_id>/baseline/*.jsonl         production rows; conversations use the ConversationRecord shape
corpus/<day_id>/baseline/daily_summary.json
corpus/<day_id>/audio/index.json         [AudioIndexEntry], paths relative to audio/
cache/<stage>/<kk>/<key>.json            stage outputs; cache/llm/ holds recorded LLM responses
runs/<run_id>/run.json                   RunRecord
runs/<run_id>/conversations/<id>.json    ConversationRecord
runs/<run_id>/day.json                   RunDay
runs/<run_id>/llm_calls.jsonl            LlmCall (written by the proxy)
runs/<run_id>/vendor_log.jsonl           VendorLogEntry (what audio went to which vendor)
runs/<run_id>/decisions.jsonl            Decision (pinned serving modes)
runs/<run_id>/ledger.json                spend ledger
runs/<run_id>/errors.log                 traceback of a failed stage
$VERDICTS/verdicts.jsonl                 Verdict, append-only; the newest row per item wins
```

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
python -m testing.pipeline_lab serve | record-stt ...   # engines from the inspector / ingest lanes
```

`make pipeline-lab ARGS="runs --json"` runs the same CLI from the repo root.
Every command takes `--json`. Exit codes: 0 ok, 2 refusal or error, 3 transport,
4 spend stop. A command whose engine is not registered fails with
`tool not registered: <name>`; a run with a stage that has no driver fails
before creating the run with `stage driver not registered: <stages>` (or skips
it with `--allow-missing`).

Overlay file: `{"env": {...}, "model_config": {...}, "pins": {"<decision>": "<mode>"}}`.
Pins are written to `decisions.jsonl`. Env values whose names look secret are
redacted in `run.json`.

## Worktrees

`worktree ensure <ref>` creates or reuses a detached checkout
`pipeline-lab-<sha12>` under `$OMI_PIPELINE_LAB_WORKTREES` (default
`$OMI_WORKTREES/omi`, else `/Volumes/Ephemeral/scratch/worktrees/omi`), using the
`git` on PATH. It refuses anything under `~/workspace`, and before every use it
checks that HEAD is the pinned sha and `backend/` is unmodified. Arms run on the
harness interpreter. `check_lockfile` fails closed when the arm's dependency lock
differs from the harness's.

## Tests

```bash
cd backend && python -m pytest tests/unit/test_pipeline_lab_core_*.py
```
