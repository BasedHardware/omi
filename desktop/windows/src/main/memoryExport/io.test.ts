import { describe, it, expect, afterAll, vi } from 'vitest'
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

  it('exportToObsidian swaps the file in via temp+rename (no in-place truncate)', async () => {
    const vault = join(work, 'vault-atomic')
    const renameSpy = vi.spyOn(fs, 'rename')
    const file = await exportToObsidian(vault, memories)
    const lastCall = renameSpy.mock.calls.at(-1)
    expect(lastCall).toBeDefined()
    expect(String(lastCall![1])).toBe(file)
    expect(String(lastCall![0])).not.toBe(file)
    renameSpy.mockRestore()
  })

  it('exportToFile swaps the file in via temp+rename (no in-place truncate)', async () => {
    const target = join(work, 'memories-atomic.md')
    await fs.mkdir(work, { recursive: true })
    const renameSpy = vi.spyOn(fs, 'rename')
    await exportToFile(target, memories)
    const lastCall = renameSpy.mock.calls.at(-1)
    expect(lastCall).toBeDefined()
    expect(String(lastCall![1])).toBe(target)
    expect(String(lastCall![0])).not.toBe(target)
    renameSpy.mockRestore()
  })

  it('exportToObsidian removes the temp file when the rename fails', async () => {
    const vault = join(work, 'vault-cleanup')
    const renameSpy = vi.spyOn(fs, 'rename').mockRejectedValueOnce(new Error('rename boom'))
    await expect(exportToObsidian(vault, memories)).rejects.toThrow('rename boom')
    renameSpy.mockRestore()
    const entries = await fs.readdir(join(vault, 'Omi'))
    expect(entries.some((e) => e.endsWith('.tmp'))).toBe(false)
  })

  it('exportToFile removes the temp file when the rename fails', async () => {
    const target = join(work, 'memories-cleanup.md')
    await fs.mkdir(work, { recursive: true })
    const renameSpy = vi.spyOn(fs, 'rename').mockRejectedValueOnce(new Error('rename boom'))
    await expect(exportToFile(target, memories)).rejects.toThrow('rename boom')
    renameSpy.mockRestore()
    const entries = await fs.readdir(work)
    expect(entries.some((e) => e.startsWith('memories-cleanup.md.') && e.endsWith('.tmp'))).toBe(false)
  })
})
