// User-scoped local-data teardown for a user-initiated Sign Out. Without it a
// second account signing in on the same machine sees the prior user's cached
// conversations, knowledge graph, rewind frames, insights, and chat thread until
// a re-sync overwrites them. Mirrors the macOS nuclear signOut scope
// (AuthService.signOut): wipe the local SQLite store + in-memory caches +
// user-scoped localStorage. Device/window settings live elsewhere and are kept.
//
// This is the NUCLEAR path. A 401 (dead session) takes the LIGHT path instead
// (authSession.forceReauth) and never wipes data.
import { clearMemoryCache } from './localAgentMemoryCache'
import { clearPendingConversations, invalidateConversationsCache } from './pageCache'
import { clearUserScopedPreferences } from './preferences'
import { CHAT_INFINITE_ID_KEY } from './chatStorageKeys'
import { POST_HISTORY_KEY } from './sync/backfillStorageKey'

// Standalone user-scoped localStorage keys (the device-prefs blob and sidebar
// collapse state are machine-scoped and NOT listed here).
const USER_SCOPED_LOCALSTORAGE_KEYS = [
  CHAT_INFINITE_ID_KEY, // shared chat conversation id (useChat)
  POST_HISTORY_KEY // from-segments post history (backfill dedupe)
]

export async function teardownUserData(): Promise<void> {
  // 1. Local SQLite: every table holds user data (conversations + outbox,
  //    captions, local KG, rewind frames, app usage, insights, indexed files).
  try {
    await window.omi?.wipeUserData?.()
  } catch (e) {
    console.warn('[auth-teardown] wipeUserData failed:', (e as Error).message)
  }
  // 2. In-memory module caches so the current window reflects the wipe without a
  //    relaunch (the Conversations list, pending placeholders, the chat-grounding
  //    memory cache).
  invalidateConversationsCache()
  clearPendingConversations()
  clearMemoryCache()
  // 3. User-scoped localStorage keys.
  for (const key of USER_SCOPED_LOCALSTORAGE_KEYS) {
    try {
      localStorage.removeItem(key)
    } catch {
      /* privacy mode / quota */
    }
  }
  // 4. User-identity fields inside the shared prefs blob (name, chosen goal) so
  //    the next account doesn't briefly inherit them. Device settings, consents,
  //    and onboarding state in the same blob are preserved.
  clearUserScopedPreferences()
}

// Machine-scoped: the last uid we hydrated for, used by the account-switch guard
// below. Deliberately NOT in USER_SCOPED_LOCALSTORAGE_KEYS — it must survive
// teardown so the NEXT sign-in can still tell whether the account changed.
const LAST_UID_KEY = 'omi.lastSignedInUid'

/**
 * Account-switch guard, called on every auth-state change with the resolved user
 * (null while signed out). When a DIFFERENT user signs in than last time, wipe
 * the previous user's local data BEFORE the app hydrates caches for the new one.
 * This closes the gap the LIGHT 401 path leaves open: forceReauth signs out
 * without a wipe, so if a different account then signs in it would otherwise see
 * the prior user's cached data. Same-uid re-auth (the common light-401 recovery)
 * does NOT wipe — that is the whole point of the light path. First-ever sign-in
 * (no stored uid) does not wipe. `await` this before mounting the authed shell so
 * hydration can't race the wipe.
 */
export async function reconcileAccountForSignIn(uid: string | null): Promise<void> {
  // Sign-out: keep the stored uid so the next DIFFERENT sign-in is still detected.
  if (!uid) return
  let stored: string | null = null
  try {
    stored = localStorage.getItem(LAST_UID_KEY)
  } catch {
    /* privacy mode */
  }
  if (stored && stored !== uid) await teardownUserData()
  try {
    localStorage.setItem(LAST_UID_KEY, uid)
  } catch {
    /* privacy mode / quota */
  }
}
