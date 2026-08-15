import type { ActionItemRecord } from '../../../shared/types'
import { callAgentLLM } from './agentLLM'
import { gatherLocalContext } from './localAgent'

// Per-task "Investigate" chat (mac parity: TaskChatPanel / TaskChatCoordinator).
// One transcript per task, keyed by the task's backendId so it survives the
// local-row id churn a re-sync can cause. The LLM transport is the same
// callAgentLLM the automation planner uses (single-prompt completion with the
// 429 fallback baked in), so this stays a thin renderer feature: no new IPC, no
// main-process state, and the transcript persists in localStorage — cheap,
// per-machine, and safe to lose (an investigation is a scratchpad, not a record).

export type TaskChatRole = 'user' | 'assistant'

export type TaskChatMessage = {
  role: TaskChatRole
  content: string
  /** Epoch ms when the message was appended locally. */
  at: number
}

// Storage caps. A transcript is a working scratchpad: keep enough for real
// continuity but bound what a runaway session can pin in localStorage (which is
// origin-shared with every other renderer feature).
export const TASK_CHAT_MAX_MESSAGES = 60
const STORAGE_PREFIX = 'omi.taskChat.v1.'

// How much transcript the prompt replays. Older turns fall off the prompt before
// they fall out of storage, so the visible history outlives the model's window.
const PROMPT_HISTORY_LIMIT = 16

function storageKey(backendId: string): string {
  return `${STORAGE_PREFIX}${backendId}`
}

export function loadTaskChat(backendId: string | null): TaskChatMessage[] {
  if (!backendId) return []
  try {
    const raw = window.localStorage.getItem(storageKey(backendId))
    if (!raw) return []
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter(
      (m): m is TaskChatMessage =>
        !!m &&
        typeof m === 'object' &&
        ((m as TaskChatMessage).role === 'user' || (m as TaskChatMessage).role === 'assistant') &&
        typeof (m as TaskChatMessage).content === 'string' &&
        typeof (m as TaskChatMessage).at === 'number'
    )
  } catch {
    return []
  }
}

export function saveTaskChat(backendId: string | null, messages: TaskChatMessage[]): void {
  if (!backendId) return
  try {
    const bounded = messages.slice(-TASK_CHAT_MAX_MESSAGES)
    window.localStorage.setItem(storageKey(backendId), JSON.stringify(bounded))
  } catch {
    // Quota/serialization failures degrade to a non-persisted chat, never a crash.
  }
}

export function clearTaskChat(backendId: string | null): void {
  if (!backendId) return
  try {
    window.localStorage.removeItem(storageKey(backendId))
  } catch {
    // Ignore — absence is the goal.
  }
}

function describeDue(dueAt: number | null): string {
  if (dueAt == null) return 'no due date'
  const d = new Date(dueAt)
  if (Number.isNaN(d.getTime())) return 'no due date'
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

/** The task-scoped preamble. Everything the model needs to be useful about THIS
 *  task and nothing else: description, schedule, priority, and where the task
 *  came from (source app/window + captured context) so "investigate" has a
 *  starting point even before the user types anything specific. */
export function buildTaskChatPreamble(task: ActionItemRecord): string {
  const lines: string[] = [
    'You are Omi, helping the user investigate and complete one specific task.',
    'Be concrete and brief. Suggest actionable next steps. If the task references',
    'a person, app, or document, reason about the likely context. Never invent',
    'completed work: if something is unknown, say what to check.',
    '',
    `Task: ${task.description}`,
    `Due: ${describeDue(task.dueAt)}`
  ]
  if (task.priority) lines.push(`Priority: ${task.priority}`)
  if (task.category) lines.push(`Category: ${task.category}`)
  if (task.sourceApp) {
    lines.push(
      `Captured from: ${task.sourceApp}${task.windowTitle ? ` — ${task.windowTitle}` : ''}`
    )
  }
  if (task.contextSummary) lines.push(`Captured context: ${task.contextSummary}`)
  if (task.conversationId) lines.push(`Origin: conversation ${task.conversationId}`)
  return lines.join('\n')
}

export function buildTaskChatPrompt(
  task: ActionItemRecord,
  history: TaskChatMessage[],
  userText: string,
  localContext: string
): string {
  const parts: string[] = [buildTaskChatPreamble(task)]
  if (localContext) {
    parts.push('', 'Relevant local context:', localContext)
  }
  const replay = history.slice(-PROMPT_HISTORY_LIMIT)
  if (replay.length > 0) {
    parts.push('', 'Conversation so far:')
    for (const m of replay) {
      parts.push(`${m.role === 'user' ? 'User' : 'Omi'}: ${m.content}`)
    }
  }
  parts.push('', `User: ${userText}`, 'Omi:')
  return parts.join('\n')
}

export type SendTaskChatDeps = {
  callLLM?: (prompt: string) => Promise<string>
  gatherContext?: (userText: string) => Promise<string>
}

/** Append the user turn, ask the model, append the reply, persist, and return the
 *  new transcript. The context gather is best-effort (localAgent already returns
 *  '' on any failure); an LLM failure throws so the panel can keep the user's
 *  typed turn visible and offer retry without fabricating a reply. */
export async function sendTaskChatMessage(
  task: ActionItemRecord,
  history: TaskChatMessage[],
  userText: string,
  deps: SendTaskChatDeps = {}
): Promise<TaskChatMessage[]> {
  const callLLM = deps.callLLM ?? callAgentLLM
  const gatherContext = deps.gatherContext ?? gatherLocalContext

  const text = userText.trim()
  if (!text) return history

  const withUser: TaskChatMessage[] = [...history, { role: 'user', content: text, at: Date.now() }]
  saveTaskChat(task.backendId, withUser)

  const localContext = await gatherContext(text).catch(() => '')
  const reply = await callLLM(buildTaskChatPrompt(task, history, text, localContext))

  const withReply: TaskChatMessage[] = [
    ...withUser,
    { role: 'assistant', content: reply.trim(), at: Date.now() }
  ]
  saveTaskChat(task.backendId, withReply)
  return withReply
}
