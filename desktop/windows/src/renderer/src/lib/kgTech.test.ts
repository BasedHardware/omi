import { describe, it, expect } from 'vitest'
import {
  slugify,
  nodeId,
  deriveTechNodes,
  deriveAppNodes,
  deriveFolderNodes,
  basename,
  MIN_FILES_FOR_TECH
} from './kgTech'

describe('basename', () => {
  it('returns the last path segment for Windows and POSIX paths', () => {
    expect(basename('C:\\Users\\a\\Documents\\VibeCoding\\sandbox-chat-kg')).toBe('sandbox-chat-kg')
    expect(basename('/home/a/projects/omi')).toBe('omi')
    expect(basename('C:\\Users\\a\\proj\\')).toBe('proj') // trailing slash
  })
})

describe('deriveFolderNodes', () => {
  const now = 7
  it('makes one file_group node per active folder, labeled by basename', () => {
    const nodes = deriveFolderNodes(
      [
        { folder: 'C:\\Users\\a\\VibeCoding\\sandbox-chat-kg', recentCount: 22, lastModified: 5 },
        { folder: 'C:\\Users\\a\\VibeCoding\\omi-windows', recentCount: 20, lastModified: 4 }
      ],
      now
    )
    expect(nodes.map((n) => n.label)).toEqual(['sandbox-chat-kg', 'omi-windows'])
    expect(nodes[0]).toMatchObject({
      id: 'sandbox-chat-kg:file_group',
      nodeType: 'file_group',
      source: 'files',
      createdAt: now
    })
    expect(nodes[0].summary).toContain('22')
    expect(nodes[0].summary.toLowerCase()).toContain('recently active')
  })
  it('dedupes folders that share a basename and skips blanks', () => {
    const nodes = deriveFolderNodes(
      [
        { folder: 'C:\\a\\proj', recentCount: 3, lastModified: 1 },
        { folder: 'D:\\b\\proj', recentCount: 1, lastModified: 1 },
        { folder: '', recentCount: 9, lastModified: 1 }
      ],
      now
    )
    expect(nodes.map((n) => n.label)).toEqual(['proj'])
  })
})

describe('slugify / nodeId', () => {
  it('lowercases and hyphenates', () => {
    expect(slugify('Visual Studio Code')).toBe('visual-studio-code')
    expect(slugify('C++')).toBe('c')
  })
  it('builds a stable id from label + type', () => {
    expect(nodeId('TypeScript', 'technology')).toBe('typescript:technology')
  })
})

describe('deriveTechNodes', () => {
  const now = 1000

  it('emits a node per tech above the evidence threshold', () => {
    const nodes = deriveTechNodes({ ts: 40, tsx: 10, py: 5 }, now)
    const labels = nodes.map((n) => n.label).sort()
    expect(labels).toEqual(['Python', 'TypeScript'])
    const tsNode = nodes.find((n) => n.label === 'TypeScript')!
    expect(tsNode.id).toBe('typescript:technology')
    expect(tsNode.nodeType).toBe('technology')
    expect(tsNode.source).toBe('derived')
    expect(tsNode.summary).toContain('50') // 40 + 10 ts/tsx files
    expect(tsNode.createdAt).toBe(now)
  })

  it('REGRESSION: no Dart/Kotlin/Gradle files => no Flutter/Dart/Android node', () => {
    const nodes = deriveTechNodes({ ts: 100, tsx: 30, py: 12 }, now)
    const labels = nodes.map((n) => n.label)
    expect(labels).not.toContain('Dart')
    expect(labels).not.toContain('Android')
    expect(labels.some((l) => /flutter/i.test(l))).toBe(false)
  })

  it('drops tech below the threshold', () => {
    const nodes = deriveTechNodes({ rs: MIN_FILES_FOR_TECH - 1 }, now)
    expect(nodes).toEqual([])
  })

  it('ignores unknown extensions and a leading dot', () => {
    const nodes = deriveTechNodes({ '.py': 5, xyz: 100 }, now)
    expect(nodes.map((n) => n.label)).toEqual(['Python'])
  })
})

describe('deriveAppNodes', () => {
  const now = 2000
  it('emits one app node per name and dedupes', () => {
    const nodes = deriveAppNodes(['Slack', 'Slack', '  Figma '], now)
    expect(nodes.map((n) => n.label)).toEqual(['Slack', 'Figma'])
    expect(nodes[0]).toMatchObject({ id: 'slack:app', nodeType: 'app', source: 'apps' })
  })
  it('skips blank names', () => {
    expect(deriveAppNodes(['', '   '], now)).toEqual([])
  })
})
