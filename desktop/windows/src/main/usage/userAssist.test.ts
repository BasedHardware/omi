import { describe, it, expect } from 'vitest'
import { rot13, parseUserAssistData, friendlyAppName, aggregateUserAssist } from './userAssist'

// Build a 72-byte Win7+ UserAssist Count blob with the fields we read.
function blob(opts: {
  runCount?: number
  focusCount?: number
  focusMs?: number
  lastUsedMs?: number
  len?: number
}): Buffer {
  const b = Buffer.alloc(opts.len ?? 72)
  if (b.length >= 8) b.writeInt32LE(opts.runCount ?? 0, 4)
  if (b.length >= 12) b.writeInt32LE(opts.focusCount ?? 0, 8)
  if (b.length >= 16) b.writeInt32LE(opts.focusMs ?? 0, 12)
  if (b.length >= 68 && opts.lastUsedMs != null) {
    // ms epoch -> Windows FILETIME (100ns ticks since 1601-01-01)
    const ticks = (BigInt(opts.lastUsedMs) + 11644473600000n) * 10000n
    b.writeBigUInt64LE(ticks, 60)
  }
  return b
}

describe('rot13', () => {
  it('decodes UserAssist value names', () => {
    expect(rot13('Puebzr')).toBe('Chrome')
    expect(rot13('qri.jnec.Jnec')).toBe('dev.warp.Warp')
  })
  it('is its own inverse and leaves non-letters untouched', () => {
    expect(rot13(rot13('C:\\Users\\a.b_1!App'))).toBe('C:\\Users\\a.b_1!App')
  })
})

describe('parseUserAssistData', () => {
  it('reads run count, focus count and focus time (ms -> seconds)', () => {
    const p = parseUserAssistData(blob({ runCount: 22, focusCount: 757, focusMs: 43_146_781 }))
    expect(p).not.toBeNull()
    expect(p!.runCount).toBe(22)
    expect(p!.focusCount).toBe(757)
    expect(p!.focusSeconds).toBe(43_147) // rounded
  })
  it('reads last-used from the FILETIME at offset 60', () => {
    const when = Date.UTC(2026, 5, 3, 12, 0, 0)
    const p = parseUserAssistData(blob({ focusMs: 1000, lastUsedMs: when }))
    expect(p!.lastUsed).toBe(when)
  })
  it('returns 0 last-used when the FILETIME is empty', () => {
    expect(parseUserAssistData(blob({ focusMs: 1000 }))!.lastUsed).toBe(0)
  })
  it('returns null for a blob too short to hold focus time', () => {
    expect(parseUserAssistData(Buffer.alloc(8))).toBeNull()
  })
})

describe('friendlyAppName', () => {
  it('drops UEME_ control entries', () => {
    expect(friendlyAppName('UEME_CTLSESSION')).toBeNull()
    expect(friendlyAppName('UEME_CTLCUACount:ctor')).toBeNull()
  })
  it('takes the last segment of a dotted AppUserModelID', () => {
    expect(friendlyAppName('dev.warp.Warp')).toBe('Warp')
    expect(friendlyAppName('Microsoft.VisualStudioCode')).toBe('VisualStudioCode')
    expect(friendlyAppName('Telegram.TelegramDesktop')).toBe('TelegramDesktop')
  })
  it('strips the package-family hash and !App suffix from packaged AUMIDs', () => {
    expect(friendlyAppName('Microsoft.ZuneMusic_8wekyb3d8bbwe!Microsoft.ZuneMusic')).toBe('ZuneMusic')
    expect(friendlyAppName('5319275A.WhatsAppDesktop_cv1g1gvanyjgm!App')).toBe('WhatsAppDesktop')
    // Uses the package-name segment, not the !Activatable id. "SpotifyMusic"
    // still matches an indexed "Spotify" via rankApps' containment rule.
    expect(friendlyAppName('SpotifyAB.SpotifyMusic_zpdnekdrzrea0!Spotify')).toBe('SpotifyMusic')
  })
  it('keeps a bare pseudo-name as-is', () => {
    expect(friendlyAppName('Chrome')).toBe('Chrome')
  })
  it('uses the exe basename (without .exe) for full paths', () => {
    expect(friendlyAppName('C:\\Users\\me\\AppData\\Local\\Programs\\Warp\\Warp.exe')).toBe('Warp')
    expect(friendlyAppName('C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe')).toBe('chrome')
  })
  it('ignores a leading KNOWNFOLDERID GUID segment in a path', () => {
    expect(
      friendlyAppName('{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe')
    ).toBe('powershell')
  })
  it('returns null for empty / GUID-only names', () => {
    expect(friendlyAppName('')).toBeNull()
    expect(friendlyAppName('{9E04CAB2-CC14-11DF-BB8C-A2F1DED72085}')).toBeNull()
  })
})

describe('aggregateUserAssist', () => {
  it('decodes, drops control entries, and sums focus time per friendly name', () => {
    const raw = [
      { name: rot13('UEME_CTLSESSION'), data: blob({ focusMs: 999_999 }) },
      { name: rot13('dev.warp.Warp'), data: blob({ focusMs: 60_000, runCount: 3, lastUsedMs: 100 }) },
      // same friendly name via a full path -> merged
      { name: rot13('C:\\x\\Warp\\Warp.exe'), data: blob({ focusMs: 30_000, runCount: 2, lastUsedMs: 200 }) },
      { name: rot13('Chrome'), data: blob({ focusMs: 120_000, lastUsedMs: 50 }) }
    ]
    const out = aggregateUserAssist(raw)
    const warp = out.find((a) => a.name === 'Warp')!
    const chrome = out.find((a) => a.name === 'Chrome')!
    expect(out.some((a) => a.name.startsWith('UEME'))).toBe(false)
    expect(warp.focusSeconds).toBe(90) // 60s + 30s merged
    expect(warp.runCount).toBe(5)
    expect(warp.lastUsed).toBe(200) // max
    expect(chrome.focusSeconds).toBe(120)
  })
  it('sorts by focus time descending', () => {
    const raw = [
      { name: rot13('Small'), data: blob({ focusMs: 1000 }) },
      { name: rot13('Big'), data: blob({ focusMs: 500_000 }) }
    ]
    expect(aggregateUserAssist(raw).map((a) => a.name)).toEqual(['Big', 'Small'])
  })
})
