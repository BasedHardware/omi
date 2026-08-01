export type RewindSearchScope = {
  query: string
  from: number | null
  to: number | null
}

const TIME_PHRASES: Array<{ pattern: RegExp; range: (now: Date) => [Date, Date] }> = [
  {
    pattern: /\byesterday morning\b/i,
    range: (now) => {
      const from = new Date(now)
      from.setDate(from.getDate() - 1)
      from.setHours(6, 0, 0, 0)
      const to = new Date(from)
      to.setHours(11, 59, 59, 999)
      return [from, to]
    }
  },
  {
    pattern: /\byesterday afternoon\b/i,
    range: (now) => {
      const from = new Date(now)
      from.setDate(from.getDate() - 1)
      from.setHours(12, 0, 0, 0)
      const to = new Date(from)
      to.setHours(17, 59, 59, 999)
      return [from, to]
    }
  },
  {
    pattern: /\byesterday evening\b/i,
    range: (now) => {
      const from = new Date(now)
      from.setDate(from.getDate() - 1)
      from.setHours(18, 0, 0, 0)
      const to = new Date(from)
      to.setHours(23, 59, 59, 999)
      return [from, to]
    }
  },
  {
    pattern: /\byesterday\b/i,
    range: (now) => {
      const from = new Date(now)
      from.setDate(from.getDate() - 1)
      from.setHours(0, 0, 0, 0)
      const to = new Date(from)
      to.setHours(23, 59, 59, 999)
      return [from, to]
    }
  },
  {
    pattern: /\bthis morning\b/i,
    range: (now) => {
      const from = new Date(now)
      from.setHours(6, 0, 0, 0)
      const to = new Date(now)
      to.setHours(11, 59, 59, 999)
      return now < from ? [from, from] : [from, now < to ? now : to]
    }
  },
  {
    pattern: /\bthis afternoon\b/i,
    range: (now) => {
      const from = new Date(now)
      from.setHours(12, 0, 0, 0)
      const to = new Date(now)
      to.setHours(17, 59, 59, 999)
      return now < from ? [from, from] : [from, now < to ? now : to]
    }
  },
  {
    pattern: /\bthis evening\b/i,
    range: (now) => {
      const from = new Date(now)
      from.setHours(18, 0, 0, 0)
      return now < from ? [from, from] : [from, now]
    }
  },
  {
    pattern: /\btoday\b/i,
    range: (now) => {
      const from = new Date(now)
      from.setHours(0, 0, 0, 0)
      return [from, now]
    }
  }
]

const QUESTION_WORDS =
  /\b(?:what(?:'s|’s)?|was|were|did|do|happened|happens|happen|i|my|on|the|screen|show|me|find|for)\b/gi
const TIME_WORDS =
  /\b(?:yesterday\s+(?:morning|afternoon|evening)|yesterday|today|this\s+(?:morning|afternoon|evening))\b/gi

export function parseRewindNaturalSearch(input: string, now = new Date()): RewindSearchScope {
  let query = input.trim()
  for (const { pattern, range } of TIME_PHRASES) {
    if (!pattern.test(query)) continue
    const [from, to] = range(now)
    query = query
      .replace(TIME_WORDS, ' ')
      .replace(QUESTION_WORDS, ' ')
      .replace(/[?'’.,:;!]/g, ' ')
      .replace(/\s+/g, ' ')
      .trim()
    return { query, from: from.getTime(), to: to.getTime() }
  }
  return { query, from: null, to: null }
}
