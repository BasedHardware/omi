# On-device tool surface

The device tool surface is how the agent reaches the user's own machine —
Contacts, Messages, and AppleScript actuation — through kernel-owned policy
rather than improvised shell.

Before this surface existed, `ProactiveTaskExecute.systemPromptSuffix` told the
agent it had "shell + osascript" access to drive Messages, Telegram, and Mail.
That was a prompt-level claim with nothing behind it: no manifest entry, no
capability bundle, no approval card, no ledger record — and in release bundles
`desktop.automation.act_dev_only` denied actuation outright.

## macOS tools

| Tool | Bundle | Decision | Needs |
|---|---|---|---|
| `search_contacts` | `desktop.contacts.read` | allow | Contacts |
| `list_message_chats` | `desktop.messaging.read` | dispatch | Full Disk Access |
| `read_message_history` | `desktop.messaging.read` | dispatch | Full Disk Access |
| `send_message` | `desktop.messaging.send` | dispatch | Automation (Messages) |
| `run_applescript` | `desktop.automation.act` | dispatch | Automation (per target app) |

All five are declared in `agent/src/runtime/omi-tool-manifest.ts` and executed by
`Desktop/Sources/Providers/ChatToolExecutor+DeviceTools.swift`. The generated
Swift surfaces come from `agent/scripts/generate-tool-surfaces.mjs`; never
hand-edit them.

### Why reads need approval too

`desktop.messaging.read` is classified sensitive alongside
`desktop.messaging.send`. Reading a thread exposes the other party's messages,
not just the user's, so it takes the same durable approval record a send does. A
scoped grant covers repeat reads within its TTL.

### `desktop.automation.act` vs `act_dev_only`

`act_dev_only` stays exactly as it was: denied outside dev/test bundles.
`desktop.automation.act` is its production sibling — reachable in a release
build, but it can never resolve to `allow` without a dispatch or an unexpired
scoped grant. Nothing about the old bundle's guarantees changed.

### Scoped grants are per-recipient

A `send_message` grant carries a `resourceRef` of the recipient handle.
Approving a message to one person does not authorize a message to anyone else;
the policy re-requires dispatch when the handle differs.

### AppleScript injection

Recipient handles, message bodies, and attachment paths are passed to
`osascript` as `argv`, never interpolated into script source. A message body can
come from a thread the agent just read, so treating it as script text would let
a crafted message execute AppleScript. `AppleScriptRunner.run` takes untrusted
values only through its `arguments` parameter.

### Testing against a fixture

`OMI_MESSAGES_DB` overrides `~/Library/Messages/chat.db`, so contract tests run
against a fixture database instead of a developer's real message history.

## iOS tools

iOS has no API for sending a message without the user seeing it, so the mobile
surface exposes a *propose* verb instead:

| Tool | Mechanism | Consent |
|---|---|---|
| `search_contacts` | `CNContactStore` | Contacts permission |
| `propose_message` | `MFMessageComposeViewController` | the compose sheet itself |

`DeviceToolsService.swift` presents the sheet prefilled with recipient and body;
the delegate reports `sent`, `cancelled`, or `failed`, and `ok` reflects what the
user actually did. A cancelled proposal never reads as a delivered message.

`limited` Contacts authorization (iOS 18) is treated as a usable grant, not a
denial — lookups still work against the shared subset.

Reading message history and running scripts have no iOS equivalent at all.
`capabilities()` reports `can_read_messages: false` and `can_run_scripts: false`
so the model does not propose them. Those capabilities exist only on the paired
Mac.

## The mobile tool-call transport

The backend model calls these tools mid-turn over the SSE stream that is
**already open** for the turn. No suspend/resume of the streaming generator was
needed — the turn simply stays live while the user answers.

```text
client  POST /v2/messages { text, device_tools: [...] }
                                   |
backend  model calls propose_message
         -> tool coroutine emits  `tool: <base64 json>`  on the open stream
         -> coroutine polls Redis for the result
                                   |
client  reads the frame, runs MFMessageComposeViewController,
        POSTs /v2/messages/device-tool/{call_id}/result
                                   |
backend  poll observes the result, tool returns it to the model,
         model finishes the turn and the reply streams as usual
```

Ownership:

- `backend/utils/device_tools.py` — specs, tool construction, the Redis handoff.
- `AsyncStreamingCallback.put_device_tool_request` — the only writer of `tool:` frames.
- `app/lib/services/device_tools/device_tool_dispatcher.dart` — parses the frame,
  executes it, returns the result.

### Why the client declares its tools per request

`SendMessageRequest.device_tools` names what this client can actually run. The
model is offered nothing else, so it cannot propose a message on an iPad with no
messaging service or on Android, where the surface has no implementation. The
capability set depends on the device in hand, so it is sent per request rather
than stored.

### Why Redis polling and not an in-process future

The result POST can land on a different worker than the one holding the awaiting
coroutine. A poll on a uid-scoped shared key does not care which worker wrote
it. The latency floor here is a human tapping a compose sheet, so the 250ms poll
interval is far below the noise.

The key is scoped by uid, so one user's POST cannot satisfy another user's call,
and the result is deleted once consumed so a later call cannot reuse it.

### Timeout

A device tool call is bounded at 180s — roughly how long a person plausibly
takes to answer a system sheet. On timeout the model receives
`{"ok": false, "reason": "timed_out"}` with an explicit instruction not to retry
automatically, because the user may still be looking at the sheet.
