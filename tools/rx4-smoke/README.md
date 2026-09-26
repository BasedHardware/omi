# rx4 smoke — agent-driven verification experiment (tschk stack)

Bounded evaluation of the tschk (The Software Company of Hong Kong) agent tooling
against this monorepo, run on 2026-09-26 in an Amp orb. The request was to "test
using tschk/eqts with rx4, zkr and praefectus". Research first, because the names
do not mean what that phrasing suggests:

| Name | What it actually is | Repo | License | Telemetry |
|---|---|---|---|---|
| **eqts** | One Rust API for TypeScript: generates adapters for Node-API, Koffi, Bun FFI, Deno FFI, and Wasm from `#[eqts::export]` Rust functions. An FFI **binding generator** — it has no test/eval/queueing flow at all. | `tschk/eqts` | ISC | none found |
| **rx4** | crates.io name of `tschk/rotary`: a pure-Rust **agent harness engine** (agent loop, builtin tools, providers, permissions, sessions, scopes). This is the piece that can "run tests". | `tschk/rotary` | MPL-2.0 | none found |
| **zkr** | Evidence-backed **temporal memory engine** for personal agents (separate crate/CLI; already the session memory engine in our Amp orbs). | `tschk/zkr` | ISC | none found |
| **praefectus** | Provider-neutral, verified **computer-use execution** (Ed25519 authority grants, outcome ledgers, AT-SPI2/UIA/AX backends). rx4's opt-in `computer-use` feature depends on the `praefectus` crate. | `tschk/praefectus` | ISC | none found |

So rx4/zkr/praefectus are not parts of eqts — they are sibling projects, and none
of the four is a test runner. The honest experiment is rx4 driving a real
verification slice of this repo, which is what this directory does.

A telemetry grep (`posthog|segment|sentry|amplitude|analytics|telemetry`) across
all four source trees returned no matches, and nothing here adds a runtime
dependency to any product package: this is opt-in local dev tooling with its own
Cargo project. There is deliberately **no CI job** — the agent needs a model
provider key, and provider keys must not become repository secrets.

## What ran, and the result

- **Slice:** `bun run --cwd packages/contracts/ratified verify` (the ratified
  contracts suite: 33 conformance tests over pagination/window cursors, recall
  completeness/trace envelopes, tasks-read projections, and write-op
  refusal/outcome semantics, plus clean-consumer typecheck and marker,
  provenance, and package integrity checks).
- **Driver:** rx4 0.7.2 as a library host (`src/main.rs`) with the builtin tool
  loadout, workspace sandbox, workspace_write policy, and GLM 5.3 Flash via the
  Z.ai coding-plan endpoint through `sse-shim.ts`.
- **Result:** PASS — exit code 0, 33/33 tests plus all sub-checks, matching the
  standalone baseline run of the same slice. `git status` confirmed the agent
  modified nothing. One behavioral note: rx4's `bash` builtin was blocked by the
  sandbox profile while its `exec` tool worked, so the agent rerouted on its own
  after two failed attempts.
- **praefectus 0.8.0** built and its JSON CLI works here (`capabilities` returns
  `ok:true`, backend `praefectus-linux`, `session_isolation: "shared_desktop"`;
  `surfaces` errors without an AT-SPI2 session, as expected in a headless orb).
  Computer-use execution is out of scope for this smoke and needs a real
  accessibility session plus a host-signed authority grant.
- **zkr** needed no experiment: it is already running as the session memory
  engine in this environment (wake/search/remember were exercised around this
  very evaluation).

## eqts verdict: not integrated

eqts is real, public, and permissively licensed, but it is the wrong tool for
this request, and its current release does not even build here:

1. It generates Rust→TypeScript bindings. This repo has no Rust library consumed
   from TypeScript (native-core is C++/CMake; the Omi BLE simulator is a
   standalone Crepuscularity GPUI app). There is no boundary for it to bind.
2. Hands-on attempt failed at the toolchain level: `cargo eqts build --target
   bun` with eqts 0.2.1 on rustc 1.98.1 fails compiling `napi-derive 3.6.3`
   (nine E0308 errors — two different `convert_case` versions unify in the
   dependency graph). That is upstream's to fix; not worked around here.

If Omi v5 ever exposes Rust logic to the TypeScript side, eqts is worth
revisiting then. Until that exists, forcing it in would be noise.

## Reproduce

```bash
# one-time: Rust (MSRV 1.88) + the rx4 crate are pulled by cargo automatically
cd tools/rx4-smoke
export RX4_SMOKE_API_KEY=...            # key for your OpenAI-compatible endpoint
export RX4_SMOKE_UPSTREAM=https://api.z.ai/api/coding/paas/v4/chat/completions
./run.sh                                # runs the slice, prints the agent report
```

`run.sh` starts the SSE shim only when `RX4_SMOKE_UPSTREAM` is set (point it
directly at a streaming endpoint by exporting `RX4_SMOKE_BASE_URL` instead and
running `target/release/rx4-smoke "<prompt>"` yourself). It ends with a
`git status --short` guard that fails loudly if the agent left changes behind.
