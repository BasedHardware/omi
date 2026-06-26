import { webContents } from 'electron'
import { apiRequest } from '../apiProxy'
import { getAuthState } from '../auth'
import { settings } from '../settings'
import { recentOcrText } from '../rewind/store'
import { addInsight, unreadCount } from './store'
import { getFloatingBar } from '../windows'
import type { ProactiveStatus } from '../../shared/types'

// Windows counterpart of the macOS ProactiveAssistants subsystem (Memory + Task +
// Insight). On an interval it reads recent screen OCR text and asks the LLM to
// extract durable memories, actionable tasks, and at most one proactive insight.
// Memories/tasks persist to the same backend the Mac app uses (/v3/memories,
// /v1/action-items); insights are stored locally and surfaced as floating-bar
// notifications. Reuses the screen-capture + OCR pipeline already feeding Rewind.

const EXTRACTION_MODEL = 'claude-haiku-4-5-20251001'

interface Extraction {
  app?: string
  memories?: { content: string }[]
  tasks?: { description: string }[]
  insight?: { title: string; body: string; category?: string } | null
}

let timer: NodeJS.Timeout | null = null
let running = false
let stopped = false
let lastRunTs: number | null = null
let lastError: string | null = null

// Bound each backend call so a hung request cannot wedge the engine. runOnce holds
// the `running` flag across its awaits; a never-settling fetch would otherwise leave
// running=true forever and block all future cycles.
const REQUEST_TIMEOUT_MS = 30000

function withTimeout<T>(p: Promise<T>, ms: number): Promise<T> {
  let t: NodeJS.Timeout
  const timeout = new Promise<never>((_, reject) => {
    t = setTimeout(() => reject(new Error('request timed out')), ms)
  })
  return Promise.race([p.finally(() => clearTimeout(t)), timeout])
}

function broadcastStatus(): void {
  const s = settings.get()
  const status: ProactiveStatus = {
    enabled: s.proactiveEnabled,
    running,
    lastRunTs,
    lastError,
    unread: unreadCount()
  }
  for (const wc of webContents.getAllWebContents()) {
    if (!wc.isDestroyed()) wc.send('proactive:status', status)
  }
}

const SYSTEM_PROMPT =
  'You are Omi\'s background analyst. You receive raw OCR text captured from the user\'s screen over the ' +
  'last few minutes. Extract only high-signal, durable items. Respond with STRICT JSON only, no prose, ' +
  'matching: {"app": string, "memories": [{"content": string}], "tasks": [{"description": string}], ' +
  '"insight": {"title": string, "body": string, "category": "focus"|"insight"|"reminder"} | null}. ' +
  'Rules: memories are lasting facts about the user (preferences, projects, people, goals), NOT transient' +
  'screen contents; at most 3. tasks are concrete actionable to-dos the user clearly needs to do; at most 3; ' +
  'omit vague ones. insight is at most one genuinely useful, specific nudge about what they could do next, or ' +
  'null. If nothing is high-signal, return empty arrays and null insight. Never invent details not supported ' +
  'by the text.'

function buildFingerprint(title: string): string {
  return title.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim().slice(0, 80)
}

async function persistMemory(content: string): Promise<void> {
  await withTimeout(
    apiRequest({
      method: 'POST',
      url: 'v3/memories',
      base: 'python',
      body: JSON.stringify({ content, visibility: 'private', source: 'desktop', category: 'interesting' })
    }),
    REQUEST_TIMEOUT_MS
  )
}

async function persistTask(description: string): Promise<void> {
  await withTimeout(
    apiRequest({
      method: 'POST',
      url: 'v1/action-items',
      base: 'python',
      body: JSON.stringify({ description, source: 'proactive' })
    }),
    REQUEST_TIMEOUT_MS
  )
}

