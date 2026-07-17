// Desktop-chat system prompt for the kernel-routed main chat (the pi-mono
// managed-cloud door). Ported faithfully from the macOS app's desktop chat
// prompt — desktop/macos/Desktop/Sources/Chat/ChatPrompts.swift (`desktopChat`)
// — which is the proven implementation this port follows.
//
// Why this exists: the main-chat pi-mono turn (ipc/mainChat.ts) previously
// passed NO system prompt, so pi fell back to its built-in "expert coding
// assistant" prompt and the model never received Omi's persona or — the point of
// this port — the <initiative> instruction that tells it to hand long/coding
// work to a background agent via spawn_agent instead of answering in text. That
// is exactly how macOS auto-routes "build me X" asks to a coding agent.
//
// Faithfulness vs. adaptation:
//  - Persona, mentor behavior, response style, critical-accuracy rules, and the
//    <initiative> block (including its ~30-second threshold, verbatim) are ported
//    directly so the spawn threshold behaves like macOS's — no more aggressive
//    trigger. A normal question still gets a normal reply; only genuine
//    multi-step build/coding/research work self-delegates.
//  - macOS bakes its full tool catalogue + SQLite schema + SQL patterns into the
//    prompt because its runtime does not advertise tools to the model. The pi
//    runtime advertises every tool (product tools + the control-plane spawn_agent
//    via MCP) to the model directly, so that Mac-specific scaffolding is omitted
//    to avoid drift from the actually-advertised tool set; a short generic tools
//    note stands in for it. spawn_agent is referenced by name only — exactly as
//    macOS does — because the model already has the tool.
//
// Stability contract: the returned string must be byte-identical across turns of
// a session so the kernel binding is reused rather than restarting the pi
// subprocess every message (isBindingCompatible keys on the system-prompt hash).
// The builder therefore interpolates only stable inputs — no volatile datetime.

/** Inputs interpolated into the prompt. All optional and stable per session. */
export interface DesktopChatPromptOptions {
  /** The signed-in user's display/given name, when available. Falls back to a
   *  neutral "the user" so the prompt reads correctly without it. */
  userName?: string
  /** IANA timezone id (e.g. "America/New_York"), for natural time formatting.
   *  Stable per machine; omitted from the prompt when not provided. */
  timezone?: string
}

const DESKTOP_CHAT_TEMPLATE = `<assistant_role>
You are Omi, an AI assistant & mentor for {user_name}. You are a smart friend who gives honest and concise feedback and responses to {user_name}'s questions in the most personalized way possible.
</assistant_role>

<mentor_behavior>
You're a mentor, not a yes-man. When you see a critical gap between {user_name}'s plan and their goal:
- Call it out directly - don't bury it after paragraphs of summary
- Only challenge when it matters - not every message needs pushback
- Be direct - "why not just do X?" rather than "Have you considered the alternative approach of X?"
- Never summarize what they just said - jump straight to your reaction/advice
- Give one clear recommendation, not 10 options
</mentor_behavior>

<response_style>
Write like a smart friend texting — casual, specific, brief.

Bright lines:
- Default 2-8 lines; quick replies 1-3; "I don't know" answers 1-2 lines max.
- Never open by summarizing or praising what they just said — jump straight to your reaction or answer.
- No section headers in conversational replies. Reflections/planning may run longer.

One example carries the register:
- Not: "Great reflection! Based on your recorded conversations, here's a summary of what you did..."
- But: "you spent most of the day in your editor — mostly the omi fix. want the breakdown?"
</response_style>

<critical_accuracy_rules>
Everything you state about {user_name} must come from tool results or the context above — never from plausible invention.

Bright lines:
1. Look it up before saying you don't know; say "I don't know" only after a tool came back empty.
2. An empty result gets a short human answer, then stop: "I don't remember that coming up" — not "no data available", not paragraphs about why, not offers to reconstruct.
3. People are the strictest case: state nothing about a person that a tool did not return.
</critical_accuracy_rules>

<tools>
You have local tools to look things up on this machine — {user_name}'s screen history, past conversations, tasks, and saved memories — plus tools to make the local changes {user_name} asks for and to start background agents. Use them; don't answer from guesswork.
</tools>

<initiative>
You are expected to act, not just answer.
- Read-only lookups (SQL, search, recap, screen history, conversations): just run them — never ask permission to look something up.
- Local changes {user_name} asked for (create/complete/delete a task, save a memory): do them and confirm in one line.
- Work needing more than ~30 seconds of tool calls or research: start a background agent with spawn_agent and say so in one line, instead of making {user_name} wait in chat.
- Ask first only when an action leaves this machine (sending, posting, sharing, purchasing) or is destructive and wasn't explicitly requested.
- If tool results surface something that changes the answer or that {user_name} clearly needs to know, say it unprompted.
</initiative>

<instructions>
- Be casual, concise, and direct—text like a friend.
- Give specific feedback/advice; never generic.
- Always answer the question directly; no extra info, no fluff.
- Use what you know about {user_name} to personalize your responses.
- Show times/dates in {user_name}'s timezone{tz}, in a natural, friendly way.
- When searching screen history, summarize findings naturally — don't dump raw data.
</instructions>`

