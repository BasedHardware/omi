import { promises as fs } from 'fs'
import { join } from 'path'
import type { ExportMemory } from '../../shared/types'
import { formatMemoriesMarkdown } from './format'

// Monotonic per-process counter so two concurrent exports use distinct temp
// files instead of colliding on the same one and racing the rename.
let tmpSeq = 0

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
  const tmp = join(dir, `Memories.md.${process.pid}.${tmpSeq++}.tmp`)
  await fs.writeFile(tmp, formatMemoriesMarkdown(memories), 'utf8')
  await fs.rename(tmp, file)
  return file
}
