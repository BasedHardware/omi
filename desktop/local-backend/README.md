# Omi Local Backend

This is the lean local-first daemon scaffold for Omi Desktop. It is separate from
`desktop/Backend-Rust` so the local daemon can build and run without Omi cloud
credentials, Firebase, Firestore, Redis, GCS, pusher, paywall, or agent-proxy
dependencies.

## Run Locally

```bash
cd desktop/local-backend
cargo run
```

The daemon listens on `127.0.0.1:8765` by default and stores local data under the
platform app data directory.

Configuration is environment-based:

```bash
OMI_LOCAL_BACKEND_HOST=127.0.0.1 \
OMI_LOCAL_BACKEND_PORT=8777 \
OMI_LOCAL_BACKEND_DATA_DIR=/tmp/omi-local-backend \
cargo run
```

Verify the health endpoint:

```bash
curl http://127.0.0.1:8765/health
```

The response includes the service name, local mode, package version, bind
address, and resolved data directory.
