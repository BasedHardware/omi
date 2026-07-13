import type { ChatUsageQuota } from './omiApi.generated'

// Global usage-limit popup channel. Anywhere in the app can raise the modal via
// showUsageLimit(); the host (UsageLimitPopupHost) subscribes via onUsageLimit.
// Same tiny pub/sub shape as lib/toast — no external deps, no React coupling.

export type UsageLimitReason = 'chat' | 'transcription' | 'trial_expired'

const listeners = new Set<(reason: UsageLimitReason | null) => void>()
let current: UsageLimitReason | null = null

function emit(): void {
  listeners.forEach((cb) => cb(current))
}

export function onUsageLimit(cb: (reason: UsageLimitReason | null) => void): () => void {
  listeners.add(cb)
  cb(current)
  return () => listeners.delete(cb)
}

export function showUsageLimit(reason: UsageLimitReason): void {
  current = reason
  emit()
}

export function dismissUsageLimit(): void {
  current = null
  emit()
}

// ── Chat-quota trigger ──────────────────────────────────────────────────────
// The chat send path lives on another branch, so rather than rewire it we watch
// the quota from the outside: after a send settles, a cheap GET usage-quota that
// reports allowed=false raises the popup. Fired at most once per app session so
// a user who keeps trying isn't nagged repeatedly.

let chatQuotaPopupShown = false

/** Test-only: reset the once-per-session guard. */
export function __resetUsageLimitSession(): void {
  chatQuotaPopupShown = false
  current = null
}

/**
 * Check the chat quota and, if it is exhausted, raise the 'chat' popup — but
 * only the first time in a session. Returns true iff the popup was shown by this
 * call. `fetchQuota` is injected so callers/tests control the network.
 */
export async function maybeTriggerChatQuotaPopup(
  fetchQuota: () => Promise<ChatUsageQuota>
): Promise<boolean> {
  if (chatQuotaPopupShown) return false
  let quota: ChatUsageQuota
  try {
    quota = await fetchQuota()
  } catch {
    // A quota probe must never surface an error to the user — stay silent.
    return false
  }
  if (quota.allowed === false) {
    chatQuotaPopupShown = true
    showUsageLimit('chat')
    return true
  }
  return false
}
