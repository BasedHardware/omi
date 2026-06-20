// Windows focus analysis engine — parity with macOS FocusAssistant.swift.
//
// Three analysis tiers, attempted in order:
//   1. Vision  — 1-2 sampled Rewind screenshots sent to Gemini Vision as
//                inlineData. Same proxy path as insightEngine.ts. 8 s timeout.
//   2. Text    — OCR + app/window text summarized and sent to Gemini text.
//   3. Heuristic — keyword match on exe/app name. No network.
//
// The public entry point is analyzeFocus(frames, useVision?). Vision can be
// toggled per-user in Notifications → Focus analysis settings.
import { generate } from './geminiClient'
import { summarizeActivity } from './insightActivity'
import type { GeminiPart } from './geminiClient'
import type { RewindFrame } from '../../../shared/types'

export type FocusStatus = 'focused' | 'distracted' | 'neutral'

export type FocusObservation = {
  ts: number
  status: FocusStatus
  reasoning: string
  app: string
  confidence: number
  method: 'vision' | 'llm' | 'heuristic'
  /** One-sentence visual description returned by Gemini Vision (vision method only). */
  visualEvidence?: string
  /** Why Vision or Text-OCR was not used (set on heuristic/llm fallback paths). */
  fallbackReason?: string
}

const OBS_KEY = 'omi.focus.observations.v1'
const MAX_OBS = 60
const LOOKBACK_MS = 5 * 60 * 1000 // last 5 min of frames
const VISION_TIMEOUT_MS = 8_000
const VISION_MAX_FRAMES = 2

// ── In-memory vision cache — keyed by "<ts>:<imagePath>" pairs so the same
// frames are never re-sent to Gemini within a session.
const visionCache = new Map<string, FocusObservation>()

// ── Keyword heuristics ──────────────────────────────────────────────────────
const FOCUS_APPS = [
  'code', 'cursor', 'vim', 'neovim', 'nvim', 'emacs', 'sublime', 'notepad', 'word', 'excel',
  'outlook', 'onenote', 'notion', 'obsidian', 'rider', 'intellij', 'pycharm', 'webstorm',
  'terminal', 'powershell', 'pwsh', 'cmd', 'wt', 'alacritty', 'gitkraken', 'git',
  'devenv', 'blender', 'premiere', 'resolve', 'photoshop', 'lightroom', 'affinity',
  'docs', 'sheets', 'slides', 'linear', 'jira', 'confluence', 'trello', 'figma', 'sketch'
]
const DISTRACT_APPS = [
  'youtube', 'netflix', 'twitch', 'hulu', 'disneyplus', 'primevideo', 'hbomax',
  'vlc', 'wmplayer', 'itunes', 'foobar',
  'discord', 'twitter', 'reddit', 'instagram', 'facebook', 'tiktok', 'snapchat', 'tumblr',
  'steam', 'epic', 'gog', 'minecraft', 'roblox', 'valorant', 'overwatch', 'fortnite',
  'xboxapp', 'xbox', 'battle.net'
]

function heuristicClassify(frames: RewindFrame[]): {
  status: FocusStatus
  app: string
  confidence: number
  reasoning: string
} {
  let focusCount = 0, distractCount = 0
  const appCounts = new Map<string, number>()

  for (const f of frames) {
    const app = f.app || f.processName || ''
    appCounts.set(app, (appCounts.get(app) ?? 0) + 1)
    const lower = app.toLowerCase()
    if (FOCUS_APPS.some((p) => lower.includes(p))) focusCount++
    else if (DISTRACT_APPS.some((p) => lower.includes(p))) distractCount++
  }

  let topApp = ''
  let maxCount = 0
  for (const [app, count] of appCounts) {
    if (count > maxCount) { maxCount = count; topApp = app }
  }

  const total = frames.length || 1
  if (focusCount > distractCount && focusCount > total * 0.3) {
    return {
      status: 'focused',
      app: topApp,
      confidence: Math.min(0.9, focusCount / total),
      reasoning: `Mostly using focus apps (${topApp})`
    }
  }
  if (distractCount > focusCount && distractCount > total * 0.3) {
    return {
      status: 'distracted',
      app: topApp,
      confidence: Math.min(0.9, distractCount / total),
      reasoning: `Mostly using distraction apps (${topApp})`
    }
  }
  return { status: 'neutral', app: topApp, confidence: 0.5, reasoning: `Mixed or neutral app activity (${topApp})` }
}

// ── Shared response schema ──────────────────────────────────────────────────
const TEXT_RESPONSE_SCHEMA = {
  type: 'object',
  properties: {
    status: { type: 'string', enum: ['focused', 'distracted', 'neutral'] },
    reasoning: { type: 'string' },
    app: { type: 'string' },
    confidence: { type: 'number' }
  },
  required: ['status', 'reasoning', 'app', 'confidence']
}

