import type { UsageCategory } from '../../shared/types'

// Deterministic exe-basename → coarse category map. Matched against the lowercased
// basename without extension. Substring match so variants ("chrome", "chrome_proxy")
// land in the same bucket. Unknown apps fall through to 'other'.
const RULES: ReadonlyArray<[UsageCategory, readonly string[]]> = [
  ['browser', ['chrome', 'msedge', 'firefox', 'opera', 'brave', 'arc', 'vivaldi']],
  ['editor', ['code', 'devenv', 'idea', 'pycharm', 'webstorm', 'sublime', 'notepad++', 'rider', 'cursor']],
  ['comms', ['slack', 'discord', 'teams', 'zoom', 'telegram', 'whatsapp', 'outlook']],
  ['media', ['spotify', 'vlc', 'wmplayer', 'itunes', 'foobar2000']]
]

export function categorize(exeName: string): UsageCategory {
  const base = exeName.toLowerCase().replace(/\.exe$/, '')
  if (!base) return 'other'
  for (const [cat, keys] of RULES) {
    if (keys.some((k) => base.includes(k))) return cat
  }
  return 'other'
}
