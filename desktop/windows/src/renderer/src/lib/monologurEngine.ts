// src/renderer/src/lib/monologurEngine.ts
import { generate } from './geminiClient'
import { liveConversation } from './liveConversation'
import { speak, stop as stopTTS, setOnSpeakingChange, isTTSSpeaking } from './ttsService'
import { getMonologurMemoryContext, saveMonologurInsight } from './monologurMemory'
import type { TTSSettings } from './ttsService'
import type { TranscriptLine } from '../../../shared/types'

export type MonologurTtsProvider = 'web' | 'deepgram'

export type MonologurSettings = {
  enabled: boolean
  intervalMs: number // How often to check if we should speak (default: 60000 = 1 min)
  minWordsBeforePrompt: number // Minimum words in conversation before prompting (default: 20)
  cooldownMs: number // Min time between proactive prompts (default: 300000 = 5 min)
  tts: TTSSettings
  ttsProvider: MonologurTtsProvider // 'web' = Web Speech API, 'deepgram' = Deepgram Aura
  deepgramVoice: string // Deepgram voice ID (e.g. 'aura-asteria-en')
  systemPrompt: string // Customizable system prompt for the AI
}

const DEFAULT_SETTINGS: MonologurSettings = {
  enabled: true,
  intervalMs: 60_000,
  minWordsBeforePrompt: 20,
  cooldownMs: 300_000,
  tts: {
    enabled: true,
    rate: 1.0,
    pitch: 1.0,
    volume: 1.0,
    voiceName: null
  },
  ttsProvider: 'web',
  deepgramVoice: 'aura-asteria-en',
  systemPrompt: `You are Monologur, a high-intelligence background listener. You are the silent observer who knows the user deeply.
  
Rules:
- Be sharp, concise, and high-value. 
- Only speak when you have a genuinely useful, personalized insight based on the user's current activity or history.
- Avoid generic advice. Be specific.
- Keep responses to 1-2 sharp sentences.
- If the user is focused or in a crowded environment, stay completely silent unless it's critical.
- Your goal is to be the "smartest person in the room" who speaks only when it truly matters.`
}

let running = false
let started = false
let timer: ReturnType<typeof setTimeout> | null = null
let lastPromptTime = 0
let lastSegments: TranscriptLine[] = []
let settings: MonologurSettings = { ...DEFAULT_SETTINGS }
let onProactiveMessage: ((text: string) => void) | null = null
let onStatusChange: ((status: 'idle' | 'listening' | 'thinking' | 'speaking') => void) | null = null
let currentAudio: HTMLAudioElement | null = null

// Get current settings from localStorage
function loadSettings(): MonologurSettings {
  try {
    const stored = localStorage.getItem('monologur-settings-v1')
    if (stored) {
      return { ...DEFAULT_SETTINGS, ...JSON.parse(stored) }
    }
  } catch {
    // ignore
  }
  return { ...DEFAULT_SETTINGS }
}

// Save settings to localStorage
export function saveMonologurSettings(s: Partial<MonologurSettings>): void {
  settings = { ...settings, ...s }
  localStorage.setItem('monologur-settings-v1', JSON.stringify(settings))
}

export function getMonologurSettings(): MonologurSettings {
  return { ...settings }
}

// Check if Deepgram TTS is available
function isDeepgramTtsAvailable(): boolean {
  return settings.ttsProvider === 'deepgram' && typeof window.omi?.deepgramTtsSynthesize === 'function'
}

// Speak using Deepgram TTS
async function speakWithDeepgram(text: string): Promise<boolean> {
  if (!isDeepgramTtsAvailable()) return false

  try {
    onStatusChange?.('speaking')
    const result = await window.omi.deepgramTtsSynthesize({
      text,
      voice: settings.deepgramVoice,
      encoding: 'mp3'
    })

    if (!result.ok || !result.audio) {
      console.warn('[monologur] Deepgram TTS failed:', result.error)
      return false
    }

    // Convert number[] back to Uint8Array and create audio blob
    const audioData = new Uint8Array(result.audio)
    const blob = new Blob([audioData], { type: result.contentType || 'audio/mpeg' })
    const url = URL.createObjectURL(blob)

    // Play the audio
    currentAudio = new Audio(url)
    currentAudio.onended = () => {
      URL.revokeObjectURL(url)
      currentAudio = null
      onStatusChange?.('listening')
    }
    currentAudio.onerror = (e) => {
      console.error('[monologur] Audio playback error:', e)
      URL.revokeObjectURL(url)
      currentAudio = null
      onStatusChange?.('listening')
    }
    await currentAudio.play()
    return true
  } catch (e) {
    console.warn('[monologur] Deepgram TTS error:', e)
    onStatusChange?.('listening')
    return false
  }
}

// Check if there's new content worth prompting about
function hasNewContent(prev: TranscriptLine[], curr: TranscriptLine[]): boolean {
  if (curr.length <= prev.length) return false
  const prevWords = prev.reduce((acc, l) => acc + l.text.split(/\s+/).length, 0)
  const currWords = curr.reduce((acc, l) => acc + l.text.split(/\s+/).length, 0)
  return currWords - prevWords >= 10
}

