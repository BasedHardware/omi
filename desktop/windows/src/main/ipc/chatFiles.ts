import { dialog, ipcMain } from 'electron'
import { readFile, stat } from 'node:fs/promises'
import { basename, extname } from 'node:path'
import type { PickedChatFile } from '../../shared/types'

// Per-file ceiling for a chat attachment. The bytes are read into memory and
// shipped over IPC, so an over-cap file is stat-gated and returned WITHOUT bytes
// (the renderer rejects it with a reason) — main never slurps a huge file.
const MAX_FILE_BYTES = 25 * 1024 * 1024

// Minimal extension→MIME map so the renderer can render a preview and set the
// upload Blob's type. The backend does its own content-type detection on
// /v2/files, so this is best-effort; anything unknown is a generic binary.
const MIME_BY_EXT: Record<string, string> = {
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.webp': 'image/webp',
  '.bmp': 'image/bmp',
  '.heic': 'image/heic',
  '.pdf': 'application/pdf',
  '.txt': 'text/plain',
  '.md': 'text/markdown',
  '.csv': 'text/csv',
  '.json': 'application/json',
  '.doc': 'application/msword',
  '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  '.xls': 'application/vnd.ms-excel',
  '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  '.ppt': 'application/vnd.ms-powerpoint',
  '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation'
}

function mimeFor(name: string): string {
  return MIME_BY_EXT[extname(name).toLowerCase()] ?? 'application/octet-stream'
}

export function registerChatFilesHandlers(): void {
  // Open a native multi-select picker and read the chosen files. Mirrors the
  // proven dialog pattern in ipc/memoryExport.ts (showOpenDialog → read on the
  // main side). Returns [] on cancel.
  ipcMain.handle('chat:openFiles', async (): Promise<PickedChatFile[]> => {
    const r = await dialog.showOpenDialog({
      title: 'Attach files',
      properties: ['openFile', 'multiSelections'],
      filters: [
        {
          name: 'Images & documents',
          extensions: [
            'png',
            'jpg',
            'jpeg',
            'gif',
            'webp',
            'bmp',
            'heic',
            'pdf',
            'txt',
            'md',
            'csv',
            'json',
            'doc',
            'docx',
            'xls',
            'xlsx',
            'ppt',
            'pptx'
          ]
        },
        { name: 'All files', extensions: ['*'] }
      ]
    })
    if (r.canceled || r.filePaths.length === 0) return []

    const picked: PickedChatFile[] = []
    for (const path of r.filePaths) {
      const name = basename(path)
      const mimeType = mimeFor(name)
      let size = 0
      try {
        size = (await stat(path)).size
      } catch {
        // Unreadable file — surface it to the renderer as a zero-byte, no-bytes
        // entry so it's rejected there rather than silently dropped.
        picked.push({ path, name, mimeType, size: 0, bytes: null })
        continue
      }
      // Over-cap: return metadata WITHOUT reading the bytes; the renderer rejects
      // it with a 'too_large' reason.
      if (size > MAX_FILE_BYTES) {
        picked.push({ path, name, mimeType, size, bytes: null })
        continue
      }
      try {
        const buf = await readFile(path)
        picked.push({ path, name, mimeType, size: buf.byteLength, bytes: new Uint8Array(buf) })
      } catch {
        picked.push({ path, name, mimeType, size, bytes: null })
      }
    }
    return picked
  })
}
