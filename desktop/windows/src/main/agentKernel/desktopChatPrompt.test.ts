import { describe, expect, it } from 'vitest'
import { buildDesktopChatSystemPrompt, buildDesktopChatPersonalization } from './desktopChatPrompt'

describe('buildDesktopChatSystemPrompt', () => {
  it('carries the <initiative> block that routes long/coding work to spawn_agent', () => {
    const prompt = buildDesktopChatSystemPrompt()
    // The whole point of the port: the model must be told to hand slow work to a
    // background agent instead of answering in text.
    expect(prompt).toContain('<initiative>')
    expect(prompt).toContain('spawn_agent')
    // The threshold is ported verbatim from macOS (the proven wording) so the
    // spawn trigger behaves like Mac's — not a more aggressive one.
    expect(prompt).toContain(
      'Work needing more than ~30 seconds of tool calls or research: start a background agent with spawn_agent'
    )
  })

  it('does NOT use a more aggressive spawn trigger than Mac (~30s threshold only)', () => {
    const prompt = buildDesktopChatSystemPrompt().toLowerCase()
    // Guard against over-eager wording that would spawn agents for normal chat —
    // the no-regressions constraint. Only the gated ~30s path may mention spawning.
    expect(prompt).not.toContain('always spawn')
    expect(prompt).not.toContain('spawn an agent for every')
    expect(prompt).not.toContain('spawn for any')
    // spawn_agent is referenced exactly once (the initiative bullet), not sprinkled
    // as a default action across the prompt.
    expect(prompt.match(/spawn_agent/g)).toHaveLength(1)
  })

  it('establishes the Omi persona and keeps normal replies conversational', () => {
    const prompt = buildDesktopChatSystemPrompt()
    expect(prompt).toContain('You are Omi')
    // Response-style guidance keeps ordinary questions as short text answers — the
    // regression guard that a system prompt does not turn every message into a spawn.
    expect(prompt).toContain('<response_style>')
    expect(prompt).toContain('Write like a smart friend texting')
  })

  it('carries the full ported persona: response_style, mentor, and critical-accuracy rules', () => {
    // The brief's parity gap — every typed reply must get the concise 2-8-line
    // register, the "mentor, not a yes-man" pushback, AND the anti-fabrication
    // guardrails, exactly as Mac front-loads them (ChatPrompts.desktopChat).
    const prompt = buildDesktopChatSystemPrompt()
    expect(prompt).toContain('<response_style>')
    expect(prompt).toContain('Default 2-8 lines')
    expect(prompt).toContain('<mentor_behavior>')
    expect(prompt).toContain("You're a mentor, not a yes-man")
    expect(prompt).toContain('<critical_accuracy_rules>')
    expect(prompt).toContain('never from plausible invention')
  })

  it('interpolates a name when provided, else reads as "the user"', () => {
    expect(buildDesktopChatSystemPrompt({ userName: 'Ada' })).toContain(
      'an AI assistant & mentor for Ada'
    )
    expect(buildDesktopChatSystemPrompt()).toContain('an AI assistant & mentor for the user')
    // No unreplaced template tokens leak through in either case.
    expect(buildDesktopChatSystemPrompt({ userName: 'Ada' })).not.toContain('{user_name}')
    expect(buildDesktopChatSystemPrompt()).not.toContain('{user_name}')
  })

  it('interpolates the timezone when provided and drops the parenthetical otherwise', () => {
    expect(buildDesktopChatSystemPrompt({ timezone: 'America/New_York' })).toContain(
      'timezone (America/New_York)'
    )
    const noTz = buildDesktopChatSystemPrompt()
    expect(noTz).toContain('timezone, in a natural')
    expect(noTz).not.toContain('{tz}')
  })

  it('is byte-stable for identical inputs (binding-reuse / no per-turn pi restart)', () => {
    // The kernel keys binding reuse on the system-prompt hash; a prompt that
    // varied turn-to-turn would restart the pi subprocess every message.
    const a = buildDesktopChatSystemPrompt({ timezone: 'UTC' })
    const b = buildDesktopChatSystemPrompt({ timezone: 'UTC' })
    expect(a).toBe(b)
  })

  it('carries NO volatile personalization (that rides the per-turn prompt, not here)', () => {
    // Personalization lives in the per-turn <user_context> block so the system
    // prompt stays byte-stable. Prove none of it leaked into the system prompt.
    const prompt = buildDesktopChatSystemPrompt({ userName: 'Ada' })
    expect(prompt).not.toContain('<user_context>')
    expect(prompt).not.toContain('<user_facts>')
    expect(prompt).not.toContain('<user_tasks>')
    expect(prompt).not.toContain('<ai_user_profile>')
  })
})

