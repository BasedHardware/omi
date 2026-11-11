import { describe, it, expect } from 'vitest'
import { goalEmoji, DEFAULT_GOAL_EMOJI } from './goalEmoji'

describe('goalEmoji', () => {
  it('maps a representative title per category', () => {
    const cases: Array<[string, string]> = [
      ['Hit $10k in revenue', '💰'],
      ['Grow to 100k users', '🚀'],
      ['Launch my startup', '🏆'],
      ['Invest in stocks', '📈'],
      ['Daily gym workout', '💪'],
      ['Run a marathon', '🏃'],
      ['Lose weight this year', '⚖️'],
      ['Meditate every morning', '🧘'],
      ['Get 8 hours of sleep', '😴'],
      ['Drink more water', '💧'],
      ['Stay healthy', '❤️'],
      ['Read 24 books', '📚'],
      ['Study for the exam', '🎓'],
      ['Code every day', '💻'],
      ['Become fluent in spanish', '🗣️'],
      ['Write a blog post', '✍️'],
      ['Film a youtube video', '🎬'],
      ['Practice guitar', '🎵'],
      ['Paint more often', '🎨'],
      ['Take a photo daily', '📸'],
      ['Finish my todo list', '✅'],
      ['Keep a daily streak', '🔥'],
      ['Focus with pomodoro', '⏰'],
      ['Ship the project', '🎯'],
      ['Travel to a new country', '✈️'],
      ['Buy a house', '🏠'],
      ['Build an emergency fund', '🏦'],
      ['Grow my social network', '👥'],
      ['Family dinner every sunday', '👨‍👩‍👧'],
      ['Plan a date night', '💕'],
      ['Win first place', '🏆'],
      ['Improve a little each day', '🌱'],
      ['Reach for the stars', '⭐']
    ]
    for (const [title, emoji] of cases) {
      expect(goalEmoji(title), title).toBe(emoji)
    }
  })

  it('is case-insensitive', () => {
    expect(goalEmoji('READ MORE BOOKS')).toBe('📚')
    expect(goalEmoji('Read More Books')).toBe('📚')
  })

  it('matches on substrings, not just whole words', () => {
    expect(goalEmoji('bookkeeping')).toBe('📚') // contains "book"
  })

  it('respects priority order — the higher bucket wins when two match', () => {
    // "growth" is in the users→🚀 bucket (priority 2); the later grow→🌱 bucket
    // (priority 32) also substring-matches "grow", but the earlier one wins.
    expect(goalEmoji('growth')).toBe('🚀')
    // "income" (money, priority 1) beats "improve" (grow, priority 32).
    expect(goalEmoji('improve my income')).toBe('💰')
  })

  it('falls back to the default for an unmatched title', () => {
    expect(goalEmoji('xyzzy nothing here')).toBe(DEFAULT_GOAL_EMOJI)
    expect(DEFAULT_GOAL_EMOJI).toBe('🎯')
  })
})
