# Integrations Philosophy

**Audience:** any agent (or human) working on Omi's desktop integrations — the
"Connect data" sources (Gmail, Calendar, Notes, Files, …) and the "Connect your
AI" connectors (Claude, ChatGPT, Codex, OpenClaw, Hermes, …).

**Status:** load-bearing. Read this before touching `CloudConnectorFormAutomation`,
`MemoryExportExecutor`, `MemoryExportService`, `MemoryBankConnector`, or any
`*ReaderService`. If you're about to add a connector, this is the contract.

---

## 0. The one thing to internalize

We integrate with surfaces **we do not own and cannot version**: other apps'
UIs, other apps' cookie encryption, other apps' config-file formats, and other
providers' web flows. None of these give us a contract, a deprecation window, or
an error we can catch. They change without warning, and when they change our
integration doesn't throw — it silently clicks the wrong button or reads a stale
cookie.

That is the permanent condition. You cannot fix it by writing better heuristics.
You can only survive it by building the right **harness** around the agent that
does the work. **The harness is the product. The automation is disposable.**

Every rule below follows from that sentence.

> **Current state for the two hardest surfaces** (ChatGPT & Claude cloud
> connectors): autonomous setup is parked and the assisted overlay flow is
> primary. The phased plan to revisit them lives in
> [cloud-connectors-roadmap.md](./cloud-connectors-roadmap.md).

---

## 1. Code owns contracts. The agent owns only what code can't reach.

If we own the format, a deterministic function writes it — never an agent.

`MemoryBankConnector` already proves the rule. The comment says it plainly:

> "OpenClaw / Hermes have no setup CLI; the agent doesn't reliably perform the
> file write. Do it deterministically ourselves (idempotent local write)."

MCP client configs (Claude Code, Codex, Cursor, …) are known JSON/TOML files. We
own that format. Write it in Swift, idempotently, every run. Reserve the agent
for surfaces with no file and no API — a provider's web "Add connector" dialog.

**Decision rule for a new connector:**

1. Is there a config file we can write? → Write it in code. Done.
2. Is there an API or CLI? → Call it in code. Done.
3. Only a human-facing UI? → *Now* an agent may drive it — under the loop in §2.

Every connector you move from category 3 to category 1/2 stops being
non-deterministic. That is the cheapest reliability you will ever buy. Do it
before anything clever.

## 2. Agent-driven surfaces run a closed loop, never a script

Fire-and-forget automation breaks on any UI change because it cannot tell that it
broke. `CloudConnectorFormAutomation` is 1,600 lines of hardcoded clicks and OCR
anchoring — it is the *least* agentic thing we could have built, and a smarter
model makes it obsolete rather than better. Do not extend it. Replace its shape.

Every agent-driven flow must run these five beats, and the harness's job is to
make each a clean tool:

- **Observe** — give the agent the *full* accessibility tree / DOM + screenshot
  as an observation. Do **not** pre-filter to "find the Add button." Localizing
  the target is the model's job; doing it for it (badly) is why we have commits
  like *"Infer Claude Add target from Cancel button."*
- **Act** — atomic primitives only: `click(x,y)`, `type`, `key`, `scroll`,
  `navigate`.
- **Re-observe** — after every action, snapshot again. Acting-then-observing is
  the single biggest reliability lever we have. It is the thing a script
  structurally cannot do.
- **Verify** — let the agent confirm the state actually changed as intended.
- **Recover** — on mismatch, feed the failure back and let the agent try another
  approach, bounded to N attempts, then fail loud.

If you find yourself hardcoding *which* element to click or *where* it is on
screen, stop. That knowledge is volatile; encoding it in Swift means every
provider redesign becomes a release cycle.

## 2b. When neither code nor agent can own the surface, ship assisted-first

Between "code writes a file" and "agent drives the UI" there is a third shape
that is often the right one: **do the deterministic 90% in code, hand the human
one clear action.** Open the exact deep link, present the setup values on a
movable on-screen card with one copy button per field (secrets masked on
screen, real value copied), auto-expand the step list — the user pastes and
clicks the final button. This is the primary flow for ChatGPT/Claude cloud
connectors today.

A 100%-reliable "you click once" beats a 60%-reliable "do it for me" that
leaves the provider UI in an unknown state. Autonomy is an upgrade you earn
back with better perception (see the roadmap doc), not the default you ship
while perception is bad. Design assisted flows to the same bar as autonomous
ones: field-level affordances, not a wall of text in the clipboard.

## 3. Never trust the UI. End every flow with a functional probe.

The UI saying "Connected" is not evidence the integration works. A setup is
complete only when a **real functional call succeeds through the thing you just
configured.**

We already have the probes: `testHostedMCPMemoryCount()` hits the live MCP
endpoint and counts memories; `testAgentConnections()` exercises both hosted and
local. Use them as the completion gate. The agent's screen-reading tells you
*where to click*; the probe tells you *whether it worked*. Keep those signals
separate or you will keep shipping false "Connected."

The probe must cover the **whole chain, including our own contract endpoints**.
The ChatGPT connector flow failed in production not on the provider's UI but on
our own OAuth wiring — an unregistered client id and an exact-match redirect
allowlist that can't cover per-connector callbacks. A probe that only checks
the MCP data call would call that setup "working." Exercise the auth handshake
the provider will actually perform.

