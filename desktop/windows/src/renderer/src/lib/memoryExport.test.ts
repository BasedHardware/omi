// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { runMemoryExport } from './memoryExport'
import type { ExportMemory } from '../../../shared/types'

const obsidian = vi.fn()
const file = vi.fn()
const notion = vi.fn()

function stubExporters(): void {
  ;(window as unknown as { omi: Record<string, unknown> }).omi = {
    memoryExportObsidian: obsidian,
    memoryExportFile: file,
    memoryExportNotion: notion
  }
}

const mems: ExportMemory[] = [{ content: 'A fact', category: null, createdAt: '2026-01-01T00:00:00Z' }]

beforeEach(() => {
  obsidian.mockReset().mockResolvedValue({ count: 1, location: '/vault' })
  file.mockReset().mockResolvedValue({ count: 1, location: '/out.md' })
  notion.mockReset().mockResolvedValue({ count: 1, location: 'https://notion.so/p' })
  stubExporters()
})

describe('runMemoryExport', () => {
  it('dispatches obsidian to memoryExportObsidian with the memories', async () => {
    const r = await runMemoryExport('obsidian', mems)
    expect(obsidian).toHaveBeenCalledWith(mems)
    expect(file).not.toHaveBeenCalled()
    expect(notion).not.toHaveBeenCalled()
    expect(r).toEqual({ count: 1, location: '/vault' })
  })

  it('dispatches file to memoryExportFile with the memories', async () => {
    await runMemoryExport('file', mems)
    expect(file).toHaveBeenCalledWith(mems)
    expect(obsidian).not.toHaveBeenCalled()
    expect(notion).not.toHaveBeenCalled()
  })

  it('dispatches notion with the token, parentPageId, and memories', async () => {
    await runMemoryExport('notion', mems, { token: 'secret_x', parentPageId: 'page1' })
    expect(notion).toHaveBeenCalledWith({
      token: 'secret_x',
      parentPageId: 'page1',
      memories: mems
    })
    expect(obsidian).not.toHaveBeenCalled()
    expect(file).not.toHaveBeenCalled()
  })
})
