// Linux active-window support. Pure parsers (tested) + thin shell wrappers
// (untested by design, mirroring userAssistRegistry.ts). Never throws; returns
// degraded values when X11 / xdotool / xprop are unavailable.
import type { ForegroundWindowInfo } from './nativeForeground'
import { execFileSync } from 'child_process'
import { readlinkSync } from 'fs'

// "_NET_ACTIVE_WINDOW(WINDOW): window id # 0x3c00007" -> "0x3c00007"; 0x0 -> null.
export function parseActiveWindowId(out: string): string | null {
  const m = out.match(/window id # (0x[0-9a-fA-F]+)/)
  if (!m) return null
  return /^0x0+$/.test(m[1]) ? null : m[1]
}

// "_NET_WM_PID(CARDINAL) = 4242" -> 4242; missing -> null.
export function parsePidFromXprop(out: string): number | null {
  const m = out.match(/_NET_WM_PID\(CARDINAL\) = (\d+)/)
  return m ? Number(m[1]) : null
}

// '_NET_WM_NAME(UTF8_STRING) = "title"' -> 'title' (xprop C-escapes " and \).
export function parseWindowTitle(out: string): string | null {
  const m = out.match(/_NET_WM_NAME\([^)]*\) = "((?:[^"\\]|\\.)*)"/)
  if (!m) return null
  return m[1].replace(/\\(["\\])/g, '$1')
}

// Pure + injectable so it's testable without a real /proc.
export function exePathForPid(pid: number | null, read: (p: string) => string): string | null {
  if (pid == null) return null
  try {
    const target = read(`/proc/${pid}/exe`)
    return target || null
  } catch {
    return null
  }
}

function xprop(args: string[]): string {
  return execFileSync('xprop', args, { encoding: 'utf8', timeout: 600 })
}

export function linuxAvailable(): boolean {
  if (!process.env.DISPLAY) return false
  try {
    execFileSync('xprop', ['-root', '_NET_SUPPORTED'], { timeout: 600, stdio: 'ignore' })
    return true
  } catch {
    return false
  }
}

function activeWindowId(): string | null {
  try {
    return parseActiveWindowId(xprop(['-root', '_NET_ACTIVE_WINDOW']))
  } catch {
    return null
  }
}

export function getLinuxForegroundInfo(): ForegroundWindowInfo {
  const win = activeWindowId()
  if (!win) return { handle: null, exePath: null, className: null }
  let pid: number | null = null
  try {
    pid = parsePidFromXprop(xprop(['-id', win, '_NET_WM_PID']))
  } catch {
    pid = null
  }
  const exePath = exePathForPid(pid, (p) => readlinkSync(p))
  return { handle: win, exePath, className: null }
}

export function getLinuxForegroundExePath(): string | null {
  return getLinuxForegroundInfo().exePath
}

export function getLinuxForegroundTitle(): string | null {
  const win = activeWindowId()
  if (!win) return null
  try {
    return parseWindowTitle(xprop(['-id', win, '_NET_WM_NAME']))
  } catch {
    return null
  }
}
