// Local "agent" layer for the RN Omi app.
//
// Goal: a user can type/say "add a task: pay the electric bill" (or a reminder)
// and Omi turns it into a concrete action WITHOUT a round-trip to the cloud —
// i.e. an on-device agent. The on-device *model* (a ~1B function-calling LLM via
// MediaPipe Tasks GenAI or a LiteRT-LM native bridge) is the pluggable piece:
// implement `LocalModel.complete()` and pass it to `runAgent`; until one is
// wired, `interpretCommand()` is a deterministic keyword heuristic so the
// text→task flow already works end to end. The heuristic is deliberately simple
// and pure so it is unit-testable and never blocks the chat fallback.

export type AgentAction =
  | { kind: 'create_task'; title: string }
  | { kind: 'create_reminder'; title: string; minutesFromNow?: number }
  | { kind: 'chat'; text: string } // not a command -> hand to Omi (cloud/LLM)

export interface LocalModel {
  // Return a strict JSON string the caller parses; implementations run on-device.
  complete: (system: string, user: string) => Promise<string>
}

const TASK_VERBS = /(add|create|make|write|new|note|jot)\s+(a\s+)?(task|todo|to-do|reminder|note)\s*[:\-]?\s*/i
const REMIND = /(^|\s)(remind me to|remind me|set a reminder to|reminder to)\s+/i

function minutesFrom(text: string): number | undefined {
  const m = text.match(/in\s+(\d+)\s*(min|mins|minute|minutes|h|hr|hour|hours)/i)
  const n = m ? Number.parseInt(m[1] ?? '', 10) : NaN
  if (!m || Number.isNaN(n)) return undefined
  return /h/i.test(m[2] ?? '') ? n * 60 : n
}

/** Pure, deterministic command interpretation. No model, no I/O. */
export function interpretCommand(text: string): AgentAction {
  const t = text.trim()
  if (!t) return { kind: 'chat', text: t }

  const remind = t.match(REMIND)
  if (remind) {
    const idx = (remind.index ?? 0) + remind[0].length
    let title = t.slice(idx)
    const when = minutesFrom(t)
    // Drop the "in N minutes/hours" clause from the title; it's captured as `when`.
    if (when !== undefined) {
      title = title.replace(/\bin\s+\d+\s*(min|mins|minute|minutes|h|hr|hour|hours)\b.*$/i, '')
    }
    title = title.replace(/[.,]+$/, '').trim()
    if (title) return { kind: 'create_reminder', title, minutesFromNow: when }
  }

  const task = t.match(TASK_VERBS)
  if (task) {
    const title = t.slice((task.index ?? 0) + task[0].length).replace(/\.$/, '').trim()
    if (title) return { kind: 'create_task', title }
  }

  return { kind: 'chat', text: t }
}

/**
 * Resolve a command to an action. With a `model`, ask it (on-device 1B LLM) for a
 * structured decision and fall back to the heuristic if it can't parse; without a
 * model, use the heuristic. Never throws — a model failure degrades to 'chat'.
 */
export async function runAgent(text: string, model?: LocalModel): Promise<AgentAction> {
  if (model) {
    try {
      const raw = await model.complete(
        'Return ONLY JSON {"kind":"create_task|create_reminder|chat","title":string}. ' +
          'Use create_task/create_reminder only when the user is asking to save a task/reminder; otherwise chat.',
        text
      )
      const json = raw.match(/\{[\s\S]*\}/)?.[0]
      if (json) {
        const d = JSON.parse(json) as { kind?: string; title?: string }
        const title = (d.title || '').trim()
        if (title && (d.kind === 'create_task' || d.kind === 'create_reminder')) {
          return d.kind === 'create_task'
            ? { kind: 'create_task', title }
            : { kind: 'create_reminder', title, minutesFromNow: minutesFrom(text) }
        }
      }
    } catch {
      /* model unavailable -> heuristic */
    }
  }
  return interpretCommand(text)
}
