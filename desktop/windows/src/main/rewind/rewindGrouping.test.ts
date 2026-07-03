import { describe, it, expect } from 'vitest'
import { groupFrames, GROUP_WINDOW_MS } from './rewindGrouping'
import type { RewindFrame } from '../../shared/types'

function frame(over: Partial<RewindFrame>): RewindFrame {
  return {
    id: 1,
    ts: 0,
    app: 'Code.exe',
    windowTitle: 'a.ts',
    processName: 'Code',
    ocrText: 'hello world',
    imagePath: '/x.jpg',
    width: 0,
    height: 0,
    indexed: 1,
    ...over
  }
}

describe('groupFrames', () => {
  it('clusters frames within the time window AND same app+window into one group', () => {
    const frames = [
      frame({ id: 1, ts: 1000 }),
      frame({ id: 2, ts: 1000 + GROUP_WINDOW_MS - 1 }),
      frame({ id: 3, ts: 1000 + GROUP_WINDOW_MS + 5000 }) // new group (gap > window)
    ]
    const groups = groupFrames(frames, 'hello')
    expect(groups).toHaveLength(2)
    // newest group (frame 3) sorts first; oldest group (frames 1,2) sorts second
    expect(groups[0].frames.map((f) => f.id)).toEqual([3])
    expect(groups[1].frames.map((f) => f.id)).toEqual([1, 2])
  })
  it('splits when app/window changes even within the window', () => {
    const groups = groupFrames(
      [frame({ id: 1, ts: 0, app: 'A' }), frame({ id: 2, ts: 10, app: 'B' })],
      'hello'
    )
    expect(groups).toHaveLength(2)
  })
  it('sorts groups newest-first and sets startTs/endTs/representative/snippet', () => {
    const groups = groupFrames([frame({ id: 1, ts: 0 }), frame({ id: 2, ts: 9_000_000 })], 'world')
    expect(groups[0].startTs).toBe(9_000_000) // newest group first
    expect(groups[0].representative.id).toBe(2)
    expect(groups[0].matchSnippet.toLowerCase()).toContain('world')
  })
  it('uses window-title matches when OCR text does not explain the search hit', () => {
    const groups = groupFrames(
      [frame({ id: 1, windowTitle: 'Project plan - Notion', ocrText: 'status notes' })],
      'notion'
    )
    expect(groups[0].representative.id).toBe(1)
    expect(groups[0].matchSnippet).toContain('Window title:')
    expect(groups[0].matchSnippet.toLowerCase()).toContain('notion')
  })
  it('prefers OCR matches over shared metadata matches in the same group', () => {
    const groups = groupFrames(
      [
        frame({ id: 1, ts: 0, windowTitle: 'Slack - general', ocrText: 'daily notes' }),
        frame({ id: 2, ts: 10, windowTitle: 'Slack - general', ocrText: 'slack launch checklist' })
      ],
      'slack'
    )
    expect(groups[0].representative.id).toBe(2)
    expect(groups[0].matchSnippet).not.toContain('Window title:')
  })
  it('uses app matches when OCR and window title do not explain the search hit', () => {
    const groups = groupFrames(
      [frame({ id: 1, app: 'Slack.exe', windowTitle: 'general', ocrText: 'team update' })],
      'slack'
    )
    expect(groups[0].matchSnippet).toContain('App:')
    expect(groups[0].matchSnippet.toLowerCase()).toContain('slack')
  })
})