const VISION_RESPONSE_SCHEMA = {
  type: 'object',
  properties: {
    status: { type: 'string', enum: ['focused', 'distracted', 'neutral'] },
    reasoning: { type: 'string' },
    app: { type: 'string' },
    confidence: { type: 'number' },
    visual_evidence: { type: 'string' }
  },
  required: ['status', 'reasoning', 'app', 'confidence', 'visual_evidence']
}

// ── Helpers ─────────────────────────────────────────────────────────────────
function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T> {
  return Promise.race([
    promise,
    new Promise<never>((_, reject) => setTimeout(() => reject(new Error(`timeout after ${ms}ms`)), ms))
  ])
}

function parseStatus(raw: string | undefined): FocusStatus {
  const valid: FocusStatus[] = ['focused', 'distracted', 'neutral']
  return valid.includes(raw as FocusStatus) ? (raw as FocusStatus) : 'neutral'
}

// ── Observation storage ─────────────────────────────────────────────────────
export function loadObservations(): FocusObservation[] {
  try {
    const raw = localStorage.getItem(OBS_KEY)
    return raw ? (JSON.parse(raw) as FocusObservation[]) : []
  } catch {
    return []
  }
}

export function saveObservations(obs: FocusObservation[]): void {
  try {
    localStorage.setItem(OBS_KEY, JSON.stringify(obs.slice(0, MAX_OBS)))
  } catch {
    /* quota */
  }
}

// ── Vision analysis ──────────────────────────────────────────────────────────
// Selects up to VISION_MAX_FRAMES most recent frames that have a stored JPEG,
// fetches them via the already-validated `rewind:frameImage` IPC, and asks
// Gemini Vision for focus classification. Returns null on any failure so the
// caller can fall back to the text/heuristic tier.
export async function analyzeFocusVision(frames: RewindFrame[]): Promise<FocusObservation | null> {
  const ts = Date.now()
  const cutoff = ts - LOOKBACK_MS

  // Only frames within the window that have a stored image file
  const eligible = frames
    .filter((f) => f.ts >= cutoff && f.imagePath && f.imagePath.length > 0)
    .sort((a, b) => b.ts - a.ts)
    .slice(0, VISION_MAX_FRAMES)

  if (eligible.length === 0) return null

  // Cache check: skip if we already classified these exact frames this session
  const cacheKey = eligible.map((f) => `${f.ts}:${f.imagePath}`).join('|')
  const cached = visionCache.get(cacheKey)
  if (cached) return cached

  try {
    // Fetch base64 image data via existing secure IPC (path validated in main)
    const dataUrls = await withTimeout(
      Promise.all(eligible.map((f) => window.omi.rewindFrameImage(f.imagePath))),
      VISION_TIMEOUT_MS / 2
    )

    // Build image parts (strip data: prefix, keep raw base64)
    const imageParts: GeminiPart[] = dataUrls.map((url) => ({
      inlineData: {
        mimeType: 'image/jpeg',
        data: url.replace(/^data:image\/jpeg;base64,/, '')
      }
    }))

    // Text context part: app, window, light OCR excerpt per frame
    const contextLines = eligible.map((f) => {
      const lines = [
        `[${new Date(f.ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}]`,
        `App: ${f.app || f.processName || 'unknown'}`,
        `Window: ${f.windowTitle || 'unknown'}`
      ]
      if (f.ocrText) lines.push(`OCR excerpt: ${f.ocrText.slice(0, 300)}`)
      return lines.join('\n')
    })
    const contextPart: GeminiPart = {
      text: `Context for each screenshot:\n\n${contextLines.join('\n---\n')}`
    }

    const raw = await withTimeout(
      generate({
        model: 'gemini-2.5-flash',
        parts: [...imageParts, contextPart],
        systemPrompt:
          'You are a focus analyst reviewing screenshots of a user\'s screen.' +
          ' Classify as "focused" (coding, writing, designing, working productively),' +
          ' "distracted" (social media, entertainment, gaming, aimless browsing),' +
          ' or "neutral" (unclear or mixed).' +
          ' Return strict JSON: status (focused|distracted|neutral),' +
          ' confidence (0.0–1.0), app (main app name),' +
          ' reasoning (max 15 words about the activity),' +
          ' visual_evidence (max 20 words describing what you see in the screenshot).',
        responseSchema: VISION_RESPONSE_SCHEMA as unknown as Record<string, unknown>
      }),
      VISION_TIMEOUT_MS
    )

    const parsed = JSON.parse(raw) as {
      status?: string
      reasoning?: string
      app?: string
      confidence?: number
      visual_evidence?: string
    }

    const obs: FocusObservation = {
      ts,
      status: parseStatus(parsed.status),
      reasoning: (parsed.reasoning ?? '').slice(0, 120),
      app: parsed.app ?? eligible[0].app ?? '',
      confidence: Math.min(1, Math.max(0, parsed.confidence ?? 0.8)),
      method: 'vision',
      visualEvidence: (parsed.visual_evidence ?? '').slice(0, 200) || undefined
    }

    visionCache.set(cacheKey, obs)
    return obs
  } catch (e) {
    console.warn('[focusEngine] vision analysis failed:', (e as Error).message)
    return null
  }
}

