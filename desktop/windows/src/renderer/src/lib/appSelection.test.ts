import { describe, it, expect } from 'vitest'
import { rankApps, MAX_APPS } from './appSelection'
import type { IndexedAppRecord, AppUsageRecord } from '../../../shared/types'

function app(name: string, modifiedAt: number, path?: string): IndexedAppRecord {
  return { name, modifiedAt, path: path ?? `C:\\ProgramData\\Microsoft\\Windows\\Start Menu\\Programs\\${name}.lnk` }
}

describe('rankApps', () => {
  it('drops installer cruft and Windows built-ins by name', () => {
    const out = rankApps([
      app('Spotify', 100),
      app('Uninstall Spotify', 200),
      app('Foo Setup', 200),
      app('Check for Updates', 200),
      app('ReadMe', 200),
      app('License', 200),
      app('Help', 200),
      app('Documentation', 200),
      app('User Manual', 200),
      app('Website', 200),
      app('Repair Foo', 200),
      app('Modify Foo', 200),
      app('Windows PowerShell', 300),
      app('Command Prompt (cmd)', 300),
      app('Control Panel', 300),
      app('Task Manager', 300)
    ])
    expect(out.map((a) => a.name)).toEqual(['Spotify'])
  })

  it('drops apps inside System Tools / Administrative Tools folders', () => {
    const sysPath = 'C:\\ProgramData\\Microsoft\\Windows\\Start Menu\\Programs\\System Tools\\Disk Cleanup.lnk'
    const admPath = 'C:\\ProgramData\\Microsoft\\Windows\\Start Menu\\Programs\\Administrative Tools\\Services.lnk'
    const out = rankApps([
      app('Disk Cleanup', 500, sysPath),
      app('Services', 500, admPath),
      app('Slack', 100)
    ])
    expect(out.map((a) => a.name)).toEqual(['Slack'])
  })

  it('dedupes by normalized name keeping the newest', () => {
    const perUser = app('Slack', 100, 'C:\\Users\\me\\AppData\\Roaming\\Microsoft\\Windows\\Start Menu\\Programs\\Slack.lnk')
    const perMachine = app('slack', 900, 'C:\\ProgramData\\Microsoft\\Windows\\Start Menu\\Programs\\slack.lnk')
    const out = rankApps([perUser, perMachine])
    expect(out).toHaveLength(1)
    expect(out[0].modifiedAt).toBe(900)
  })

  it('ranks by modifiedAt descending', () => {
    const out = rankApps([app('A', 100), app('B', 300), app('C', 200)])
    expect(out.map((a) => a.name)).toEqual(['B', 'C', 'A'])
  })

  it('breaks modifiedAt ties by name for stable ordering', () => {
    const out = rankApps([app('Charlie', 100), app('Alpha', 100), app('Bravo', 100)])
    expect(out.map((a) => a.name)).toEqual(['Alpha', 'Bravo', 'Charlie'])
  })

  it('caps at MAX_APPS', () => {
    const many = Array.from({ length: MAX_APPS + 5 }, (_, i) => app(`App${i}`, 1000 - i))
    const out = rankApps(many)
    expect(out).toHaveLength(MAX_APPS)
    expect(out[0].name).toBe('App0')
  })

  it('returns empty for empty input', () => {
    expect(rankApps([])).toEqual([])
  })

  it('respects a custom limit', () => {
    const many = Array.from({ length: 40 }, (_, i) => app(`App${i}`, 1000 - i))
    const out = rankApps(many, 30)
    expect(out).toHaveLength(30)
    expect(out[0].name).toBe('App0')
  })

  it('defaults to MAX_APPS when no limit is given', () => {
    const many = Array.from({ length: 40 }, (_, i) => app(`App${i}`, 1000 - i))
    expect(rankApps(many)).toHaveLength(MAX_APPS)
  })
})

// usage is the THIRD arg (the second is the pre-existing `limit`), passed as
// rankApps(apps, MAX_APPS, usage) so the existing limit call sites stay valid.
function appT(name: string, modifiedAt: number, targetPath?: string): IndexedAppRecord {
  return {
    name,
    path: `C:\\Start\\${name}.lnk`,
    modifiedAt,
    targetPath
  }
}

function usage(exePath: string, totalSeconds: number): AppUsageRecord {
  return {
    exePath,
    exeName: exePath.split('\\').pop() as string,
    category: 'other',
    totalSeconds,
    lastUsed: 0,
    distinctDays: 1
  }
}

