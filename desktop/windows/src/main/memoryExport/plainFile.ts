import { promises as fs } from 'fs'
import type { ExportMemory } from '../../shared/types'
import { formatMemoriesMarkdown } from './format'

// Write memories as Markdown to an arbitrary file path the user picked. The
// "plain file" target — no app integration, just a portable .md export.
export async function exportToFile(filePath: string, memories: ExportMemory[]): Promise<string> {
  // Write to a sibling temp file then rename onto the destination, so replacing an
  // existing file is atomic and a partial write never leaves it truncated.
  const tmp = `${filePath}.${process.pid}.tmp`
  await fs.writeFile(tmp, formatMemoriesMarkdown(memories), 'utf8')
  await fs.rename(tmp, filePath)
  return filePath
}
