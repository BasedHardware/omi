// Detection for delegated coding-agent tasks — the chat pre-step that decides
// whether a message (typed or push-to-talk) should be handed to Claude Code /
// OpenClaw / Hermes / Codex instead of the normal Omi chat. Conservative on
// purpose, like the automation planner's looksLikeAction: a false negative
// just falls through to ordinary chat; a false positive would hijack a normal
// message, so detection requires an explicit agent mention (or an explicit
// "agent" delegation phrase).

import type { CodingAgentId } from '../../../shared/types'

export type AgentTaskDetection = {
  /** Named agent, or undefined for "some agent" (Omi picks the best one). */
  agentId?: CodingAgentId
  /** The task text to hand to the agent (mention phrasing stripped). */
  prompt: string
}

// Alias → adapter id. Longer aliases first so "claude code" wins over "claude".
const AGENT_ALIASES: Array<[RegExp, CodingAgentId]> = [
  [/claude\s*code/i, 'acp'],
  [/\bclaude\b/i, 'acp'],
  [/open\s*claw/i, 'openclaw'],
  [/\bhermes\b/i, 'hermes'],
  [/\bcodex\b/i, 'codex']
]

const ALIAS_PATTERN = '(?:claude\\s*code|claude|open\\s*claw|openclaw|hermes|codex)'

// "ask codex to …", "use claude code and fix …", "have openclaw look at …",
// "delegate this to hermes", "with codex, add …"
const DELEGATION_BEFORE_NAME = new RegExp(
  `\\b(?:ask|tell|use|have|get|let|delegate(?:\\s+\\w+)?\\s+to|hand(?:\\s+\\w+)?\\s+to|via|using|with)\\s+(?:the\\s+)?${ALIAS_PATTERN}\\b`,
  'i'
)

// "codex, fix the failing test", "hey claude code: add a readme"
const NAME_LEADS = new RegExp(`^\\s*(?:hey\\s+|ok\\s+)?${ALIAS_PATTERN}\\s*[,:–-]`, 'i')

// Unnamed delegation: "ask a coding agent to …", "have an agent fix …"
const UNNAMED_AGENT = /\b(?:ask|tell|use|have|get|let)\s+(?:an?\s+)?(?:coding\s+|code\s+)?agent\b/i

// Guidance questions are never delegations ("what can codex do?").
const GUIDANCE_QUESTION =
  /^\s*(where|what|which|how|why|when|who)\b|\b(should i|do i|can you tell me about)\b/i

function namedAgent(text: string): CodingAgentId | undefined {
  for (const [pattern, id] of AGENT_ALIASES) {
    if (pattern.test(text)) return id
  }
  return undefined
}

/**
 * Decide whether this message names (or asks for) a coding agent. Returns null
 * for everything that should stay in normal chat.
 */
export function detectAgentTask(text: string): AgentTaskDetection | null {
  if (!text.trim()) return null
  if (GUIDANCE_QUESTION.test(text)) return null

  if (DELEGATION_BEFORE_NAME.test(text) || NAME_LEADS.test(text)) {
    return { agentId: namedAgent(text), prompt: text.trim() }
  }
  if (UNNAMED_AGENT.test(text)) {
    return { agentId: undefined, prompt: text.trim() }
  }
  return null
}

/** An explicit absolute Windows path anywhere in the message. */
export function explicitPathIn(text: string): string | undefined {
  const match = text.match(/(?:^|[\s"'(])([A-Za-z]:[\\/][^\s"')]+)/)
  return match?.[1]
}

/** A "in my omi repo" / "in the desktop folder" style folder-name hint. */
export function folderHintIn(text: string): string | undefined {
  const match = text.match(
    /\b(?:in|inside|under|to)\s+(?:my|the|our)\s+([\w][\w .-]{0,40}?)\s+(?:repo|repository|project|folder|directory|codebase)\b/i
  )
  return match?.[1]?.trim()
}

type FileSearch = (q: string) => Promise<Array<{ folder: string }>>
type SqlQuery = (sql: string) => Promise<{ columns: string[]; rows: Record<string, unknown>[] }>

/**
 * Resolve the working directory for a task: an explicit path in the message,
 * else the indexed folder matching a "in my X repo" hint, else the most
 * recently active indexed working folder. Undefined lets main fall back to the
 * user's home directory. Best-effort — any failure returns undefined.
 */
export async function resolveTaskCwd(
  text: string,
  deps: { searchFiles: FileSearch; executeSql: SqlQuery }
): Promise<string | undefined> {
  const explicit = explicitPathIn(text)
  if (explicit) return explicit

  try {
    const hint = folderHintIn(text)
    if (hint) {
      const files = await deps.searchFiles(hint)
      const folder = files.find((f) => f.folder.toLowerCase().includes(hint.toLowerCase()))?.folder
      if (folder) return folder
    }
    // Exclude app shortcuts: the index also scans Start-Menu folders (kind
    // 'apps'), and without the filter "most recent folder" can resolve to
    // C:\ProgramData\...\Start Menu\Programs\<vendor> (seen live).
    const recent = await deps.executeSql(
      "SELECT folder, MAX(modified_at) AS last_modified FROM indexed_files WHERE file_type != 'application' GROUP BY folder ORDER BY last_modified DESC LIMIT 1"
    )
    const folder = recent.rows[0]?.folder
    return typeof folder === 'string' && folder ? folder : undefined
  } catch {
    return undefined
  }
}
