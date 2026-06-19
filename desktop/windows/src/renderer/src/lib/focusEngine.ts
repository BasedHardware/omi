// Windows focus analysis engine — parity with macOS FocusAssistant.swift.
// Uses the existing Gemini proxy (same path as insightEngine.ts) for LLM-based
// classification; heuristic fallback when Gemini is unavailable or fails.
import { generate } from './geminiClient'
import { summarizeActivity } from './insightActivity'
import type { RewindFrame } from '../../../shared/types'

export type FocusStatus = 'focused' | 'distracted' | 'neutral'

export type FocusObservation = {
  ts: number
  status: FocusStatus
  reasoning: string
  app: string
  confidence: number
  method: 'llm' | 'heuristic'
}

const OBS_KEY = 'omi.focus.observations.v1'
const MAX_OBS = 60
const LOOKBACK_MS = 5 * 60 * 1000 // last 5 min of frames

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

  // Top app by frame count
  let topApp = ''
  let maxCount = 0
  for (const [app, count] of appCounts) {
    if (count > maxCount) { maxCount = count; topApp = app }
  }

  const total = frames.length || 1
  if (focusCount > distractCount && focusCount > total * 0.3) {
    return { status: 'focused', app: topApp, confidence: Math.min(0.9, focusCount / total), reasoning: `Mostly using focus apps (${topApp})` }
  }
  if (distractCount > focusCount && distractCount > total * 0.3) {
    return { status: 'distracted', app: topApp, confidence: Math.min(0.9, distractCount / total), reasoning: `Mostly using distraction apps (${topApp})` }
  }
  return { status: 'neutral', app: topApp, confidence: 0.5, reasoning: `Mixed or neutral app activity (${topApp})` }
}

const FOCUS_RESPONSE_SCHEMA = {
  type: 'object',
  properties: {
    status: { type: 'string', enum: ['focused', 'distracted', 'neutral'] },
    reasoning: { type: 'string' },
    app: { type: 'string' },
    confidence: { type: 'number' }
  },
  required: ['status', 'reasoning', 'app', 'confidence']
}

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

// Analyze focus state from the last LOOKBACK_MS of Rewind frames.
// Tries Gemini LLM first; falls back to keyword heuristic on failure.
export async function analyzeFocus(allFrames: RewindFrame[]): Promise<FocusObservation> {
  const ts = Date.now()
  const cutoff = ts - LOOKBACK_MS
  const frames = allFrames.filter((f) => f.ts >= cutoff)

  if (frames.length === 0) {
    return {
      ts,
      status: 'neutral',
      reasoning: 'No recent screen activity',
      app: '',
      confidence: 0,
      method: 'heuristic'
    }
  }

  // Try LLM classification
  try {
    const summary = summarizeActivity(frames, 3000)
    if (summary) {
      const raw = await generate({
        model: 'gemini-2.5-flash',
        parts: [{ text: `Screen activity summary (last 5 minutes):\n\n${summary}` }],
        systemPrompt:
          'You are a focus analyst. Classify the user as "focused" (coding, writing, designing, working), "distracted" (social media, entertainment, gaming, browsing without purpose), or "neutral" (unclear or mixed). Return strict JSON with: status (focused|distracted|neutral), reasoning (max 15 words), app (main app name), confidence (0.0–1.0).',
        responseSchema: FOCUS_RESPONSE_SCHEMA as unknown as Record<string, unknown>
      })
      const parsed = JSON.parse(raw) as {
        status?: string
        reasoning?: string
        app?: string
        confidence?: number
      }
      const valid = ['focused', 'distracted', 'neutral']
      const status: FocusStatus = valid.includes(parsed.status ?? '')
        ? (parsed.status as FocusStatus)
        : 'neutral'
      return {
        ts,
        status,
        reasoning: (parsed.reasoning ?? '').slice(0, 120),
        app: parsed.app ?? frames[frames.length - 1]?.app ?? '',
        confidence: Math.min(1, Math.max(0, parsed.confidence ?? 0.7)),
        method: 'llm'
      }
    }
  } catch (e) {
    console.warn('[focusEngine] LLM failed, using heuristic:', e)
  }

  // Heuristic fallback
  const h = heuristicClassify(frames)
  return { ts, method: 'heuristic', ...h }
}
