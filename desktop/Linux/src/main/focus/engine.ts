import { webContents } from 'electron'
import { apiRequest } from '../apiProxy'
import { getAuthState } from '../auth'
import { settings } from '../settings'
import { latestOcrText } from '../rewind/store'
import { addSession, listSessions, todaySummary } from './store'
import { flashGlow } from './glow'
import type { FocusStatus } from '../../shared/types'

// Focus assistant, ported from ProactiveAssistants/Assistants/Focus. On an
// interval it reads recent screen text and classifies focused vs distracted,
// stores a session, and flashes the screen-edge glow on a focus<->distraction
// transition (green on refocus, red on distraction, then a cooldown).

const MODEL = 'claude-haiku-4-5-20251001'

const PROMPT =
  'You classify whether the user is FOCUSED on productive work or DISTRACTED, from OCR text of their screen. ' +
  'Distracted: YouTube, Twitch, Netflix, TikTok, Twitter/X, Instagram, Facebook, Reddit, news sites, games. ' +
  'Focused: code editors/IDEs, terminals, documents, spreadsheets, email, Slack, work research. Judge the ' +
  'PRIMARY visible content, not text that merely mentions a site (e.g. a terminal log). Lean distracted when ' +
  'genuinely unsure. Respond with STRICT JSON only: ' +
  '{"status":"focused"|"distracted","app_or_site":string,"description":string,"message":string}. ' +
  'message is <=100 chars of gentle coaching if distracted, else empty.'

let timer: NodeJS.Timeout | null = null
let monitoring = false
let stopped = false
let lastStatus: 'focused' | 'distracted' | null = null
let lastApp: string | null = null
let lastError: string | null = null
let cooldownUntil = 0

function broadcast(): void {
  const s = settings.get()
  const status: FocusStatus = {
    enabled: s.focusEnabled,
    monitoring,
    current: lastStatus,
    currentApp: lastApp,
    lastError
  }
  for (const wc of webContents.getAllWebContents()) {
    if (!wc.isDestroyed()) wc.send('focus:status', status)
  }
}

function parseJson(body: string): { status?: string; app_or_site?: string; description?: string; message?: string } | null {
  let text = body.trim()
  const fence = text.match(/```(?:json)?\s*([\s\S]*?)```/)
  if (fence) text = fence[1].trim()
  const a = text.indexOf('{')
  const b = text.lastIndexOf('}')
  if (a === -1 || b === -1) return null
  try {
    return JSON.parse(text.slice(a, b + 1))
  } catch {
    return null
  }
}

async function runOnce(): Promise<void> {
  if (!settings.get().focusEnabled || !getAuthState().signedIn) return
  const screenText = latestOcrText(90000)
  if (!screenText || screenText.length < 60) return

  try {
    const res = await apiRequest({
      method: 'POST',
      url: 'v2/chat/completions',
      base: 'rust',
      body: JSON.stringify({
        model: MODEL,
        stream: false,
        max_tokens: 256,
        messages: [
          { role: 'system', content: PROMPT },
          { role: 'user', content: `Screen text:\n\n${screenText.slice(0, 5000)}` }
        ]
      })
    })
    if (res.status < 200 || res.status >= 300) {
      lastError = `focus HTTP ${res.status}`
      broadcast()
      return
    }
    const content = JSON.parse(res.body)?.choices?.[0]?.message?.content
    const parsed = typeof content === 'string' ? parseJson(content) : null
    if (!parsed || (parsed.status !== 'focused' && parsed.status !== 'distracted')) {
      lastError = 'focus parse failed'
      return
    }
    lastError = null
    const status = parsed.status
    const appOrSite = parsed.app_or_site || 'Unknown'
    addSession({
      ts: Date.now(),
      status,
      appOrSite,
      description: parsed.description || '',
      message: parsed.message || null
    })

    const prev = lastStatus
    lastStatus = status
    lastApp = appOrSite

    if (status !== prev && settings.get().focusGlow) {
      const now = Date.now()
      if (status === 'distracted') {
        if (now >= cooldownUntil) {
          flashGlow('distracted')
          cooldownUntil = now + settings.get().focusCooldownMs
        }
      } else {
        // Refocus glow is always allowed (positive reinforcement).
        flashGlow('focused')
      }
    }
    broadcast()
  } catch (e) {
    lastError = String(e)
    broadcast()
  }
}

function schedule(): void {
  if (timer) clearTimeout(timer)
  if (stopped) return
  if (!settings.get().focusEnabled) {
    monitoring = false
    broadcast()
    return
  }
  monitoring = true
  broadcast()
  timer = setTimeout(async () => {
    await runOnce()
    schedule()
  }, Math.max(30000, settings.get().focusAnalysisDelayMs))
}

// Stop the engine on app quit: clear the timer so no analysis cycle fires during
// shutdown. Idempotent.
export function stopFocusEngine(): void {
  stopped = true
  if (timer) {
    clearTimeout(timer)
    timer = null
  }
  monitoring = false
}

export function startFocusEngine(): void {
  settings.on('changed', (next, prev) => {
    if (next.focusEnabled !== prev.focusEnabled || next.focusAnalysisDelayMs !== prev.focusAnalysisDelayMs) schedule()
  })
  schedule()
}

export function getFocusStatus(): FocusStatus {
  const s = settings.get()
  return { enabled: s.focusEnabled, monitoring, current: lastStatus, currentApp: lastApp, lastError }
}

export { listSessions, todaySummary }
