// Meeting-detection pattern data + pure Tier 1 matching.
//
// The pattern list is UPDATABLE DATA, not code: the bundled default lives in
// ./patterns.json (imported at build time so it always exists), and a user/ops
// override can be dropped at `<userData>/meeting-patterns.json` — it is read at
// runtime and, when valid, replaces the bundled list wholesale. Invalid or
// partial override files fall back to the bundled default (never a crash).
//
// Matching is pure and unit-tested: process snapshots and foreground-window
// reads happen elsewhere (processSnapshot.ts / nativeForeground.ts); this module
// only maps those inputs to matches.
import bundled from './patterns.json'

export type MeetingAppPattern = {
  /** Stable id used for per-app setting overrides (e.g. 'zoom'). */
  id: string
  /** Human name shown in the toast ("Zoom"). */
  name: string
  /** Process image names, lowercase (e.g. 'zoom.exe'). */
  exes: string[]
  /** Substrings matched against packaged (Store) ConsentStore key names,
   *  lowercase (e.g. 'msteams' matches 'MSTeams_8wekyb3d8bbwe'). */
  packaged?: string[]
}

export type MeetingTitlePattern = {
  id: string
  name: string
  /** Regex source tested against the foreground window title. */
  pattern: string
  /** Compiled once at sanitize time — matchTier1 runs on every evaluate. */
  regex: RegExp
}

export type MeetingPatterns = {
  version: number
  apps: MeetingAppPattern[]
  /** Browser exes whose window titles are eligible for title matches. */
  browsers: string[]
  titles: MeetingTitlePattern[]
}

/** A Tier 1 hit: a conferencing app is present (process) or a browser tab looks
 *  like a meeting (title). `exe` is the process to correlate with Tier 2. */
export type Tier1Match = {
  id: string
  name: string
  /** Lowercase image name of the matched process (browser exe for title
   *  matches); null only if the foreground exe couldn't be read. */
  exe: string | null
  via: 'process' | 'title'
}

/** A Tier 1 match confirmed by Tier 2: `tier2Key` is the exact ConsentStore id
 *  (exe basename or packaged key) that shows the app capturing the mic. */
export type AgreedMatch = Tier1Match & { tier2Key: string }

const lower = (s: string): string => s.toLowerCase()

function isStringArray(v: unknown): v is string[] {
  return Array.isArray(v) && v.every((x) => typeof x === 'string')
}

/** Validate an untrusted pattern object. Returns null when the shape is not
 *  usable (caller falls back to the bundled default). Bad regexes in `titles`
 *  drop that entry only. */
export function sanitizePatterns(raw: unknown): MeetingPatterns | null {
  if (typeof raw !== 'object' || raw === null) return null
  const r = raw as Record<string, unknown>
  if (!Array.isArray(r.apps) || !Array.isArray(r.titles) || !isStringArray(r.browsers)) return null
  const apps: MeetingAppPattern[] = []
  for (const a of r.apps as unknown[]) {
    const o = a as Record<string, unknown>
    if (typeof o?.id !== 'string' || typeof o?.name !== 'string' || !isStringArray(o.exes)) continue
    apps.push({
      id: o.id,
      name: o.name,
      exes: o.exes.map(lower),
      ...(isStringArray(o.packaged) ? { packaged: o.packaged.map(lower) } : {})
    })
  }
  const titles: MeetingTitlePattern[] = []
  for (const t of r.titles as unknown[]) {
    const o = t as Record<string, unknown>
    if (typeof o?.id !== 'string' || typeof o?.name !== 'string' || typeof o?.pattern !== 'string')
      continue
    try {
      // Compile once here (also rejects invalid sources) — not per match call.
      titles.push({ id: o.id, name: o.name, pattern: o.pattern, regex: new RegExp(o.pattern) })
    } catch {
      /* drop just this entry */
    }
  }
  if (apps.length === 0 && titles.length === 0) return null
  return { version: typeof r.version === 'number' ? r.version : 0, apps, browsers: r.browsers.map(lower), titles }
}

