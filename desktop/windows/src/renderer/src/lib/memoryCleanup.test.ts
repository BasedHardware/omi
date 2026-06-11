import { describe, it, expect } from 'vitest'
import {
  isAppIndexMemory,
  appIndexMemoryIds,
  summarizeMemories,
  APP_INDEX_TAG
} from './memoryCleanup'
import { SCREEN_TAG } from './screenTag'
import type { Memory } from '../hooks/useMemories'

function mem(id: string, content: string, tags?: string[]): Memory {
  return {
    id,
    uid: 'u',
    content,
    tags,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z'
  }
}

describe('isAppIndexMemory', () => {
  it('matches the provenance tag regardless of content', () => {
    expect(isAppIndexMemory(mem('1', 'anything at all', [APP_INDEX_TAG]))).toBe(true)
  })
  it('treats SCREEN_TAG (Rewind synthesis) memories as removable', () => {
    expect(isAppIndexMemory(mem('1', 'The user is working on omi-windows', [SCREEN_TAG]))).toBe(true)
  })
  it('matches the tight "Uses <App>" template (untagged legacy builds)', () => {
    expect(isAppIndexMemory(mem('1', 'Uses Warp'))).toBe(true)
    expect(isAppIndexMemory(mem('2', 'Uses Visual Studio Code'))).toBe(true)
    expect(isAppIndexMemory(mem('3', 'Uses Google Chrome'))).toBe(true)
  })
  it('does NOT match a genuine memory that merely starts with "Uses …"', () => {
    expect(isAppIndexMemory(mem('1', 'Uses Excel daily for budgeting and taxes.'))).toBe(false)
    expect(isAppIndexMemory(mem('2', 'Used to work at Google before joining Omi'))).toBe(false)
  })
  it('matches file/project-index synthesis sentences (stem + a path)', () => {
    expect(
      isAppIndexMemory(
        mem('1', "The user's local projects include ~/projects/omi-cheap-voice-demo/app/scripts/me")
      )
    ).toBe(true)
    expect(
      isAppIndexMemory(mem('2', "The user's local files include C:\\Users\\ander\\Documents\\report.pdf"))
    ).toBe(true)
    expect(
      isAppIndexMemory(mem('3', "The user's repositories include /home/a/dev/omi and /home/a/dev/sandbox"))
    ).toBe(true)
  })
  it('matches the other file-index synthesis sentences (no path required)', () => {
    expect(
      isAppIndexMemory(mem('1', 'A recently modified local file is named PaperPreview-Light.json.'))
    ).toBe(true)
    expect(isAppIndexMemory(mem('2', 'The user works on a local project named chatgpt-github-app.'))).toBe(
      true
    )
    expect(isAppIndexMemory(mem('3', "The user's local files show active work in TypeScript."))).toBe(true)
    expect(
      isAppIndexMemory(mem('4', 'The user has 12,814 local files indexed across their machine.'))
    ).toBe(true)
  })
  it('does NOT match a project mention without a filesystem path', () => {
    // Real knowledge about a project, no path -> keep it.
    expect(isAppIndexMemory(mem('1', "The user's projects include a community garden initiative"))).toBe(
      false
    )
    expect(isAppIndexMemory(mem('2', 'Working on the omi-cheap-voice-demo project this week'))).toBe(false)
  })
  it('does not match unrelated memories', () => {
    expect(isAppIndexMemory(mem('1', 'Lives in Madrid', ['gmail/import/note']))).toBe(false)
    expect(isAppIndexMemory(mem('2', 'Prefers dark mode'))).toBe(false)
    expect(isAppIndexMemory(mem('3', 'The user lives near a local park'))).toBe(false)
  })
})

describe('appIndexMemoryIds', () => {
  it('returns only the matching ids', () => {
    const all = [
      mem('a', 'Uses Warp'),
      mem('b', 'Lives in Madrid'),
      mem('c', 'x', [APP_INDEX_TAG]),
      mem('d', 'Prefers tea')
    ]
    expect(appIndexMemoryIds(all)).toEqual(['a', 'c'])
  })
})

describe('summarizeMemories', () => {
  it('counts total and groups by tag with samples', () => {
    const all = [
      mem('a', 'Uses Warp', [APP_INDEX_TAG]),
      mem('b', 'Uses Chrome', [APP_INDEX_TAG]),
      mem('c', 'Email from boss about Q3', ['gmail/import/note']),
      mem('d', 'Likes hiking')
    ]
    const s = summarizeMemories(all)
    expect(s.total).toBe(4)
    expect(s.groups[0]).toMatchObject({ key: APP_INDEX_TAG, count: 2 })
    expect(s.groups.find((g) => g.key === '(untagged)')?.count).toBe(1)
    expect(s.groups.find((g) => g.key === 'gmail/import/note')?.count).toBe(1)
  })
  it('reports the app-index delete target count and samples', () => {
    const all = [mem('a', 'Uses Warp', [APP_INDEX_TAG]), mem('b', 'Likes hiking')]
    const s = summarizeMemories(all)
    expect(s.appIndexCount).toBe(1)
    expect(s.appIndexSamples).toEqual(['Uses Warp'])
  })
})
