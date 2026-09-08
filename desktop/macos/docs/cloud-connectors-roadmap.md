# Cloud Connectors Roadmap — ChatGPT & Claude

**Scope:** the two "Connect your AI" cloud connectors that have **no config file
and no API** — ChatGPT (custom connector / developer mode) and Claude
(claude.ai custom connector). Everything else is category 1/2 per
[integrations-philosophy.md](./integrations-philosophy.md) §1 and is not covered
here.

**Status (July 2026):** ChatGPT is directory-first: Desktop opens Omi’s
approved ChatGPT listing and reads the user’s existing OAuth grant on return.
The developer-mode custom-app fields remain an advanced fallback. Claude is
still assisted-first. Autonomous setup remains **parked**, not abandoned — this
doc is the plan for bringing it back on a sounder foundation where a directory
is not available.

---

## Why we parked autonomous setup

Both flows were pure category-3 surfaces driven through low-fidelity perception,
and they failed differently:

- **ChatGPT** — the deepest flow we automated: Settings → Apps → Advanced →
  enable Developer mode (plan-gated) → Create app → 8-field OAuth form →
  consent. The agent drove the user's default browser via AppleScript/AX/
  screenshots and routinely died mid-flow. Some "failures" were never
  automation failures at all: custom connectors require a paid plan with
  developer mode, and we didn't detect that precondition.
- **Claude** — the native path (`CloudConnectorFormAutomation`, ~1,600 lines of
  hardcoded AX anchoring) worked on some machines only: AX exposure differs per
  browser (Chrome/Safari/Arc/Atlas), Claude hides Add/Connect from AX in some
  of them, and it needed Accessibility (sometimes Screen Recording) grants.

Conclusion per the philosophy doc: stop tuning heuristics on surfaces we don't
own. Make the deterministic 90% ours, hand the user the last click.

## Phase 1 — Assisted-first (Claude, and ChatGPT fallback)

"Do it for me" for Claude — and the optional ChatGPT developer-mode fallback — now:

1. opens the provider deep link in the default browser,
2. shows an on-screen card with **one copy button per field**
   (`CloudConnectorGuidanceOverlay.presentFieldCopyCard`, values from
   `assistedSetupFields`; secrets masked on screen, real value copied),
3. auto-expands the field-by-field steps in the connector sheet.

No Accessibility/Screen Recording permission needed; nothing left in an unknown
UI state. `MCPExecuteKind.browserAutonomous` still exists but is unmapped —
`MemoryExportExecutor.runBrowserAutonomous` / `runClaudeNativeCloudSetup` are
kept as the routing slot for Phase 2.

Follow-ups worth doing inside Phase 1:

- [ ] Gate "Connected" for these two on the functional probe
  (`testHostedMCPMemoryCount`), not the `markConnected` latch (philosophy §3/§4).
- [ ] ChatGPT precondition probe: detect plan/developer-mode ineligibility and
  say so, instead of sending the user into a flow that can't succeed.

## Phase 2 — DOM-fidelity automation (NEXT)

Re-introduce autonomous setup only with real DOM perception (philosophy §5),
not AX/OCR of a native browser window. Preferred shape:

- **Embedded WKWebView inside Omi**: load claude.ai / chatgpt.com in our own
  webview, drive it with `evaluateJavaScript`. Full DOM fidelity, zero
  cross-browser AX variance, no macOS permission dance. Cost: separate cookie
  jar → user signs in once inside it (Google OAuth blocks webviews; email/code
  login works). The held session doubles as the heartbeat re-verify channel
  (philosophy §8).
- Alternative: a controlled real browser (Playwright/CDP on the user's
  profile) — better session reuse, heavier to ship. Decide by prototype.

Rules when building it: selectors/flow knowledge ship as remotely-updatable
data (§6), every run captures a sanitized trace for the eval corpus (§7), and
completion is gated on the functional probe. When this lands, delete
`CloudConnectorFormAutomation` rather than extending it.

## Phase 3 — Get out of category 3 entirely

The real fix is distribution, not automation:

- **Anthropic connector directory**: get Omi Memory listed so Claude users
  click "Connect" in the directory and do a standard OAuth consent. No form,
  no automation.
- **OpenAI Apps SDK (SHIPPED):** Omi is listed as a ChatGPT app. Desktop opens
  the directory listing directly and verifies the resulting OAuth grant after
  the user returns.

The backend is already shaped for this (`backend/routers/mcp_sse.py` supports
public PKCE clients and per-provider callback allowlisting). Once listed,
Phases 1–2 become the fallback for users outside the directories.

## How to pick up this work

1. Phase 1 follow-ups are small, self-contained PRs — start there.
2. Phase 2 starts with a WKWebView spike: can a signed-in session add a Claude
   custom connector end-to-end via `evaluateJavaScript`? Timebox it before
   committing to the harness build-out.
3. Phase 3 is a checklist item per provider: prepare the OAuth client metadata,
   submit, track review. Check whether directory requirements changed before
   assuming this doc is current.
