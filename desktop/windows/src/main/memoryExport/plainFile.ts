import { promises as fs } from 'fs'
import type { ExportMemory } from '../../shared/types'
import { formatMemoriesMarkdown } from './format'

// Monotonic per-process counter so two concurrent exports to the same path use
// distinct temp files instead of colliding on one and racing the rename.
let tmpSeq = 0

// Write memories as Markdown to an arbitrary file path the user picked. The
// "plain file" target — no app integration, just a portable .md export.
export async function exportToFile(filePath: string, memories: ExportMemory[]): Promise<string> {
  // Write to a sibling temp file then rename onto the destination, so replacing an
  // existing file is atomic and a partial write never leaves it truncated.
  const tmp = `${filePath}.${process.pid}.${tmpSeq++}.tmp`
  try {
    await fs.writeFile(tmp, formatMemoriesMarkdown(memories), 'utf8')
    await fs.rename(tmp, filePath)
  } catch (err) {
    // Best-effort cleanup so a failed write or rename does not leave the temp
    // file behind. Swallow any unlink failure (the temp may never have been
    // created); the original error is what the caller needs to see.
    await fs.rm(tmp, { force: true }).catch(() => {})
    throw err
  }
  return filePath
}