/** The bundled default — always valid (build-time JSON). */
export function bundledPatterns(): MeetingPatterns {
  // The JSON is checked into the repo; sanitize anyway so a bad edit fails loud
  // in tests rather than silently at runtime.
  const p = sanitizePatterns(bundled)
  if (!p) throw new Error('[meeting] bundled patterns.json is invalid')
  return p
}

/** Basename of a Windows path, lowercase ('C:\\x\\Zoom.exe' → 'zoom.exe'). */
export function exeBasename(path: string | null | undefined): string | null {
  if (!path) return null
  const i = Math.max(path.lastIndexOf('\\'), path.lastIndexOf('/'))
  return lower(i >= 0 ? path.slice(i + 1) : path)
}

export type ForegroundInfo = { exePath: string | null; title: string | null }

/**
 * Tier 1: which known conferencing apps are present right now?
 * - process matches: any snapshot exe name appears in a pattern's `exes`.
 * - title matches: the foreground window is a known browser AND its title
 *   matches a meeting-title regex.
 * `processes` are lowercase image names from the Toolhelp32 snapshot.
 */
export function matchTier1(
  processes: string[],
  foreground: ForegroundInfo,
  patterns: MeetingPatterns
): Tier1Match[] {
  const present = new Set(processes.map(lower))
  const matches: Tier1Match[] = []
  for (const app of patterns.apps) {
    // Packaged (Store) apps are deliberately NOT candidates on presence alone —
    // their ConsentStore id (not a snapshot exe) confirms them in
    // pickAgreedMatch, so 'candidate' isn't permanently true for everyone with
    // Teams installed.
    const exe = app.exes.find((e) => present.has(e))
    if (exe) matches.push({ id: app.id, name: app.name, exe, via: 'process' })
  }
  const fgExe = exeBasename(foreground.exePath)
  if (fgExe && foreground.title && patterns.browsers.includes(fgExe)) {
    for (const t of patterns.titles) {
      if (t.regex.test(foreground.title)) {
        matches.push({ id: t.id, name: t.name, exe: fgExe, via: 'title' })
        break // one title match is enough; the foreground window is one meeting
      }
    }
  }
  return matches
}

/**
 * Tier1+Tier2 agreement: find the first Tier 1 match whose process is ALSO
 * actively capturing the mic per Tier 2. `tier2Ids` are lowercase ConsentStore
 * identifiers: exe basenames for NonPackaged entries, package key names for
 * packaged ones. Packaged apps (Store Teams) match via the pattern's `packaged`
 * substrings against packaged ids.
 */
export function pickAgreedMatch(
  matches: Tier1Match[],
  tier2Ids: string[],
  patterns: MeetingPatterns
): AgreedMatch | null {
  const ids = tier2Ids.map(lower)
  // The Tier 2 id (if any) matching an app pattern's packaged substrings.
  const packagedId = (app: MeetingAppPattern | undefined): string | undefined =>
    app?.packaged?.length ? ids.find((id) => app.packaged!.some((p) => id.includes(p))) : undefined
  for (const m of matches) {
    if (m.exe && ids.includes(m.exe)) return { ...m, tier2Key: m.exe }
    // Same app, packaged install: correlate via the pattern's packaged ids.
    const pkg = packagedId(patterns.apps.find((a) => a.id === m.id))
    if (pkg) return { ...m, tier2Key: pkg }
  }
  // A packaged app capturing the mic with NO unpackaged process match — e.g.
  // Store Teams, whose exe list may not appear in the snapshot under the same
  // name. Treat "packaged id active in Tier 2" + "pattern lists it" as both
  // present and agreeing (the process demonstrably exists — it holds the mic).
  for (const app of patterns.apps) {
    const pkg = packagedId(app)
    if (pkg) return { id: app.id, name: app.name, exe: null, via: 'process', tier2Key: pkg }
  }
  return null
}
