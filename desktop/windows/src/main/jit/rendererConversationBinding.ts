/**
 * The renderer-visible chat/session that owns a delivered JIT artifact.
 *
 * JIT turns deliberately run on a separate `jit_assistant/candidate` kernel
 * surface. This binding is the explicit projection back to the real renderer
 * surface whose deletion should retire any attached keyframe. It is updated by
 * renderer selection IPC, never by a chat send, so a background turn cannot
 * accidentally inherit whichever chat happened to run most recently.
 *
 * `accountGeneration` is process-local auth generation. It advances whenever
 * the host owner changes or the session is cleared. The owner and generation
 * travel together in the snapshot and are checked by the JIT delivery path;
 * that makes an old renderer selection unusable after sign-out/account switch.
 */

export type RendererConversationBinding = {
  ownerId: string
  accountGeneration: number
  deletionKey: string
}

let ownerId: string | null = null
let accountGeneration = 0
let deletionKey: string | null = null
// Selection can arrive during the renderer's cold-start auth gap. Keep only the
// non-sensitive visible key until the host verifies an owner, then adopt it;
// sign-out clears this pending value so it cannot cross accounts.
let pendingDeletionKey: string | null = null

function normalizedOwner(value: string | null | undefined): string | null {
  const normalized = typeof value === 'string' ? value.trim() : ''
  return normalized || null
}

function normalizedKey(value: string | null | undefined): string | null {
  const normalized = typeof value === 'string' ? value.trim() : ''
  return normalized || null
}

/** Fence the binding to the host-authenticated owner. Repeated token refreshes
 * for the same owner preserve the selected renderer surface; a different owner
 * drops it and advances the local account generation before a new selection can
 * be accepted. */
export function fenceRendererConversationOwner(nextOwnerId: string | null | undefined): void {
  const next = normalizedOwner(nextOwnerId)
  if (next === ownerId) return
  ownerId = next
  accountGeneration += 1
  deletionKey = next ? pendingDeletionKey : null
  pendingDeletionKey = null
}

/** Record the renderer's currently selected visible chat/session. */
export function setRendererConversationSelection(
  nextOwnerId: string | null | undefined,
  nextDeletionKey: string | null | undefined
): void {
  const nextOwner = normalizedOwner(nextOwnerId)
  if (nextOwner !== ownerId) fenceRendererConversationOwner(nextOwner)
  if (!ownerId) {
    pendingDeletionKey = normalizedKey(nextDeletionKey)
    deletionKey = null
    return
  }
  deletionKey = normalizedKey(nextDeletionKey)
}

/** Clear the selection on sign-out/reset. The generation bump invalidates any
 * snapshot captured by an in-flight JIT analysis. */
export function clearRendererConversationBinding(): void {
  ownerId = null
  deletionKey = null
  pendingDeletionKey = null
  accountGeneration += 1
}

/** Capture the current owner-fenced selection for JIT delivery. */
export function rendererConversationBinding(): RendererConversationBinding | null {
  if (!ownerId || !deletionKey) return null
  return { ownerId, accountGeneration, deletionKey }
}

/** True when an in-flight artifact still belongs to the current account. A
 * different selected chat in the same account is intentionally allowed: the
 * captured deletion key still points at the renderer surface that owned it. */
export function rendererConversationBindingIsCurrent(
  binding: RendererConversationBinding
): boolean {
  return (
    binding.ownerId === ownerId &&
    binding.accountGeneration === accountGeneration &&
    ownerId !== null
  )
}

/** Test seam / process teardown helper. */
export function resetRendererConversationBindingForTests(): void {
  ownerId = null
  deletionKey = null
  pendingDeletionKey = null
  accountGeneration = 0
}
