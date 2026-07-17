// Global "Upgrade to Omi Pro" sheet channel — Windows port of macOS's
// ChatProvider.isClaudeAuthRequired + ClaudeAuthSheet semantics.
//
// CORRECT TRIGGER (Mac parity): the sheet is shown ONLY by an `auth_required`
// event the coding-agent bridge emits MID-TURN — i.e. Claude Code's token was
// rejected while a chat turn was running (taskRunner emits it; useChat handles
// it → beginClaudeSignIn). Mac presents its ClaudeAuthSheet the same way, via
// `.sheet(isPresented: $chatProvider.isClaudeAuthRequired)` on ChatPage.
//
// NOT a trigger: the Settings → Agents "Sign in to Claude" button. That button
// is a plain coding-agent OAuth — it calls window.omi.codingAgentStartAuth()
// directly with NO upsell, so a user (Omi Pro or not) is never paywalled just
// for connecting the coding agent. (An earlier Windows build wrongly routed the
// sign-in button through this sheet and mislabeled it "Mac-faithful"; it was
// not — Mac never ties the sheet to that button.)
//
// beginClaudeSignIn() (the mid-turn entry point) shows the sheet AND launches
// the real Claude OAuth in the browser IN PARALLEL (main's codingAgentStartAuth
// builds + validates the claude.com/cai/oauth/authorize URL, opens it, and awaits
// the loopback callback):
//  - If the user completes the parallel OAuth before dismissing, the flow
//    resolves connected → the sheet auto-closes and Claude is granted, no
//    purchase (Mac's auth_success bypass — kept deliberately).
//  - "Upgrade to Omi Pro" opens omi.me/pricing and dismisses; "Cancel" (and
//    Esc/outside-click) just dismisses. Both close the sheet.
//  - Fail-closed: if the flow fails (main rejects an invalid authorize URL, or
//    the callback times out), the sheet closes and the caller surfaces a
//    generic "Unable to start Claude sign-in. Try again." error (mirrors
//    ChatProvider.startClaudeAuth's invalid-URL branch, which hides the sheet
//    and sets an error rather than leaving a broken sheet up).
//
// The sheet is a global modal mounted once at the app root (like
// UsageLimitPopup). The bar is a separate renderer and does not host it.

import { createSignal } from './signal'
import type { CodingAgentStartAuthResult } from '../../../shared/types'

/** The pricing page the "Upgrade to Omi Pro" CTA opens (matches macOS). */
export const OMI_PRICING_URL = 'https://omi.me/pricing'

/** Shown when the sign-in flow can't start or complete (macOS parity copy). */
export const CLAUDE_SIGN_IN_FAILED = 'Unable to start Claude sign-in. Try again.'

type SheetState = { open: boolean }

const signal = createSignal<SheetState>({ open: false })
// True once a flow is launched, until it resolves — a second trigger (e.g. an
// auth_required event landing while Settings already opened the sheet) joins the
// in-flight flow instead of launching a second browser tab.
let inFlight = false
// Set when the user dismisses via Upgrade/Cancel so a late flow resolution does
// not re-drive the (now closed) sheet or fire a stale caller callback.
let dismissed = false

export function onClaudeSignIn(cb: (state: SheetState) => void): () => void {
  return signal.subscribe(cb)
}

/** Cancel/Upgrade/Esc — close the sheet. Reverts to the default chat path. */
export function dismissClaudeSignIn(): void {
  dismissed = true
  signal.set({ open: false })
}

/**
 * Mid-turn `auth_required` entry point: show the upsell sheet and launch the
 * parallel Claude OAuth. Call this ONLY from the coding-agent auth_required
 * handler (useChat) — NOT the Settings sign-in button, which does plain OAuth.
 * `onResult` fires once the flow resolves, unless the user already dismissed
 * the sheet.
 */
export function beginClaudeSignIn(onResult?: (result: CodingAgentStartAuthResult) => void): void {
  dismissed = false
  signal.set({ open: true })
  if (inFlight) return
  inFlight = true
  void window.omi
    .codingAgentStartAuth()
    .then((result) => {
      // Granted (bypass) or failed — either way the sheet's job is done. Upgrade/
      // Cancel may have already closed it; set() is idempotent.
      signal.set({ open: false })
      if (!dismissed) onResult?.(result)
    })
    .catch(() => {
      signal.set({ open: false })
      if (!dismissed) {
        onResult?.({
          ok: false,
          error: CLAUDE_SIGN_IN_FAILED,
          status: { connected: false, expiresAt: null }
        })
      }
    })
    .finally(() => {
      inFlight = false
    })
}

/** Test-only: reset module state between cases. */
export function __resetClaudeSignIn(): void {
  inFlight = false
  dismissed = false
  signal.set({ open: false })
}
