---
name: ai-chat-debug
description: "Debug the VM agent pipeline — Phone → Agent-Proxy → VM (mobile) and Desktop Claude Agent Bridge. Use when AI chat messages don't come through, AI stops unexpectedly, second query times out, EPIPE errors, session confusion, tool calls failing, or agent bridge crashes. Triggers: 'AI chat not working', 'message not coming through', 'AI stopped', 'agent bridge', 'EPIPE', 'nodeNotFound', 'agent chat timeout', 'second query', 'query not responding', 'VM agent', 'agent proxy'."
---

# VM Agent Pipeline Debug

## Part 1: Mobile (Phone → Agent-Proxy → VM)

### Architecture

```
Phone (agent_chat_service.dart)
    ↓ (WebSocket via wss://agent.omi.me/v1/agent/ws)
Agent-Proxy (backend/agent-proxy/main.py) — GKE pods
    ↓ (WebSocket ws://<vm-ip>:8080/ws)
Agent VM (desktop/agent-cloud/agent.mjs) — per-user GCE VM
    ↓ (Claude Agent SDK, streaming input mode)
Claude API
```

### Key Files

- `app/lib/services/agent_chat_service.dart` — Phone WS connection, event stream, 120s response timer
- `app/lib/providers/message_provider.dart` — Query loop, auto-reconnect + retry logic
- `backend/agent-proxy/main.py` — WebSocket proxy, history injection, message persistence
- `desktop/agent-cloud/agent.mjs` — Persistent Claude session via AsyncMessageQueue

### Test Accounts

See `scripts/test-accounts.md` for emails, UIDs, and VM names. To find any user's VM: look up `agentVm.vmName` in Firestore `users/<uid>`.

### Testing Pipeline A: Simulator (local dev, immediate)

**Run the app:** Use `/local-dev mobile` or manually:
```bash
xcrun simctl list devices | grep Booted  # get device ID
cd app && flutter run -d <device-id> --flavor dev
```
See the `local-dev` skill for full simulator setup, env files, and troubleshooting.

**Check logs (ALWAYS do this first after a query):**
```bash
# Use `strings` because flutter-run.log may contain binary data that breaks grep:
strings /tmp/flutter-run.log | grep "\[TIMING\]" | tail -30
```
This shows the full end-to-end timing — connection, query, tool calls, result — even when proxy/VM logs are empty.

**Then check server-side** (proxy + VM) in parallel if needed — see "Server-Side Logs" below.

**After checking phone/app logs, ALWAYS also check VM logs for intermediate tool calls.**
Phone logs only show "tool started/completed". VM logs show every individual tool call
with timestamps — including extra rounds (Bash, Read, Grep) that Claude does to parse
large results. These are invisible in phone logs but dominate latency.

### Testing Pipeline B: TestFlight (physical device via USB)

**Deploy:** Merge to `main` → Codemagic auto-builds iOS TestFlight (triggered when `app/**` changes). Build takes ~15 min, then TestFlight review (~1 min usually).

**Check logs:** Phone is connected via USB. Logs are file-based (print/developer.log are stripped in release builds):
```bash
python3 -m pymobiledevice3 apps pull com.friend-app-with-wearable.ios12 Documents/agent_chat.log /tmp/agent_chat_phone.log
cat /tmp/agent_chat_phone.log
```

**Then check server-side** (proxy + VM) in parallel if needed — see "Server-Side Logs" below.

**After checking phone/app logs, ALWAYS also check VM logs for intermediate tool calls.**
Phone logs only show "tool started/completed". VM logs show every individual tool call
with timestamps — including extra rounds (Bash, Read, Grep) that Claude does to parse
large results. These are invisible in phone logs but dominate latency.

### Server-Side Logs

**Agent-proxy** (GKE, filter by user UID):
```bash
kubectl logs -n prod-omi-backend -l app=agent-proxy --timestamps --since=10m | grep "<uid>"
```
Key patterns: `first query with N history messages`, `follow-up query (session has context)`, `saved AI response (N chars)`, `disconnected`

**VM agent** (per-user GCE instance — use VM name from test accounts table or Firestore):
```bash
# For primary test account (see scripts/test-accounts.md for VM name):
gcloud compute ssh <vm-name> --zone=us-central1-a --project=based-hardware \
  --command="journalctl -u omi-agent --no-pager --since '10 minutes ago' | grep -v Sync"

# For any user — filter useful logs:
gcloud compute ssh omi-agent-<id> --zone=us-central1-a --project=based-hardware \
  --command="journalctl -u omi-agent --no-pager --since '10 minutes ago' | grep -E 'Client|Query|Prewarm|session|disconnect|error|Persistent|TOOL_CALL|model|version'"
```
Key patterns: `Client connected/disconnected`, `Prewarm: session ready`, `Starting persistent session with model:`, `Query:`, `[TOOL_CALL] <name> input={...}`, `Running version:`

### Deploying VM Code (agent.mjs)

- **Auto (all VMs):** Merge `desktop/agent-cloud/` changes to `main` → Codemagic uploads to GCS → running VMs poll every 10 min and hot-reload.
- **Manual (single VM for testing):** `gcloud compute scp agent.mjs omi-agent-<id>:~/omi-agent/agent.mjs` then kill the node process (systemd restarts it). Note: if the VM reboots, the startup script pulls from GCS and overwrites the manual push.

