// The bar's send path, gated on the chat usage limit (Mac's
// FloatingControlBarWindow pre-send check + FloatingBarUsageLimiter). Both bar
// surfaces funnel through here — typed submits and PTT commits — so a user over
// their monthly limit can't keep talking to the bar past the cap the main window
// already enforces.
//
// The bar is its OWN renderer process: it can't show the shared UsageLimitPopup
// (mounted in the main window) and can't speak (TTS lives in the main window's
// voiceController). So a blocked send hops the existing bar→main bridge — main's
// ChatBridgeHost raises the popup there, and speaks the line back for a voice
// turn — while the bar itself renders the same copy inline (Mac shows both: a
// local assistant bubble in the bar AND the modal on the main window).
import { createChatQuotaGate, type ChatQuotaGate } from '../../lib/chatQuotaGate'
import { auth } from '../../lib/firebase'

export type BarSender = {
  /** Send through the quota gate. Resolves to the blocked-notice text when the
   *  send was REFUSED (the bar renders it inline), or null when it went out. */
  send: (text: string, fromVoice: boolean) => Promise<string | null>
  /** Refresh the quota snapshot (mount + every reveal), so the hot send path
   *  reads a cached verdict instead of a network round trip. */
  sync: () => Promise<void>
}

export function createBarSender(
  gate: ChatQuotaGate = createChatQuotaGate(),
  // Signed-out gate: the quota probe is the FIRST authenticated call the bar
  // renderer ever makes. A dead session (a forceReauth sign-out leaves
  // `onboarded` set, so the bar stays summonable) would 401 it → refreshIdToken
  // → forceReauth → a spurious "Your session expired" toast raised from the bar.
  // No session ⇒ no quota call. Nothing is weakened: a signed-out user has no
  // chat to gate, and the server enforces the cap regardless.
  isSignedIn: () => boolean = () => auth.currentUser != null
): BarSender {
  return {
    sync: async (): Promise<void> => {
      if (!isSignedIn()) return
      await gate.sync()
    },
    send: async (text: string, fromVoice: boolean): Promise<string | null> => {
      if (!text.trim()) return null
      const verdict = isSignedIn() ? await gate.check() : ({ blocked: false } as const)
      if (verdict.blocked) {
        window.omiBar.notifyUsageLimit({ message: verdict.message, spoken: fromVoice })
        return verdict.message
      }
      // Onboarding: the user asked something in the bar.
      window.omiOverlay.notifyAsked()
      window.omiBar.sendChat(text, fromVoice)
      // Optimistic count so back-to-back sends between two server syncs can't
      // slip past the cap (Mac's FloatingBarUsageLimiter.recordQuery).
      gate.recordQuery()
      return null
    }
  }
}
