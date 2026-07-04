# Agent Router — setup & demo guide (Track 1)

Routes a spoken/typed task to the best available agent instead of always using
Claude Code, with automatic fallback and a "not connected → guide setup" path.

- **Router** (`src/runtime/agent-router.ts`): explicit mention › capability match › default (Claude Code).
- **Fallback** (`src/runtime/agent-fallback.ts`): advances through the plan on retryable failures, logging why.
- **Codex adapter** (`src/adapters/codex.ts`): registered production ACP adapter, gated on `OMI_CODEX_ADAPTER_COMMAND`.
- Connection detection reuses the existing **credential-safe** probes (env var / PATH executable) — it never reads any agent's auth files.

## 1. Clean checkout → working demo

```bash
git clone https://github.com/ats4321/omi.git && cd omi
git checkout feat/agent-router
cd desktop/macos/agent
npm install
npm run build
```

### Reproducible demo (no real agents, no desktop build)

```bash
npm test -- agent-router agent-fallback   # 12 unit tests: the 4 cases + edges
node scripts/router-demo.mjs              # prints each case's routing decision + fallback trail
```

`router-demo.mjs` output maps 1:1 to the four judged cases (a explicit+connected,
b explicit+not-connected→setup, c no-mention+capability pick, d primary fails→fallback).

## 2. Live push-to-talk demo (desktop app)

Connect the agents by pointing the activation env vars at an ACP command (a real
install, or a mock). If a var is unset, the Swift detector also searches
`~/.hermes/…`, `~/.local/bin`, `/opt/homebrew/bin`, `/usr/local/bin` for a matching
executable — presence only, never the agent's credentials.

```bash
export OMI_OPENCLAW_ADAPTER_COMMAND="openclaw acp"     # or a mock ACP command
export OMI_HERMES_ADAPTER_COMMAND="hermes acp"
export OMI_CODEX_ADAPTER_COMMAND="codex acp"           # mock is fine for the demo
```

To demo "not connected" for one agent, leave its var unset and make sure its
binary is absent from every detector search path (not just PATH — also
`~/.hermes/…`, `~/.local/bin`, `/opt/homebrew/bin`, and `/usr/local/bin`).

Launch a named test bundle (never the prod app):

```bash
cd .. && OMI_APP_NAME="omi-agent-router" OMI_SKIP_TUNNEL=1 ./run.sh
```

### Spoken script (run in order)

| # | Say (push-to-talk) | Expected |
|---|--------------------|----------|
| a | "Use **OpenClaw** to rename this function." | Routes to OpenClaw; it completes the task. |
| b | "Use **Codex** to add a test." *(Codex var unset)* | "Codex isn't connected" + install/connect guidance — no silent Claude Code fallback. |
| c | "**Research** the fastest way to do X." *(no agent named)* | Picks the best connected agent for research (Hermes), Claude Code as fallback. |
| d | "Have **OpenClaw** edit this file." *(kill/mock OpenClaw to fail)* | OpenClaw fails → logs the reason → automatically retries the next agent. |

## 3. Known limitations / rough edges

- **"Default is Claude Code" is the configured fallback**, but most Swift entry
  points construct the bridge with `harnessMode: "piMono"` (Omi's own hosted
  agent). The router's default is `acp` (Claude Code); wire the Swift call sites
  to the router to make that the live default everywhere.
- **Codex is a mock for the demo** — the adapter is real and registered, but it
  needs an ACP-speaking command behind `OMI_CODEX_ADAPTER_COMMAND`. There is no
  real Codex ACP endpoint wired here.
- **Swift-side wiring is partial.** The Node runtime routes, falls back, and runs
  codex today. Still to do on the Swift side: add `codex` to `AgentHarnessMode` /
  `DirectedProvider`, parse the spoken agent name into a routing directive, and
  turn the existing `setupPrompt` text into a guided install flow.
- **Fallback covers both activation and run failures.** `facade.handleQuery`
  accepts `{ suppressFailureEmit: true }` and returns an outcome, so a terminal
  *run* failure (not just a spawn failure) advances to the next agent when the
  failure is retryable, and surfaces immediately when it isn't — without a
  non-final error event leaking to the client, and without touching `kernel.ts`.
  Run `node scripts/dispatch-harness.mjs` to see cases (e)/(f).
- **Capability table is intentionally simple** (task-type → ranked agents). It's
  built to extend with success-rate / cost / latency signals without touching
  call sites.
