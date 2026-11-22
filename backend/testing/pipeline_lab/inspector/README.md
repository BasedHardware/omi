# Pipeline-lab inspector

A loopback web inspector for a replayed day: read the day the way the owner lived it and see at a
glance where the replay differs from what production produced. Plain HTML, CSS and JS served by a
stdlib Python server. No framework, no CDN, no build step, no new dependency.

## Run it

```bash
cd backend
# A synthetic store (fictional day, two runs) for UI work and tests. The root must be outside git.
python -m testing.pipeline_lab.inspector.sample_run \
  --root /Volumes/Ephemeral/pipeline-lab-sample --verdicts /Volumes/Ephemeral/pipeline-lab-sample-verdicts

# Serve a store (defaults: $OMI_PIPELINE_LAB_ROOT, $OMI_PIPELINE_LAB_VERDICTS, port 8765; --port 0 picks one).
python -m testing.pipeline_lab.inspector.server --root /Volumes/Ephemeral/pipeline-lab-sample \
  --verdicts /Volumes/Ephemeral/pipeline-lab-sample-verdicts --port 0
```

The server prints `{"url": ..., "pid": ...}`; stop it by that PID. `serve` is not a heavy command, so
do not wrap it in `omi-heavy`.

### From another device

The server binds loopback only and refuses any other address. Use `tailscale serve` (never funnel):

```bash
OMI_PIPELINE_LAB_ALLOWED_LOGINS=<your tailscale login> python -m testing.pipeline_lab.inspector.server
tailscale serve --bg --https=8765 http://127.0.0.1:8765     # and `tailscale serve --https=8765 off` after
```

A request that arrives through a proxy (non-loopback `Host`, or any `Tailscale-User-Login`,
`X-Forwarded-*` or `Forwarded` header) must carry a `Tailscale-User-Login` on the allow list, for
every route. Unknown `Host` headers are refused (DNS rebinding); `*.ts.net` and loopback are accepted,
others with `--allow-host`.

## What it reads and writes

It reads the DESIGN store contract (`corpus/<day>/…`, `runs/<run>/…`) and nothing else, through
`reader.py`, which validates every id against the contract id pattern and refuses any resolved path
outside the store (symlinks included). The only write is an append to
`$OMI_PIPELINE_LAB_VERDICTS/verdicts.jsonl` (file `0600`, directory `0700`). The server rebuilds each
verdict's `item_snapshot` from the store, so a client cannot record an item that does not exist.

| File | Role |
|---|---|
| `reader.py` | Store reads, content keys (same recipe as the contract), replay↔production pairing, statuses, item pairs |
| `views.py` | The JSON each route returns; callable directly by agents |
| `server.py` | Routing, audio with HTTP Range, access policy, verdict POST |
| `sample_run.py` | Synthetic corpus day + baseline + two runs + tone WAVs + optional sample verdicts |
| `static/` | `index.html`, `app.css`, `app.js` |

Pairing, grouping and change classification are `baseline/compare.py` (one implementation): the reader
uses `runs/<id>/baseline.json` when it is `version` 2 and covers every replay conversation, and otherwise
runs the same `compare.baseline_view` in memory. The unit the day page shows is a **group**: a 1:1 pair
(`same`, `cosmetic`, `content`), a `merge` (N production → 1 replay), a `split` (1 → N), a `regroup`
(N → M), `new` or `missing`. Each group carries tags (`home_dropped`, `summary`, `tasks`, `cosmetic`,
`worth`, …); every number in the "What changed" digest is the count of groups with that tag, and the chip
filters the list to exactly those groups. Text fields compare after casefold + whitespace + punctuation
normalization; emoji, category and the hidden reason (when both sides are hidden) are cosmetic and not
"worth a look". Items on the conversation page pair by content key, then by word overlap (≥ 0.45) as
`changed`, else `added` / `removed`. Differences are labelled `vs production`, never "regression":
production ran other code.

Day page: compact header, the digest (Home / Grouping / Content / Cosmetic), a "Worth a look" /
"Everything" toggle, Time / Most different sort, and the paired list (production left, replay right, a
time gutter in the middle: hour ticks, one lane per side, filled blocks are on Home). The day panel is a
collapsible side column. Conversation page: Home state of both sides on top; the Summary tab lists every
compared field, unchanged ones dimmed.

## API

See the module docstring of `server.py`. Every route is JSON except `/audio/<day>/<clip>` and
`/api/verdicts/export` (JSONL download).

## Keyboard

`j`/`k` next/previous conversation · `Enter` open · `/` filter · `↑`/`↓` item in tab · `←`/`→` tab ·
`1` good · `2` bad · `n` note · `Space` play/pause · `t` transcript replay → production → diff ·
`Esc` back · `v` verdicts · `?` help. Links accept `?tab=tasks` and `?tr=diff`.

## Tests

```bash
cd backend
<workspace>/bin/omi-heavy run -- .venv/bin/python -m pytest \
  tests/unit/test_pipeline_lab_inspector_server.py tests/unit/test_pipeline_lab_inspector_sample_run.py -q
```

Synthetic fixtures only. Never commit real runs, audio, transcripts, verdicts or screenshots of them.
