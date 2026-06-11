import type { FileIndexDigest } from '../../../shared/types'
import { basename } from './kgTech'

// How many memory lines to feed the synthesizer (keeps the prompt bounded).
const MAX_MEMORY_LINES = 60

// Build the one-shot synthesis prompt. The model returns a semantic entity graph
// as {nodes:[{label,type,summary,aliases?,sourceRefs?}], edges:[{source,target,label}]}.
// Technologies are NOT requested here — they are derived deterministically from
// real file extensions and merged in afterwards, so the model can't invent a
// tech stack (the Flutter/Android hallucination guard).
export function buildSynthesisPrompt(digest: FileIndexDigest, memories: string[]): string {
  const folders = digest.activeFolders
    .map((f) => `- ${basename(f.folder)} (${f.recentCount} recent files) — ${f.folder}`)
    .join('\n')
  const mems = memories
    .slice(0, MAX_MEMORY_LINES)
    .map((m) => `- ${m}`)
    .join('\n')
  return [
    'You build a small knowledge graph of the user from evidence about their machine.',
    'Output ONLY one raw JSON object: {"nodes":[...],"edges":[...]}. No prose, no fences.',
    'Node: {"label","type","summary","aliases"?,"sourceRefs"?}. type is one of:',
    'project | person | org | interest. (Do NOT emit technology, app, or file_group',
    'nodes — technologies come from real file extensions, and apps + active folders',
    'are already added as nodes automatically. Do not recreate them.)',
    'Edge: {"source","target","label"} where source/target are node labels and label',
    'is a short relationship like "works on", "collaborates with", "interested in".',
    'You MAY reference the existing app and folder names below as edge endpoints to',
    'relate a project/person to them — e.g. {"source":"<project>","target":"<app>",',
    '"label":"uses"} or {"source":"<project>","target":"<folder>","label":"lives in"}.',
    '',
    'RULES:',
    '- Emit a "project" node ONLY if it is supported by a memory below OR a',
    '  recently-active folder below. Never invent projects from nothing.',
    '- One atomic fact per node summary. Put the justifying folder path or memory',
    '  text in sourceRefs.',
    '- Prefer fewer, well-evidenced nodes over many speculative ones.',
    '',
    'RECENTLY-ACTIVE WORKING FOLDERS (already nodes — relate to them via edges):',
    folders || '(none)',
    '',
    'MEMORIES (things the user has saved/said):',
    mems || '(none)',
    '',
    'INSTALLED APPS (already nodes — relate to them via edges):',
    digest.apps.slice(0, 20).join(', ') || '(none)'
  ].join('\n')
}

// Build the prompt for the background "overview" card: a short, grounded
// natural-language summary of the user, synthesized once per build and served to
// the chat floor instantly (no hot-path LLM). Same anti-hallucination discipline
// as the graph synthesis — summarize ONLY the evidence, never invent facts.
export function buildOverviewPrompt(
  nodes: { label: string; nodeType: string; summary: string }[],
  memories: string[]
): string {
  const entities = nodes.map((n) => `- ${n.label} (${n.nodeType}): ${n.summary}`).join('\n')
  const mems = memories
    .slice(0, MAX_MEMORY_LINES)
    .map((m) => `- ${m}`)
    .join('\n')
  return [
    'You write a short factual profile of the user from the evidence below.',
    'Output ONLY 2-4 plain sentences. No markdown, no lists, no preamble.',
    'Summarize what the user works on, the technologies they use, and who or what',
    'they collaborate with or are interested in — using ONLY the evidence below.',
    'Do NOT invent projects, technologies, employers, or relationships not present.',
    '',
    'KNOWN ENTITIES (label (type): summary):',
    entities || '(none)',
    '',
    'MEMORIES (things the user has saved/said):',
    mems || '(none)'
  ].join('\n')
}
