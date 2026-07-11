import { promises as fs } from 'fs'
import { randomBytes } from 'crypto'
import { join } from 'path'
import type { ExportMemory } from '../../shared/types'
import { formatMemoriesMarkdown } from './format'

// Write memories to <vault>/Omi/Memories.md, mirroring the macOS Obsidian
// target. This is a full export, so the file is overwritten each time.
export async function exportToObsidian(
  vaultPath: string,
  memories: ExportMemory[]
): Promise<string> {
  const dir = join(vaultPath, 'Omi')
  await fs.mkdir(dir, { recursive: true })
  const file = join(dir, 'Memories.md')
  // Write to a temp file then rename onto the target so a failed or partial write
  // (disk full, crash) never truncates the user's previous export.
  // Random suffix (not a per-module counter) so temp names never collide across
  // exporters or processes writing to the same destination directory.
  const tmp = join(dir, `Memories.md.${process.pid}.${randomBytes(6).toString('hex')}.tmp`)
  try {
    await fs.writeFile(tmp, formatMemoriesMarkdown(memories), 'utf8')
    await fs.rename(tmp, file)
  } catch (err) {
    // Best-effort cleanup so a failed write or rename does not leave the temp
    // file behind. Swallow any unlink failure (the temp may never have been
    // created); the original error is what the caller needs to see.
    await fs.rm(tmp, { force: true }).catch(() => {})
    throw err
  }
  return file
}