function parseExtraction(body: string): Extraction | null {
  // The model is asked for strict JSON, but tolerate code fences / surrounding text.
  let text = body.trim()
  const fence = text.match(/```(?:json)?\s*([\s\S]*?)```/)
  if (fence) text = fence[1].trim()
  const start = text.indexOf('{')
  const end = text.lastIndexOf('}')
  if (start === -1 || end === -1 || end < start) return null
  try {
    return JSON.parse(text.slice(start, end + 1)) as Extraction
  } catch {
    return null
  }
}

async function runOnce(): Promise<void> {
  if (running) return
  if (!settings.get().proactiveEnabled) return
  if (!getAuthState().signedIn) return

  const windowMs = Math.max(120000, settings.get().proactiveIntervalMs * 2)
  const screenText = recentOcrText(windowMs)
  if (!screenText || screenText.length < 80) return // not enough to analyze

  running = true
  broadcastStatus()
  try {
    const res = await withTimeout(
      apiRequest({
        method: 'POST',
        url: 'v2/chat/completions',
        base: 'rust',
        body: JSON.stringify({
          model: EXTRACTION_MODEL,
          stream: false,
          max_tokens: 1024,
          messages: [
            { role: 'system', content: SYSTEM_PROMPT },
            { role: 'user', content: `Screen text (most recent first):\n\n${screenText}` }
          ]
        })
      }),
      REQUEST_TIMEOUT_MS
    )
    if (res.status < 200 || res.status >= 300) {
      lastError = `extraction HTTP ${res.status}`
      return
    }
    const content = JSON.parse(res.body)?.choices?.[0]?.message?.content
    const extraction = typeof content === 'string' ? parseExtraction(content) : null
    if (!extraction) {
      lastError = 'could not parse extraction'
      return
    }
    lastError = null

    for (const m of (extraction.memories ?? []).slice(0, 3)) {
      if (m?.content?.trim()) await persistMemory(m.content.trim()).catch(() => {})
    }
    for (const t of (extraction.tasks ?? []).slice(0, 3)) {
      if (t?.description?.trim()) await persistTask(t.description.trim()).catch(() => {})
    }

    const insight = extraction.insight
    if (insight?.title?.trim() && insight?.body?.trim()) {
      const stored = addInsight({
        ts: Date.now(),
        title: insight.title.trim(),
        body: insight.body.trim(),
        category: insight.category || 'insight',
        sourceApp: extraction.app ?? null,
        fingerprint: buildFingerprint(insight.title)
      })
      if (stored && settings.get().proactiveNotifications) {
        getFloatingBar()?.webContents.send('proactive:notification', {
          id: stored.id,
          title: stored.title,
          body: stored.body,
          category: stored.category
        })
      }
    }
  } catch (e) {
    lastError = String(e)
  } finally {
    lastRunTs = Date.now()
    running = false
    broadcastStatus()
  }
}

function schedule(): void {
  if (timer) clearTimeout(timer)
  if (stopped) return
  if (!settings.get().proactiveEnabled) {
    broadcastStatus()
    return
  }
  const interval = Math.max(60000, settings.get().proactiveIntervalMs)
  timer = setTimeout(async () => {
    await runOnce()
    schedule()
  }, interval)
}

// Stop the engine on app quit: clear the timer so no analysis cycle fires during
// shutdown. Idempotent.
export function stopProactiveEngine(): void {
  stopped = true
  if (timer) {
    clearTimeout(timer)
    timer = null
  }
}

export function startProactiveEngine(): void {
  settings.on('changed', (next, prev) => {
    if (next.proactiveEnabled !== prev.proactiveEnabled || next.proactiveIntervalMs !== prev.proactiveIntervalMs) {
      schedule()
    }
  })
  schedule()
}

export function getProactiveStatus(): ProactiveStatus {
  const s = settings.get()
  return { enabled: s.proactiveEnabled, running, lastRunTs, lastError, unread: unreadCount() }
}

/** Run an analysis immediately (Settings "Run now" / first-enable kick). */
export async function runProactiveNow(): Promise<void> {
  await runOnce()
}
