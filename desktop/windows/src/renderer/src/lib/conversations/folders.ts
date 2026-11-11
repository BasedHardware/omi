// Conversation-folder client API: backend CRUD (/v1/folders) plus reconciliation
// with the local cache (window.omi.* → conversation_folders) so the tab strip
// paints instantly and stays consistent. The backend is authoritative; the local
// cache is a disposable mirror for first paint. Calls go through the axios omiApi
// (types come from the generated client).

import { omiApi } from '../apiClient'
import type { ConversationFolder } from '../../../../shared/types'
import type { Folder, CreateFolderRequest, UpdateFolderRequest } from '../omiApi.generated'

/** Map a backend Folder DTO to the local ConversationFolder cache shape. Pure —
 *  exported for unit testing the snake_case→camelCase field mapping. */
export function toConversationFolder(f: Folder): ConversationFolder {
  return {
    id: f.id,
    name: f.name,
    color: f.color ?? null,
    icon: f.icon ?? null,
    orderIdx: f.order ?? 0,
    isSystem: f.is_system ?? false,
    conversationCount: f.conversation_count ?? 0,
    updatedAt: f.updated_at ? new Date(f.updated_at).getTime() : null
  }
}

/** Cached folders for instant paint (before the network reconcile lands). */
export function loadCachedFolders(): Promise<ConversationFolder[]> {
  return window.omi.listConversationFolders()
}

/** Fetch the authoritative folder list and replace the local cache with it. */
export async function fetchFolders(): Promise<ConversationFolder[]> {
  const r = await omiApi.get<Folder[]>('/v1/folders')
  const folders = (Array.isArray(r.data) ? r.data : []).map(toConversationFolder)
  await window.omi.replaceConversationFolders(folders)
  return folders
}

/** Create a folder, mirror it into the cache, return the created folder. */
export async function createFolder(req: CreateFolderRequest): Promise<ConversationFolder> {
  const r = await omiApi.post<Folder>('/v1/folders', req)
  const folder = toConversationFolder(r.data)
  await window.omi.upsertConversationFolder(folder)
  return folder
}

/** Rename / recolor a folder, mirror the change into the cache. */
export async function updateFolder(
  id: string,
  req: UpdateFolderRequest
): Promise<ConversationFolder> {
  const r = await omiApi.patch<Folder>(`/v1/folders/${id}`, req)
  const folder = toConversationFolder(r.data)
  await window.omi.upsertConversationFolder(folder)
  return folder
}

/** Delete a folder. `moveToFolderId` reassigns its conversations (backend
 *  `?move_to_folder_id`); omit to leave them unfiled. Drops it from the cache. */
export async function deleteFolder(id: string, moveToFolderId?: string): Promise<void> {
  await omiApi.delete(`/v1/folders/${id}`, {
    params: moveToFolderId ? { move_to_folder_id: moveToFolderId } : undefined
  })
  await window.omi.deleteConversationFolder(id)
}