/**
 * Build the Omi desktop-chat system prompt for a main-chat pi-mono turn.
 *
 * Pure and deterministic: identical options yield a byte-identical string (the
 * stability contract above). Pass only stable inputs.
 */
export function buildDesktopChatSystemPrompt(options: DesktopChatPromptOptions = {}): string {
  const name = options.userName?.trim() || 'the user'
  const tz = options.timezone?.trim()
  // "{tz}" carries the surrounding " (...)" so the parenthetical vanishes cleanly
  // when no timezone is supplied, leaving "...in the user's timezone, in a...".
  const tzClause = tz ? ` (${tz})` : ''
  return DESKTOP_CHAT_TEMPLATE.replaceAll('{user_name}', name).replaceAll('{tz}', tzClause)
}

// ---------------------------------------------------------------------------
// Per-turn personalization (Mac's <user_context> block).
//
// Mac front-loads the user's facts/goals/tasks/AI-profile into the SYSTEM prompt
// (`buildDesktopChat` → memories_section/goal_section/tasks_section/
// ai_profile_section). On Windows this data is VOLATILE within a session — the
// memory/task assistants extract continuously, and the AI profile regenerates —
// so baking it into the system prompt would change the prompt hash turn-to-turn
// and force a pi-subprocess restart every message (isBindingCompatible keys on
// that hash; see the stability contract above). That is a real regression.
//
// So we keep the system prompt as the STABLE persona and deliver the same
// personalization as PER-TURN context, prepended to the user prompt alongside
// the <conversation_history> tail (mainChat.ts). This mirrors both the existing
// tail-injection pattern AND Mac's own floating-bar design, which splits the
// static persona from a live tail carrying exactly this volatile context
// (ChatProvider.buildFloatingBarSystemPrompt, cacheSplitSentinel). The model
// receives the same facts Mac gives it; only the transport differs.
//
// Wording is a faithful port of Mac's formatters (ChatProvider.swift):
//  - <user_facts>       ← formatMemoriesSection   ("Facts about <name>:", "- [memory] …")
//  - <user_tasks>       ← formatTasksSection      ("Current tasks:", "- <desc> [priority: …] …")
//  - <ai_user_profile>  ← formatAIProfileSection  (raw profile text)
// Goals (Mac's formatGoalSection) are intentionally omitted: on Windows goals are
// backend-only and read over async HTTP (assistants/goals/context.ts), and a
// per-turn network fetch on every typed reply would add latency and a failure
// surface to the hot path. Documented as a known gap, not an oversight.

/** One active task rendered into the <user_tasks> block. Shape is the subset of
 *  ActionItemRecord this section reads. */
export interface DesktopChatPersonalizationTask {
  description: string
  priority?: string | null
  /** Due date as epoch milliseconds, or null/undefined when none. */
  dueAt?: number | null
  category?: string | null
}

/** Already-read personalization inputs for the <user_context> block. All optional
 *  — each absent/empty source simply drops its section, and an entirely empty
 *  input yields '' (no wrapper). The caller (mainChatPersonalization.ts) does the
 *  impure reads and fails each source open. */
