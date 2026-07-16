// The target → window.omi.memoryExport{Obsidian,File,Notion} dispatch, shared by
// Settings → Advanced and the Hub → Connections export rows so the switch lives in
// one place. Pure glue: the toast, empty-check, and Notion-credential UI logic all
// stay in the callers. Mirrors lib/pasteImport.ts / lib/stickyNotesImport.ts.
import type { ExportMemory, MemoryExportResult } from '../../../shared/types'

export async function runMemoryExport(
  target: 'obsidian' | 'file' | 'notion',
  memories: ExportMemory[],
  notion?: { token: string; parentPageId: string }
): Promise<MemoryExportResult> {
  if (target === 'obsidian') return window.omi.memoryExportObsidian(memories)
  if (target === 'file') return window.omi.memoryExportFile(memories)
  // Callers validate + trim the Notion creds before dispatching notion; fall back to
  // empty strings so the type holds if that ever slips.
  return window.omi.memoryExportNotion({
    token: notion?.token ?? '',
    parentPageId: notion?.parentPageId ?? '',
    memories
  })
}
