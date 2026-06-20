// Maps a knowledge-graph node to a hex color. The brain map uses three fixed
// categories, NOT a per-type rainbow:
//   - apps you use      → purple
//   - your languages    → blue
//   - everything else    → orange (people, places, orgs, memory concepts, …)
// The fixed user/center node is always white.
//
// Category is derived from the node id, not nodeType alone: nodeType is
// ambiguous (onboarding languages are 'concept', onboarding apps are 'thing',
// and the server KG reuses those types for unrelated entities). The id prefixes
// (`language_`, `app_`) and the local-KG `:app` suffix / `app` type are the
// stable signals across both the onboarding floor graph and the server KG.
const PURPLE = '#a855f7' // apps
const BLUE = '#0a84ff' // languages
const ORANGE = '#ff9f0a' // everything else

export function nodeColor(nodeType: string, isFixed: boolean, id?: string): string {
  if (isFixed) return '#ffffff'
  if (isLanguageNode(id)) return BLUE
  if (isAppNode(nodeType, id)) return PURPLE
  return ORANGE
}

function isLanguageNode(id?: string): boolean {
  return id?.startsWith('language_') ?? false
}

function isAppNode(nodeType: string, id?: string): boolean {
  if (nodeType === 'app') return true // local KG app node
  return id?.startsWith('app_') || id?.endsWith(':app') || false // onboarding / local KG ids
}
