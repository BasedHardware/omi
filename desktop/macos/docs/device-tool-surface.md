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
| `list_mail_messages` | `desktop.mail.read` | dispatch | Full Disk Access |
| `send_message` | `desktop.messaging.send` | dispatch | Automation (Messages) |
| `propose_message` | `desktop.compose.propose` | allow (the Messages composer is the approval) | Messages set up |
| `propose_email` | `desktop.compose.propose` | allow (the compose window is the approval) | a default email app |
| `run_applescript` | `desktop.automation.act` | dispatch | Automation (per target app) |

All eight are declared in `agent/src/runtime/omi-tool-manifest.ts`. The two
`propose_*` tools are executed by
`Desktop/Sources/Providers/ChatToolExecutor+ComposeProposals.swift`, the others
by `Desktop/Sources/Providers/ChatToolExecutor+DeviceTools.swift`. The generated
Swift surfaces come from `agent/scripts/generate-tool-surfaces.mjs`; never
hand-edit them.

### Draft, you send: `propose_message` and `propose_email`

These open a compose window through `NSSharingService` (`.composeMessage`,
`.composeEmail`), filled in with the recipients, the subject (email only) and
the body, and stop there. The person reviews the draft and presses Send. Omi
has no AppleScript or automation path behind these tools, so it cannot send
one. Nothing is sent until the person presses Send, but an email app may
autosave an open draft to the account's Drafts mailbox on the mail server.

**Which app.** On current macOS (verified on 27), `.composeMessage` shows no
sheet. It places the draft in the Messages app's own composer and reports the
handoff at once, so Omi cannot see whether the person sends or discards it.
(If the system showed a sheet instead, Omi would get a Send or Cancel report.
That path is still handled, but this macOS does not use it.) `.composeEmail`
hands the draft to whatever app handles `mailto:` links. That may be Mail,
another mail app such as Outlook, or a browser, which opens its web mail site
(Outlook on the web, Gmail).
- The result names that app (`app`, plus `app_is_browser`). It is resolved
  through `NSWorkspace.urlForApplication(toOpen: mailto:)`, and nothing assumes
  Mail.
- When the handler is a browser, the result says the draft opened on its web
  mail site and that Omi cannot see whether it was sent.

**Routing.** `propose_message` is the default for any request to text or
message someone. `send_message` is only for when the person asks Omi to send
it for them. Neither is ever pre-filed through `create_desktop_dispatch`. The
guidance of all three tools says so.

**Shared with iOS `propose_message`:** the tool name, `to` plus `text`, and
the "does not send" contract. **Different on the Mac:**
- the Mac never reports `sent`. Both Messages and the email app take the draft
  and report a handoff before the person presses Send, so Omi cannot see the
  send. iOS gets `sent` or `cancelled` from its compose sheet;
- the Mac returns as soon as the draft is handed off, instead of holding the
  turn until the person acts;
- Mac `propose_message` takes no `subject`;
- the Mac adds `propose_email`.

- **No Omi approval card.** `desktop.compose.propose` is a platform-confirmed
  write bundle. Apple's window already shows the person the exact recipients
  and text, and nothing is sent until they press Send, so a card would ask
  twice for the same effect. The bundle is narrow:
  - any other write requested beside it keeps its own approval;
  - the tools are `coordinatorOnly`, so a background or pill worker cannot put
    a window in front of the person;
  - an ask-mode service run cannot call them at all.
- **Recipients must come from the person.** The compose window has no "Omi
  wants to…" framing, so `send_message`'s rule is enforced in code, not only in
  the prompt. Every recipient must come from one of:
  - words the person typed, pasted or dictated in this turn. Voice runs carry
    the provider transcript as the run text, so this needs no separate path;
  - the person's one previous turn in the same main chat, so that "yes, that
    one" can confirm an address;
  - a `search_contacts` result in the same run, for the same owner;
  - the signed-in account's own address.

  Anything else returns `recipient_needs_confirmation` and opens nothing. That
  covers an address the model read in a page, an email or on screen.

  Limits of this check:
  - **Question-card answers do not count.** On a question card the person
    clicks a label, but the turn's text is the model-written `preparedAnswer`.
    Those turns are recognised by their `qri_` turn key and left out, as the
    current turn and as the previous one.
  - **Pasted text counts as the person's.** If they paste a thread and ask for
    a reply, its addresses are grounded. That is the point of pasting, but it
    also means a pasted page can carry an address in.
  - **Spoken addresses don't match.** "sam at example dot com" is not an
    address, so voice users reach people through Contacts.
  - **Phone numbers match as whole numbers.** The digits must be the same, or
    one side may add a one-to-three-digit country code to a national number of
    ten or more digits. Dates, numbers inside an address or word, and numbers
    after "order", "invoice", "ticket", "#" and similar words never ground a
    phone number.

  Validation:
  - a bare name returns `recipient_needs_lookup` with `next_tool:
    search_contacts`;
  - addresses use a narrow ASCII form: no `?`, `&`, `%`, `/`, `#` or lookalike
    Unicode domains.
