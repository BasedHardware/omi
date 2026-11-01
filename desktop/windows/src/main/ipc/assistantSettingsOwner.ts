// Pure owner-fence state for assistant-settings writes. Kept in an Electron-free
// leaf module so the signature-verified session relay can bind the active UID
// without pulling in Electron UI or notification dependencies at import time.
let currentOwnerUid: string | null = null

/** Bind or clear the active authenticated owner UID for assistant-settings writes.
 *  An incoming `assistants:setSettings` patch carrying an old `ownerUid` /
 *  `expectedOwnerUid` is dropped after account replacement or sign-out. */
export function setAssistantSettingsOwner(uid: string | null): void {
  const trimmed = typeof uid === 'string' ? uid.trim() : ''
  currentOwnerUid = trimmed.length > 0 ? trimmed : null
}

export function getAssistantSettingsOwner(): string | null {
  return currentOwnerUid
}

export function isStaleOwnerWrite(patch: unknown, expectedOwnerUid?: unknown): boolean {
  const candidate =
    typeof expectedOwnerUid === 'string'
      ? expectedOwnerUid.trim()
      : patch &&
          typeof patch === 'object' &&
          typeof (patch as Record<string, unknown>).ownerUid === 'string'
        ? ((patch as Record<string, unknown>).ownerUid as string).trim()
        : null
  if (!candidate) return false
  return candidate !== currentOwnerUid
}
