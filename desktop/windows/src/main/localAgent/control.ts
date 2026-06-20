import { clipboard } from 'electron'
import type {
  LocalAgentSetupPromptArgs,
  LocalAgentStatus,
  LocalAgentToolsTestResult
} from '../../shared/types'
import { getLocalAgentSettings, setLocalAgentSettings } from './settings'
import { getLocalAgentServerInfo, startLocalAgentServer, stopLocalAgentServer } from './server'
import { ensureLocalAgentToken, loadLocalAgentToken, rotateLocalAgentToken } from './tokenStore'
import { addObservabilityBreadcrumb } from '../observability'

const LOCAL_AGENT_HOST = '127.0.0.1'

type OmiAgentSetupPromptParts = LocalAgentSetupPromptArgs & {
  localUrl: string
  localToolEndpoint: string
  localToken: string
}

function validatePort(port: number): number {
  if (!Number.isInteger(port) || port < 1024 || port > 65535) {
    throw new Error('Local agent port must be between 1024 and 65535')
  }
  return port
}

function requireText(value: string, label: string): string {
  const trimmed = value.trim()
  if (!trimmed) throw new Error(`${label} is required`)
  return trimmed
}

function omiAgentSkillText(hostedServerUrl: string, localUrl: string): string {
  return `---
name: omi
description: Use Omi memories, conversations, and same-Windows-PC context through hosted MCP and the Omi local API.
---

# Omi Agent Skill

Use this skill when the user asks about their Omi memories, conversations, screen history, transcriptions, tasks, or wants you to use Omi context while helping.

## Discovery

- Hosted MCP: list available tools before use. If \`get_user_profile\` exists, use it for a high-level summary. If it is absent, use \`get_memories(limit=5)\` and \`search_memories\`.
- Local Omi API: call \`GET ${localUrl}/health\` and \`GET ${localUrl}/v1/local/tools\` before local work. If either fails, Omi Windows, the local URL, or the local token is not ready.

## Routing

- Hosted MCP: durable memories, synced conversations, preferences, relationships, projects, goals, and profile-like context.
- Local API: this Windows PC's screen history, screenshots, app/window activity, local transcriptions, read-only SQL, daily recaps, indexed files, local goals, and best-effort local tasks.
- Use \`search_conversations\` for synced meetings, calls, and remembered events. Use local transcription tables only for recent same-PC or unsynced local history.
- Use \`search_screen_history\` for fuzzy Rewind/OCR questions. Use \`get_screenshot\` only after a result returns a screenshot ID and the screenshot tool is present.
- Use \`execute_sql\` for read-only counts, exact filters, local transcriptions, action items, indexed files, goals, and database questions.
- Use \`search_tasks\` only if task tools are listed.
- Use \`complete_task\` or \`delete_task\` only when those tools are listed and the user clearly asked you to complete or delete that task. If task tools are absent or unavailable, do not mutate tasks.
- Create, edit, or delete hosted memories only after explicit user intent.

## Verification Checklist

- Hosted MCP tools are listed from ${hostedServerUrl}.
- Hosted memory query succeeds with \`get_memories(limit=5)\` or equivalent.
- Local status succeeds with \`GET ${localUrl}/health\`.
- Local tools are listed with \`GET ${localUrl}/v1/local/tools\`.
- Route only to tools that were discovered.

## Write Discipline

- Do not create, edit, complete, or delete Omi memories or local tasks unless the user clearly asked for that change.
- Prefer proposing the memory or task change first when intent is ambiguous.
- Never treat transient screen activity as a durable memory without explicit user intent or strong evidence.

## Local API Reference

- Tool discovery: \`GET ${localUrl}/v1/local/tools\`
- Tool calls: \`POST ${localUrl}/v1/local/tool\`
- Required headers: \`Authorization: Bearer <omi_local_key>\` and \`Content-Type: application/json\`
- Tool call body: \`{"name":"search_screen_history","arguments":{"query":"example","days":7}}\`
`
}

