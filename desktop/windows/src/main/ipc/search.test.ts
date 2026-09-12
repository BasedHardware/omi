import { describe, expect, it, vi, beforeEach } from 'vitest'

const searchDesktopCorpora = vi.fn()

vi.mock('electron', () => ({ ipcMain: { handle: vi.fn() } }))
vi.mock('./db', () => ({ searchDesktopCorpora }))

const { MAX_QUERY_CHARS, searchLocalCorpora } = await import('./search')
const { PER_CORPUS_LIMIT } = await import('../search/desktopSearch')

const RESULT = {
  memories: { hits: [], total: 3 },
  tasks: { hits: [], total: 0 },
  screen: { hits: [], total: 0 }
}
const EMPTY = {
  memories: { hits: [], total: 0 },
  tasks: { hits: [], total: 0 },
  screen: { hits: [], total: 0 }
}

beforeEach(() => {
  searchDesktopCorpora.mockReset()
  searchDesktopCorpora.mockReturnValue(RESULT)
})

describe('searchLocalCorpora', () => {
  it('passes the query through and returns what the corpora gave', () => {
    expect(searchLocalCorpora('lease')).toBe(RESULT)
    expect(searchDesktopCorpora).toHaveBeenCalledWith('lease', PER_CORPUS_LIMIT)
  })

  it('ignores a non-string query instead of handing it to SQLite', () => {
    for (const bad of [undefined, null, 42, {}, ['lease']]) {
      expect(searchLocalCorpora(bad)).toEqual(EMPTY)
    }
    expect(searchDesktopCorpora).not.toHaveBeenCalled()
  })

  it('truncates a pasted-in query rather than refusing it', () => {
    searchLocalCorpora('x'.repeat(MAX_QUERY_CHARS + 500))
    // Refusing would make the box look broken; an unbounded string becomes an
    // unbounded FTS expression running on every keystroke.
    expect(searchDesktopCorpora.mock.calls[0][0].length).toBe(MAX_QUERY_CHARS)
  })

  it('clamps the limit to the per-corpus cap in both directions', () => {
    searchLocalCorpora('lease', 5)
    expect(searchDesktopCorpora.mock.calls[0][1]).toBe(5)

    searchLocalCorpora('lease', 9999)
    expect(searchDesktopCorpora.mock.calls[1][1]).toBe(PER_CORPUS_LIMIT)

    searchLocalCorpora('lease', 0)
    expect(searchDesktopCorpora.mock.calls[2][1]).toBe(1)

    searchLocalCorpora('lease', Number.NaN)
    expect(searchDesktopCorpora.mock.calls[3][1]).toBe(PER_CORPUS_LIMIT)
  })

  it('degrades to no local results instead of throwing at the renderer', () => {
    searchDesktopCorpora.mockImplementation(() => {
      throw new Error('database is locked')
    })
    // A search box must never take the window down, and the server-side
    // conversation search the renderer runs alongside this still works.
    expect(searchLocalCorpora('lease')).toEqual(EMPTY)
  })
})