// ── Text/OCR LLM analysis ───────────────────────────────────────────────────
async function analyzeFocusText(frames: RewindFrame[]): Promise<FocusObservation | null> {
  try {
    const summary = summarizeActivity(frames, 3000)
    if (!summary) return null

    const raw = await generate({
      model: 'gemini-2.5-flash',
      parts: [{ text: `Screen activity summary (last 5 minutes):\n\n${summary}` }],
      systemPrompt:
        'You are a focus analyst. Classify the user as "focused" (coding, writing, designing, working),' +
        ' "distracted" (social media, entertainment, gaming, browsing without purpose),' +
        ' or "neutral" (unclear or mixed).' +
        ' Return strict JSON: status (focused|distracted|neutral),' +
        ' reasoning (max 15 words), app (main app name), confidence (0.0–1.0).',
      responseSchema: TEXT_RESPONSE_SCHEMA as unknown as Record<string, unknown>
    })

    const parsed = JSON.parse(raw) as {
      status?: string
      reasoning?: string
      app?: string
      confidence?: number
    }

    return {
      ts: Date.now(),
      status: parseStatus(parsed.status),
      reasoning: (parsed.reasoning ?? '').slice(0, 120),
      app: parsed.app ?? frames[frames.length - 1]?.app ?? '',
      confidence: Math.min(1, Math.max(0, parsed.confidence ?? 0.7)),
      method: 'llm'
    }
  } catch (e) {
    console.warn('[focusEngine] text LLM failed:', (e as Error).message)
    return null
  }
}

// ── Public entry point ───────────────────────────────────────────────────────
// Attempts each tier in order: vision → text-LLM → heuristic.
// Pass useVision=true to enable the vision tier (requires Rewind + Gemini).
export async function analyzeFocus(
  allFrames: RewindFrame[],
  useVision = false
): Promise<FocusObservation> {
  const ts = Date.now()
  const cutoff = ts - LOOKBACK_MS
  const frames = allFrames.filter((f) => f.ts >= cutoff)

  if (import.meta.env.DEV) {
    const withImage = frames.filter((f) => f.imagePath).length
    console.log(`[focusEngine] analyzeFocus: ${frames.length} frames (${withImage} with imagePath), useVision=${useVision}`)
  }

  if (frames.length === 0) {
    return {
      ts,
      status: 'neutral',
      reasoning: 'No recent screen activity',
      app: '',
      confidence: 0,
      method: 'heuristic',
      fallbackReason: 'No recent Rewind frames'
    }
  }

  // Tier 1: Gemini Vision (sampled screenshots)
  if (useVision) {
    const eligible = frames.filter((f) => f.imagePath && f.imagePath.length > 0)
    if (import.meta.env.DEV) {
      console.log(`[focusEngine] vision tier: ${eligible.length} frames with imagePath`)
    }
    if (eligible.length === 0) {
      if (import.meta.env.DEV) console.log('[focusEngine] vision skipped — no frames with imagePath')
    } else {
      const visionObs = await analyzeFocusVision(frames)
      if (import.meta.env.DEV) console.log(`[focusEngine] vision result: ${visionObs ? visionObs.method : 'null (failed)'}`)
      if (visionObs) return visionObs
    }
  }

  // Tier 2: Gemini text (OCR + app/window summary)
  const textObs = await analyzeFocusText(frames)
  if (textObs) {
    const visionSkipReason = !useVision
      ? 'Vision disabled'
      : frames.filter((f) => f.imagePath).length === 0
        ? 'No screenshots in Rewind frames'
        : 'Vision failed (Gemini timeout or API error)'
    return { ...textObs, fallbackReason: visionSkipReason }
  }

  // Tier 3: keyword heuristic
  if (import.meta.env.DEV) console.log('[focusEngine] text LLM failed — using heuristic')
  const visionReason = !useVision
    ? 'Vision disabled'
    : frames.filter((f) => f.imagePath).length === 0
      ? 'No screenshots in Rewind frames'
      : 'Vision failed (Gemini timeout or API error)'
  const h = heuristicClassify(frames)
  return {
    ts,
    method: 'heuristic',
    ...h,
    fallbackReason: `${visionReason} · Gemini text analysis also failed`
  }
}
