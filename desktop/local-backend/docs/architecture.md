# Omi Local Backend Architecture

This note describes the backend-free desktop MVP shape that should survive past
the prototype stage.

## Crate Layout

`desktop/local-backend/` is a separate Rust workspace from
`desktop/Backend-Rust`. Keeping it separate prevents Firebase, Firestore, Redis,
GCS, pusher, paywall, agent-proxy, and Cloud Run assumptions from entering the
local daemon's critical path.

- `src/main.rs` owns startup, tracing, config loading, SQLite open, worker
  startup, and Axum router assembly.
- `src/config.rs` resolves the loopback bind address and data directory from
  environment variables.
- `src/health.rs` exposes health metadata for desktop startup checks.
- `src/routes.rs` is the HTTP API boundary for desktop MVP flows.
- `src/storage.rs` owns migrations, SQLite pragmas, repositories, normalized
  transcript rows, FTS, sync metadata fields, and local profile/settings.
- `src/processing.rs` owns durable job execution, deterministic fallback
  processing, and output persistence.
- `src/providers.rs` owns direct provider adapters. The current adapter is
  OpenAI-compatible chat completions and is configured only through local
  settings.

## Data Directory And Database

The daemon stores data under the platform app data directory by default, or
under `OMI_LOCAL_BACKEND_DATA_DIR` when set. The SQLite database is named
`omi-local-backend.sqlite`.

SQLite is the local source of truth. Startup creates the data directory, opens
the database, runs migrations, enables WAL and foreign keys, and creates FTS
indexes over conversation title, overview, and transcript segment text.
Transcript segments are stored as normalized rows keyed by conversation and
session. JSON exists at the API boundary for client compatibility, not as the
canonical transcript representation.

Tables include local IDs, timestamps, soft-delete fields, sync state/version,
and optional cloud IDs so later sync can map local records without making cloud
state authoritative.

## Desktop Backend Mode Selection

Desktop selects a backend through `DesktopBackendEnvironment`.

- `cloud` is the default and routes to the configured Omi cloud Python backend
  with auth.
- `local` / `local-daemon` routes MVP local flows to
  `OMI_LOCAL_DAEMON_URL`, defaulting to `http://127.0.0.1:8765/`, without
  Firebase auth.
- `custom` preserves the existing custom remote URL path for developer use.

Local daemon mode has an explicit capability matrix. Local conversation data,
transcript ingestion, search, memories, action items, settings, and optional
Firebase sign-in remain available. Managed agent VM, Omi backend provider
proxies, hosted transcription endpoints, public sharing, cloud sync, payments,
quotas, and Crisp support are unavailable before request construction.

## Direct Provider Adapters

Remote AI/STT providers are allowed only when explicitly configured by the user
or developer. The daemon talks directly to configured providers; it does not use
Omi backend provider proxies.

The MVP includes an OpenAI-compatible chat completions adapter with local
settings for base URL, model, and API key. The processing pipeline still works
without any provider key by using deterministic fallbacks:

- title: first meaningful transcript words, bounded length
- overview: clipped transcript excerpt
- action items: empty list
- memories: empty list

Provider keys stay in local daemon settings and are not sent to Omi-hosted
services.

## Cloud Sync Boundary

Cloud sync is a future optional adapter. The local database remains the source
of truth in local daemon mode. Sync metadata fields and cloud IDs are present to
support mapping, conflict handling, and outbox-style work later, but the MVP
does not require Omi cloud credentials or services for local read/write/search
or processing fallback.

## End-To-End Validation Checklist

Run the local daemon API smoke:

```bash
desktop/local-backend/tools/e2e_smoke.sh
```

Run local daemon tests:

```bash
cd desktop/local-backend
cargo test
```

Run focused desktop routing checks:

```bash
cd desktop/Desktop
swift test --filter APIClientRoutingTests
```

Manual desktop local mode check:

```bash
cd desktop/local-backend
OMI_LOCAL_BACKEND_PORT=8765 cargo run
```

In another terminal, launch the dev desktop app with:

```bash
cd desktop
OMI_DESKTOP_BACKEND_MODE=local \
OMI_LOCAL_DAEMON_URL=http://127.0.0.1:8765 \
OMI_PYTHON_API_URL=http://omi-cloud-invalid:9001 \
OMI_DESKTOP_API_URL=http://omi-rust-invalid:9002 \
./run.sh
```

The app-facing local MVP routes should use the loopback daemon and should not
require Firebase, Omi backend, Redis, Firestore, GCS, pusher, or agent-proxy
credentials. Cloud mode routing basics are covered by `APIClientRoutingTests`,
which verifies default cloud URL selection, custom URL selection, and local
daemon routing without auth.

## Known Limitations And Follow-Up Work

- The desktop app currently has a documented dev launch contract for the daemon;
  production supervision/packaging is not implemented.
- Hosted transcription is intentionally unavailable in local daemon mode. The
  MVP validates transcript import/append/finalize, not direct local STT parity.
- Existing desktop GRDB/Rewind stores are not migrated into the local daemon
  database yet.
- Local provider configuration exists at the daemon API/settings layer, but the
  user-facing settings workflow is still thin.
- Cloud sync remains disabled until a dedicated optional sync adapter is
  designed and tested.
