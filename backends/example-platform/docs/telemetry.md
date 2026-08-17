# Runtime telemetry

The local product writes append-only JSONL that an agent can read without
instrumenting a process first. No running stack is required to inspect it.

This is the local/dev inspection log. It is not the content-safe production
operational-telemetry contract in
`docs/memory-productionization/operational-telemetry-contract.md`. That
contract forbids routes and identifiers. This log exists so a 404 is visible
from the first click.

## Where the files are

Directory: `${OMI_DEV_STACK_RUNDIR:-/tmp/omi-dev-stack}/logs/`

One file per process:

| Process | File |
|---|---|
| service | `service.jsonl` |
| gateway | `gateway.jsonl` |
| chat | `chat.jsonl` |
| shell | `shell.jsonl` |
| surface | `surface-console.jsonl` |

Each file is capped at 32 MiB. When a write would exceed the cap, the current
file is renamed to `<name>.1` (replacing any previous generation) and a new
file starts. A process that never ran simply has no file.

If the directory cannot be created or written, the service prints one warning
and continues on stderr. Logging never crashes the product.

## Line shape

One event per line, no multi-line records:

```json
{"ts":"<ISO-8601>","proc":"service|gateway|chat|shell|surface","level":"debug|info|warn|error","event":"<stable-slug>"}
```

Event-specific fields follow the envelope. `ts`, `proc`, `level`, and `event`
are always present.

## What is never logged

Bearer tokens, API keys, `Authorization` headers, chat message bodies, memory
or conversation content, OCR text, and frame pixels. Log identifiers, counts,
statuses, durations, and sizes — never payloads. Query strings contribute key
names only, never values. Origins are redacted if they appear.

## How to read them

```bash
bun run logs
integration/dev-logs.sh
```

No arguments prints the last 50 events across every process file, merged by
timestamp, one line each.

| Flag | Effect |
|---|---|
| `--since <ISO-8601>` | Events at or after that timestamp |
| `--proc service\|gateway\|chat\|shell\|surface` | One process |
| `--level debug\|info\|warn\|error` | Exact level |
| `--event <slug>` | Exact event slug |
| `--errors` | `warn` and `error` only |
| `--json` | JSON array on stdout |
| `--limit <n>` | Last N matching events (default 50) |
| `--dir <path>` | Read this directory instead of the default |

Missing files are not an error. `--json` of an empty directory is `[]`.

## Event slugs

Grep these, not prose.

### service (`service.jsonl`)

| Slug | Level | When |
|---|---|---|
| `service.boot` | info | Process started. Fields: `persona` (`demo`\|`qa`), `stt_engine` (`scripted`\|`mlx-whisper`), `gateway_kind` (`none`\| the gateway's `/ready` `schema` \| `unknown`), `gateway_model` (the `/ready` `model` when present), `port`, `storage` (`:memory:`\|`file`). Never keys or origins. A configured gateway that does not answer `/ready`, or answers without a schema, is `unknown` — never guessed, never defaulted to real. |
| `service.ready` | info | Listener is accepting requests |
| `service.shutdown` | info | SIGINT/SIGTERM teardown |
| `service.boot.refused` | error | Boot aborted. Field: `reason` (closed code below) |
| `service.request` | info / warn / error | Every HTTP request. 2xx info, 4xx warn, 5xx error. Fields: `method`, `path`, `query_keys`, `status`, `duration_ms`, `owner_account_id`, `run_id`, `request_id` |
| `service.request.dropped` | warn | Client disconnected before a response existed |

`service.boot.refused` reasons: `invalid_port`, `port_unallocated`, `invalid_seed_count`, `invalid_persona`, `invalid_timezone`, `run_id_ready_record_mismatch`, `invalid_run_id`, `empty_ready_record_path`, `gateway_config_incomplete`, `invalid_stt`, `database_unopenable`, `seed_failed`, `bind_in_use`, `bind_failed`, `readiness_write_failed`.

### dev-stack (also `service.jsonl`, `proc=service`)

| Slug | Level | When |
|---|---|---|
| `dev-stack.start` | info | Exclusive run directory created |
| `dev-stack.ready` | info | `--up` left the stack running |
| `dev-stack.stop` | info | `--stop` |
| `dev-stack.refused` | warn / error | Stack would not start. Field: `reason` |

`dev-stack.refused` reasons: `invalid_run_id`, `run_dir_exists`, `log_dir_unwritable`, `port_occupied`, `gateway_not_ready`, `service_not_ready`.

Gateway, chat, shell, and surface-console files are written by those processes
to this same contract. Their slugs live with those lanes.

## Hot paths

Listen audio frames and screen frames are not logged per frame. HTTP upgrades
and periodic counters are the grain. A long session cannot fill a disk: see
rotation above.
