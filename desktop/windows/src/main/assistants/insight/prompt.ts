// The Insight assistant's prompt. Pure: every input is injected, nothing is
// fetched here, so the exact text we ship to Gemini is unit-testable.
//
// DEFAULT_ANALYSIS_PROMPT is Mac's `InsightAssistantSettings.defaultAnalysisPrompt`
// VERBATIM — it is product copy (the "impress the user" bar, the GOOD/BAD example
// gallery, the confidence rubric). The ONE re-grounding: the WORKFLOW's example
// SQL names Windows' `rewind_frames`/`ocr_text`/`app`/`ts`, not Mac's
// `screenshots`/`ocrText`/`appName`/`timestamp` — a verbatim example that named a
// non-existent table would send the model querying nothing.
import { REWIND_SCHEMA_DESC } from './models'

/** Bump wipes a user's saved custom prompt (see promptStore.migrate) so a prompt
 *  fix reaches people who edited theirs. Mac is at 2; we start where Mac is. */
export const CURRENT_PROMPT_VERSION = 2

export const DEFAULT_ANALYSIS_PROMPT = `You analyze screenshots to find ONE specific, high-value insight the user would NOT figure out on their own. The goal is to IMPRESS the user — make them think "wow, I'm glad I have this."

WORKFLOW:
1. Review the ACTIVITY SUMMARY to understand what the user has been doing
2. Use execute_sql to investigate OCR text from interesting apps/windows
   Example: SELECT id, ocr_text FROM rewind_frames WHERE app = 'Terminal' AND ts >= ... ORDER BY ts DESC LIMIT 5
3. When you find something interesting, call request_screenshot with the frame ID and a summary of your findings
   (You'll then see the actual screenshot to confirm your hypothesis before giving advice)
4. If nothing interesting turns up after investigating, call no_advice

CORE QUESTION: Is the user about to make a mistake, or is there a non-obvious shortcut/tool that would significantly help with EXACTLY what they're doing right now?

Call provide_advice ONLY when you can answer YES to BOTH:
1. The advice is SPECIFIC to what's on screen (not generic wisdom)
2. The user likely does NOT already know this (non-obvious)

Call no_advice when:
- You'd be stating something obvious (user can see it themselves)
- The advice is generic and not tied to what's on screen
- The advice duplicates something in PREVIOUSLY PROVIDED ADVICE (use semantic comparison)
- You're reaching — if you have to stretch to find advice, there isn't any

WHAT QUALIFIES (high bar):
- User is doing something the SLOW way and there's a specific shortcut (name the shortcut)
- User is about to make a visible mistake (wrong recipient, sensitive info in wrong place)
- There's a specific, lesser-known tool/feature that directly solves what they're struggling with
- A concrete error or misconfiguration visible on screen they may not have noticed

GOOD EXAMPLES (this is the quality bar):
- "You've scheduled this for 2026 — double-check the year"
- "Sensitive credentials visible in terminal — mask before sharing"
- "You stashed changes 2 hours ago — remember to git stash pop"
- "npm tokens expiring tomorrow — renew via npm token create"
- "This regex misses Unicode — use \\p{L} instead of [a-zA-Z]"
- "Replying to group thread, not DM — check the recipient"

BAD EXAMPLES (never produce these):
- "Set your first goal to get started" (pointing at UI the user can see)
- "Click Allow to grant permission" (narrating what's on screen)
- "Press Cmd+Enter to send the message" (basic shortcut everyone knows)
- "Having 48 tasks is overwhelming — try prioritizing" (unsolicited judgment)
- "Consider adding tests" (vague, generic dev suggestion)
- "Take a break / Stay hydrated" (we're not a health app)

WHAT DOES NOT QUALIFY:
- Generic wellness/hygiene advice ("Take a break", "Stay hydrated", "Remember to commit")
- Vague dev suggestions ("Consider adding tests", "This could be refactored")
- Basic keyboard shortcuts everyone knows ("Cmd+C to copy", "Cmd+Enter to send")
- Anything a reasonable person would already know or figure out in seconds
- Anything about the user's posture, health, or breaks (we're not a health app)
- Never point at UI elements the user can already see (buttons, dialogs, permission prompts)

CATEGORIES: "productivity", "communication", "learning", "other"

CONFIDENCE (only relevant when calling provide_advice):
- 0.90-1.0: Preventing a clear mistake or revealing a critical shortcut
- 0.75-0.89: Highly relevant non-obvious tool/feature for current task
- 0.60-0.74: Useful but user might already know

FORMAT: Keep advice under 100 characters. Start with the actionable part.`

/** The schema block Mac appends to the system prompt at call time
 *  (InsightAssistant.swift:568), re-grounded to rewind_frames. */
export const DB_SCHEMA_BLOCK = `DATABASE SCHEMA for execute_sql:\n${REWIND_SCHEMA_DESC}`

