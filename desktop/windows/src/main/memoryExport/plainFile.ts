import { promises as fs } from 'fs'
import type { ExportMemory } from '../../shared/types'
import { formatMemoriesMarkdown } from './format'

// Write memories as Markdown to an arbitrary file path the user picked. The
// "plain file" target — no app integration, just a portable .md export.
export async function exportToFile(filePath: string, memories: ExportMemory[]): Promise<string> {
  await fs.writeFile(filePath, formatMemoriesMarkdown(memories), 'utf8')
  return filePath
}
