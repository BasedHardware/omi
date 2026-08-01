// IPC surface for delegated coding-agent tasks. Follows the house pattern:
// invoke-style handlers plus a broadcast channel for streaming task events
// (both the main window and the overlay may render the same task's progress).

import { ipcMain, BrowserWindow, shell } from 'electron'
import {
  ADAPTER_PROFILES,
  adapterActivationError,
  adapterIsActivated,
  type AdapterCommandOverrides
} from '../codingAgent/adapterRegistry'
import { PRODUCTION_ADAPTER_IDS } from '../codingAgent/interface'
import { cancelTask, runCodingAgentTask, testAgentConnection } from '../codingAgent/taskRunner'
import {
  claudeAuthStatus,
  removeClaudeCredentials,
  startClaudeOAuthFlow,
  validateClaudeOAuthUrl,
  type ClaudeOAuthFlowHandle
} from '../codingAgent/claudeOAuth'
import { messageFrom } from '../codingAgent/failures'
import { getAppSettings, setAppSettings, type AgentCommands } from '../appSettings'
import { detectAgents } from '../codingAgent/agentDetect'
import { codexApiKeyStatus, saveCodexApiKey } from '../codingAgent/codexAuth'
import type { ProductionAdapterId } from '../codingAgent/interface'
import type {
  AgentDetectionMap,
  CodexKeyResult,
  CodexKeyStatus,
  CodingAgentAuthStatus,
  CodingAgentEvent,
  CodingAgentInfo,
  CodingAgentResult,
  CodingAgentRunArgs,
  CodingAgentStartAuthResult
} from '../../shared/types'

function broadcast(event: CodingAgentEvent): void {
  for (const win of BrowserWindow.getAllWindows()) {
    if (!win.isDestroyed()) {
      win.webContents.send('codingAgent:event', event)
    }
  }
}

// The configured external-agent launch commands, read from the main-process
// settings store.
//
// SECURITY: this is the ONLY source of the strings acp.ts spawns. It used to be
// whatever the renderer passed in (backed by localStorage), which turned one
// write to that origin's storage into persistent code execution, re-run on every
// agent turn. Renderer-supplied overrides are now ignored outright rather than
// merged — a merge would leave the same injection path open.
function configuredCommands(): AdapterCommandOverrides {
  return getAppSettings().agentCommands
}

export function registerCodingAgentHandlers(): void {
  ipcMain.handle(
    'codingAgent:list',
    // The legacy `commandOverrides` argument is accepted and DISCARDED: older
    // renderer call sites still send it, and silently ignoring it is what makes
    // the command string unreachable from the renderer.
    (): CodingAgentInfo[] => {
      const overrides = configuredCommands()
      return PRODUCTION_ADAPTER_IDS.map((id) => {
        const connected = adapterIsActivated(id, overrides)
        return {
          id,
          displayName: ADAPTER_PROFILES[id].displayName,
          connected,
          installHint: connected ? undefined : adapterActivationError(id)
        }
      })
    }
  )

  ipcMain.handle(
    'codingAgent:run',
    (_e, args: CodingAgentRunArgs): Promise<CodingAgentResult> =>
      // Overwrite (never merge) any commandOverrides the renderer put on `args`:
      // the task prompt and agent id are the renderer's to choose, the command
      // that gets spawned is not.
      runCodingAgentTask(
        { ...args, commandOverrides: configuredCommands() },
        broadcast,
        (message) => console.log(`[codingAgent] ${message}`)
      )
  )

  ipcMain.handle('codingAgent:cancel', (_e, taskId: string): boolean => cancelTask(taskId))

  // Only the agent id crosses from the renderer; the command comes from settings.
  ipcMain.handle('codingAgent:test', (_e, agentId: ProductionAdapterId) =>
    testAgentConnection(agentId, configuredCommands(), (message) =>
      console.log(`[codingAgent] ${message}`)
    )
  )

  // Settings → Agents reads and writes the launch commands through these two
  // handlers instead of keeping its own copy. setAppSettings runs the store's
  // sanitizer, which drops unknown ids and over-long values.
  ipcMain.handle('codingAgent:getCommands', (): AgentCommands => configuredCommands())

  ipcMain.handle('codingAgent:setCommands', (_e, next: AgentCommands): AgentCommands => {
    return setAppSettings({ agentCommands: next ?? {} }).agentCommands
  })

  // One-time import of the pre-migration renderer-stored commands. Applied only
  // while main's own store is still empty, so it cannot be replayed later to
  // overwrite (or re-inject) a command the user has since set here.
  ipcMain.handle('codingAgent:migrateCommands', (_e, legacy: AgentCommands): AgentCommands => {
    const current = configuredCommands()
    if (Object.keys(current).length > 0) return current
    return setAppSettings({ agentCommands: legacy ?? {} }).agentCommands
  })

  ipcMain.handle('codingAgent:authStatus', (): CodingAgentAuthStatus => claudeAuthStatus())

  ipcMain.handle(
    'codingAgent:startAuth',
    (): Promise<CodingAgentStartAuthResult> => startClaudeAuth()
  )

  ipcMain.handle('codingAgent:signOut', (): CodingAgentAuthStatus => {
    removeClaudeCredentials()
    return claudeAuthStatus()
  })

  // PATH auto-detection for the external agent CLIs (Codex / Hermes / OpenClaw).
  ipcMain.handle('codingAgent:detect', (): Promise<AgentDetectionMap> => detectAgents())

  // Codex OpenAI API-key lane (encrypted store, boolean-only status to renderer).
  ipcMain.handle('codingAgent:codexKeyStatus', (): CodexKeyStatus => codexApiKeyStatus())
  ipcMain.handle(
    'codingAgent:setCodexKey',
    (_e, key: string): Promise<CodexKeyResult> =>
      saveCodexApiKey(typeof key === 'string' ? key : '')
  )
}

// One in-flight Claude sign-in at a time. A duplicate request (e.g. the user
// double-clicks "Sign in") joins the running flow instead of opening a second
// browser tab or spinning up a second callback server — mirrors macOS's
// idempotent startAuthFlow / one-launch latch.
let activeAuth: Promise<CodingAgentStartAuthResult> | null = null

async function startClaudeAuth(): Promise<CodingAgentStartAuthResult> {
  if (activeAuth) return activeAuth
  activeAuth = runClaudeAuthOnce().finally(() => {
    activeAuth = null
  })
  return activeAuth
}

async function runClaudeAuthOnce(): Promise<CodingAgentStartAuthResult> {
  const log = (message: string): void => console.log(`[codingAgent] ${message}`)
  let flow: ClaudeOAuthFlowHandle | null = null
  try {
    flow = await startClaudeOAuthFlow(log)
    // Validate before opening: never hand the browser a URL that isn't the
    // exact claude.ai PKCE loopback authorize request we built.
    const validated = validateClaudeOAuthUrl(flow.authUrl)
    if (!validated) {
      flow.cancel()
      // Fail-closed (macOS parity): don't hand the browser a URL that isn't the
      // exact claude.ai PKCE loopback request; surface the same generic copy.
      return {
        ok: false,
        error: 'Unable to start Claude sign-in. Try again.',
        status: claudeAuthStatus()
      }
    }
    // Don't spawn a real browser under E2E (keeps the harness hermetic and lets
    // it screenshot the upsell sheet without a claude.ai tab opening).
    if (!process.env.OMI_E2E) void shell.openExternal(validated.toString())
    await flow.complete
    return { ok: true, status: claudeAuthStatus() }
  } catch (error) {
    flow?.cancel()
    return { ok: false, error: messageFrom(error), status: claudeAuthStatus() }
  }
}
