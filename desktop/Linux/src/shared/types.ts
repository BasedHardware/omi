export interface AuthState {
  signedIn: boolean
  uid?: string
  email?: string
  name?: string
}

export interface AppSettings {
  hotkey: string
  floatingBarVisible: boolean
  floatingBarPosition?: { x: number; y: number }
  rewindEnabled: boolean
  rewindIntervalMs: number
  retentionDays: number
  transcriptionLanguage: string
  launchAtLogin: boolean
  fontScale: number
  proactiveEnabled: boolean
  proactiveIntervalMs: number
  proactiveNotifications: boolean
  focusEnabled: boolean
  focusGlow: boolean
  focusAnalysisDelayMs: number
  focusCooldownMs: number
  realtimeProvider: 'auto' | 'gemini' | 'openai'
  ttsEnabled: boolean
  ttsVoice: string
  customVocabulary: string[]
  aiModel: string
  updateChannel: 'stable' | 'beta'
  hasOnboarded: boolean
  byokActive: boolean
  byokAnthropic: string
  byokOpenAI: string
  byokGemini: string
  byokDeepgram: string
  pythonApiUrl: string
  rustApiUrl: string
}

export interface Insight {
  id: number
  ts: number
  title: string
  body: string
  category: string
  sourceApp: string | null
  read: number
}

export interface ProactiveStatus {
  enabled: boolean
  running: boolean
  lastRunTs: number | null
  lastError: string | null
  unread: number
}

export interface ProactiveNotification {
  id: number
  title: string
  body: string
  category: string
}

export interface FocusSession {
  id: number
  ts: number
  status: 'focused' | 'distracted'
  appOrSite: string
  description: string
  message: string | null
  durationSeconds: number
}

export interface FocusStatus {
  enabled: boolean
  monitoring: boolean
  current: 'focused' | 'distracted' | null
  currentApp: string | null
  lastError: string | null
}

export interface ApiRequest {
  method: string
  /** Path relative to base, or absolute http(s) URL */
  url: string
  base: 'python' | 'rust'
  body?: string | null
  contentType?: string
  /** Skip Authorization header (auth endpoints) */
  anonymous?: boolean
}

export interface ApiResponse {
  status: number
  body: string
}

export interface TranscriptSegment {
  id?: string
  text: string
  speaker?: string
  speaker_id?: number
  is_user?: boolean
  person_id?: string | null
  start?: number
  end?: number
}

export type TranscribeEvent =
  | { type: 'segments'; segments: TranscriptSegment[] }
  | { type: 'message'; payload: Record<string, unknown> }
  | { type: 'interim'; text: string }
  | { type: 'final'; text: string }
  | { type: 'status'; status: 'connecting' | 'connected' | 'closed' | 'error'; detail?: string }

export interface RewindFrame {
  id: number
  ts: number
  day: string
  path: string
  ocr: string | null
  snippet?: string
}

export interface RewindStats {
  frames: number
  days: number
  bytes: number
  ocrPending: number
  capturing: boolean
}

export interface ScreenshotResult {
  dataUrl: string
  width: number
  height: number
}
