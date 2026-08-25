import type { LiveStatus } from './liveConversation'
import { isQuotaExhaustedMessage } from './transcriptionClient'
import { isByokActiveCached } from './byokKeys'
import { createSignal } from './signal'

// Global usage-limit popup channel. Anywhere in the app can raise the modal via
// showUsageLimit(); the host (UsageLimitPopupHost) subscribes via onUsageLimit.

export type UsageLimitReason = 'chat' | 'transcription' | 'trial_expired'

const signal = createSignal<UsageLimitReason | null>(null)

export function onUsageLimit(cb: (reason: UsageLimitReason | null) => void): () => void {
  return signal.subscribe(cb)
}

export function showUsageLimit(reason: UsageLimitReason): void {
  signal.set(reason)
}

export function dismissUsageLimit(): void {
  signal.set(null)
}

/** Test-only: reset the once-per-session guards. */
export function __resetUsageLimitSession(): void {
  transcriptionQuotaPopupShown = false
  signal.set(null)
}

// ── Transcription-quota trigger ─────────────────────────────────────────────
// The always-on mic session runs in the hidden capture window, a SEPARATE
// renderer from the one that mounts UsageLimitPopup — so it can't raise the
// popup itself (showUsageLimit's in-memory signal is per-renderer). It instead
// broadcasts its terminal 'error' live-status op, which the main window's
// LiveMirrorHost replays through here. A quota/entitlement exhaustion raises the
// 'transcription' popup (macOS UsageLimitPopup-on-1008 parity): a quota-blocked
// account can't create conversations, so mid-capture audio is dropped — the exact
// "Upgrade so your new recordings aren't lost" case. The inline error line stays;
// the modal is additive.

let transcriptionQuotaPopupShown = false

/**
 * Given a mirrored live-capture status, raise the 'transcription' popup once per
 * exhaustion when the status is a quota-exhausted error. Repeated error callbacks
 * for the same exhaustion don't re-raise it; any recovery (a non-error status)
 * re-arms the latch so a later real exhaustion shows again. A non-quota error
 * (mic unavailable, generic drop) keeps only the inline error line. Returns true
 * iff this call raised the popup.
 */
export function maybeTriggerTranscriptionQuotaPopup(status: LiveStatus, error?: string): boolean {
  if (status !== 'error') {
    // Recovery (connecting/live/idle) re-arms the latch for the next exhaustion.
    transcriptionQuotaPopupShown = false
    return false
  }
  if (!error || !isQuotaExhaustedMessage(error)) return false
  // BYOK users must never be paywalled — they pay the provider directly. The
  // backend exempts them, but a heartbeat lag can briefly emit the exhaustion
  // event locally after BYOK activation, so ignore it here (macOS
  // AppState+ListenEvents `freemium_threshold_reached` parity). Read the same
  // synchronous BYOK cache the request-header lanes use; don't touch the latch,
  // so a later exhaustion after BYOK is cleared still shows.
  if (isByokActiveCached()) return false
  if (transcriptionQuotaPopupShown) return false
  transcriptionQuotaPopupShown = true
  showUsageLimit('transcription')
  return true
}