describe('rankApps with usage', () => {
  it('ranks used apps by foreground time, above unused apps', () => {
    const apps = [
      appT('Newest Installed', 9999, 'C:\\x\\rare.exe'), // newest mtime, no usage
      appT('Editor', 1, 'C:\\x\\code.exe'),
      appT('Browser', 2, 'C:\\x\\chrome.exe')
    ]
    const u = [usage('C:\\x\\chrome.exe', 3600), usage('C:\\x\\code.exe', 7200)]
    const ranked = rankApps(apps, MAX_APPS, u).map((a) => a.name)
    expect(ranked).toEqual(['Editor', 'Browser', 'Newest Installed'])
  })

  it('matches usage by target-exe basename, case-insensitively', () => {
    const apps = [appT('Code', 1, 'C:\\Apps\\Code.exe'), appT('Other', 2, 'C:\\Apps\\other.exe')]
    const ranked = rankApps(apps, MAX_APPS, [usage('D:\\Different\\CODE.EXE', 500)]).map((a) => a.name)
    expect(ranked[0]).toBe('Code')
  })

  it('falls back to mtime ordering when no usage is provided', () => {
    const apps = [appT('A', 1), appT('B', 9)]
    expect(rankApps(apps).map((a) => a.name)).toEqual(['B', 'A'])
  })
})

// UserAssist-seeded usage rows carry a FRIENDLY NAME in exeName (e.g. "Warp",
// "Chrome", "VisualStudioCode") rather than an exe path, because Windows records
// historical focus time under AppUserModelIDs. rankApps must match these to the
// indexed Start-Menu app NAME, not just the (often-missing) target-exe basename.
function nameUsage(exeName: string, totalSeconds: number): AppUsageRecord {
  return { exePath: `userassist:${exeName}`, exeName, category: 'other', totalSeconds, lastUsed: 0, distinctDays: 1 }
}

describe('rankApps name-matching (UserAssist seed)', () => {
  it('matches a seeded friendly name to an indexed app with no targetPath', () => {
    const apps = [appT('Warp', 5), appT('Notepad', 9)] // no targetPath on either
    const ranked = rankApps(apps, MAX_APPS, [nameUsage('Warp', 600)]).map((a) => a.name)
    expect(ranked[0]).toBe('Warp')
  })

  it('matches by containment when the friendly token differs from the full app name', () => {
    const apps = [appT('Google Chrome', 1), appT('Visual Studio Code', 2), appT('Some Tool', 3)]
    const usage = [nameUsage('Chrome', 7200), nameUsage('VisualStudioCode', 600)]
    const ranked = rankApps(apps, MAX_APPS, usage).map((a) => a.name)
    expect(ranked.slice(0, 2)).toEqual(['Google Chrome', 'Visual Studio Code'])
  })

  it('does not containment-match on very short tokens', () => {
    // "Go" (len 2) must NOT match "Google"; avoids spurious joins.
    const apps = [appT('Google Chrome', 1)]
    expect(rankApps(apps, MAX_APPS, [nameUsage('Go', 9999)])[0].name).toBe('Google Chrome')
    // ...but it still appears (no filter); its usage is 0, proving no false match
    // would have ranked anything else above it (single app).
  })
})

describe('rankApps usage-threshold filter', () => {
  it('with filterUnused, drops apps that have no recorded usage', () => {
    const apps = [appT('Warp', 5), appT('Telegram', 6), appT('Random Updater Tool', 9)]
    const usage = [nameUsage('Warp', 600), nameUsage('Telegram', 120)]
    const ranked = rankApps(apps, MAX_APPS, usage, { filterUnused: true }).map((a) => a.name)
    expect(ranked).toEqual(['Warp', 'Telegram'])
  })

  it('with filterUnused but NO usage data, keeps mtime behavior (no signal to filter on)', () => {
    const apps = [appT('A', 1), appT('B', 9)]
    expect(rankApps(apps, MAX_APPS, [], { filterUnused: true }).map((a) => a.name)).toEqual(['B', 'A'])
  })

  it('without filterUnused, unused apps are still included (ranked below used ones)', () => {
    const apps = [appT('Warp', 1), appT('Figma', 9)] // Figma has newer mtime but no usage
    const ranked = rankApps(apps, MAX_APPS, [nameUsage('Warp', 600)]).map((a) => a.name)
    expect(ranked).toEqual(['Warp', 'Figma'])
  })
})
