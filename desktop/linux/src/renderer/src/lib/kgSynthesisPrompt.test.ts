import { describe, it, expect } from 'vitest'
import { buildSynthesisPrompt } from './kgSynthesisPrompt'
import type { FileIndexDigest } from '../../../shared/types'

const digest: FileIndexDigest = {
  totalFiles: 100,
  byType: {},
  byExtension: { ts: 40, py: 10 },
  topFolders: [],
  activeFolders: [
    { folder: 'C:\\Users\\a\\VibeCoding\\omi-windows', recentCount: 20, lastModified: 5 }
  ],
  apps: ['Visual Studio Code', 'Slack'],
  sampleFiles: []
}

describe('buildSynthesisPrompt', () => {
  it('includes recently-active folders and memory snippets', () => {
    const p = buildSynthesisPrompt(digest, ['I am building the Omi Windows port'])
    expect(p).toContain('omi-windows')
    expect(p).toContain('Omi Windows port')
  })
  it('states the evidence rule for project nodes', () => {
    const p = buildSynthesisPrompt(digest, [])
    expect(p.toLowerCase()).toContain('only')
    expect(p.toLowerCase()).toContain('project')
    expect(p).toMatch(/memory|recently[- ]active folder/i)
  })
  it('asks for the nodes/edges JSON shape', () => {
    const p = buildSynthesisPrompt(digest, [])
    expect(p).toContain('"nodes"')
    expect(p).toContain('"edges"')
  })
  it('does NOT ask the model to invent technologies (those are deterministic)', () => {
    const p = buildSynthesisPrompt(digest, [])
    expect(p.toLowerCase()).toContain('do not')
    expect(p.toLowerCase()).toContain('technolog')
  })
  it('caps the number of memory lines rendered', () => {
    const many = Array.from({ length: 200 }, (_, i) => `memory number ${i}`)
    const p = buildSynthesisPrompt(digest, many)
    expect(p).not.toContain('memory number 100')
  })
})
