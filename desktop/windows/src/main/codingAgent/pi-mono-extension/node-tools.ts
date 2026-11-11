// Windows port of desktop/macos/agent/src/runtime/node-tools.ts.
//
// Pure node (node:fs/promises, node:os, node:path only). Used by the pi-mono
// omi-provider extension's in-process `load_skill` tool. The extension relays
// every other tool to the host over OMI_BRIDGE_PIPE, but load_skill reads a
// local SKILL.md directly, so it lives here.
//
// Windows deviation from the macOS source (load-bearing):
//   - Symlink-escape containment used `realFilePath.startsWith(`${realRoot}/`)`.
//     On Windows `realpath()` returns backslash paths, so a forward-slash
//     boundary would never match and EVERY skill would be rejected. We use
//     `realRoot + sep` (node:path separator) so the containment check works on
//     both platforms while still rejecting symlinks that escape the skills root.

import { readFile, realpath } from 'node:fs/promises'
import { homedir } from 'node:os'
import { resolve, sep } from 'node:path'

export function isSafeSkillName(name: string): boolean {
  return /^[A-Za-z0-9._-]+$/.test(name) && name !== '.' && name !== '..' && !name.includes('..')
}

export async function loadSkillInstructions(
  name: string,
  workspace = process.env.OMI_WORKSPACE ?? ''
): Promise<string> {
  const trimmedName = name.trim()
  if (!isSafeSkillName(trimmedName)) {
    return 'Invalid skill name. Use the exact skill name listed in available_skills.'
  }

  const roots = [
    workspace ? resolve(workspace, '.claude', 'skills') : '',
    resolve(homedir(), '.claude', 'skills')
  ].filter(Boolean)

  let content: string | null = null
  for (const root of roots) {
    let realRoot: string
    let realFilePath: string
    try {
      realRoot = await realpath(root)
      realFilePath = await realpath(resolve(root, trimmedName, 'SKILL.md'))
    } catch {
      continue
    }
    // Containment guard: the resolved SKILL.md must live UNDER the resolved
    // skills root. `sep` (not a hard-coded '/') keeps this correct on Windows,
    // where realpath returns backslash paths.
    if (!realFilePath.startsWith(realRoot + sep)) {
      continue
    }
    try {
      content = await readFile(realFilePath, 'utf8')
      break
    } catch {
      // Try the next configured skill location.
    }
  }

  if (content && trimmedName === 'dev-mode' && workspace) {
    return `Workspace: ${workspace}\n\n${content}`
  }

  return (
    content ??
    `Skill '${trimmedName}' not found. Check the name matches one listed in <available_skills>.`
  )
}
