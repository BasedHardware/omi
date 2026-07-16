// Delete-a-session + re-thread pairing for the multi-chat header. Kept in its own
// module (not HubChatHeader.tsx) so the .tsx file only exports components
// (react-refresh/only-export-components) and so the decision is unit-testable
// without driving the popover UI.

/**
 * Delete a chat session and, if it was the ACTIVE thread, re-thread the engine
 * back to the default shared thread. `useChatSessions` and `useChat` are separate
 * hooks, so a bare `removeSession` leaves the engine's `sessionIdRef` /
 * `currentThreadId` pointing at the deleted id — the stale transcript stays on
 * screen, the next send persists to a dead `session_id`, and the kernel tail reads
 * the deleted chat's turns. `removeSession` re-throws on failure, so a failed
 * delete never re-threads.
 */
export async function deleteAndRethread(
  removeSession: (id: string) => Promise<void>,
  activeThreadId: string | null,
  switchThread: (id: string | null) => void,
  id: string
): Promise<void> {
  const wasActive = id === activeThreadId
  try {
    await removeSession(id)
  } catch {
    return // delete failed — leave the current thread untouched
  }
  if (wasActive) switchThread(null)
}
