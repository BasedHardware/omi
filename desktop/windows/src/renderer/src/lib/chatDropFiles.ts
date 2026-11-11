import type { PickedChatFile } from '../../../shared/types'

// Turn dropped browser File objects (drag-and-drop onto the ask bar) into the
// PickedChatFile shape addAttachments() consumes. The native picker
// (window.omi.openChatFiles) already returns PickedChatFile[] with a filesystem
// path; dropped files have no path, so we read their bytes in the renderer.
//
// A file that fails to read comes back with bytes:null — the attachment layer then
// rejects it with reason 'empty', matching the main picker's contract for
// over-cap/unreadable files, rather than throwing here.
export async function filesToPickedChatFiles(files: File[]): Promise<PickedChatFile[]> {
  return Promise.all(
    files.map(async (f) => {
      let bytes: Uint8Array | null = null
      try {
        bytes = new Uint8Array(await f.arrayBuffer())
      } catch {
        bytes = null
      }
      return {
        name: f.name,
        mimeType: f.type || 'application/octet-stream',
        size: f.size,
        bytes
      }
    })
  )
}
