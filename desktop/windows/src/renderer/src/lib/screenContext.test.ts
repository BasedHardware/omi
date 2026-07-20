import { describe, it, expect, vi, afterEach } from 'vitest'
import { screen } from './native'
import { readCurrentScreen } from './screenContext'

vi.mock('./native', () => ({ screen: { readText: vi.fn() } }))

// Mock window.omi.screenReadText so we can drive the OCR result.
function mockScreenReadText(value: string): void {
  vi.mocked(screen.readText).mockResolvedValue(value)
}

describe('readCurrentScreen', () => {
  afterEach(() => {
    vi.mocked(screen.readText).mockReset()
  })

  it('prepends the ambient screen-context preamble and includes the OCR text', async () => {
    mockScreenReadText('Inbox — 3 unread messages')
    const out = await readCurrentScreen()
    expect(out).toContain('[Screen context')
    expect(out).toContain('ignore this completely')
    expect(out).toContain('Inbox — 3 unread messages')
  })

  it('returns empty string when OCR returns empty', async () => {
    mockScreenReadText('')
    expect(await readCurrentScreen()).toBe('')
  })

  it('returns empty string when OCR returns only whitespace', async () => {
    mockScreenReadText('   \n\t  ')
    expect(await readCurrentScreen()).toBe('')
  })

  it('clips long OCR text at MAX_SCREEN_CHARS and appends an ellipsis', async () => {
    const long = 'a'.repeat(5000)
    mockScreenReadText(long)
    const out = await readCurrentScreen()
    expect(out).toContain('…')
    // 4000 chars of OCR + ellipsis; the original 5000-char run must be truncated.
    expect(out).toContain('a'.repeat(4000))
    expect(out).not.toContain('a'.repeat(4001))
  })
})
