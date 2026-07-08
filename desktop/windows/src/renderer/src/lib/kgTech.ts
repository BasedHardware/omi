import type { LocalKGNode, LocalKGNodeType } from '../../../shared/types'

// Minimum number of files of a given technology before we assert the user
// "uses" it. Guards against single stray files creating noise nodes.
export const MIN_FILES_FOR_TECH = 3

export function slugify(label: string): string {
  return label
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
}

export function nodeId(label: string, nodeType: LocalKGNodeType): string {
  return `${slugify(label)}:${nodeType}`
}

// Extension (no dot, lowercase) -> technology label. Deterministic: the ONLY
// source of technology nodes. If no files of an extension exist, that
// technology gets no node — structurally preventing the model from inferring a
// stack from project names (the Flutter/Android hallucination).
export const EXT_TO_TECH: Record<string, string> = {
  ts: 'TypeScript',
  tsx: 'TypeScript',
  js: 'JavaScript',
  jsx: 'JavaScript',
  mjs: 'JavaScript',
  cjs: 'JavaScript',
  py: 'Python',
  rs: 'Rust',
  go: 'Go',
  dart: 'Dart',
  kt: 'Kotlin',
  kts: 'Kotlin',
  gradle: 'Android',
  swift: 'Swift',
  java: 'Java',
  rb: 'Ruby',
  php: 'PHP',
  cs: 'C#',
  cpp: 'C++',
  cc: 'C++',
  cxx: 'C++',
  c: 'C',
  sql: 'SQL'
}

export function deriveTechNodes(byExtension: Record<string, number>, now: number): LocalKGNode[] {
  const counts = new Map<string, number>()
  for (const [ext, n] of Object.entries(byExtension)) {
    const tech = EXT_TO_TECH[ext.toLowerCase().replace(/^\./, '')]
    if (!tech) continue
    counts.set(tech, (counts.get(tech) ?? 0) + n)
  }
  const nodes: LocalKGNode[] = []
  for (const [tech, n] of counts) {
    if (n < MIN_FILES_FOR_TECH) continue
    nodes.push({
      id: nodeId(tech, 'technology'),
      label: tech,
      nodeType: 'technology',
      summary: `${tech} — ${n} file${n === 1 ? '' : 's'} in the local index.`,
      source: 'derived',
      createdAt: now
    })
  }
  return nodes
}

// Last path segment of a folder path (Windows or POSIX), trailing separators
// trimmed. Used to label a folder node by its short name, not its full path.
export function basename(folder: string): string {
  const norm = folder.replace(/[\\/]+$/, '')
  const idx = Math.max(norm.lastIndexOf('\\'), norm.lastIndexOf('/'))
  return idx >= 0 ? norm.slice(idx + 1) : norm
}

// Recently-active working folders -> factual file_group nodes. These are the
// macOS-style recency atoms ("what you're working on now"), stated as facts —
// NOT LLM-inferred "projects". Deduped by basename.
export function deriveFolderNodes(
  folders: { folder: string; recentCount: number; lastModified?: number }[],
  now: number
): LocalKGNode[] {
  const seen = new Set<string>()
  const out: LocalKGNode[] = []
  for (const f of folders) {
    const label = basename(f.folder)
    if (!label) continue
    const id = nodeId(label, 'file_group')
    if (seen.has(id)) continue
    seen.add(id)
    const n = f.recentCount
    out.push({
      id,
      label,
      nodeType: 'file_group',
      summary: `Recently active folder "${label}" — ${n} file${n === 1 ? '' : 's'} modified in the last 30 days (${f.folder}).`,
      source: 'files',
      createdAt: now
    })
  }
  return out
}

export function deriveAppNodes(apps: string[], now: number): LocalKGNode[] {
  const seen = new Set<string>()
  const nodes: LocalKGNode[] = []
  for (const name of apps) {
    const label = name.trim()
    if (!label) continue
    const id = nodeId(label, 'app')
    if (seen.has(id)) continue
    seen.add(id)
    nodes.push({
      id,
      label,
      nodeType: 'app',
      summary: `Installed application: ${label}.`,
      source: 'apps',
      createdAt: now
    })
  }
  return nodes
}
