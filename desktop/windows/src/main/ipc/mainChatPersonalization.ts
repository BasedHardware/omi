// Reads the signed-in user's local personalization (memories, active tasks, AI
// profile, name) and renders it into the per-turn <user_context> block that
// mainChat.ts prepends to a main-chat prompt — the Windows delivery of Mac's
// buildDesktopChat personalization. See the long note over
// buildDesktopChatPersonalization (agentKernel/desktopChatPrompt.ts) for WHY this
// rides in the per-turn prompt rather than the (byte-stable) system prompt.
//
// IMPORTANT — vitest boundary: this module statically imports ./db, whose graph
// loads the better-sqlite3 NATIVE binary (built for Electron's ABI; unloadable
// under plain-node Vitest). mainChat.ts therefore imports THIS module only via a
// lazy dynamic import inside defaultDeps() — never statically — so mainChat.test.ts
// stays loadable. Do not add a static `import` of this module to mainChat.ts.
//
// Every source read fails open (its own try/catch → skipped section): a missing
// DB, an empty table, or a decode miss must never throw out of a chat turn or
// blank the whole block. The name is opportunistic — decoded from the relayed
// session token's claims — because Windows keeps no synchronous main-side profile.

import { recentMemories, getLocalActionItems, latestAiUserProfile } from './db'
import { getPiMonoSession } from '../codingAgent/piMonoSession'
import { decodeJwtClaims } from '../auth/omiAuth'
import {
  buildDesktopChatPersonalization,
  type DesktopChatPersonalizationTask
} from '../agentKernel/desktopChatPrompt'

/** Mac caps: formatMemoriesSection prefix(30), tasks loaded with limit 20. */
const MEMORIES_LIMIT = 30
const TASKS_LIMIT = 20

/** The user's given name from the relayed Firebase ID token, or undefined.
 *  Tries `given_name` (Google claim), then the first word of `name` (the Firebase
 *  displayName claim) — the same fallback order as auth/omiAuth. Never throws. */
function readUserName(): string | undefined {
  try {
    const token = getPiMonoSession()?.token
    if (!token) return undefined
    const claims = decodeJwtClaims(token)
    if (!claims) return undefined
    const given = typeof claims.given_name === 'string' ? claims.given_name.trim() : ''
    if (given) return given
    const full = typeof claims.name === 'string' ? claims.name.trim() : ''
    if (full) return full.split(/\s+/)[0]
    return undefined
  } catch {
    return undefined
  }
}

/** Memory contents, newest-first, capped. Fails open to []. */
function readMemories(): string[] {
  try {
    return recentMemories(MEMORIES_LIMIT)
      .map((m) => m.content?.trim() ?? '')
      .filter((c) => c.length > 0)
  } catch {
    return []
  }
}

/** Active (incomplete) tasks, capped, in the shape the block renders. Fails open. */
function readTasks(): DesktopChatPersonalizationTask[] {
  try {
    return getLocalActionItems({ completed: false, limit: TASKS_LIMIT }).map((t) => ({
      description: t.description,
      priority: t.priority,
      dueAt: t.dueAt,
      category: t.category
    }))
  } catch {
    return []
  }
}

/** The latest AI-generated profile text, or undefined. Fails open. */
function readAiProfileText(): string | undefined {
  try {
    return latestAiUserProfile()?.profileText || undefined
  } catch {
    return undefined
  }
}

/**
 * Assemble the per-turn `<user_context>` block from the local stores, or '' when
 * there is nothing to say. Synchronous (all reads are better-sqlite3 sync reads).
 * Never throws — each source fails open, and the pure builder handles the empty
 * case by returning ''.
 */
export function readTurnPersonalization(): string {
  return buildDesktopChatPersonalization({
    userName: readUserName(),
    // Same machine IANA zone mainChat feeds the system prompt — so task due dates
    // render in the user's local wall-clock, matching the times the prompt tells
    // the model to display.
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    memories: readMemories(),
    tasks: readTasks(),
    aiProfileText: readAiProfileText()
  })
}
