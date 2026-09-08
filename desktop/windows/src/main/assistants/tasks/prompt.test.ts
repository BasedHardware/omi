import { describe, expect, it } from 'vitest'

import { TASK_SYSTEM_PROMPT, buildUserPrompt } from './prompt'

describe('TASK_SYSTEM_PROMPT', () => {
  it('is a non-empty string', () => {
    expect(typeof TASK_SYSTEM_PROMPT).toBe('string')
    expect(TASK_SYSTEM_PROMPT.length).toBeGreaterThan(0)
  })

  it('contains its key anchor phrases (verbatim Mac port)', () => {
    expect(TASK_SYSTEM_PROMPT).toContain('You are a task commitment detector.')
    expect(TASK_SYSTEM_PROMPT).toContain('MANDATORY WORKFLOW:')
    expect(TASK_SYSTEM_PROMPT).toContain('PATTERN 1 — USER COMMITMENT (highest priority):')
    expect(TASK_SYSTEM_PROMPT).toContain('PATTERN 2 — UNADDRESSED REQUEST (secondary):')
    expect(TASK_SYSTEM_PROMPT).toContain(
      'SOURCE CLASSIFICATION (mandatory for every extracted task):'
    )
    // Names all five tools by name.
    expect(TASK_SYSTEM_PROMPT).toContain('no_task_found')
    expect(TASK_SYSTEM_PROMPT).toContain('search_similar')
    expect(TASK_SYSTEM_PROMPT).toContain('search_keywords')
    expect(TASK_SYSTEM_PROMPT).toContain('extract_task')
    expect(TASK_SYSTEM_PROMPT).toContain('reject_task')
  })
})

describe('buildUserPrompt', () => {
  const today = '2025-10-04 (Saturday)'

  it("includes the app name and today's date in the header", () => {
    const prompt = buildUserPrompt('Notion', today, false)
    expect(prompt).toContain('Screenshot from Notion.')
    expect(prompt).toContain('Today is 2025-10-04 (Saturday).')
    expect(prompt).toContain(
      'Analyze this screenshot for any unaddressed request directed at the user.'
    )
  })

  it('appends the messaging reminder when isMessagingApp is true', () => {
    const prompt = buildUserPrompt('Slack', today, true)
    expect(prompt).toContain('REMINDER — THIS IS A MESSAGING APP:')
    expect(prompt).toContain(
      'LEFT-SIDE messages = from the other person. RIGHT-SIDE/colored = from the user.'
    )
    expect(prompt).toContain('naming the other person in the conversation.')
  })

  it('omits the messaging reminder when isMessagingApp is false', () => {
    const prompt = buildUserPrompt('Google Chrome', today, false)
    expect(prompt).not.toContain('REMINDER — THIS IS A MESSAGING APP:')
  })

  it('places the header before the reminder block', () => {
    const prompt = buildUserPrompt('WhatsApp', today, true)
    expect(prompt.indexOf('Screenshot from WhatsApp.')).toBeLessThan(
      prompt.indexOf('REMINDER — THIS IS A MESSAGING APP:')
    )
  })
})
