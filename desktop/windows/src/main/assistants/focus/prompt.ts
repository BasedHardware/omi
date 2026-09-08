// The Focus assistant's prompt. Pure: every input is injected, nothing is
// fetched here — so the exact text we ship to Gemini is unit-testable without a
// DB, a session or a clock.
//
// The system prompt is Mac's `FocusAssistantSettings.defaultAnalysisPrompt`
// VERBATIM. It is product copy — the anti-hallucination rule ("logs mentioning
// YouTube are not YouTube"), the focused/distracted taxonomy, and the
// "when in doubt, lean toward distracted" tie-break are the product's opinion
// about what focus IS, not a macOS implementation detail. Reworded, Windows
// would silently judge differently from Mac.
import type { ScreenAnalysis } from './models'

/** Bump when DEFAULT_SYSTEM_PROMPT changes — a bump wipes a user's saved custom
 *  prompt (see `migrateFocusPrompt`) so a prompt fix actually reaches the people
 *  who edited theirs. Mac is at 2; we start where Mac is. */
export const CURRENT_PROMPT_VERSION = 2

export const DEFAULT_SYSTEM_PROMPT = `You are a focus coach. Analyze the PRIMARY/MAIN window in screenshots to determine if the user is focused or distracted.

IMPORTANT: Look at the MAIN APPLICATION WINDOW, not log text or terminal output. If you see a code editor with logs that mention "YouTube" - that's just log text, the user is CODING, not on YouTube. Text in logs/terminals mentioning a site does NOT mean the user is on that site.

CONTEXT-AWARE ANALYSIS:
Each request may include the user's active goals, current tasks, recent memories, time of day, and analysis history. Use this context when available, but DO NOT let it prevent you from flagging obvious distractions.

- GOALS & TASKS: If the user's screen activity clearly relates to their active goals or current tasks, they are FOCUSED.
- HISTORY: Use recent analysis history to notice patterns, acknowledge transitions, and vary your responses.

Set status to "distracted" if the PRIMARY window is:
- YouTube, Twitch, Netflix, TikTok (actual video site visible, not just text mentioning it)
- Social media feeds: Twitter/X, Instagram, Facebook, Reddit (casual browsing, not researching a specific work topic)
- News sites, entertainment sites, games
- Any content consumption with no clear work purpose

Set status to "focused" if the PRIMARY window is:
- Code editors, IDEs, terminals, command line
- Documents, spreadsheets, slides, design tools
- Email, work chat (Slack, Teams), research
- Browsing that is clearly work-related (Stack Overflow, docs, PRs, Jira, etc.)

When in doubt, lean toward "distracted" — it's better to nudge the user once too often than to silently let them drift.

Always provide a short coaching message (100 characters max for notification banner):
- If distracted: Create a unique nudge to refocus. Vary your approach — be playful, direct, or motivational.
- If focused: Acknowledge their work with variety — don't just say "Nice focus!" every time.`

/** How many past analyses ride along in the prompt (Mac's `maxHistorySize`). */
export const MAX_HISTORY = 10

/** Mac's caps, per source. */
export const MAX_GOALS = 10
export const MAX_TASKS = 50
export const MAX_MEMORIES = 50

/** The grounding data behind the context block. Fetched by context.ts; this
 *  module only formats it. */
export type FocusContextData = {
  /** The AI user profile text (assistants/aiUserProfile), or null. */
  profileText: string | null
  goals: { title: string; description?: string | null }[]
  tasks: { description: string; priority?: string | null }[]
  /** Contents of recent "core"-category memories. */
  memories: string[]
  /** Clock injected so the block is testable. */
  now: Date
}

// "Monday, July 14, 2026 at 3:07 PM" — Mac's "EEEE, MMMM d, yyyy 'at' h:mm a".
function formatTime(now: Date): string {
  const date = now.toLocaleDateString('en-US', {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
    year: 'numeric'
  })
  const time = now.toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true
  })
  return `${date} at ${time}`
}

/** The context block: who the user is, what time it is, what they are trying to
 *  do. Empty sections are omitted entirely rather than sent as a header with
 *  nothing under it (which reads to a model as "this user has no goals"). */
export function buildContextBlock(data: FocusContextData): string {
  const sections: string[] = []

  const profile = data.profileText?.trim()
  if (profile) sections.push(`USER PROFILE (who this user is):\n${profile}`)

  sections.push(`TIME CONTEXT:\n${formatTime(data.now)}`)

  const goals = data.goals.filter((g) => g.title.trim()).slice(0, MAX_GOALS)
  if (goals.length > 0) {
    const lines = ['ACTIVE GOALS:']
    goals.forEach((g, i) => {
      const desc = g.description?.trim() ? ` - ${g.description.trim()}` : ''
      lines.push(`${i + 1}. ${g.title.trim()}${desc}`)
    })
    sections.push(lines.join('\n'))
  }

  const tasks = data.tasks.filter((t) => t.description.trim()).slice(0, MAX_TASKS)
  if (tasks.length > 0) {
    const lines = ['CURRENT TASKS (by importance):']
    tasks.forEach((t, i) => {
      lines.push(`${i + 1}. [${t.priority?.trim() || 'medium'}] ${t.description.trim()}`)
    })
    sections.push(lines.join('\n'))
  }

  const memories = data.memories.filter((m) => m.trim()).slice(0, MAX_MEMORIES)
  if (memories.length > 0) {
    const lines = ['RECENT MEMORIES:']
    memories.forEach((m, i) => lines.push(`${i + 1}. ${m.trim()}`))
    sections.push(lines.join('\n'))
  }

  return sections.join('\n\n')
}

/** The history block. `history` is oldest-first (the order it is rendered in) —
 *  the caller keeps at most MAX_HISTORY. */
export function formatHistory(history: ScreenAnalysis[]): string {
  if (history.length === 0) return ''
  const lines = ['Recent activity (oldest to newest):']
  history.slice(-MAX_HISTORY).forEach((past, i) => {
    lines.push(`${i + 1}. [${past.status}] ${past.appOrSite}: ${past.description}`)
    if (past.message) lines.push(`   Message: ${past.message}`)
  })
  return lines.join('\n')
}

/** The full user-turn text that accompanies the screenshot. */
export function buildFocusPrompt(context: FocusContextData, history: ScreenAnalysis[]): string {
  const parts: string[] = []
  const contextBlock = buildContextBlock(context)
  if (contextBlock) parts.push(contextBlock)
  const historyBlock = formatHistory(history)
  if (historyBlock) parts.push(historyBlock)
  parts.push('Now analyze this new screenshot:')
  return parts.join('\n\n')
}
