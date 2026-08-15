import type { ActionItemRecord } from '../../../shared/types'
import { normalizePriority, PRIORITY_LABEL } from './taskFields'

// Pure policy behind the task detail panel (mac parity: TaskDetailPanelPolicy /
// TaskDetailSourceLinkPolicy). The component renders; this decides what exists —
// so the rules stay testable without a DOM.

/** Mac's exact "Why Omi added this" copy (TaskDetailPanelPolicy.whyOmiAddedThis),
 *  with the platform word swapped for the screen-sourced line. */
export function whyOmiAddedThis(source: string | null): string {
  const s = (source ?? '').toLowerCase()
  if (!s || s === 'manual') return 'You added this task directly.'
  if (s.includes('screen') || s === 'screenshot') return 'It matched context on this PC.'
  if (s.includes('transcription') || s.includes('conversation')) {
    return 'It came from a conversation you captured.'
  }
  return 'It came from an authorized Omi source.'
}

export type TaskSourceLink =
  | { kind: 'conversation'; id: string; title: string; subtitle: string }
  | { kind: 'rewind'; title: string; subtitle: string }

/** Navigable origins for this task. Windows rows carry no provenance array, so
 *  this is mac's fallback rule generalized: the conversation id when one exists,
 *  and a Rewind entry when the task was captured from a screenshot frame (no
 *  frame deep-link — Rewind has no such contract, same as mac). Deduped. */
export function sourceLinks(task: ActionItemRecord): TaskSourceLink[] {
  const links: TaskSourceLink[] = []
  const conversationId = (task.conversationId ?? '').trim()
  if (conversationId) {
    links.push({
      kind: 'conversation',
      id: conversationId,
      title: 'Conversation',
      subtitle: 'Open conversation'
    })
  }
  if (task.screenshotId != null) {
    links.push({ kind: 'rewind', title: 'Screen context', subtitle: 'Open Rewind' })
  }
  return links
}

export type TaskDetailField = { label: string; value: string }

function formatStamp(ms: number | null | undefined): string | null {
  if (ms == null) return null
  const d = new Date(ms)
  if (Number.isNaN(d.getTime())) return null
  return d.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit'
  })
}

function capitalize(v: string): string {
  return v.length === 0 ? v : v[0].toUpperCase() + v.slice(1)
}

/** Read-only field table, in mac's Details order (fields absent from the row are
 *  simply omitted — no empty rows). */
export function detailFields(task: ActionItemRecord): TaskDetailField[] {
  const fields: TaskDetailField[] = []
  fields.push({ label: 'Status', value: task.completed ? 'Completed' : 'Active' })
  const priority = normalizePriority(task.priority)
  if (priority) fields.push({ label: 'Priority', value: PRIORITY_LABEL[priority] })
  if (task.category) fields.push({ label: 'Category', value: capitalize(task.category) })
  if (task.tags.length > 0) fields.push({ label: 'Tags', value: task.tags.join(', ') })
  if (task.source) fields.push({ label: 'Source', value: task.source })
  if (task.sourceApp) fields.push({ label: 'Source app', value: task.sourceApp })
  if (task.windowTitle) fields.push({ label: 'Window', value: task.windowTitle })
  const created = formatStamp(task.createdAt)
  if (created) fields.push({ label: 'Created', value: created })
  const due = formatStamp(task.dueAt)
  if (due) fields.push({ label: 'Due', value: due })
  if (task.confidence != null) {
    fields.push({ label: 'Confidence', value: `${Math.round(task.confidence * 100)}%` })
  }
  return fields
}

export type TaskDetailAction = 'toggleCompletion' | 'edit' | 'investigate' | 'delete'

/** Mac's availableActions, minus the mac-only surface (execute, indent, share):
 *  toggle/edit/delete always; investigate rides the chat feature flag. Priority
 *  editing is a section, not an action — editable only while the task is active
 *  (mac hides the whole section for completed tasks). */
export function availableActions(
  task: ActionItemRecord,
  opts: { hasChat: boolean }
): TaskDetailAction[] {
  const actions: TaskDetailAction[] = ['toggleCompletion', 'edit']
  if (opts.hasChat) actions.push('investigate')
  actions.push('delete')
  return actions
}

export function isPriorityEditable(task: ActionItemRecord): boolean {
  return !task.completed
}

/** Context blocks (mac's Context section): captured summary and activity. */
export function contextBlocks(task: ActionItemRecord): { label: string; text: string }[] {
  const blocks: { label: string; text: string }[] = []
  if (task.contextSummary) blocks.push({ label: 'Summary', text: task.contextSummary })
  if (task.currentActivity) blocks.push({ label: 'Activity', text: task.currentActivity })
  return blocks
}
