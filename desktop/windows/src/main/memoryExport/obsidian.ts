import { promises as fs } from 'fs'
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
  await fs.writeFile(file, formatMemoriesMarkdown(memories), 'utf8')
  return file
}