export interface DesktopChatPersonalization {
  /** The signed-in user's given name; falls back to "the user" in the header. */
  userName?: string
  /** IANA timezone id (e.g. "America/New_York") for rendering task due dates in
   *  the user's local wall-clock — same tz the system prompt is told to display
   *  times in. Omitted → due dates render as UTC with an explicit marker. */
  timezone?: string
  /** Memory contents, newest-first; capped to Mac's 30. */
  memories?: string[]
  /** Active (incomplete) tasks; capped to Mac's 20. */
  tasks?: DesktopChatPersonalizationTask[]
  /** The latest AI-generated user-profile text. */
  aiProfileText?: string
}

/** Mac caps: formatMemoriesSection prefix(30), tasks loaded with limit 20. */
const MEMORIES_CAP = 30
const TASKS_CAP = 20

/** Render a due date as "YYYY-MM-DD HH:mm" in the USER'S timezone (Mac renders
 *  task.dueAt with a local-zone DateFormatter). The prompt tells the model to
 *  show times in the user's tz, so feeding it the local wall-clock keeps them
 *  consistent — an unlabeled UTC time would be read as-if-local and be off by the
 *  user's offset. Deterministic for a fixed (epoch, tz). When no tz is known (or
 *  it is invalid), fall back to UTC WITH an explicit marker so the model never
 *  mistakes it for local time, and the pure builder stays test-deterministic
 *  (never the runtime-local zone). */
function formatDueAt(dueAt: number, timezone?: string): string {
  if (timezone) {
    try {
      const parts = new Intl.DateTimeFormat('en-US', {
        timeZone: timezone,
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        hourCycle: 'h23'
      }).formatToParts(new Date(dueAt))
      const at = (type: Intl.DateTimeFormatPartTypes): string =>
        parts.find((p) => p.type === type)?.value ?? ''
      return `${at('year')}-${at('month')}-${at('day')} ${at('hour')}:${at('minute')}`
    } catch {
      // Invalid timezone id → fall through to the marked-UTC path below.
    }
  }
  return `${new Date(dueAt).toISOString().slice(0, 16).replace('T', ' ')} UTC`
}

/**
 * Build the per-turn `<user_context>` personalization block, or '' when there is
 * nothing to say. Pure and deterministic — identical inputs yield an identical
 * string — so it is fully unit-testable with no DB or network.
 */
export function buildDesktopChatPersonalization(p: DesktopChatPersonalization = {}): string {
  const name = p.userName?.trim() || 'the user'
  const sections: string[] = []

  const memories = (p.memories ?? [])
    .map((m) => m.trim())
    .filter((m) => m.length > 0)
    .slice(0, MEMORIES_CAP)
  if (memories.length > 0) {
    sections.push(
      [
        '<user_facts>',
        `Facts about ${name}:`,
        ...memories.map((m) => `- [memory] ${m}`),
        '</user_facts>'
      ].join('\n')
    )
  }

  const tasks = (p.tasks ?? []).filter((t) => t.description.trim().length > 0).slice(0, TASKS_CAP)
  if (tasks.length > 0) {
    const lines = tasks.map((t) => {
      let line = `- ${t.description.trim()}`
      if (t.priority && t.priority.trim()) line += ` [priority: ${t.priority.trim()}]`
      if (typeof t.dueAt === 'number' && Number.isFinite(t.dueAt)) {
        line += ` [due: ${formatDueAt(t.dueAt, p.timezone)}]`
      }
      if (t.category && t.category.trim()) line += ` [category: ${t.category.trim()}]`
      return line
    })
    sections.push(['<user_tasks>', 'Current tasks:', ...lines, '</user_tasks>'].join('\n'))
  }

  const profile = p.aiProfileText?.trim()
  if (profile) {
    sections.push(`<ai_user_profile>\n${profile}\n</ai_user_profile>`)
  }

  if (sections.length === 0) return ''
  return `<user_context>\n${sections.join('\n\n')}\n</user_context>`
}
