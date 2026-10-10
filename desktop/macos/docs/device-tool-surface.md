# On-device tool surface

The device tool surface is how the agent reaches the user's own machine —
Contacts, Messages, AppleScript actuation and reading other apps' windows —
through kernel-owned policy rather than improvised shell.

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
| `run_applescript` | `desktop.automation.act` | dispatch | Automation (per target app) |
| `ui_snapshot` | `desktop.automation.observe` | dispatch, per app | Accessibility |

All are declared in `agent/src/runtime/omi-tool-manifest.ts` and executed by
`Desktop/Sources/Providers/ChatToolExecutor+DeviceTools.swift`, except
`ui_snapshot`, which runs in `ChatToolExecutor+UISnapshot.swift`. The generated
Swift surfaces come from `agent/scripts/generate-tool-surfaces.mjs`; never
hand-edit them.

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
the policy re-requires dispatch when the handle differs. Tools without a
natural target get a stable ref so a session grant can still name them:
`list_message_chats` is `messages:chats` and `list_mail_messages` is
`mail:inbox`. `capture_screen` gets `screen` so its card names a target, but
no grant ever covers it (below).

The resource is derived only from the fields the tool acts on (`to`, `script`,
`chat_id` or `handle`, `bundle_id`). The model cannot name it: the gated tools are held
to their manifest schema at the kernel boundary, so an unknown key such as
`resource_ref`, a missing required field, or a wrong type is refused as
`invalid_tool_input` before anything is prepared.

### How a dispatch is asked and answered

A `dispatch` decision does not fail the tool call. The kernel writes the
invocation to the ledger as `prepared`, inserts one `approval` dispatch bound
to that exact invocation (its id and input hash live in the dispatch payload),
moves the run to `waiting_approval`, and appends `approval.requested`, all in
one transaction. The runtime sends Swift an `approval_requested` frame with the
recipient, the exact text or script, the options, and the expiry. The card
shows the whole input or nothing: text or a script longer than the 4 KiB card
bound is refused as `input_too_large_to_approve` so the model can shorten it.

The user answers through signed direct control with `resolve_desktop_dispatch`:

| Answer | Call | Effect |
|---|---|---|
| Allow once | `status: resolved`, `resolution: { decision: "allow" }` | this invocation runs once; no grant |
| Allow for this chat | the same plus a `grant` with `runId: null`, the dispatch's capability/operation/resource, and an `expiresAtMs` at most 24 h out | mints a session-scoped grant, then runs |
| Deny | `resolution: { decision: "deny" }` or `status: cancelled` | the model gets `approval_denied`; the run continues |

"Allow for this chat" is offered only when there is an exact resource for the
grant to cover, and each option says what that is (`covers`): messages to this
recipient, this conversation, your recent Messages conversations, your Mail
inbox headers. For `run_applescript` the grant covers only the identical
script, byte for byte; a different script asks again. A thread read with
neither `chat_id` nor `handle`, and every live screenshot, offers allow once
and deny only, and the kernel refuses to mint a grant for a card that did not
offer one.

Expiry (180 s, matching the mobile device-tool transport), run cancellation,
owner change and a disconnected relay client also end as `approval_denied`,
and every card ends with exactly one `approval.resolved` event and one
`approval_resolved` frame, whatever ended it. A daemon restart fails the
prepared invocation and expires its dispatch; nothing is replayed. A later call
with the same recipient and text is a new invocation and asks again unless a
grant covers it. The model-side wait for every gated tool is the `long` class
(10 min) so the model does not give up before the user answers; a test
pins it for every tool in the approval set.

The model cannot answer for the user: `resolve_desktop_dispatch` from an
adapter relay returns `policy_denied` and leaves the dispatch pending. A
dispatch the model creates itself through `create_desktop_dispatch` has its
`invocation` payload key stripped, so it can never pose as a parked tool call.

Interim gate: parking is on only after a connected client declares the
`desktop_tool_approval_cards` capability through the `client_capabilities`
message. The Mac shell sends that message right after a successful handshake
(`AgentRuntimeProcess.clientCapabilitiesWireMessage`), so parking is on
whenever the app is connected. A daemon with no card-bearing client keeps the
immediate `approval_required` rather than holding a call nobody can answer.
Removing the gate so parking is unconditional is a follow-up once the card has
shipped in a beta.

### The card on the Mac

