import { app } from 'electron'
import { readFileSync, writeFileSync, renameSync, mkdirSync, rmSync, existsSync } from 'fs'
import { isAbsolute, join } from 'path'
import { homedir } from 'os'
import { EventEmitter } from 'events'
import type { AppSettings } from '../shared/types'

// Linux launch-at-login. Electron's app.setLoginItemSettings/getLoginItemSettings are
// macOS/Windows only (no-ops on Linux), so the Win32 mechanism in index.ts does nothing
// here. The freedesktop.org autostart spec instead reads $XDG_CONFIG_HOME/autostart
// (or ~/.config/autostart)/*.desktop on
// session start, so enabling writes that file and disabling removes it; current state is
// simply whether the file exists.
const CONFIG_HOME =
  process.env.XDG_CONFIG_HOME && isAbsolute(process.env.XDG_CONFIG_HOME)
    ? process.env.XDG_CONFIG_HOME
    : join(homedir(), '.config')
const AUTOSTART_DIR = join(CONFIG_HOME, 'autostart')
const AUTOSTART_FILE = join(AUTOSTART_DIR, 'omi.desktop')

// Prefer $APPIMAGE (set by the AppImage runtime) so autostart relaunches the AppImage
// itself rather than the unpacked binary inside the temporary mount, which disappears
// after exit. Otherwise fall back to the running executable.
function autostartExec(): string {
  return process.env.APPIMAGE || process.execPath
}

function quoteDesktopExec(path: string): string {
  const escaped = path
    .replace(/\\/g, '\\\\')
    .replace(/"/g, '\\"')
    .replace(/\$/g, '\\$')
    .replace(/`/g, '\\`')
    .replace(/%/g, '%%')
  return `"${escaped}"`
}

function autostartDesktopEntry(): string {
  return [
    '[Desktop Entry]',
    'Type=Application',
    'Name=Omi',
    `Exec=${quoteDesktopExec(autostartExec())}`,
    'X-GNOME-Autostart-enabled=true',
    'Hidden=false',
    ''
  ].join('\n')
}

function applyLaunchAtLogin(enabled: boolean): boolean {
  try {
    if (enabled) {
      mkdirSync(AUTOSTART_DIR, { recursive: true })
      writeFileSync(AUTOSTART_FILE, autostartDesktopEntry())
    } else {
      rmSync(AUTOSTART_FILE, { force: true })
    }
    return true
  } catch (e) {
    console.error('settings: applyLaunchAtLogin failed', e)
    return false
  }
}

// Current OS autostart state = does the .desktop file exist.
function launchAtLoginEnabled(): boolean {
  return existsSync(AUTOSTART_FILE)
}

const DEFAULTS: AppSettings = {
  hotkey: 'Control+Shift+Space',
  floatingBarVisible: true,
  rewindEnabled: false,
  rewindIntervalMs: 3000,
  retentionDays: 30,
  transcriptionLanguage: 'en',
  launchAtLogin: false,
  fontScale: 1.0,
  proactiveEnabled: false,
  proactiveIntervalMs: 180000,
  proactiveNotifications: true,
  focusEnabled: false,
  focusGlow: true,
  focusAnalysisDelayMs: 60000,
  focusCooldownMs: 600000,
  realtimeProvider: 'auto',
  ttsEnabled: false,
  ttsVoice: 'marin',
  customVocabulary: [],
  aiModel: 'claude-sonnet-4-6',
  updateChannel: 'stable',
  hasOnboarded: false,
  byokActive: false,
  byokAnthropic: '',
  byokOpenAI: '',
  byokGemini: '',
  byokDeepgram: '',
  pythonApiUrl: '',
  rustApiUrl: ''
}

class SettingsStore extends EventEmitter {
  private data: AppSettings
  private file: string

  constructor() {
    super()
    this.file = join(app.getPath('userData'), 'settings.json')
    this.data = { ...DEFAULTS }
    try {
      this.data = { ...DEFAULTS, ...JSON.parse(readFileSync(this.file, 'utf8')) }
    } catch {
      // first run
    }
    // On Linux the source of truth for autostart is the ~/.config/autostart/.desktop
    // file (the user may have removed it via their DE), so reconcile the stored flag to
    // the actual file state at startup.
    this.data.launchAtLogin = launchAtLoginEnabled()
  }

  get(): AppSettings {
    return { ...this.data }
  }

  set(partial: Partial<AppSettings>): AppSettings {
    const before = this.data
    this.data = { ...this.data, ...partial }
    // Apply the OS autostart side-effect on Linux when the toggle changes. index.ts also
    // calls app.setLoginItemSettings on 'changed', but that is a no-op on Linux, so the
    // .desktop file write/remove must happen here for the Settings toggle to take effect.
    if (partial.launchAtLogin !== undefined && partial.launchAtLogin !== before.launchAtLogin) {
      const applied = applyLaunchAtLogin(this.data.launchAtLogin)
      if (!applied) this.data = { ...this.data, launchAtLogin: launchAtLoginEnabled() }
    }
    try {
      mkdirSync(app.getPath('userData'), { recursive: true })
      // Atomic write: a crash mid-write must not truncate settings.json (which would
      // reset all settings to defaults on next launch).
      const tmp = this.file + '.tmp'
      writeFileSync(tmp, JSON.stringify(this.data, null, 2))
      renameSync(tmp, this.file)
    } catch (e) {
      console.error('settings: persist failed', e)
    }
    this.emit('changed', this.data, before)
    return this.get()
  }
}

export const settings = new SettingsStore()
