// Pure parsing of Windows UserAssist registry data. The registry READ (native,
// per-machine) lives in userAssistRegistry.ts; everything here is deterministic
// and unit-tested so the fiddly bits (ROT13, the binary blob layout, AUMID ->
// friendly name) are covered without a Windows box.
//
// UserAssist records per-user, historical app usage under
//   HKCU\...\Explorer\UserAssist\{GUID}\Count
// with ROT13-encoded value names (an exe path or an AppUserModelID) and a binary
// blob carrying run count + focus count + focus time. We use it ONCE at
// onboarding to seed app_usage so the first brain-map build ranks apps by REAL
// historical foreground time instead of install-recency noise (see the
// spike findings in the app-usage-ranking work).

// Offsets into the Win7+ Count blob (72 bytes). Earlier fields exist on shorter
// blobs; the FILETIME only on full-length ones.
const OFF_RUN_COUNT = 4
const OFF_FOCUS_COUNT = 8
const OFF_FOCUS_MS = 12
const OFF_LAST_USED_FILETIME = 60
// 100ns ticks between 1601-01-01 (FILETIME epoch) and 1970-01-01 (Unix epoch).
const FILETIME_UNIX_OFFSET_MS = 11_644_473_600_000n

export type ParsedUserAssist = {
  runCount: number
  focusCount: number
  focusSeconds: number
  // ms epoch of last execution, or 0 when absent/zeroed.
  lastUsed: number
}

export type UserAssistApp = {
  // Friendly app token (e.g. "Warp", "Chrome", "VisualStudioCode"). Matched
  // against indexed Start-Menu app names by appSelection.rankApps.
  name: string
  focusSeconds: number
  runCount: number
  lastUsed: number
}

// Caesar-shift by 13. Letters only; everything else (digits, '.', '\', '!', ':')
// passes through unchanged — exactly how Windows encodes UserAssist names.
export function rot13(s: string): string {
  return s.replace(/[a-zA-Z]/g, (ch) => {
    const base = ch <= 'Z' ? 65 : 97
    return String.fromCharCode(((ch.charCodeAt(0) - base + 13) % 26) + base)
  })
}

// Parse a Count value's binary blob. Returns null when it's too short to even
// hold the focus-time field (control/sentinel entries can be tiny).
export function parseUserAssistData(data: Buffer): ParsedUserAssist | null {
  if (data.length < OFF_FOCUS_MS + 4) return null
  const focusMs = data.readInt32LE(OFF_FOCUS_MS)
  let lastUsed = 0
  if (data.length >= OFF_LAST_USED_FILETIME + 8) {
    const ticks = data.readBigUInt64LE(OFF_LAST_USED_FILETIME)
    if (ticks > 0n) lastUsed = Number(ticks / 10_000n - FILETIME_UNIX_OFFSET_MS)
  }
  return {
    runCount: data.readInt32LE(OFF_RUN_COUNT),
    focusCount: data.readInt32LE(OFF_FOCUS_COUNT),
    focusSeconds: Math.round(focusMs / 1000),
    lastUsed
  }
}

function looksLikeGuid(s: string): boolean {
  return /^\{[0-9a-f-]{36}\}$/i.test(s)
}

// Reduce a decoded UserAssist value name to a friendly app token, or null when
// it isn't an app (UEME_ control entries, empty/GUID-only names).
//
// Three shapes occur in the wild (confirmed by spike):
//   - full/known-folder path:  C:\...\Warp.exe  or  {GUID}\...\powershell.exe
//   - packaged AUMID:          Microsoft.ZuneMusic_8wekyb3d8bbwe!Microsoft.ZuneMusic
//   - bare pseudo-name:        Chrome
export function friendlyAppName(rawName: string): string | null {
  const name = rawName.trim()
  if (!name) return null
  if (name.startsWith('UEME_')) return null

  // Path (incl. KNOWNFOLDERID-prefixed): take the basename, drop a .exe suffix.
  if (name.includes('\\') || name.includes('/')) {
    const base = name.split(/[\\/]/).pop() ?? ''
    const stem = base.replace(/\.exe$/i, '').trim()
    return stem && !looksLikeGuid(stem) ? stem : null
  }

  // AUMID / pseudo-name: drop the !Activatable suffix, strip the package-family
  // hash (_8wekyb3d8bbwe), then take the last dotted segment.
  const beforeBang = name.split('!')[0]
  const noHash = beforeBang.replace(/_[a-z0-9]+$/i, '')
  const seg = noHash.split('.').filter(Boolean).pop() ?? ''
  return seg && !looksLikeGuid(seg) ? seg : null
}

// Decode raw {name, data} registry pairs into per-app usage, merged by friendly
// name (Windows can list the same app under both an exe path and an AUMID) and
// sorted by focus time desc.
export function aggregateUserAssist(raw: { name: string; data: Buffer }[]): UserAssistApp[] {
  const byName = new Map<string, UserAssistApp>()
  for (const { name, data } of raw) {
    const friendly = friendlyAppName(rot13(name))
    if (!friendly) continue
    const parsed = parseUserAssistData(data)
    if (!parsed) continue
    const existing = byName.get(friendly)
    if (existing) {
      existing.focusSeconds += parsed.focusSeconds
      existing.runCount += parsed.runCount
      existing.lastUsed = Math.max(existing.lastUsed, parsed.lastUsed)
    } else {
      byName.set(friendly, {
        name: friendly,
        focusSeconds: parsed.focusSeconds,
        runCount: parsed.runCount,
        lastUsed: parsed.lastUsed
      })
    }
  }
  return [...byName.values()].sort((a, b) => b.focusSeconds - a.focusSeconds)
}
