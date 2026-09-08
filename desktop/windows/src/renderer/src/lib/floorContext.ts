import type { ContextSection } from './localAgentProtocol'

// The kinds of section the deterministic floor can produce. `kind` lets the
// intent router reorder sections without string-matching on headings.
export type FloorKind = 'overview' | 'relationships' | 'tech' | 'apps' | 'entities' | 'folders'
export type KindedSection = ContextSection & { kind: FloorKind }

// Tier 1 — surface the labeled relationships the background synthesis built.
// `kgQueryNodes` already returns incident edges; render them as readable lines
// using each node's label. Edges whose endpoints aren't in the node set are
// dropped (dangling after node truncation), so we never emit "undefined" lines.
export function relationshipItems(
  nodes: { id: string; label: string }[],
  edges: { sourceId: string; targetId: string; label: string }[]
): string[] {
  const labelById = new Map(nodes.map((n) => [n.id, n.label]))
  const items: string[] = []
  for (const e of edges) {
    const source = labelById.get(e.sourceId)
    const target = labelById.get(e.targetId)
    if (!source || !target) continue
    items.push(`${source} — ${e.label} → ${target}`)
  }
  return items
}

// Tier 2 — deterministic intent router. Maps the user's question to the floor
// section kinds it's about, so the chat leads with the relevant context (which
// also protects it from formatContextBlock's end-trimming). No LLM: a keystroke
// can't add latency. Evaluated in a fixed specificity order so multi-match
// questions lead with the most specific kind.
const INTENT_RULES: { kind: FloorKind; re: RegExp }[] = [
  { kind: 'relationships', re: /\b(relate[ds]?|related|relationship|connect|depend|between|tied|link)/i },
  { kind: 'tech', re: /\b(language|languages|tech|stack|framework|programming|coding|written in|code in)/i },
  { kind: 'apps', re: /\b(app|apps|editor|ide|tool|tooling|program|software)\b/i },
  { kind: 'folders', re: /\b(folder|folders|directory|directories|where.*(file|save|stor))/i },
  { kind: 'entities', re: /\b(project|projects|working on|building|who|people|person|team|colleague|client|company|org)/i }
]

export function routeIntent(userText: string): FloorKind[] {
  return INTENT_RULES.filter((r) => r.re.test(userText)).map((r) => r.kind)
}

// Reorder the floor sections so question-relevant kinds lead (in intent order),
// with the remaining sections keeping their default order. Strips the `kind` tag
// so the result is a plain ContextSection[] for formatContextBlock.
export function orderFloorSections(
  sections: KindedSection[],
  userText: string
): ContextSection[] {
  const intents = routeIntent(userText)
  const matched = intents
    .map((k) => sections.find((s) => s.kind === k))
    .filter((s): s is KindedSection => s !== undefined)
  const rest = sections.filter((s) => !intents.includes(s.kind))
  return [...matched, ...rest].map(({ heading, items }) => ({ heading, items }))
}