export function buildOmiAgentSetupPrompt(parts: OmiAgentSetupPromptParts): string {
  const hostedServerUrl = requireText(parts.hostedServerUrl, 'Hosted MCP server URL')
  const hostedKey = requireText(parts.hostedKey, 'Hosted MCP key')
  const localUrl = requireText(parts.localUrl, 'Local Omi URL')
  const localToolEndpoint = requireText(parts.localToolEndpoint, 'Local Omi tool endpoint')
  const localToken = requireText(parts.localToken, 'Local Omi token')

  return `Set up Omi access for this agent.

1. Configure hosted Omi MCP for synced memories, conversations, and profile context.

Hosted server URL:
${hostedServerUrl}

Hosted authorization header:
Authorization: Bearer ${hostedKey}

2. Configure the local Omi Windows API for this PC. Local access includes screen history, screenshot retrieval, local transcriptions, read-only SQL, daily recaps, indexed files, goals, app/window activity, and best-effort task search while Omi Windows is running.

Local Omi Windows URL:
${localUrl}

Local Omi Windows tool endpoint:
${localToolEndpoint}

Local Omi Windows authorization header:
Authorization: Bearer ${localToken}

Local API setup:
- Direct HTTP is the primary path. No CLI is required for this setup.
- Verify local status: \`GET ${localUrl}/health\`
- Discover local tools: \`GET ${localUrl}/v1/local/tools\` with the local authorization header.
- Call a local tool: \`POST ${localToolEndpoint}\` with the local authorization header and JSON body \`{"name":"get_local_status","arguments":{}}\`.
- Optional CLI compatibility: only use an Omi CLI or equivalent wrapper if it is already installed and supports this Windows local API. Treat it as a convenience wrapper around the same local URL and bearer token; fall back to direct HTTP if the CLI is absent or fails.

3. Save the Omi guide below. If this agent supports skills, install it as a skill named \`omi\`; otherwise save it in durable agent or project instructions.

${omiAgentSkillText(hostedServerUrl, localUrl)}

4. Verify setup:
- List hosted MCP tools.
- If hosted \`get_user_profile\` exists, call it. Otherwise call \`get_memories\` with \`limit: 5\`.
- Call \`GET ${localUrl}/health\`.
- Call \`GET ${localUrl}/v1/local/tools\`.
- Use only hosted and local tools that were discovered.
`
}

export function getLocalAgentStatus(): LocalAgentStatus {
  const settings = getLocalAgentSettings()
  const info = getLocalAgentServerInfo()
  return {
    enabled: settings.enabled,
    running: info !== null,
    host: info?.host ?? LOCAL_AGENT_HOST,
    configuredPort: settings.port,
    currentPort: info?.port ?? null,
    localUrl: info?.localUrl ?? null,
    toolEndpoint: info?.toolEndpoint ?? null,
    hasToken: loadLocalAgentToken() !== null
  }
}

export async function setLocalAgentEnabled(enabled: boolean): Promise<LocalAgentStatus> {
  const settings = setLocalAgentSettings({ ...getLocalAgentSettings(), enabled })
  addObservabilityBreadcrumb(
    'local_agent.enabled_changed',
    { enabled, configuredPort: settings.port },
    { category: 'local_agent' }
  )
  if (!enabled) {
    await stopLocalAgentServer()
    return getLocalAgentStatus()
  }

  await startLocalAgentServer({ preferredPort: settings.port })
  return getLocalAgentStatus()
}

export async function setLocalAgentPort(port: number): Promise<LocalAgentStatus> {
  const validatedPort = validatePort(port)
  const settings = setLocalAgentSettings({ ...getLocalAgentSettings(), port: validatedPort })
  addObservabilityBreadcrumb(
    'local_agent.port_changed',
    { configuredPort: settings.port, enabled: settings.enabled },
    { category: 'local_agent' }
  )

  if (settings.enabled) {
    await stopLocalAgentServer()
    await startLocalAgentServer({ preferredPort: settings.port })
  }

  return getLocalAgentStatus()
}

