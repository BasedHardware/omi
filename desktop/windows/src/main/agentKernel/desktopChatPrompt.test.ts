import { describe, expect, it } from 'vitest'
import { buildDesktopChatSystemPrompt } from './desktopChatPrompt'

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
})
