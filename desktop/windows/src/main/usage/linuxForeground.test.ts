import { describe, it, expect } from 'vitest'
import {
  parseActiveWindowId,
  parsePidFromXprop,
  parseWindowTitle,
  exePathForPid
} from './linuxForeground'

describe('parseActiveWindowId', () => {
  it('extracts the hex window id', () => {
    expect(parseActiveWindowId('_NET_ACTIVE_WINDOW(WINDOW): window id # 0x3c00007')).toBe(
      '0x3c00007'
    )
  })
  it('returns null when no window is active', () => {
    expect(parseActiveWindowId('_NET_ACTIVE_WINDOW(WINDOW): window id # 0x0')).toBeNull()
  })
  it('returns null on unrelated output', () => {
    expect(parseActiveWindowId('garbage')).toBeNull()
  })
})

describe('parsePidFromXprop', () => {
  it('extracts the pid', () => {
    expect(parsePidFromXprop('_NET_WM_PID(CARDINAL) = 4242')).toBe(4242)
  })
  it('returns null when absent', () => {
    expect(parsePidFromXprop('_NET_WM_PID:  not found.')).toBeNull()
  })
})

describe('parseWindowTitle', () => {
  it('extracts a quoted UTF-8 title', () => {
    expect(parseWindowTitle('_NET_WM_NAME(UTF8_STRING) = "Inbox — Firefox"')).toBe(
      'Inbox — Firefox'
    )
  })
  it('unescapes embedded quotes and backslashes', () => {
    expect(parseWindowTitle('_NET_WM_NAME(UTF8_STRING) = "a \\"b\\" \\\\ c"')).toBe('a "b" \\ c')
  })
  it('returns null when absent', () => {
    expect(parseWindowTitle('_NET_WM_NAME:  not found.')).toBeNull()
  })
})

describe('exePathForPid', () => {
  it('reads /proc/<pid>/exe via the injected reader', () => {
    const read = (p: string): string => (p === '/proc/4242/exe' ? '/usr/bin/firefox' : '')
    expect(exePathForPid(4242, read)).toBe('/usr/bin/firefox')
  })
  it('returns null when the reader throws', () => {
    const read = (): string => {
      throw new Error('ENOENT')
    }
    expect(exePathForPid(4242, read)).toBeNull()
  })
  it('returns null for a null pid', () => {
    expect(exePathForPid(null, () => '/x')).toBeNull()
  })
})
