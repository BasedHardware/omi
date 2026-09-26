import {
  completeJitKeyframeCleanup,
  listPendingJitKeyframeCleanup,
  listJitConversationKeyframePinDetails,
  listJitKeyframePinDetailsForDeletionKey,
  markJitKeyframeCleanupRetry,
  type JitMirrorDb
} from './jitTriggerMirror'
import type { JitKeyframePin } from './jitTriggerMirror'

/**
 * Delete an attached Rewind keyframe before retiring its durable references.
 *
 * This small seam keeps the filesystem operation injectable: a transient
 * delete failure must leave both the Rewind row and JIT pin for a later retry.
 * ENOENT is terminal because the file is already absent.
 */
export type JitKeyframeDeleteResult = 'removed' | 'retry'

export type JitKeyframeDeleteInput = {
  removeFile: () => Promise<void>
  deleteFrame: () => void
  removePin: () => void
}

/** Chat/session IDs and agent-kernel conversation IDs are separate namespaces.
 * Keep both ownership keys so a renderer deletion cannot strand a JIT pin. */
export function jitConversationIdsForDeletion(
  sessionId: string,
  resolveConversationId: (deletionKey: string) => string | null | readonly string[],
  options: { includeOriginalKey?: boolean } = {}
): string[] {
  const ids = new Set<string>()
  if (options.includeOriginalKey !== false) ids.add(sessionId)
  try {
    const resolved = resolveConversationId(sessionId)
    const conversationIds = Array.isArray(resolved) ? resolved : [resolved]
    for (const conversationId of conversationIds) {
      if (conversationId) ids.add(conversationId)
    }
  } catch {
    // If the authoritative resolver is unavailable, preserve only the optional
    // original key; failing closed preserves the pin for the durable cleanup
    // worker rather than guessing another conversation.
  }
  return [...ids]
}

/** Resolve every durable JIT pin owned by a renderer deletion. The kernel
 * conversation resolver covers ordinary main-chat surfaces; the explicit
 * renderer-key association covers the dedicated jit_assistant/candidate
 * surface, whose conversation is intentionally not the renderer surface. */
export function listJitKeyframePinsForDeletion(
  db: JitMirrorDb,
  deletionKey: string,
  resolveConversationId: (key: string) => string | null | readonly string[]
): JitKeyframePin[] {
  const pins = new Map<number, JitKeyframePin>()
  const conversationIds = jitConversationIdsForDeletion(deletionKey, resolveConversationId, {
    includeOriginalKey: false
  })
  for (const conversationId of conversationIds) {
    for (const pin of listJitConversationKeyframePinDetails(db, conversationId)) {
      pins.set(pin.frameId, pin)
    }
  }
  for (const pin of listJitKeyframePinDetailsForDeletionKey(db, deletionKey)) {
    pins.set(pin.frameId, pin)
  }
  return [...pins.values()]
}

export async function deleteJitKeyframeFileThenReferences(
  input: JitKeyframeDeleteInput
): Promise<JitKeyframeDeleteResult> {
  try {
    await input.removeFile()
  } catch (error) {
    const code = (error as { code?: unknown })?.code
    if (code !== 'ENOENT') return 'retry'
  }

  input.deleteFrame()
  input.removePin()
  return 'removed'
}

export type JitKeyframeCleanupDriver = {
  db: JitMirrorDb
  /** Read the current row, if it survived. The durable pin also carries a
   * path so cleanup can still unlink a file after a crash removed this row. */
  readFrame: (frameId: number) => { imagePath: string } | null
  removeFile: (imagePath: string) => Promise<void>
  deleteFrame: (frameId: number) => void
  now?: () => number
  limit?: number
}

/** Drain a bounded durable cleanup batch. This is intentionally independent of
 * the renderer/session lifecycle: launch, conversation deletion, and the
 * scheduled worker can all call it, while the outbox keeps failures retriable. */
export async function drainJitKeyframeCleanup(driver: JitKeyframeCleanupDriver): Promise<number> {
  const now = driver.now ?? Date.now
  const at = now()
  const pending = listPendingJitKeyframeCleanup(driver.db, at, driver.limit ?? 32)
  let removed = 0
  for (const item of pending) {
    const path = driver.readFrame(item.frameId)?.imagePath || item.imagePath
    if (!path) {
      markJitKeyframeCleanupRetry(driver.db, item.frameId, 'missing_rewind_path', at)
      continue
    }
    try {
      await driver.removeFile(path)
      // File removal is the commit point. Keep the pin and outbox if the
      // database update fails so a later bounded drain can finish the job.
      driver.deleteFrame(item.frameId)
      completeJitKeyframeCleanup(driver.db, item.frameId)
      removed += 1
    } catch (error) {
      const code = (error as { code?: unknown })?.code
      if (code === 'ENOENT') {
        try {
          driver.deleteFrame(item.frameId)
          completeJitKeyframeCleanup(driver.db, item.frameId)
          removed += 1
        } catch (dbError) {
          markJitKeyframeCleanupRetry(
            driver.db,
            item.frameId,
            dbError instanceof Error ? dbError.message : 'cleanup_reference_failure',
            at
          )
        }
      } else {
        markJitKeyframeCleanupRetry(
          driver.db,
          item.frameId,
          error instanceof Error ? error.message : 'frame_delete_failure',
          at
        )
      }
    }
  }
  return removed
}

export function startJitKeyframeCleanupWorker(
  driver: JitKeyframeCleanupDriver,
  intervalMs = 60_000
): () => void {
  void drainJitKeyframeCleanup(driver).catch((error) =>
    console.warn('[jit] initial keyframe cleanup failed:', error)
  )
  const timer = setInterval(() => {
    void drainJitKeyframeCleanup(driver).catch((error) =>
      console.warn('[jit] keyframe cleanup retry failed:', error)
    )
  }, intervalMs)
  return () => clearInterval(timer)
}
