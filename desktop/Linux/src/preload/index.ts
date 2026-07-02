import { contextBridge, ipcRenderer } from 'electron'
import type {
  ApiRequest,
  ApiResponse,
  AppSettings,
  AuthState,
  Insight,
  ProactiveNotification,
  ProactiveStatus,
  RewindFrame,
  ScreenshotResult,
  TranscribeEvent
} from '../shared/types'

type Mode = 'conversation' | 'ptt'

let streamCounter = 0

const api = {
  auth: {
    getState: (): Promise<AuthState> => ipcRenderer.invoke('auth:get-state'),
    signIn: (provider: 'google' | 'apple'): void => ipcRenderer.send('auth:sign-in', provider),
    signOut: (): void => ipcRenderer.send('auth:sign-out'),
    onChanged: (cb: (state: AuthState) => void): (() => void) => {
      const handler = (_e: unknown, state: AuthState) => cb(state)
      ipcRenderer.on('auth:changed', handler)
      return () => ipcRenderer.removeListener('auth:changed', handler)
    }
  },
  api: {
    request: (req: ApiRequest): Promise<ApiResponse> => ipcRenderer.invoke('api:request', req),
    requestBinary: (req: ApiRequest): Promise<{ status: number; base64: string; contentType: string }> =>
      ipcRenderer.invoke('api:request-binary', req),
    stream: (
      req: ApiRequest,
      onChunk: (data: string) => void,
      onDone: () => void,
      onError: (status: number, body: string) => void
    ): (() => void) => {
      const id = `s${++streamCounter}_${Date.now()}`
      const channel = `api:stream:${id}`
      const handler = (_e: unknown, payload: { type: string; data?: string; status?: number; body?: string }) => {
        if (payload.type === 'chunk') onChunk(payload.data ?? '')
        else if (payload.type === 'done') {
          ipcRenderer.removeListener(channel, handler)
          onDone()
        } else {
          ipcRenderer.removeListener(channel, handler)
          onError(payload.status ?? 0, payload.body ?? '')
        }
      }
      ipcRenderer.on(channel, handler)
      void ipcRenderer.invoke('api:stream', id, req)
      return () => {
        ipcRenderer.removeListener(channel, handler)
        ipcRenderer.send('api:stream:cancel', id)
      }
    }
  },
  settings: {
    get: (): Promise<AppSettings> => ipcRenderer.invoke('settings:get'),
    set: (partial: Partial<AppSettings>): Promise<AppSettings> => ipcRenderer.invoke('settings:set', partial)
  },
  floating: {
    setSize: (width: number, height: number): void => ipcRenderer.send('floating:set-size', { width, height }),
    hide: (): void => ipcRenderer.send('floating:hide'),
    openMain: (page?: string): void => ipcRenderer.send('floating:open-main', page),
    focus: (): void => ipcRenderer.send('floating:focus'),
    onToggleAsk: (cb: () => void): (() => void) => {
      const handler = () => cb()
      ipcRenderer.on('floating:toggle-ask', handler)
      return () => ipcRenderer.removeListener('floating:toggle-ask', handler)
    }
  },
  nav: {
    onNavigate: (cb: (page: string) => void): (() => void) => {
      const handler = (_e: unknown, page: string) => cb(page)
      ipcRenderer.on('app:navigate', handler)
      return () => ipcRenderer.removeListener('app:navigate', handler)
    }
  },
  transcribe: {
    start: (mode: Mode, language?: string): Promise<boolean> => ipcRenderer.invoke('transcribe:start', mode, language),
    sendAudio: (mode: Mode, chunk: ArrayBuffer): void => ipcRenderer.send('transcribe:audio', mode, chunk),
    finalize: (mode: Mode): void => ipcRenderer.send('transcribe:finalize', mode),
    stop: (mode: Mode): void => ipcRenderer.send('transcribe:stop', mode),
    onEvent: (mode: Mode, cb: (event: TranscribeEvent) => void): (() => void) => {
      const channel = `transcribe:event:${mode}`
      const handler = (_e: unknown, event: TranscribeEvent) => cb(event)
      ipcRenderer.on(channel, handler)
      return () => ipcRenderer.removeListener(channel, handler)
    }
  },
  capture: {
    screenshot: (): Promise<ScreenshotResult | null> => ipcRenderer.invoke('capture:screenshot'),
    /** Arm an app-initiated display-media capture; must be called right before getDisplayMedia. */
    armLoopback: (): void => ipcRenderer.send('capture:arm-loopback')
  },
  realtime: {
    start: (): Promise<{ ok: boolean; inputRate?: number; provider?: string }> => ipcRenderer.invoke('realtime:start'),
    sendAudio: (chunk: ArrayBuffer): void => ipcRenderer.send('realtime:audio', chunk),
    commit: (): void => ipcRenderer.send('realtime:commit'),
    stop: (): void => ipcRenderer.send('realtime:stop'),
    onEvent: (cb: (e: Record<string, unknown>) => void): (() => void) => {
      const handler = (_e: unknown, ev: Record<string, unknown>) => cb(ev)
      ipcRenderer.on('realtime:event', handler)
      return () => ipcRenderer.removeListener('realtime:event', handler)
    }
  },
  rewind: {
    list: (day: string | null, limit?: number, offset?: number): Promise<RewindFrame[]> =>
      ipcRenderer.invoke('rewind:list', day, limit, offset),
    days: (): Promise<{ day: string; count: number }[]> => ipcRenderer.invoke('rewind:days'),
    search: (q: string, limit?: number): Promise<RewindFrame[]> => ipcRenderer.invoke('rewind:search', q, limit),
    status: (): Promise<{ frames: number; days: number; bytes: number; ocrPending: number; capturing: boolean }> =>
      ipcRenderer.invoke('rewind:status'),
    image: (id: number): Promise<string | null> => ipcRenderer.invoke('rewind:image', id),
    thumbnail: (id: number, width: number): Promise<string | null> => ipcRenderer.invoke('rewind:thumbnail', id, width),
    latestOcr: (maxAgeMs?: number): Promise<string | null> => ipcRenderer.invoke('rewind:latest-ocr', maxAgeMs),
    onStatus: (cb: (status: unknown) => void): (() => void) => {
      const handler = (_e: unknown, s: unknown) => cb(s)
      ipcRenderer.on('rewind:status', handler)
      return () => ipcRenderer.removeListener('rewind:status', handler)
    }
  },
  proactive: {
    list: (): Promise<Insight[]> => ipcRenderer.invoke('proactive:list'),
    status: (): Promise<ProactiveStatus> => ipcRenderer.invoke('proactive:status'),
    runNow: (): Promise<void> => ipcRenderer.invoke('proactive:run-now'),
    markRead: (id: number): Promise<void> => ipcRenderer.invoke('proactive:mark-read', id),
    markAllRead: (): Promise<void> => ipcRenderer.invoke('proactive:mark-all-read'),
    remove: (id: number): Promise<void> => ipcRenderer.invoke('proactive:delete', id),
    onStatus: (cb: (status: ProactiveStatus) => void): (() => void) => {
      const handler = (_e: unknown, s: ProactiveStatus) => cb(s)
      ipcRenderer.on('proactive:status', handler)
      return () => ipcRenderer.removeListener('proactive:status', handler)
    },
    onNotification: (cb: (n: ProactiveNotification) => void): (() => void) => {
      const handler = (_e: unknown, n: ProactiveNotification) => cb(n)
      ipcRenderer.on('proactive:notification', handler)
      return () => ipcRenderer.removeListener('proactive:notification', handler)
    }
  },
  byok: {
    status: (): Promise<{ openai: boolean; anthropic: boolean; gemini: boolean; deepgram: boolean }> =>
      ipcRenderer.invoke('byok:status'),
    activate: (): Promise<{ ok: boolean; error?: string; missing?: string[] }> => ipcRenderer.invoke('byok:activate'),
    deactivate: (): Promise<{ ok: boolean; error?: string }> => ipcRenderer.invoke('byok:deactivate')
  },
  files: {
    index: (): Promise<{ ok: boolean; summary?: string; error?: string }> => ipcRenderer.invoke('files:index')
  },
  updater: {
    check: (): Promise<{ status: string; version?: string; percent?: number; error?: string }> =>
      ipcRenderer.invoke('updater:check'),
    onState: (cb: (s: { status: string; version?: string; percent?: number }) => void): (() => void) => {
      const handler = (_e: unknown, s: { status: string; version?: string; percent?: number }) => cb(s)
      ipcRenderer.on('updater:state', handler)
      return () => ipcRenderer.removeListener('updater:state', handler)
    }
  },
  focus: {
    status: (): Promise<unknown> => ipcRenderer.invoke('focus:status'),
    sessions: (): Promise<unknown> => ipcRenderer.invoke('focus:sessions'),
    summary: (): Promise<unknown> => ipcRenderer.invoke('focus:summary'),
    onStatus: (cb: (s: unknown) => void): (() => void) => {
      const handler = (_e: unknown, s: unknown) => cb(s)
      ipcRenderer.on('focus:status', handler)
      return () => ipcRenderer.removeListener('focus:status', handler)
    },
    onGlow: (cb: (g: { status: 'focused' | 'distracted' }) => void): (() => void) => {
      const handler = (_e: unknown, g: { status: 'focused' | 'distracted' }) => cb(g)
      ipcRenderer.on('glow:show', handler)
      return () => ipcRenderer.removeListener('glow:show', handler)
    }
  },
  system: {
    version: (): Promise<string> => ipcRenderer.invoke('app:version'),
    openExternal: (url: string): void => ipcRenderer.send('shell:open-external', url)
  }
}

export type OmiBridge = typeof api

contextBridge.exposeInMainWorld('omi', api)
