import type { IndexedAppRecord, AppUsageRecord } from '../../../shared/types'

// How many apps become memories/modules. Matches the ~9 modules the macOS app
// showed on its onboarding brain map, and keeps us from spamming the memory
// store with hundreds of Start-Menu shortcuts.
export const MAX_APPS = 10

// Substrings (case-insensitive) that mark a Start-Menu shortcut as installer
// cruft or a Windows built-in rather than an app the user actually "uses".
// Substring (not exact) match is deliberate: real Start-Menu entries read
// "Uninstall Foo", "Foo Setup", "Windows PowerShell", "Check for Updates".
// It can over-match (e.g. an app literally named "...Help..."), which is an
// acceptable trade for keeping the module list clean.
const DENY_SUBSTRINGS = [
  'uninstall',
  'setup',
  'update',
  'readme',
  'license',
  'help',
  'documentation',
  'manual',
  'website',
  'repair',
  'modify',
  // Non-English installer/uninstaller verbs (es/fr/de/pt). Real Start-Menu cruft
  // ships localized — e.g. "Desinstalar Telegram". Recorded usage is the PRIMARY
  // filter now (see rankApps filterUnused); this list is only the backstop for the
  // opt-out / no-usage path, so a little over-matching is fine.
  'desinstal', // es/pt desinstalar
  'désinstall', // fr désinstaller
  'deinstall', // de deinstallieren
  'instalar', // es/pt instalar
  'installer', // fr/en installer
  'installieren', // de
  'actualiz', // es actualizar
  'aktualisier', // de aktualisieren
  'mise à jour', // fr update
  // Driver / updater / redistributable utilities (e.g. "Intel Driver & Support
  // Assistant"). Multilingual driver synonyms included.
  'driver',
  'controlador', // es driver
  'pilote', // fr driver
  'treiber', // de driver
  'updater',
  'redistributable',
  // Windows built-ins
  'cmd',
  'powershell',
  'control panel',
  'task manager',
  'file explorer'
]

// Start-Menu folders whose contents are OS/dev tooling, not user apps. Matched
// against the shortcut's path so every entry inside them is excluded. Windows
// Kits (SDK) and "Visual Studio Tools" dump ~18 tool shortcuts (verifiers, cert
// kits, native-tools prompts) that rank high by install recency and drown real
// apps; deny the folders, not each name. (The real "Visual Studio" app lives one
// level up, outside "Visual Studio Tools", so it is kept.)
const DENY_FOLDERS = [
  '\\system tools\\',
  '\\administrative tools\\',
  '/system tools/',
  '/administrative tools/',
  '\\windows kits\\',
  '/windows kits/',
  '\\visual studio tools\\',
  '/visual studio tools/'
]

function normalizeName(name: string): string {
  return name.trim().toLowerCase()
}

function isDenied(app: IndexedAppRecord): boolean {
  const name = normalizeName(app.name)
  if (!name) return true
  if (DENY_SUBSTRINGS.some((term) => name.includes(term))) return true
  const path = app.path.toLowerCase()
  if (DENY_FOLDERS.some((folder) => path.includes(folder))) return true
  return false
}

// Lowercased exe basename, used to join an indexed app's resolved .lnk target to
// an app_usage row regardless of install location or casing.
function exeKey(p: string | undefined): string {
  if (!p) return ''
  const base = p.split(/[\\/]/).pop() ?? ''
  return base.toLowerCase()
}

// Collapse a name to an alphanumeric token for fuzzy app<->usage matching:
// lowercase, drop everything non-alphanumeric, drop a trailing "exe". Bridges the
// gap between an indexed app NAME ("Google Chrome", "Visual Studio Code") and the
// friendly token a UserAssist seed carries in exeName ("Chrome", "VisualStudioCode")
// or a live row's exe basename ("chrome.exe"). All map into one space:
// googlechrome / chrome / visualstudiocode / code.
function nameToken(s: string | undefined): string {
  if (!s) return ''
  return s
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '')
    .replace(/exe$/, '')
}

// True when two name tokens refer to the same app: exact, or one contains the
// other (e.g. "chrome" in "googlechrome", "telegram" in "telegramdesktop").
// Containment requires the shorter token be >= 4 chars so noise like "go" can't
// match "google".
function tokenMatch(a: string, b: string): boolean {
  if (!a || !b) return false
  if (a === b) return true
  const [short, long] = a.length <= b.length ? [a, b] : [b, a]
  return short.length >= 4 && long.includes(short)
}

// Pure, deterministic. Given the raw indexed apps, returns the subset to turn
// into "Uses <App>" memories:
//   1. drop installer cruft / built-ins (denylist),
//   2. rank by real foreground time (joined from `usage` via the app's resolved
//      target-exe basename) desc, then by modifiedAt desc (the .lnk mtime) as a
//      fallback for apps with no recorded usage,
//   3. dedupe by normalized name (Start Menu lists per-user AND per-machine
//      shortcuts for the same app) keeping the highest-ranked,
//   4. cap at `limit` (default MAX_APPS).
// Ties break by name (asc) so the output is stable regardless of input ordering.
// `usage` defaults to [] — with no usage data, ordering is pure mtime (today's
// behavior).
//
// `opts.filterUnused` (used by the brain-map build) makes recorded usage the
// PRIMARY filter: when usage data exists, apps with no matching usage are dropped
// entirely (so onboarding shows the handful of apps the user actually uses, ~9 on
// macOS, not 30 install-recency guesses). With no usage data it's a no-op — there
// is no signal to filter on, so we keep the denylist + mtime fallback.
export function rankApps(
  apps: IndexedAppRecord[],
  limit = MAX_APPS,
  usage: AppUsageRecord[] = [],
  opts: { filterUnused?: boolean } = {}
): IndexedAppRecord[] {
  // Match usage rows to apps two ways: exact target-exe basename (live rows with
  // a resolved .lnk target) OR fuzzy name token (UserAssist seeds keyed by a
  // friendly name, or live rows whose basename ~ the app name). Each row is
  // counted at most ONCE per app, so the two strategies never double-add.
  const usageRows = usage.map((u) => ({
    exe: exeKey(u.exePath),
    token: nameToken(u.exeName),
    seconds: u.totalSeconds
  }))
  const usageOf = (a: IndexedAppRecord): number => {
    const targetExe = exeKey(a.targetPath)
    const appToks = [nameToken(a.name), nameToken(targetExe)].filter(Boolean)
    let total = 0
    for (const row of usageRows) {
      const hit =
        (!!targetExe && row.exe === targetExe) || appToks.some((at) => tokenMatch(at, row.token))
      if (hit) total += row.seconds
    }
    return total
  }

  const hasUsage = usage.length > 0
  const ranked = apps
    .filter((a) => !isDenied(a))
    .filter((a) => !(opts.filterUnused && hasUsage) || usageOf(a) > 0)
    .slice()
    .sort(
      (a, b) => usageOf(b) - usageOf(a) || b.modifiedAt - a.modifiedAt || a.name.localeCompare(b.name)
    )

  const seen = new Set<string>()
  const deduped: IndexedAppRecord[] = []
  for (const app of ranked) {
    const key = normalizeName(app.name)
    if (seen.has(key)) continue
    seen.add(key)
    deduped.push(app)
    if (deduped.length >= limit) break
  }
  return deduped
}