- **No handoff while the person is typing.** The Messages composer takes
  keyboard focus, and **Return sends from it**. A keystroke that lands in the
  draft can send it before the person has reviewed it, so this guard is
  load-bearing, not cosmetic.
  - The coordinator hands a draft off only after 3 s with no key press. The
    idle time is the system-wide keyDown idle, through `UserInputPresence`.
  - The last idle check runs with no suspension before the handoff.
  - It waits at most 8 s for quiet. Otherwise the result is `not_opened` /
    `person_typing`.
  - Residual risk: someone who starts typing again after the handoff can still
    type into the composer.
- **Limits.** Every limit is per signed-in owner, and a sign-out releases them.
  - A request (run) opens at most one email draft and one message draft, so
    "email Sam and text him" works.
  - At most three drafts open in a minute, or one a minute when there is no run
    ID.
  - The same draft is not handed off again within two minutes: same channel,
    the same recipients in any order or spelling, and the same text. The
    result is `not_opened` / `draft_already_open`, which tells the model the
    draft is waiting and the person presses Send there. The coordinator keeps
    only a SHA-256 digest of the draft. A cancel or failure report clears it,
    so the person can ask for the same draft again.
  - Only if the system shows a Messages sheet: while it is still open, no
    other draft opens (`compose_already_open`), and a sheet that never reports
    stops blocking after five minutes.
- **"Send it" after a draft.** The guidance for `propose_message`,
  `propose_email` and `send_message` says the person sends an open draft
  themselves. If they say "send" or "send it", the model tells them to press
  Send in Messages or their email app. It never opens the same draft again and
  never calls `send_message` or `create_desktop_dispatch` for it.
  The guidance alone did not hold in a live test, so `send_message` also
  checks in code, before any send. If the same owner handed a
  `propose_message` draft to Messages in the last ten minutes, and the send's
  recipient matches any recipient of that draft, `send_message` returns
  `not_sent` / `draft_in_messages` and sends nothing. The recipient match uses
  the same normalisation as the grounding check. The text does not matter. A
  cancelled draft does not count. This check runs in Swift, so with an
  approval card in front of `send_message` (the separate approval stack), the
  card would still appear first.
- **Results never say sent.** Every result carries `sent_by_omi: false` and a
  `status`:
  - `handed_to_email_app`: the email app named in `app` took the draft, which macOS reports before the
    person presses Send.
  - `handed_to_messages`: the draft is in Messages for the person to review
    and send. Whether they send or discard it cannot be observed.
  - `cancelled`: the person closed the window. Only a system sheet or an email
    app that reports a cancel produces this.
  - `open`: the window was still up when the wait ended, or the turn was
    stopped after the window opened. Only a sheet produces the first case.
  - `not_opened`: nothing opened. The reason is one of `stopped`,
    `person_typing`, `draft_already_open`, `compose_already_open`,
    `draft_limit_reached`, `compose_unavailable`, or a validation reason.
- **Not supported yet:** CC/BCC and attachments. `NSSharingService` has no CC
  field, and a `mailto:` fallback would lose the outcome report.

### Why reads need approval too

`desktop.messaging.read` is classified sensitive alongside
`desktop.messaging.send`. Reading a thread exposes the other party's messages,
not just the user's, so it takes the same durable approval record a send does. A
scoped grant covers repeat reads within its TTL.

`desktop.mail.read` is sensitive for the same reason and is a *separate* bundle:
agreeing to let the agent read a text thread is not agreeing to let it read the
inbox, so a messaging grant never authorizes a mail read.

### Mail is headers only

`list_mail_messages` reads `~/Library/Mail/V*/MailData/Envelope Index` — subject,
sender, date, and read/flagged/replied state. Message bodies sit beside that
index as `.emlx` files, and this reader never opens them. Answering "what's
waiting for me" does not require the full text of the user's mail, and the tool
description tells the model to say a body is unavailable rather than infer one.

The reader probes the schema with `PRAGMA table_info` before querying, because
Mail's schema is Apple's private business and has changed across releases; an OS
update degrades to a legible `schema_unavailable` instead of a raw SQLite error
mid-query. It picks the highest-numbered `V{n}` directory, since Mail leaves old
format versions in place and a hardcoded version would silently read stale mail
after an upgrade. `OMI_MAIL_ENVELOPE_DB` points it at a fixture for tests.

Note the epoch: Mail's `date_received` is plain Unix seconds, unlike the Core
Data reference dates in Notes and the Apple absolute times in Messages. Reusing a
sibling reader's conversion shifts every message by 31 years.

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
| `request_permission` | system permission prompt | the prompt itself |
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