/** The final system prompt: the (stored or default) analysis prompt, plus the DB
 *  schema block, plus — only when the user's language is a non-English override —
 *  Mac's language directive. Mirrors InsightAssistant.swift:564-568. */
export function buildSystemPrompt(analysisPrompt: string, language: string | null): string {
  let out = analysisPrompt
  if (language && language !== 'en') {
    out += `\n\nIMPORTANT: Respond in the user's preferred language: ${language}`
  }
  out += `\n\n${DB_SCHEMA_BLOCK}`
  return out
}

/** How many previous insights ride along for dedupe (Mac's maxInsightsInPrompt). */
export const MAX_INSIGHTS_IN_PROMPT = 30

/** One aggregate row of the activity summary. */
export type ActivityRow = {
  app: string
  windowTitle: string
  count: number
  firstSeen: number
  lastSeen: number
}

/** The grounding data the Phase-1 seed prompt formats. Fetched by context.ts. */
export type InsightContextData = {
  /** Current foreground frame's app + window title. */
  currentApp: string
  currentWindowTitle: string | null
  now: Date
  /** AI user profile text, or null. */
  profileText: string | null
  activity: ActivityRow[]
  /** Elapsed minutes the activity summary spans (for the header line). */
  activitySpanMinutes: number
  /** Previous insight advice texts (newest first), for the dedupe block. */
  previousInsights: string[]
}

// "3:07 PM, Monday" — Mac's "h:mm a, EEEE".
function formatTime(now: Date): string {
  const time = now.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true })
  const day = now.toLocaleDateString('en-US', { weekday: 'long' })
  return `${time}, ${day}`
}

/** Mac's activity table (buildActivitySummary): App | Window | Screenshots | Est.
 *  Duration, duration estimated as count/60 minutes. Empty → '' (block omitted). */
export function formatActivitySummary(rows: ActivityRow[], spanMinutes: number): string {
  if (rows.length === 0) return ''
  const total = rows.reduce((s, r) => s + r.count, 0)
  const lines = [
    `ACTIVITY SUMMARY (last ${Math.round(spanMinutes)} min, ${total} screenshots):`,
    'App | Window | Screenshots | Est. Duration'
  ]
  for (const r of rows) {
    const mins = (r.count / 60).toFixed(1)
    lines.push(`${r.app} | ${r.windowTitle} | ${r.count} | ${mins} min`)
  }
  return lines.join('\n')
}

/** Mac's previous-insights dedupe block (numbered list), or the simpler line
 *  when there are none yet. */
export function formatPreviousInsights(previous: string[]): string {
  const list = previous.filter((s) => s.trim()).slice(0, MAX_INSIGHTS_IN_PROMPT)
  if (list.length === 0) {
    return "Only provide insight if there's something specific and non-obvious that would help."
  }
  const lines = ['PREVIOUSLY PROVIDED INSIGHTS (do NOT repeat — use semantic comparison):']
  list.forEach((s, i) => lines.push(`${i + 1}. ${s.trim()}`))
  lines.push(
    "Only provide insight if there's a genuinely NEW non-obvious insight not covered above."
  )
  return lines.join('\n')
}

/** The Phase-1 seed (user-turn) prompt. Mac's runAdviceExtraction assembly. */
export function buildPhase1Prompt(data: InsightContextData): string {
  const parts: string[] = []

  let head = `CURRENT APP: ${data.currentApp}.`
  if (data.currentWindowTitle) head += ` Window: "${data.currentWindowTitle}".`
  head += ` Time: ${formatTime(data.now)}.`
  parts.push(head)

  const activity = formatActivitySummary(data.activity, data.activitySpanMinutes)
  if (activity) parts.push(activity)

  const profile = data.profileText?.trim()
  if (profile) parts.push(`USER PROFILE (who this user is):\n${profile}`)

  parts.push(formatPreviousInsights(data.previousInsights))

  parts.push(
    "Investigate the activity summary. Scan OCR from the TOP 3-5 apps (not just the dominant one) — the best insights often come from browsers, communication apps, and notes, not just the app with the most screenshots. Skip apps with < 10 screenshots. When you've identified the most interesting screenshot, call request_screenshot with the ID and your findings. Or call no_advice if nothing qualifies."
  )

  return parts.join('\n\n')
}

/** The Phase-2 seed prompt (accompanies the screenshot image). Carries the
 *  Phase-1 findings forward. */
export function buildPhase2Prompt(findings: string): string {
  return [
    "You requested this screenshot after investigating the user's recent activity.",
    `INVESTIGATION FINDINGS:\n${findings}`,
    'Now look at the attached screenshot to confirm your hypothesis. Cross-reference with execute_sql if it helps verify the issue is still relevant. Then call provide_advice with ONE specific, non-obvious insight, or no_advice if nothing qualifies (including if cross-referencing shows the issue was already resolved).'
  ].join('\n\n')
}
