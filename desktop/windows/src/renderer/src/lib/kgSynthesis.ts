import { deriveTechNodes, deriveAppNodes, deriveFolderNodes } from './kgTech'
import { rankApps } from './appSelection'
import { mergeGraph } from './kgGraph'
import type { ParsedGraph } from './kgGraph'
import { omiApi } from './apiClient'
import type { LocalKGNode, LocalKGNodeType, LocalKGStatus } from '../../../shared/types'
import type { Memory } from '../hooks/useMemories'

const STALE_MS = 12 * 60 * 60 * 1000
const MAX_MEMORY_LINES = 60

type ExtractNode = { id?: string; label?: string; node_type?: string; aliases?: string[] }
type ExtractEdge = { source_id?: string; target_id?: string; label?: string }

// Fetch up to 200 memory contents (best-effort). Memories are the macOS app's
// primary MEANING source (they already absorb the Gmail/Notes/import facts).
async function fetchMemoryStrings(): Promise<string[]> {
  try {
    const r = await omiApi.get('/v3/memories', { params: { limit: 200, offset: 0 } })
    const data = r.data as { memories?: Memory[] } | Memory[]
    const list = Array.isArray(data) ? data : (data.memories ?? [])
    return list
      .map((m) => m.content)
      .filter((c): c is string => typeof c === 'string' && !!c.trim())
  } catch {
    return []
  }
}

function mapBackendNodeType(raw: string): LocalKGNodeType | null {
  const t = raw.trim().toLowerCase()
  if (t === 'person') return 'person'
  if (t === 'organization' || t === 'org') return 'org'
  if (t === 'project') return 'project'
  if (t === 'interest') return 'interest'
  if (t === 'place' || t === 'thing' || t === 'concept') return 'interest'
  return null
}

function extractResponseToParsed(nodes: ExtractNode[], edges: ExtractEdge[]): ParsedGraph {
  const idToLabel = new Map<string, string>()
  const parsedNodes: ParsedGraph['nodes'] = []
  for (const n of nodes) {
    const label = typeof n.label === 'string' ? n.label.trim() : ''
    const id = typeof n.id === 'string' ? n.id : ''
    const nodeType = typeof n.node_type === 'string' ? mapBackendNodeType(n.node_type) : null
    if (!label || !nodeType) continue
    if (id) idToLabel.set(id, label)
    parsedNodes.push({
      label,
      nodeType,
      summary: label,
      ...(Array.isArray(n.aliases) && n.aliases.length
        ? { aliases: n.aliases.filter((a): a is string => typeof a === 'string' && !!a.trim()) }
        : {})
    })
  }
  const parsedEdges: ParsedGraph['edges'] = []
  for (const e of edges) {
    const sourceLabel = e.source_id ? idToLabel.get(e.source_id) : undefined
    const targetLabel = e.target_id ? idToLabel.get(e.target_id) : undefined
    const label = typeof e.label === 'string' ? e.label.trim() : 'related to'
    if (!sourceLabel || !targetLabel) continue
    parsedEdges.push({ sourceLabel, targetLabel, label: label || 'related to' })
  }
  return { nodes: parsedNodes, edges: parsedEdges }
}

function buildExtractEvidenceText(
  memories: string[],
  activeFolders: { folder: string; recentCount: number }[],
  apps: string[]
): string {
  const parts = [
    'MEMORIES:',
    ...memories.slice(0, MAX_MEMORY_LINES).map((m) => `- ${m}`),
    '',
    'RECENTLY-ACTIVE WORKING FOLDERS:',
    ...activeFolders.map((f) => `- ${f.folder} (${f.recentCount} recent files)`),
    '',
    'INSTALLED APPS:',
    apps.slice(0, 20).join(', ') || '(none)'
  ]
  return parts.join('\n').slice(0, 40_000)
}

