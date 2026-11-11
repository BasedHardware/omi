import { describe, it, expect, vi } from 'vitest'

// memoryExtract pulls in apiClient (axios/firebase) at import; stub it so the
// pure normalize() can be unit-tested in isolation.
vi.mock('./apiClient', () => ({ desktopApi: {}, omiApi: {} }))

import { normalize } from './memoryExtract'

describe('normalize', () => {
  it('lowercases, drops punctuation, and collapses whitespace', () => {
    expect(normalize('  Works in  NY. ')).toBe('works in ny')
  })

  it('keeps + and # so C++ and C# stay distinct dedupe keys', () => {
    expect(normalize('Proficient in C++')).not.toBe(normalize('Proficient in C#'))
    expect(normalize('Proficient in C++')).toBe('proficient in c++')
  })
})