export function copyLocalAgentToken(): LocalAgentStatus {
  clipboard.writeText(ensureLocalAgentToken())
  addObservabilityBreadcrumb('local_agent.token_copied', {}, { category: 'local_agent' })
  return getLocalAgentStatus()
}

export async function copyLocalAgentSetupPrompt(
  args: LocalAgentSetupPromptArgs
): Promise<LocalAgentStatus> {
  const hostedServerUrl = requireText(args.hostedServerUrl, 'Hosted MCP server URL')
  const hostedKey = requireText(args.hostedKey, 'Hosted MCP key')
  const settings = setLocalAgentSettings({ ...getLocalAgentSettings(), enabled: true })
  addObservabilityBreadcrumb(
    'local_agent.setup_prompt_requested',
    { hasHostedServerUrl: Boolean(hostedServerUrl), hasHostedKey: Boolean(hostedKey) },
    { category: 'local_agent' }
  )
  const info = await startLocalAgentServer({ preferredPort: settings.port })
  const localToken = ensureLocalAgentToken()

  clipboard.writeText(
    buildOmiAgentSetupPrompt({
      hostedServerUrl,
      hostedKey,
      localUrl: info.localUrl,
      localToolEndpoint: info.toolEndpoint,
      localToken
    })
  )

  return getLocalAgentStatus()
}

export async function rotateLocalAgentAccessToken(): Promise<LocalAgentStatus> {
  rotateLocalAgentToken()
  const settings = getLocalAgentSettings()
  addObservabilityBreadcrumb(
    'local_agent.token_rotated',
    { enabled: settings.enabled, configuredPort: settings.port },
    { category: 'local_agent' }
  )

  if (settings.enabled) {
    await stopLocalAgentServer()
    await startLocalAgentServer({ preferredPort: settings.port })
  }

  return getLocalAgentStatus()
}

export async function testLocalAgentTools(): Promise<LocalAgentToolsTestResult> {
  const info = getLocalAgentServerInfo()
  addObservabilityBreadcrumb(
    'local_agent.tools_test_started',
    { running: info !== null, port: info?.port ?? null },
    { category: 'local_agent' }
  )
  if (!info) {
    addObservabilityBreadcrumb(
      'local_agent.tools_test_finished',
      { ok: false, errorCode: 'not_listening' },
      { category: 'local_agent', level: 'warning' }
    )
    return { ok: false, error: 'Local agent API is not listening' }
  }

  const token = loadLocalAgentToken()
  if (!token) {
    addObservabilityBreadcrumb(
      'local_agent.tools_test_finished',
      { ok: false, port: info.port, errorCode: 'missing_token' },
      { category: 'local_agent', level: 'warning' }
    )
    return { ok: false, error: 'Local agent token is missing' }
  }

  try {
    const response = await fetch(`${info.localUrl}/v1/local/tools`, {
      headers: { authorization: `Bearer ${token}` }
    })
    if (!response.ok) {
      addObservabilityBreadcrumb(
        'local_agent.tools_test_finished',
        { ok: false, port: info.port, status: response.status },
        { category: 'local_agent', level: 'warning' }
      )
      return { ok: false, status: response.status, error: `HTTP ${response.status}` }
    }

    const body = (await response.json()) as { tools?: unknown[] }
    const toolCount = Array.isArray(body.tools) ? body.tools.length : 0
    addObservabilityBreadcrumb(
      'local_agent.tools_test_finished',
      { ok: true, port: info.port, status: response.status, toolCount },
      { category: 'local_agent' }
    )
    return { ok: true, status: response.status, toolCount }
  } catch (error) {
    addObservabilityBreadcrumb(
      'local_agent.tools_test_finished',
      {
        ok: false,
        port: info.port,
        errorMessage: error instanceof Error ? error.message : String(error)
      },
      { category: 'local_agent', level: 'warning' }
    )
    return {
      ok: false,
      error: error instanceof Error ? error.message : 'Local agent tools test failed'
    }
  }
}