describe('buildDesktopChatPersonalization', () => {
  it('renders memories, tasks, and AI profile into one <user_context> block', () => {
    const block = buildDesktopChatPersonalization({
      userName: 'Ada',
      memories: ['prefers dark mode', 'lives in Berlin'],
      tasks: [
        { description: 'ship the installer', priority: 'high', category: 'work' },
        { description: 'call the bank' }
      ],
      aiProfileText: 'Ada is a systems engineer shipping a desktop app.'
    })
    expect(block).toContain('<user_context>')
    expect(block).toContain('</user_context>')
    // Faithful to Mac's formatMemoriesSection wording.
    expect(block).toContain('<user_facts>')
    expect(block).toContain('Facts about Ada:')
    expect(block).toContain('- [memory] prefers dark mode')
    expect(block).toContain('- [memory] lives in Berlin')
    // Faithful to Mac's formatTasksSection wording.
    expect(block).toContain('<user_tasks>')
    expect(block).toContain('Current tasks:')
    expect(block).toContain('- ship the installer [priority: high] [category: work]')
    expect(block).toContain('- call the bank')
    // Faithful to Mac's formatAIProfileSection.
    expect(block).toContain('<ai_user_profile>')
    expect(block).toContain('Ada is a systems engineer shipping a desktop app.')
  })

  it('renders a due date deterministically (UTC) when a task has one', () => {
    const block = buildDesktopChatPersonalization({
      tasks: [{ description: 'submit report', dueAt: Date.UTC(2026, 6, 20, 15, 30) }]
    })
    expect(block).toContain('- submit report [due: 2026-07-20 15:30]')
  })

  it('falls back to "the user" in the facts header when no name is given', () => {
    const block = buildDesktopChatPersonalization({ memories: ['likes tea'] })
    expect(block).toContain('Facts about the user:')
  })

  it('drops empty sections and returns "" when there is nothing to say', () => {
    // Whole-empty input → no wrapper at all (never inject an empty shell).
    expect(buildDesktopChatPersonalization()).toBe('')
    expect(buildDesktopChatPersonalization({ userName: 'Ada', memories: [], tasks: [] })).toBe('')
    // Only one source present → only that section, still wrapped.
    const onlyProfile = buildDesktopChatPersonalization({ aiProfileText: 'engineer' })
    expect(onlyProfile).toContain('<ai_user_profile>')
    expect(onlyProfile).not.toContain('<user_facts>')
    expect(onlyProfile).not.toContain('<user_tasks>')
  })

  it('caps memories at 30 and tasks at 20 (Mac parity)', () => {
    const block = buildDesktopChatPersonalization({
      memories: Array.from({ length: 50 }, (_, i) => `memory ${i}`),
      tasks: Array.from({ length: 40 }, (_, i) => ({ description: `task ${i}` }))
    })
    expect((block.match(/\[memory\]/g) ?? []).length).toBe(30)
    expect((block.match(/^- task /gm) ?? []).length).toBe(20)
  })

  it('ignores blank memories and blank-description tasks', () => {
    const block = buildDesktopChatPersonalization({
      memories: ['  ', 'real memory', ''],
      tasks: [{ description: '   ' }, { description: 'real task' }]
    })
    expect(block).toContain('- [memory] real memory')
    expect(block).toContain('- real task')
    // The blank entries did not produce empty bullets.
    expect(block).not.toContain('- [memory] \n')
  })
})