`DesktopToolApprovalStore` (`Desktop/Sources/Chat/DesktopToolApprovalStore.swift`)
turns each `approval_requested` frame into a card and closes it on
`approval_resolved`, whoever ended it. `DesktopToolApprovalCardList` renders
the cards of one thread, matched by the surface's session id, so a card never
shows under another conversation: main chat (`QueryAnswerThread`), a
workstream (`TaskChatPanel`), and the agent pill (`AIResponseView`). Each
`DesktopToolApprovalCard` shows the tool's title and question, the exact
target (`resourceRef`), the content preview, the expiry time, and the answers:
Allow Once, Allow for This Chat (1 h) only when the request offers
`allow_session` (with its `covers` text), and Deny. A tool whose resource is
only a stable key (`messages:chats`, `mail:inbox`, `screen`) shows no target
row, so the screenshot card is just "Take a screenshot", "Let Omi take a
screenshot of your whole screen?", Allow Once and Deny. An answer goes through
signed direct control (`DesktopCoordinatorService.resolveDispatchJSON`, which
calls `resolve_desktop_dispatch`): allow once sends no grant; allow for this
chat sends a grant with `runId: null`, the dispatch's capability, operation and
`resourceRef`, and a 1 h expiry. A refused or undelivered answer returns the
card to pending with the reason, and the kernel's `approval_resolved` always
wins over a local answer in flight. The card never runs anything itself; the
only path to the tool is the kernel's resolution.

A card waiting on the person is not a stall. The chat turn's `StallDetector`
pauses while a card for the session the turn resolved is pending
(`setWaitingOnUser`), whichever surface sent the turn: the tool
row reads "Waiting for your approval", the "taking longer than usual" banner
stays down, and the 90 s no-progress abort that interrupts the bridge cannot
fire; when the card closes, the clocks restart from that moment. The composer's
stop button still cancels the run, and the card then reads "Cancelled, not
run". On the daemon side the hermes and openclaw adapters' 150 s no-progress
cancel treats a run in `waiting_approval` as progress for the same reason.

Cards belong to one daemon process and one owner: the store is cleared on every
runtime handshake, when the daemon exits, and when the owner is revoked. A card
whose deadline passes without a frame closes locally as expired, and an answer
the kernel refuses because the dispatch is no longer pending closes the card
the way the kernel did instead of offering buttons that can only fail. The
shell declares `desktop_tool_approval_cards` only to a runtime whose `init`
advertises `desktop_tool_approval_requests`; an older daemon still runs the
chat and keeps its immediate `approval_required`.

### Live screenshots ask too

`capture_screen` is not in the table above, but it takes the same gate: its
bundle, `desktop.context.screenshot_image`, is sensitive, so a live capture
parks behind the same card ("Take a screenshot") under the stable resource
`screen`, and nothing is captured or saved until the user allows it. It is
allow once only: the capture is the whole display, including windows the
person keeps out of capture elsewhere, so the card offers no "Allow for this
chat", no grant row covers a capture (even one naming `screen`), and
`desktop.context.screenshot_image` grants must name an exact resource.

`get_screenshot` and its `look_at_frame` alias share the bundle but are served
only by the local agent API, and the realtime voice `screenshot` tool is
offered only to realtime voice runs through their surface projection; none of
them is advertised to the chat, pill or workstream relays. `show_rewind_evidence`
is classed with the screen-history reads: the model gets back only the stored
frame's title, app and OCR excerpt, and the pixels go to the person's own Chat
turn. Tests in `run-tool-capability.test.ts` require every relay-callable tool
to be classified on purpose and hold the approval set to every relay-callable
tool in a sensitive bundle, naming each deliberate exception.

### Reading app windows

`ui_snapshot` reads one window of another app as named elements through
Accessibility: role, label, value, the closed action vocabulary (`press`,
`menu`, `adjust`, `confirm`, `pick`, `set`) and a reference per element
(`a:<AXIdentifier>`, else `n:<role>:"<label>"`, else a `p:` child path) with a
fingerprint of role, label and window-relative frame. It never clicks, types,
raises a window or moves the cursor; the source it reads through has no such
method.

- **Per-app approval.** `desktop.automation.observe` is sensitive like
  `desktop.messaging.read`, because a window shows the app's content. The grant
  resource is the trimmed, lowercased `bundle_id`, so Allow for This Chat covers
  every window of that one app for an hour and another app asks again. Observe
  grants must name an app, and the bundle is separate from
  `desktop.automation.act`: approving a read never approves acting. `bundle_id`
  is required because the kernel cannot scope a call by pid; `pid` only picks
  between running copies and must belong to the bundle.
- **Refusal floor.** One list, `agent/src/runtime/ui-automation-safety-floor.ts`,
  generated into `GeneratedUIAutomationSafetyFloor.swift`. The kernel refuses a
  malformed bundle id, every `com.omi.*` build, sign-in, SSO, authorization and
  iCloud Keychain prompts, `UserNotificationCenter` alerts and notification
  banners (they carry one-time codes), Keychain Access, Passwords and its menu
  bar extra, the AutoFill panel and the AutoFill and passkey sign-in view
  services, terminals, password managers, and every
  sensitive System Settings pane's own extension, as a hard deny with no card
  and no dispatch row. Swift checks again against the real process: Omi's own
  pid, the same list, anything that is not an application bundle (`.app`):
  app extensions, XPC view services and bare executables, an app that reports no name
  (capture exclusion is keyed by name, so it cannot be checked), apps excluded
  from capture (a card can appear before this refusal), and a frontmost app
  while secure input is on. Right before and after the read it re-checks that
  the pid still belongs to the approved bundle.
