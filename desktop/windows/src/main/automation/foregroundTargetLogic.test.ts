import { describe, it, expect } from 'vitest'
import { isSelfExe, isShellWindow, pickTarget } from './foregroundTargetLogic'

const SELF = 'C:\\Apps\\Omi\\omi.exe'

describe('isSelfExe', () => {
  it('matches our own exe by basename, case-insensitively', () => {
    expect(isSelfExe('D:\\other\\path\\OMI.EXE', SELF)).toBe(true)
  })
  it('is false for a different app', () => {
    expect(isSelfExe('C:\\Windows\\notepad.exe', SELF)).toBe(false)
  })
  it('is false for a null path', () => {
    expect(isSelfExe(null, SELF)).toBe(false)
  })
})

describe('pickTarget', () => {
  it('adopts a non-self foreground window', () => {
    expect(pickTarget({ handle: '111', exePath: 'C:\\x\\notepad.exe' }, SELF, null)).toBe('111')
  })
  it('keeps the previous target when the foreground is our own window', () => {
    expect(pickTarget({ handle: '999', exePath: SELF }, SELF, '111')).toBe('111')
  })
  it('keeps the previous target when no handle could be read', () => {
    expect(pickTarget({ handle: null, exePath: 'C:\\x\\notepad.exe' }, SELF, '111')).toBe('111')
  })
  it('updates as the user moves between non-self apps', () => {
    let t: string | null = null
    t = pickTarget({ handle: '111', exePath: 'C:\\x\\notepad.exe' }, SELF, t)
    t = pickTarget({ handle: '222', exePath: 'C:\\y\\slack.exe' }, SELF, t)
    t = pickTarget({ handle: '333', exePath: SELF }, SELF, t) // clicked into Omi
    expect(t).toBe('222')
  })

  it('keeps the previous target when the foreground is a bare shell surface', () => {
    // The desktop, taskbar, etc. are explorer.exe windows with no actionable
    // tree — adopting one left the planner snapshotting an empty window (B2 bug).
    const taskbar = { handle: '65984', exePath: 'C:\\Windows\\explorer.exe', className: 'Shell_TrayWnd' }
    expect(pickTarget(taskbar, SELF, '111')).toBe('111')
  })

  it('still adopts a real File Explorer folder window (CabinetWClass)', () => {
    const folder = { handle: '777', exePath: 'C:\\Windows\\explorer.exe', className: 'CabinetWClass' }
    expect(pickTarget(folder, SELF, '111')).toBe('777')
  })

  it('keeps the real app when a shell surface flashes between it and Omi', () => {
    let t: string | null = null
    t = pickTarget({ handle: '111', exePath: 'C:\\x\\chrome.exe', className: 'Chrome_WidgetWin_1' }, SELF, t)
    t = pickTarget({ handle: '65984', exePath: 'C:\\Windows\\explorer.exe', className: 'WorkerW' }, SELF, t) // clicked desktop/taskbar
    t = pickTarget({ handle: '333', exePath: SELF, className: 'Chrome_WidgetWin_1' }, SELF, t) // clicked into Omi
    expect(t).toBe('111')
  })
})

describe('isShellWindow', () => {
  it('flags desktop/taskbar/start shell classes, case-insensitively', () => {
    for (const c of ['Progman', 'WorkerW', 'Shell_TrayWnd', 'Shell_SecondaryTrayWnd', 'Windows.UI.Core.CoreWindow']) {
      expect(isShellWindow(c)).toBe(true)
    }
  })
  it('flags the Alt-Tab/window-switch transient surfaces (real B2 culprits)', () => {
    // Observed live: switching browser->Omi flashed these explorer.exe windows
    // as foreground, and the tracker latched onto an empty 0-element snapshot.
    expect(isShellWindow('ForegroundStaging')).toBe(true)
    expect(isShellWindow('XamlExplorerHostIslandWindow')).toBe(true)
  })
  it('does not flag real app window classes', () => {
    for (const c of ['Chrome_WidgetWin_1', 'CabinetWClass', 'Notepad', null, undefined, '']) {
      expect(isShellWindow(c)).toBe(false)
    }
  })
})
