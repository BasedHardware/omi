import { deriveTechNodes, deriveAppNodes, deriveFolderNodes } from './kgTech'
import { rankApps } from './appSelection'
import { mergeGraph, parseGraphResponse } from './kgGraph'
import { buildSynthesisPrompt, buildOverviewPrompt } from './kgSynthesisPrompt'
import { desktopApi, omiApi } from './apiClient'
import type { LocalKGNode, LocalKGStatus } from '../../../shared/types'
import type { Memory } from '../hooks/useMemories'

const SYNTH_MODEL = 'claude-haiku-4-5-20251001'
const STALE_MS = 12 * 60 * 60 * 1000

type ChatCompletion = { choices?: { message?: { content?: string } }[] }

// Fetch up to 200 memory contents (best-effort). Memories are the macOS app's
// primary MEANING source (they already absorb the Gmail/Notes/import facts).
async function fetchMemoryStrings(): Promise<string[]> {
  try {
    const r = await omiApi.get('/v3/memories', { params: { limit: 200, offset: 0 } })
    const data = r.data as { memories?: Memory[] } | Memory[]
    const list = Array.isArray(data) ? data : (data.memories ?? [])
    return list.map((m) => m.content).filter((c): c is string => typeof c === 'string' && !!c.trim())
  } catch {
    return []
  }
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

    let parsed = { nodes: [], edges: [] } as ReturnType<typeof parseGraphResponse>
    try {
      const res = await desktopApi.post(
        '/v2/chat/completions',
        {
          model: SYNTH_MODEL,
          stream: false,
          messages: [{ role: 'user', content: buildSynthesisPrompt(digest, memories) }]
        },
        { timeout: 60_000 }
      )
      const content = (res.data as ChatCompletion)?.choices?.[0]?.message?.content ?? ''
      parsed = parseGraphResponse(content)
    } catch (e) {
      console.warn('[kg] synthesis LLM call failed; saving deterministic floor only', e)
    }

    const graph = mergeGraph([...tech, ...appNodes, ...folderNodes], parsed, now)

    // Background augmentation: synthesize a short grounded "overview" card from
    // the graph + memories so the chat floor serves a coherent natural-language
    // summary instantly — the model work happens here, off the chat hot path, so
    // it never adds latency. Best-effort: a failure just means no card this build.
    let cardNode: LocalKGNode | null = null
    try {
      const entityNodes = graph.nodes.filter((n) =>
        ['project', 'person', 'org', 'interest', 'technology'].includes(n.nodeType)
      )
      const res = await desktopApi.post(
        '/v2/chat/completions',
        {
          model: SYNTH_MODEL,
          stream: false,
          messages: [{ role: 'user', content: buildOverviewPrompt(entityNodes, memories) }]
        },
        { timeout: 60_000 }
      )
      const text = ((res.data as ChatCompletion)?.choices?.[0]?.message?.content ?? '').trim()
      if (text) {
        cardNode = {
          id: 'overview:card',
          label: 'Overview',
          nodeType: 'card',
          summary: text,
          source: 'derived',
          createdAt: now
        }
      }
    } catch (e) {
      console.warn('[kg] overview card synthesis failed; saving graph without it', e)
    }

    const finalGraph = cardNode
      ? { nodes: [...graph.nodes, cardNode], edges: graph.edges }
      : graph
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