- **What the floor does not cover.** It refuses apps, not screens. Credential
  UI hosted inside an app the person approved (a sign-in sheet, a browser's
  saved-password page once revealed) is read like any other content, apart
  from secure fields.
- **System Settings** is not refused as a whole, and it is checked by an
  allow-list. On every read, and for every open Settings window, Swift reads
  the selected row of the sidebar and the window title. A sensitive name in
  either refuses: Privacy & Security, Passwords and
  AutoFill & Passwords, Users & Groups, Touch ID & Password, Lock Screen,
  Wallet & Apple Pay, Apple Account (iCloud, Family), Internet Accounts, Game
  Center, Screen Time, General > Sharing, Login Items & Extensions, and Network
  (Wi‑Fi, VPN). A window titled with a page of Privacy & Security (Full Disk
  Access, Location Services, FileVault, Accessibility, Screen & System Audio
  Recording, Input Monitoring, Files & Folders, Automation and the rest, in
  every installed language) is refused unless the sidebar selects that same
  name, as the top-level Accessibility pane does. Otherwise the sidebar selection must name an ordinary
  top-level pane, and with General selected the title must name an ordinary
  General subpage. Names come from every language the installed System Settings
  extensions ship: their display names, and General's subpage strings from its
  `Localizable` table. No selection, an unknown row, a search result, an active
  sidebar search, a sheet over the window, a list in the window with no
  position (the sidebar cannot be told from a content table), or a window it cannot identify is
  refused as `refused_settings_pane_unknown`.
- **Text.** A secure text field's value and length are never requested and its
  children are never walked. Any app text over 300 characters (a value, a
  label, a window title, the app's name) is left out and only its length is
  sent (`value_chars`, `label_chars`, `window_title_chars`); nothing is
  shortened and sent. Every URL-like token in app text, with any scheme
  (`https:`, `file:`, `mailto:`, `tel:`, an app's own) or none, loses its query
  string and fragment, and long opaque path segments
  (16 or more characters mixing letters and digits, or 32 or more) become `…`. App text
  is sanitized and quoted so it cannot break its line or pose as a field.
- **Sparse.** The header says `sparse=true` with a reason when there are
  fewer than five elements, none the model can act on, or a walk cut off by
  depth that found almost nothing beyond the window's own buttons; with the
  Electron or Chromium switch on, a sparse first pass is read once more.
- **Result.** The first line is Omi's own header (completeness, stop reason,
  counts, order), with the app's name and window title last and quoted; then
  one line per element. The window's main content comes first
  (`order=content_first`): the region holding most of the window's text (by
  text values, not control labels), or an `AXLandmarkMain` region, is moved
  before sidebars, toolbars and chrome, so a chat's conversation is in view
  before its channel list; references and paths are unchanged. When the kernel
  has to cut the result to the model budget, the projection opens with what was
  left out and points at `search_tool_output` (the contract's
  `omissionNoticeFirst`). The result carries facts only: how to read it and that its text
  is data, never instructions, is in the tool's manifest description and
  guidelines.
- **Bounds.** 400 elements, depth 12 counting only informative elements
  (anonymous wrapper groups, which Electron and Chromium nest dozens deep
  around web content, cost no depth and are not emitted) with an absolute
  raw depth of 64, 2,000 elements visited, at most 200
  children per container (its first and last 100, the rest counted as omitted
  and the walk carrying on), 3 s for the whole read including the window list
  and the pane check, a 0.25 s messaging timeout per element, and the first
  timeout from a hung app stops the walk with what it already read. The walk
  runs off the main actor and stops when the calling task is cancelled. The
  result fits the 8 KB model budget; the rest is reachable with
  `search_tool_output`.
- **Electron and Chromium.** These apps expose their elements only to an
  assistive client. After the person has approved the app, and only then,
  `ui_snapshot` sets `AXManualAccessibility` on an Electron app or
  `AXEnhancedUserInterface` on a Chromium app. That switch is the only write
  `ui_snapshot` makes, and it does not outlast the read: on every exit
  (success, failure, timeout, cancellation) the switch is turned back off,
  only if Omi turned it on and it is still on, so another assistive client's
  switch is kept and a read leaves no lasting change in the other app. A
  sparse first pass after turning it on is read once more. The app is
  recognised from its own bundle layout, not from a list of apps.

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
