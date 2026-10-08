import { describe, expect, it } from 'vitest'
import { formatConversationSummaryMarkdown as format } from './summaryMarkdown'

describe('conversation summary Markdown', () => {
  it('follows issue #12360 formatting with the full overview, saved task states and local date', () => {
    const result = format(
      {
        title: 'Planning sync',
        capturedAt: '2026-07-01T23:30:00Z',
        overview: 'Discussed the **roadmap**.\n\nSecond paragraph.',
        actionItems: [
          { description: 'Send recap', completed: false },
          { description: 'Book room', completed: true }
        ]
      },
      { locale: 'en-AU', timeZone: 'Australia/Sydney' }
    )
    expect(result).toBe(
      '### 💡 Planning sync\n\n*Captured via Omi • 2 July 2026, 09:30 am GMT+10:00*\n\n' +
        '**Key Takeaways:**\n\nDiscussed the **roadmap**.\n\nSecond paragraph.\n\n' +
        '**Action Items:**\n\n- [ ] Send recap\n- [x] Book room'
    )
  })

  it('omits missing sections and does not invent a date or a task', () => {
    expect(format({ title: '  ', overview: ' \n ', actionItems: [] })).toBe('### 💡 Conversation')
    expect(
      format({ title: 'Memo', capturedAt: 'invalid', actionItems: [{ description: ' ' }] })
    ).toBe('### 💡 Memo')
  })

  it('handles an explicit source offset and daylight saving without double conversion', () => {
    const result = format(
      { capturedAt: '2026-01-02T00:30:00+11:00' },
      { locale: 'en-AU', timeZone: 'America/New_York' }
    )
    expect(result).toContain('1 Jan 2026, 08:30 am GMT-05:00')
  })

  it('keeps plain-text titles and multiline tasks from creating extra Markdown structures', () => {
    const result = format({
      title: '[Roadmap](https://example.com)\n# later',
      actionItems: [{ description: 'Check *output*\n- [x] unexpected <html>', completed: false }]
    })
    expect(result).toContain('### 💡 \\[Roadmap\\](https://example.com) # later')
    expect(result).toContain('- [ ] Check \\*output\\* - \\[x\\] unexpected \\<html\\>')
    expect(result.split('\n').filter((line) => line.startsWith('- ['))).toHaveLength(1)
  })
})