// Build context from recent conversation
function buildConversationContext(segments: TranscriptLine[]): string {
  const recent = segments.slice(-10)
  return recent
    .map((s) => `${s.speaker || 'Unknown'}: ${s.text}`)
    .join('\n')
}

// The user's own recent speech only — Monologur reacts to what YOU say, not to
// other people in the room (identified via the enrolled voiceprint).
function userSpeech(segments: TranscriptLine[]): string {
  return segments
    .filter((s) => s.isUser)
    .slice(-10)
    .map((s) => s.text)
    .join('\n')
    .trim()
}

// Generate a proactive prompt using the LLM
async function generateProactivePrompt(context: string, segments: TranscriptLine[]): Promise<string | null> {
  try {
    // Pull the user's saved memories and rank them against what they just said,
    // so Monologur can reference real context like the main Omi agent does.
    const memoryContext = await getMonologurMemoryContext(userSpeech(segments))
    const augmentedContext = memoryContext ? `${context}\n\n${memoryContext}` : context

    const response = await generate({
      model: 'gemini-2.5-flash',
      parts: [
        {
          text: `Based on this ongoing conversation, decide if you should proactively speak to the user.
 
 Conversation context:
 ${augmentedContext}
 
 Rules:
 - If the conversation just started or is too short, respond with "SKIP"
 - If the user is in the middle of something complex, respond with "SKIP"
 - If you have a genuinely useful suggestion, insight, or reminder, provide it
 - If the user mentioned something you could help with, offer help
 - Reference the user's saved memories when relevant to make it personal
 - Keep your response to 1-2 sentences maximum
 - Be natural and conversational
 
 If you should speak, respond with just what you would say. If you should stay quiet, respond with exactly "SKIP"`
        }
      ],
      systemPrompt: settings.systemPrompt
    })

    if (response === 'SKIP' || !response.trim()) {
      return null
    }

    return response.trim()
  } catch (e) {
    console.warn('[monologur] LLM call failed:', e)
    return null
  }
}

// Main check loop
async function checkAndPrompt(): Promise<void> {
  if (!settings.enabled || running) return

  const now = Date.now()
  if (now - lastPromptTime < settings.cooldownMs) return

  const segments = liveConversation.getSegments()
  const totalWords = segments.reduce((acc, l) => acc + l.text.split(/\s+/).length, 0)

  if (totalWords < settings.minWordsBeforePrompt) return
  if (!hasNewContent(lastSegments, segments)) return

  running = true
  onStatusChange?.('thinking')

  try {
    const context = buildConversationContext(segments)
    const prompt = await generateProactivePrompt(context, segments)

    if (prompt) {
      lastPromptTime = now
      onProactiveMessage?.(prompt)
      // Persist genuinely useful, durable insights back to the shared memory store
      // so Monologur's help compounds over time (tap the Omi agent memory).
      void saveMonologurInsight(prompt)

      if (settings.tts.enabled) {
        // Try Deepgram TTS first, fall back to Web Speech API
        if (isDeepgramTtsAvailable()) {
          await speakWithDeepgram(prompt)
        } else {
          onStatusChange?.('speaking')
          speak(prompt, settings.tts, {
            onEnd: () => onStatusChange?.('listening'),
            onError: () => onStatusChange?.('listening')
          })
        }
      }
    }

    lastSegments = [...segments]
  } catch (e) {
    console.warn('[monologur] check failed:', e)
  } finally {
    running = false
    if (!isTTSSpeaking() && !currentAudio) {
      onStatusChange?.('listening')
    }
  }
}

// Schedule the check loop
function scheduleCheck(): void {
  if (timer) clearTimeout(timer)
  if (!settings.enabled) return

  timer = setTimeout(async () => {
    await checkAndPrompt()
    scheduleCheck()
  }, settings.intervalMs)
}

export function setOnProactiveMessage(cb: ((text: string) => void) | null): void {
  onProactiveMessage = cb
}

export function setOnMonologurStatusChange(
  cb: ((status: 'idle' | 'listening' | 'thinking' | 'speaking') => void) | null
): void {
  onStatusChange = cb
}

// Start the monologur engine
export function startMonologur(): void {
  if (started) return
  started = true
  settings = loadSettings()

  setOnSpeakingChange((speaking) => {
    if (!speaking && settings.enabled && !currentAudio) {
      onStatusChange?.('listening')
    }
  })

  if (settings.enabled) {
    scheduleCheck()
  }
}

// Stop the monologur engine
export function stopMonologur(): void {
  started = false
  if (timer) {
    clearTimeout(timer)
    timer = null
  }
  stopTTS()
  if (currentAudio) {
    currentAudio.pause()
    currentAudio = null
  }
  setOnSpeakingChange(null)
  onStatusChange?.('idle')
}

// Toggle monologur on/off
export function toggleMonologur(): void {
  settings.enabled = !settings.enabled
  saveMonologurSettings({ enabled: settings.enabled })

  if (settings.enabled) {
    startMonologur()
  } else {
    stopMonologur()
  }
}

// Force a proactive prompt (for testing or manual trigger)
export async function forcePrompt(): Promise<void> {
  lastPromptTime = 0
  await checkAndPrompt()
}
