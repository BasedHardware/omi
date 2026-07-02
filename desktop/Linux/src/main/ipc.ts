import { app, ipcMain, shell, nativeImage } from 'electron'
import { readFileSync, realpathSync } from 'fs'
import { sep } from 'path'
import { getAuthState, startSignIn, signOut } from './auth'
import { settings } from './settings'
import { setByokKeys, migrateLegacyByokKeys, byokStatus, type ByokKeys, type ByokProvider } from './secrets'
import type { AppSettings } from '../shared/types'
import { resizeFloatingBar, toggleFloatingBar, createMainWindow, getFloatingBar } from './windows'
import { rebuildTrayMenu } from './tray'
import { listFrames, listDays, searchFrames, getFrame, latestOcrText, rewindRoot } from './rewind/store'
import { getRewindStatus } from './rewind/capturer'
import { registerApiIpc } from './apiProxy'
import { registerTranscriptionIpc } from './transcription'
import { registerRealtimeIpc } from './realtime'
import { registerCaptureIpc } from './capture'
import { listInsights, markRead, markAllRead, deleteInsight } from './proactive/store'
import { getProactiveStatus, runProactiveNow } from './proactive/engine'
import { activateByok, deactivateByok } from './byok'
import { checkForUpdates } from './updater'
import { getFocusStatus, listSessions as listFocusSessions, todaySummary } from './focus/engine'
import { registerFileIndexIpc } from './fileIndex'

const BYOK_FIELDS: Record<string, ByokProvider> = {
  byokOpenAI: 'openai',
  byokAnthropic: 'anthropic',
  byokGemini: 'gemini',
  byokDeepgram: 'deepgram'
}

// Settings the renderer is allowed to write. Backend URL overrides (pythonApiUrl /
// rustApiUrl) and the byok* secrets are deliberately excluded: URL overrides are
// env-var only (a renderer must not be able to repoint where credentials are sent),
// and byok keys are routed to the encrypted secret store, never settings.json.
const RENDERER_WRITABLE = new Set<string>([
  'hotkey', 'floatingBarVisible', 'floatingBarPosition', 'rewindEnabled', 'rewindIntervalMs',
  'retentionDays', 'transcriptionLanguage', 'launchAtLogin', 'fontScale', 'proactiveEnabled',
  'proactiveIntervalMs', 'proactiveNotifications', 'focusEnabled', 'focusGlow',
  'focusAnalysisDelayMs', 'focusCooldownMs', 'realtimeProvider', 'ttsEnabled', 'ttsVoice',
  'customVocabulary', 'aiModel', 'updateChannel', 'hasOnboarded', 'byokActive'
])

// Provider secrets and backend-URL overrides are never sent to the renderer (the
// renderer cannot write them either; URL overrides are env-var only).
function withoutByok(s: AppSettings): AppSettings {
  return {
    ...s,
    byokOpenAI: '',
    byokAnthropic: '',
    byokGemini: '',
    byokDeepgram: '',
    pythonApiUrl: '',
    rustApiUrl: ''
  }
}

// rewind:image / rewind:thumbnail read a file off disk by frame id. Confirm the
// stored path still resolves under the rewind data dir before reading it, so a
// tampered/poisoned path column can't become an arbitrary-file read.
function underRewindRoot(p: string): boolean {
  // realpath both sides so a symlink/junction whose path is inside the rewind dir but
  // resolves outside it is caught (consistent with fileIndex's confine).
  try {
    const root = realpathSync(rewindRoot())
    const rp = realpathSync(p)
    return rp === root || rp.startsWith(root + sep)
  } catch {
    return false
  }
}