### Log Patterns (both pipelines)

- `=== QUERY START ===` — query sent
- `*** FIRST TEXT DELTA ***` — first response token arrived (perceived latency)
- `*** RESULT ***` — query completed (total time)
- `*** RESPONSE TIMEOUT ***` — no event in 120s, connection marked dead, triggers auto-retry if `gotContent == false`
- `[RETRY] No content + disconnected` — auto-reconnect + retry fired
- `Stream done` — WS closed normally

### Agent-Proxy Design Rules

- **`vm_to_phone()` must NEVER block on I/O.** Any `await` in the `async for msg in vm_ws` loop blocks ALL event forwarding from VM to phone. Use `asyncio.create_task()` for fire-and-forget saves, never `await asyncio.to_thread(...)`.
- **`phone_to_vm()` saves are also fire-and-forget** — user message saves use `asyncio.create_task()` to avoid blocking query forwarding.
- **History injection happens only on first query** per connection (`first_query_sent` flag). The persistent Claude session retains context natively for follow-up queries.
- **`asyncio.wait(FIRST_COMPLETED)`** — the proxy runs 3 tasks: `phone_to_vm`, `vm_to_phone`, `keepalive_pinger`. If ANY task completes or errors, ALL are cancelled and the connection tears down. This means a bug in any single task kills the entire connection.

### Common Issues

1. **Second query times out (zero events)**: Check if `vm_to_phone()` has any blocking `await` after `result` events. The save must be fire-and-forget.
2. **Phone auto-reconnects after every query**: The `onDone` handler sets `_connected = false`. Check if the VM or agent-proxy is closing the WS after each result.
3. **First text delta takes 30+ seconds**: Prewarm may not be completing before the query arrives. Check VM logs for `Prewarm turn completed` timing vs `Query:` timing.
4. **Duplicate text in response**: Both `stream_event` and `assistant` message handlers in the `for await` loop can send the same text. The `assistant` handler has a `!fullText.includes(block.text)` guard but it's imperfect.
5. **404 on chat session save**: Firestore `ArrayUnion` with `set(merge=True)` can fail if the session document was deleted. The error is caught and logged as warning.
6. **Connection dies after ~90-140s idle**: GCP LB or network layer drops the WebSocket silently. App's `onDone` never fires, `_connected` stays true. Next query sends into a dead sink, gets zero events, and the 120s timeout detects it. The proxy logs `connection closed` from the phone side before `disconnected`.
7. **Timeout fires but response arrives later**: The 120s timeout closes `_eventController` and sets `_connected = false`. If the VM was still working (slow tool call), data arriving after timeout is silently dropped. Auto-retry only fires if `gotContent == false` (no text deltas were received before timeout). If partial content was received, the timeout error shows but no retry.
8. **`init` event takes 3-5 seconds**: This is the Claude SDK session resume — an API round-trip from the GCE VM to Anthropic. Irreducible latency.

### Deployment (Agent-Proxy)

```bash
# Auto-deploys on push to main, or manual:
gh workflow run gcp_backend_agent_proxy.yml -f environment=prod -f branch=<branch>
```

---

## Part 2: Desktop Agent Chat (Claude Agent Bridge)

### Architecture

```
Swift ChatProvider (Desktop/Sources/Chat/ChatProvider.swift)
    ↓ (stdin/stdout JSON-RPC)
Node.js Bridge (agent-bridge/src/index.ts)
    ↓ (Claude Agent SDK)
Claude API
```

### Key Files

- `Desktop/Sources/Chat/ChatProvider.swift` — Swift side, manages the Node.js process
- `Desktop/Sources/Chat/ClaudeAgentBridge.swift` — Bridge protocol and message types
- `agent-bridge/src/index.ts` — Node.js entry point, handles JSON-RPC messages
- `agent-bridge/src/omi-tools.ts` — Tool definitions for the Claude agent

### Common Issues and Fixes

1. **EPIPE crash**: Node.js process died but Swift kept writing to stdin. Fix: check process liveness before writing, handle SIGPIPE.
2. **nodeNotFound**: Node.js binary not found at expected path. Check bundle path resolution.
3. **Session confusion**: Messages go to wrong chat (task chat vs sidebar vs floating bar). Each should have separate session IDs.
4. **Messages not appearing**: Check if the JSON-RPC response parsing is correct. Look for malformed JSON in stdout.
5. **AI stopped unexpectedly**: The Node.js process crashed. Check stderr output captured in logs.
6. **Tool call rendering**: Tool calls may not render properly in the UI. Check the message type handling in ChatProvider.

### Debugging Steps

1. Check `/private/tmp/omi.log` for `AGENT_BRIDGE:`, `CHAT:`, or `CLAUDE:` log prefixes.
2. Check if the Node.js process is running: `ps aux | grep agent-bridge`
3. Verify the agent-bridge was built: check `agent-bridge/dist/` exists.
4. Check for stderr output from the Node.js process.
5. Review recent changes to bridge files: `git log --oneline -10 -- agent-bridge/ Desktop/Sources/Chat/`

### Log Prefixes

- `AGENT_BRIDGE:` — Bridge lifecycle events
- `CHAT:` — Chat message flow
- `CLAUDE:` — Claude API interactions
- `TOOL:` — Tool call execution