// Build the local knowledge graph the macOS way: a deterministic technology
// FLOOR (real file extensions only — the anti-hallucination guard) plus an
// LLM-synthesized layer of SEMANTIC ENTITIES (project/person/org/interest) and
// labeled relationships, evidenced by memories + recently-active folders. The
// LLM may not invent technologies (those come only from real extensions) and
// may only assert a "project" backed by a memory or an active folder. On ANY
// failure we fall back to saving just the deterministic floor — never throws.
export async function buildLocalGraph(): Promise<LocalKGStatus> {
  const now = Date.now()
  try {
    const digest = await window.omi.kgFileIndexDigest()
    if (digest.totalFiles === 0) return { nodeCount: 0, edgeCount: 0, lastBuiltAt: null }

    const tech = deriveTechNodes(digest.byExtension, now)
    // Apps: pull full records (digest.apps is names-only and can't be ranked),
    // then recency-rank + denylist + cap at 30 before turning them into nodes.
    // Best-effort: an IPC failure just means no app nodes this build.
    let appNodes: ReturnType<typeof deriveAppNodes> = []
    try {
      const appRecords = await window.omi.indexFilesApps(200)
      // Rank by REAL foreground time (live monitor + one-time UserAssist seed) and
      // keep ONLY apps with recorded usage (filterUnused) — onboarding shows the
      // handful the user actually uses (~9 on macOS), not 30 install-recency
      // guesses. With no usage data, rankApps falls back to denylist + mtime.
      const usage = await window.omi.getAppUsage().catch(() => [])
      appNodes = deriveAppNodes(
        rankApps(appRecords, 30, usage, { filterUnused: true }).map((a) => a.name),
        now
      )
    } catch (e) {
      console.warn('[kg] indexFilesApps failed; building without app nodes', e)
    }
    // Recently-active working folders become factual file_group nodes (no LLM).
    const folderNodes = deriveFolderNodes(digest.activeFolders, now)
    const memories = await fetchMemoryStrings()

    let parsed: ParsedGraph = { nodes: [], edges: [] }
    try {
      const res = await omiApi.post(
        '/v1/knowledge-graph/extract',
        {
          text: buildExtractEvidenceText(memories, digest.activeFolders, digest.apps),
          include_existing: false
        },
        { timeout: 60_000 }
      )
      const data = res.data as { nodes?: ExtractNode[]; edges?: ExtractEdge[] }
      parsed = extractResponseToParsed(data.nodes ?? [], data.edges ?? [])
    } catch (e) {
      // Provider/correctness fallback: the saved graph loses its semantic layer and is
      // still stamped fresh, so this must not look like a successful build. The renderer
      // has no recordFallback emitter (see billing.ts), so this is the same structured,
      // loud console record the fallback contract asks for.
      console.error('[kg] fallback', {
        component: 'knowledge_graph',
        from: 'backend_extract',
        to: 'deterministic_floor',
        reason: 'extract_failed',
        outcome: 'degraded',
        error: e instanceof Error ? e.name : 'Error'
      })
    }

    const graph = mergeGraph([...tech, ...appNodes, ...folderNodes], parsed, now)

    // Deterministic overview card from entity summaries — no second LLM call.
    // Keeps chat-floor copy grounded in the same SSOT extract without Haiku.
    let cardNode: LocalKGNode | null = null
    const entityNodes = graph.nodes.filter((n) =>
      ['project', 'person', 'org', 'interest', 'technology'].includes(n.nodeType)
    )
    const summaryBits = entityNodes
      .slice(0, 8)
      .map((n) => (n.summary || n.label).trim())
      .filter(Boolean)
    if (summaryBits.length) {
      cardNode = {
        id: 'overview:card',
        label: 'Overview',
        nodeType: 'card',
        summary: summaryBits.join(' '),
        source: 'derived',
        createdAt: now
      }
    }

    const finalGraph = cardNode ? { nodes: [...graph.nodes, cardNode], edges: graph.edges } : graph
    await window.omi.kgSaveGraph(finalGraph)
    return {
      nodeCount: finalGraph.nodes.length,
      edgeCount: finalGraph.edges.length,
      lastBuiltAt: now
    }
  } catch (e) {
    console.warn('[kg] buildLocalGraph failed', e)
    return { nodeCount: 0, edgeCount: 0, lastBuiltAt: null }
  }
}

// Lazy trigger from the chat side (no Settings.tsx coupling). Synthesis now costs
// an LLM round-trip again, so rebuild only when the graph is empty or older than
// STALE_MS — not on every launch. Fire-and-forget; never blocks chat.
export async function maybeBuildLocalGraph(): Promise<void> {
  try {
    const status = await window.omi.kgStatus()
    const stale = !status.lastBuiltAt || Date.now() - status.lastBuiltAt > STALE_MS
    if (status.nodeCount === 0 || stale) void buildLocalGraph()
  } catch {
    // Best-effort; never blocks chat.
  }
}
