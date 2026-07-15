import { createSignal } from './signal'
import { uploadChatFile } from './chatAttachmentUpload'
import type { PickedChatFile } from '../../../shared/types'

// Mac's cap: at most 4 files attached to one chat message.
export const MAX_CHAT_ATTACHMENTS = 4
// Keep in lockstep with the main-process reader (ipc/chatFiles.ts).
const MAX_FILE_BYTES = 25 * 1024 * 1024

export type AttachmentStatus = 'uploading' | 'uploaded' | 'failed'

/** One pending chat attachment. `id` is a stable local id (the chip key, stable
 *  across status changes). `serverId` is the uploaded file's `FileChat.id` — the
 *  value that goes into the /v2/messages `file_ids` — present only once uploaded. */
export type PendingAttachment = {
  id: string
  name: string
  mimeType: string
  size: number
  status: AttachmentStatus
  serverId?: string
}

export type RejectReason = 'cap_exceeded' | 'too_large' | 'empty'

/** Result of addAttachments: what was accepted (now uploading) and what was
 *  rejected, so the UI can surface rejections rather than silently dropping. */
export type AddResult = {
  accepted: PendingAttachment[]
  rejected: { name: string; reason: RejectReason }[]
}

/** Injectable upload seam for tests. */
export type AttachmentDeps = { upload?: typeof uploadChatFile }

const signal = createSignal<PendingAttachment[]>([])
// In-flight upload promises, keyed by local attachment id, so a send can await
// everything settling before it reads the uploaded ids.
const inflight = new Map<string, Promise<void>>()

/** Subscribe to the pending list (replays the current value immediately). */
export function onPendingAttachments(cb: (list: PendingAttachment[]) => void): () => void {
  return signal.subscribe(cb)
}

export function getPendingAttachments(): PendingAttachment[] {
  return signal.get()
}

/** The uploaded server file ids, in list order — what goes into file_ids. */
export function getUploadedFileIds(): string[] {
  return signal
    .get()
    .filter((a) => a.status === 'uploaded' && a.serverId)
    .map((a) => a.serverId as string)
}

// Apply a partial update to one attachment by id, emitting a new array. A no-op
// if the attachment was already removed (its upload may still resolve later).
function patch(id: string, next: Partial<PendingAttachment>): void {
  signal.set(signal.get().map((a) => (a.id === id ? { ...a, ...next } : a)))
}

function startUpload(
  att: PendingAttachment,
  bytes: Uint8Array,
  upload: typeof uploadChatFile
): void {
  const p = upload({ name: att.name, mimeType: att.mimeType, bytes })
    .then((fc) => {
      patch(att.id, { status: 'uploaded', serverId: fc.id })
    })
    .catch(() => {
      // A failed upload marks ONLY this attachment failed; the others proceed.
      patch(att.id, { status: 'failed' })
    })
    .finally(() => {
      inflight.delete(att.id)
    })
  inflight.set(att.id, p)
}

/**
 * Add files to the pending list and kick off their uploads optimistically (so by
 * send time most are already uploaded). Enforces the 4-file cap and the per-file
 * size limit, returning both the accepted attachments and any rejections (with a
 * reason) so the UI can surface them.
 */
export function addAttachments(files: PickedChatFile[], deps: AttachmentDeps = {}): AddResult {
  const upload = deps.upload ?? uploadChatFile
  const accepted: PendingAttachment[] = []
  const rejected: AddResult['rejected'] = []
  const toUpload: { att: PendingAttachment; bytes: Uint8Array }[] = []
  // Count against the CURRENT list plus what we accept in this call.
  let count = signal.get().length

  for (const f of files) {
    if (!f.bytes || f.size <= 0) {
      rejected.push({ name: f.name, reason: 'empty' })
      continue
    }
    if (f.size > MAX_FILE_BYTES) {
      rejected.push({ name: f.name, reason: 'too_large' })
      continue
    }
    if (count >= MAX_CHAT_ATTACHMENTS) {
      rejected.push({ name: f.name, reason: 'cap_exceeded' })
      continue
    }
    const att: PendingAttachment = {
      id: crypto.randomUUID(),
      name: f.name,
      mimeType: f.mimeType,
      size: f.size,
      status: 'uploading'
    }
    accepted.push(att)
    toUpload.push({ att, bytes: f.bytes })
    count++
  }

  if (accepted.length > 0) {
    signal.set([...signal.get(), ...accepted])
    for (const { att, bytes } of toUpload) startUpload(att, bytes, upload)
  }
  return { accepted, rejected }
}

/** Remove one pending attachment. Its in-flight upload (if any) is forgotten; if
 *  it later resolves, the patch is a no-op since the entry is gone. */
export function removeAttachment(id: string): void {
  signal.set(signal.get().filter((a) => a.id !== id))
  inflight.delete(id)
}

/** Drop all pending attachments (called after a successful send). */
export function clearAttachments(): void {
  signal.set([])
  inflight.clear()
}

/** Resolve once every currently in-flight upload has settled (uploaded|failed).
 *  Send awaits this so no message goes out with a half-uploaded file. */
export async function awaitUploadsSettled(): Promise<void> {
  await Promise.all([...inflight.values()])
}