export function registerIpc(): void {
  // One-time migration off any pre-encryption plaintext BYOK keys in settings.json.
  migrateLegacyByokKeys()
  registerApiIpc()
  registerTranscriptionIpc()
  registerRealtimeIpc()
  registerCaptureIpc()
  registerFileIndexIpc()

  ipcMain.handle('auth:get-state', () => getAuthState())
  ipcMain.on('auth:sign-in', (_e, provider: 'google' | 'apple') => startSignIn(provider))
  ipcMain.on('auth:sign-out', () => signOut())
  // No 'auth:get-token' channel: the renderer never needs the raw token. Every
  // authenticated call goes through the api:* proxy, which attaches the token in the
  // main process. A token-minting channel would let a compromised renderer read the
  // Bearer token directly and replay it.

  ipcMain.handle('settings:get', () => withoutByok(settings.get()))
  ipcMain.handle('settings:set', (_e, partial: Record<string, unknown>) => {
    const input = partial && typeof partial === 'object' ? partial : {}
    const byok: Partial<ByokKeys> = {}
    const clean: Record<string, unknown> = {}
    for (const [key, value] of Object.entries(input)) {
      const provider = BYOK_FIELDS[key]
      if (provider) {
        if (typeof value === 'string') byok[provider] = value
      } else if (RENDERER_WRITABLE.has(key)) {
        clean[key] = value
      }
      // pythonApiUrl / rustApiUrl / unknown keys are intentionally dropped.
    }
    if (Object.keys(byok).length) setByokKeys(byok)
    const next = settings.set(clean as Partial<AppSettings>)
    rebuildTrayMenu()
    return withoutByok(next)
  })

  ipcMain.on('floating:set-size', (_e, size: { width: number; height: number }) => {
    resizeFloatingBar(size.width, size.height)
  })
  ipcMain.on('floating:hide', () => {
    toggleFloatingBar(false)
    rebuildTrayMenu()
  })
  ipcMain.on('floating:open-main', (_e, page?: string) => {
    const win = createMainWindow()
    if (page) win.webContents.send('app:navigate', page)
  })
  ipcMain.on('floating:focus', () => {
    getFloatingBar()?.focus()
  })

  ipcMain.handle('rewind:list', (_e, day: string | null, limit: number, offset: number) =>
    listFrames(day, limit ?? 200, offset ?? 0)
  )
  ipcMain.handle('rewind:days', () => listDays())
  ipcMain.handle('rewind:search', (_e, q: string, limit?: number) => searchFrames(q, limit ?? 60))
  ipcMain.handle('rewind:status', () => getRewindStatus())
  ipcMain.handle('rewind:latest-ocr', (_e, maxAgeMs?: number) => latestOcrText(maxAgeMs ?? 30_000))
  ipcMain.handle('rewind:image', (_e, id: number) => {
    const frame = getFrame(id)
    if (!frame || !underRewindRoot(frame.path)) return null
    try {
      const buf = readFileSync(frame.path)
      return `data:image/jpeg;base64,${buf.toString('base64')}`
    } catch {
      return null
    }
  })
  ipcMain.handle('rewind:thumbnail', (_e, id: number, width: number) => {
    const frame = getFrame(id)
    if (!frame || !underRewindRoot(frame.path)) return null
    try {
      const img = nativeImage.createFromPath(frame.path)
      const size = img.getSize()
      const h = Math.round((width / size.width) * size.height)
      return `data:image/jpeg;base64,${img.resize({ width, height: h }).toJPEG(70).toString('base64')}`
    } catch {
      return null
    }
  })

  ipcMain.handle('proactive:list', () => listInsights(100))
  ipcMain.handle('proactive:status', () => getProactiveStatus())
  ipcMain.handle('proactive:run-now', () => runProactiveNow())
  ipcMain.handle('proactive:mark-read', (_e, id: number) => markRead(id))
  ipcMain.handle('proactive:mark-all-read', () => markAllRead())
  ipcMain.handle('proactive:delete', (_e, id: number) => deleteInsight(id))

  ipcMain.handle('focus:status', () => getFocusStatus())
  ipcMain.handle('focus:sessions', () => listFocusSessions(200))
  ipcMain.handle('focus:summary', () => todaySummary())

  ipcMain.handle('byok:status', () => byokStatus())
  ipcMain.handle('byok:activate', () => activateByok())
  ipcMain.handle('byok:deactivate', () => deactivateByok())

  ipcMain.handle('updater:check', () => checkForUpdates(true))

  ipcMain.handle('app:version', () => app.getVersion())
  ipcMain.on('shell:open-external', (_e, url: string) => {
    try {
      const u = new URL(String(url))
      if (u.protocol === 'http:' || u.protocol === 'https:') shell.openExternal(u.toString())
    } catch {
      // ignore malformed or non-web URLs
    }
  })
}