## 4. "Connected" means "verified recently," not "once true."

Today connection state is a one-way latch:

```swift
func markConnected(dest) { defaults.set(Date()..., forKey: dest.connectedAtKey) }
hasConnection = exportedCount > 0 || defaults.double(forKey: connectedAtKey) > 0
```

Once the timestamp is written the source reads "Connected" **forever** — even
after the cookie expires, the key rotates, or the user deletes the connector on
the provider side. The user's mental model and reality diverge, and that reads as
"randomly broken."

Rule: derive status from a recent functional probe (§3) and from
`CredentialHealthManager`, never from a latch. If it hasn't been verified inside
the freshness window, it is not "Connected" — it is "needs check."

## 5. Prefer the highest-fidelity perception available

Perception fidelity is reliability. Ranked best to worst:

1. **API response** (a contract) — use if it exists.
2. **DOM** via a controllable browser (CDP/Playwright) — stable selectors, real
   element state, `aria` labels.
3. **Accessibility tree** — structured, but app-dependent.
4. **Vision/OCR of pixels** — the last resort. "Did OCR read 'Add' or 'Add-on'?"

Provider connector flows are *web pages*. Driving them through OCR of a native
window is the worst option for the easiest-to-improve surface. When you next
touch a web-based flow, move it to a browser context so the agent perceives DOM,
not pixels. Same user session, no new auth — just a vastly richer observation.

## 6. Provider knowledge is data, not binary

Much of our pain is *latency*: a provider moves a button, and the fix needs a
Swift edit, a clean release build, notarization, and a user update — days, for a
"the button moved" change. That is backwards.

- The **harness** (perceive/act/verify/probe/recover) is stable → compile it.
- The **provider knowledge** (how to set up X, what the flow looks like) is
  volatile → ship it as remotely-updatable config/skills the app fetches.

When a provider redesigns, push a new instruction blob and installed apps
self-correct on next run. No release cycle for volatile knowledge.

**Our own backend config is provider knowledge too.** OAuth client ids,
redirect allowlists, and authorize/token URLs live in the backend's
environment, diverge between dev and prod, and change without a desktop
release. Compiling them into Swift (as `chatgptOAuthClientID` does today)
means desktop guidance can silently drift from what the backend actually
registers — which is exactly how "Unknown OAuth client" shipped. Serve
connector setup values from the backend the desktop is pointed at.

## 7. Build the eval flywheel — this is how the "agents get smarter" bet pays off

A brittle surface with no test is found broken by users while CI stays green. Make
the surface testable by **capturing observations as fixtures**:

- Every real run records its trace: observations (AX tree / DOM / screenshot),
  actions, outcome, verified-or-not.
- Failed runs auto-upload a **sanitized** trace. That is simultaneously the
  canary (we learn a provider changed *before* users flood in) and the eval
  corpus.
- Replay captured traces offline against a candidate model/prompt. "Does the next
  model still complete all N provider setups?" becomes a CI question answered
  against real captured snapshots — not a production discovery.

A smarter model only helps if we can feed it the failure data and prove the
improvement offline. Without this loop, a model upgrade is a coin flip we can't
measure. With it, every provider UI change becomes: capture new snapshot → add to
eval set → harness and next model are hardened against it.

**Sanitization is non-negotiable** — traces contain the user's screen. Use
`sanitize()` / `sanitize_pii()` conventions; strip cookies, tokens, and
message bodies before anything leaves the machine.

## 8. Self-heal, and isolate blast radius

- **Continuous verifier → auto-reheal.** Run the functional probe on a heartbeat.
  On failure, don't just flip the badge — spawn the agent to redo setup in the
  background before the user notices. This is where the agent's adaptability
  becomes visible: the integration quietly fixes itself.
- **Per-provider isolation.** One provider's broken flow must be a circuit
  breaker, not an outage across the whole column. Do not let connectors share a
  god-module where a Claude change can regress Gmail. (`CloudConnectorFormAutomation`
  and the oversized `MemoryExportService` are the anti-patterns to break apart,
  not extend.)

---

## Anti-patterns (do not do these)

- Adding another hardcoded element-anchoring heuristic to
  `CloudConnectorFormAutomation`. The churn history of that file is the evidence.
- Gating "Connected" on a timestamp or a one-time success.
- Sending an agent to do a job a deterministic file write could do.
- Perceiving a web flow through Vision/OCR when a DOM is available.
- Compiling volatile provider knowledge into the Swift binary.
- Shipping a setup flow with no functional probe at the end.
- Uploading a trace without stripping cookies, tokens, and PII.

## If you only have an hour

1. Move one more connector from "agent does it" to "code writes the file."
2. Make one connector's status gate on its functional probe instead of the latch.

Both are pure reliability with zero model risk, and they compound.

---

## Why this document exists

We are betting that agents get smarter and that a well-built harness lets them
"make magic happen." That bet is only sound if we spend our effort on the parts
we control — the harness, the perception fidelity, the verification loop, the
eval flywheel — and stop spending it on the parts we don't — other people's UIs.
A smart agent inside a fire-and-forget script is still brittle. A modest agent
inside a perceive → act → verify → probe → recover loop, fed by an eval corpus
and hot-updatable knowledge, is robust. Build the second one.
