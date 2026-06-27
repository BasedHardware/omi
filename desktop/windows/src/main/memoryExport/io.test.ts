import { describe, it, expect, afterAll } from 'vitest'
import { promises as fs } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'
import { exportToObsidian } from './obsidian'
import { exportToFile } from './plainFile'

// Real-filesystem checks for the file-writing export targets (no auth needed).
const work = join(tmpdir(), `omi-export-test-${Date.now()}`)
const memories = [
  { content: 'Has two cats', category: 'Personal' },
  { content: 'Prefers TypeScript', category: 'Work' }
]

afterAll(async () => {
  await fs.rm(work, { recursive: true, force: true })
})

describe('export file I/O (real disk)', () => {
  it('exportToObsidian writes <vault>/Omi/Memories.md', async () => {
    const vault = join(work, 'vault')
    const file = await exportToObsidian(vault, memories)
    expect(file).toBe(join(vault, 'Omi', 'Memories.md'))
    const text = await fs.readFile(file, 'utf8')
    expect(text).toContain('# Omi Memories')
    expect(text).toContain('## Personal')
    expect(text).toContain('- Has two cats')
    expect(text).toContain('## Work')
  })

  it('exportToFile writes Markdown to the given path', async () => {
    const target = join(work, 'memories.md')
    await fs.mkdir(work, { recursive: true })
    const file = await exportToFile(target, memories)
    expect(file).toBe(target)
    const text = await fs.readFile(file, 'utf8')
    expect(text).toContain('- Prefers TypeScript')
    expect(text).toContain('· 2 memories_')
  })
})
