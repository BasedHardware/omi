// Agent control plane host — the process-wide AgentRuntimeKernel and the
// trusted-direct-control entry point into the 18 agent-control tools.
//
// WHY THIS EXISTS. macOS reaches the control tools two ways: model-facing
// adapters call them over the MCP/JSONL transport, and the Swift host calls them
// directly (e.g. TaskChatCoordinator's `control("evaluate_desktop_tool_policy",
// …)`). Windows has no MCP server and no model tool-calling loop yet, so the
// second path — TRUSTED DIRECT CONTROL — is the one that exists, and this module
// is it. When a model-facing tool loop lands, it builds its own context with
// `trustedUserControl: false` and the caller's real `executionRole`, and
// `agentControlToolDefinitionsFor()` tells it which tools that caller may see.
//
// OWNER AUTHORITY (INV-AGENT). The active owner is host state. A per-call
// `ownerId` in a tool's input is only a GUARD — `effectiveControlToolOwnerId`
// rejects it when it does not match the active owner. A caller can never widen
// its own scope by asserting a different ownerId, which is why the owner is not
// read off the per-call payload.
//
// For the same reason `setControlPlaneOwner` is MAIN-SIDE ONLY and is not
// reachable from the renderer: a caller that can set the active owner defeats the
// per-call guard entirely (the guard would just compare against whatever it set).
// It IS now wired to main's auth state — the `pimono:setSession` IPC handler
// decodes the uid from the relayed Firebase ID token (the credential itself, not
// a renderer-asserted field) and calls `setControlPlaneOwner`, resetting to
// DEFAULT_LOCAL_OWNER_ID on sign-out. Until that relay arrives on cold start the
// owner is the default constant; `hasKnownControlPlaneOwner()` is false then, and
// the main-chat / control-tool paths refuse rather than key a session under the
// shared default. Never re-expose the setter over IPC. See ../ipc/agentControl.ts
// and ../ipc/pimono.ts.
//
// Chat routing stays OFF: constructing the kernel does not route user-facing chat
// through it. The adapter registry starts EMPTY, so the read/policy/dispatch
// tools work immediately and the run-starting tools (send_agent_message,
// spawn_*) fail cleanly until the chat-routing PR registers real adapters.

import omiMcpEntry from './omi-mcp-entry.mjs?asset'
import { AdapterRegistry } from './adapterRegistry'
import { AgentRuntimeKernel } from './kernel'
import { SqliteAgentStore } from './store'
import { AgentControlMcpBridge } from './controlMcpBridge'
import { AgentToolRelayBridge } from './toolRelayBridge'
import { configuredPiMonoMaxWorkers } from './workerPool'
import { PiMonoAdapter, PiMonoRuntimeAdapter } from '../codingAgent/piMono'
import {
  getPiMonoByokEnv,
  getPiMonoSession,
  piMonoManagedApiBaseUrl,
  registerPiMonoAdapter
} from '../codingAgent/piMonoSession'
import type { CodingAgentAdapterId, RuntimeAdapter } from '../codingAgent/interface'
import {
  ADAPTER_PROFILES,
  adapterConfiguredCommand,
  adapterIsActivated
} from '../codingAgent/adapterRegistry'
import { claudeAuthStatus } from '../codingAgent/claudeOAuth'
import { PRODUCTION_ADAPTER_IDS } from '../codingAgent/interface'
import {
  DEFAULT_LOCAL_OWNER_ID,
  handleAgentControlToolCall,
  type AgentControlToolContext
} from './controlTools'

let kernel: AgentRuntimeKernel | null = null
let registry: AdapterRegistry | null = null
let mcpBridge: AgentControlMcpBridge | null = null
let toolRelayBridge: AgentToolRelayBridge | null = null
let activeOwnerId = DEFAULT_LOCAL_OWNER_ID

/**
 * The process-wide kernel. Created on first use so a failure to open the store
 * surfaces at the first control call rather than crashing app boot (the same
 * non-fatal posture as `probeAgentStoreRuntimeAtStartup`).
 */
export function getAgentRuntimeKernel(): AgentRuntimeKernel {
  if (!kernel) {
    registry = new AdapterRegistry()
    // The kernel and the bridge each need the other, so the kernel takes a
    // closure: it is only called when a binding opens, long after both exist.
    kernel = new AgentRuntimeKernel({
      store: new SqliteAgentStore(),
      registry,
      controlMcpServers: (sessionId, adapterId) =>
        mcpBridge ? controlMcpServers(mcpBridge, sessionId, adapterId) : []
    })
    mcpBridge = new AgentControlMcpBridge({
      kernel,
      log: (message) => console.log(message)
    })
    // Listen eagerly so the socket is up long before the first run spawns an MCP
    // subprocess. A failure here is non-fatal — models just get no control tools.
    void mcpBridge.start().catch((error) => {
      console.error('[agent-mcp] failed to start the control tool server:', error)
    })
    // The pi-mono product/control tool relay. Constructed alongside the kernel and
    // control bridge (not per-adapter). DARK: nothing spawns pi with its pipe/token
    // in production yet, so it listens with no live client. A failure is non-fatal.
    toolRelayBridge = new AgentToolRelayBridge({
      kernel,
      log: (message) => console.log(message)
    })
    void toolRelayBridge.start().catch((error) => {
      console.error('[tool-relay] failed to start the pi-mono tool relay server:', error)
    })
  }
  return kernel
}

/**
 * The MCP server config handed to an adapter so its model can reach the control
 * plane. Spawned as Electron's own binary running as Node — the same mechanism
 * the bundled ACP entry uses (see codingAgent/claudeCode.ts), which is what makes
 * this work in both dev and a packaged build with no `node` on PATH.
 *
 * The pipe path and token are what bind this subprocess to THIS session's
 * authority. They are request-scoped env (already excluded from the kernel's
 * binding hash), not identity the child gets to assert.
 */
function controlMcpServers(
  bridge: AgentControlMcpBridge,
  sessionId: string,
  adapterId: string
): Record<string, unknown>[] {
  const { pipePath, token } = bridge.register(sessionId, adapterId)
  return [
    {
      name: 'omi',
      command: process.execPath,
      args: [omiMcpEntry],
      env: [
        { name: 'ELECTRON_RUN_AS_NODE', value: '1' },
        { name: 'OMI_BRIDGE_PIPE', value: pipePath },
        { name: 'OMI_BRIDGE_TOKEN', value: token }
      ]
    }
  ]
}

/** The model-facing tool server. Present once the kernel has been constructed. */
export function getAgentControlMcpBridge(): AgentControlMcpBridge | null {
  return mcpBridge
}

/** The pi-mono product/control tool relay. Present once the kernel is constructed. */
export function getAgentToolRelayBridge(): AgentToolRelayBridge | null {
  return toolRelayBridge
}

/** The live adapter registry, for the chat-routing PR to register adapters into. */
export function getAgentAdapterRegistry(): AdapterRegistry {
  getAgentRuntimeKernel()
  return registry as AdapterRegistry
}

/**
 * Build a fresh pi-mono RuntimeAdapter from the CURRENT relayed Firebase session.
 *
 * Re-reads `getPiMonoSession()` on every call — the worker pool invokes the
 * registered factory LAZILY on first use, by which point a token refresh
 * (`configurePiMonoSession`) may have replaced the token that was present when
 * `ensurePiMonoAdapterRegistered()` ran. Reading here, not closing over an outer
 * `session`, guarantees the freshest token is used at actual spawn time.
 *
 * Registers the harness with the session store so a later token refresh restarts
 * THIS instance. Exported as a test seam for the re-read nuance.
 */
export function buildPiMonoRuntimeAdapter(): RuntimeAdapter {
  const session = getPiMonoSession()
  if (!session) {
    throw new Error('pi-mono session was cleared before the adapter started.')
  }
  const harness = new PiMonoAdapter({
    omiApiBaseUrl: piMonoManagedApiBaseUrl(session),
    authToken: session.token,
    byokEnv: getPiMonoByokEnv(),
    onRestart: (reason) => console.log(`[pi-mono] restart: ${reason}`),
    // Lets the pi subprocess reach the product/control tool relay. Resolved per
    // attempt (idempotent host-side) so the pipe/token ride the per-turn context
    // file — surviving resume + pool-eviction remint with no subprocess restart.
    // Passed as a callback to avoid a piMono → controlPlane import cycle.
    registerToolRelay: (sessionId) =>
      getAgentToolRelayBridge()?.register(sessionId, 'pi-mono') ?? null
  })
  registerPiMonoAdapter(harness)
  return new PiMonoRuntimeAdapter(harness)
}

/**
 * Register the managed-cloud pi-mono adapter into the live kernel registry, once,
 * when a Firebase session has been relayed. Called from the `pimono:setSession`
 * IPC handler after `configurePiMonoSession` succeeds. Returns false (a no-op)
 * when signed out, so the registry stays empty until a real session exists.
 *
 * DARK after PR-D1: this only makes `registry.has('pi-mono')` true — nothing calls
 * openBinding/executeAttempt on it yet (default chat still routes through
 * /v2/messages; main_chat routing arrives in PR-E). Idempotent: guarded by
 * `registry.has` so a token refresh re-invoking it never double-registers.
 */
export function ensurePiMonoAdapterRegistered(): boolean {
  if (!getPiMonoSession()) return false
  const registry = getAgentAdapterRegistry()
  if (!registry.has('pi-mono')) {
    // Cap pi-mono's pool well below the generic default (mac parity): each
    // pinned worker owns one pi subprocess, so bound concurrent subprocesses.
    registry.register('pi-mono', buildPiMonoRuntimeAdapter, configuredPiMonoMaxWorkers())
  }
  return true
}

/**
 * Register a user-selectable coding agent (acp/openclaw/hermes/codex) into the
 * live kernel registry, once, so `spawn_agent`'s host-picked fallback can
 * actually execute a run. Same lazy-factory posture as pi-mono: registration is
 * cheap (the adapter subprocess only spawns when a binding opens), and the
 * factory re-reads the configured command at build time. Idempotent; returns
 * false (never throws) when registration fails so the caller can fall through
 * to the next connected agent.
 */
export function ensureCodingAgentAdapterRegistered(adapterId: CodingAgentAdapterId): boolean {
  try {
    const registry = getAgentAdapterRegistry()
    if (registry.has(adapterId)) return true
    const profile = ADAPTER_PROFILES[adapterId]
    registry.register(adapterId, () =>
      profile.createAdapter({
        log: (message) => console.log(`[${adapterId}] ${message}`),
        command: adapterConfiguredCommand(adapterId)
      })
    )
    return true
  } catch (error) {
    console.error(`[agent-kernel] failed to register coding agent ${adapterId}:`, error)
    return false
  }
}

/** Injectable edges for `resolveSpawnableCodingAgentAdapterId` (unit tests). */
export interface SpawnableAdapterDeps {
  env?: NodeJS.ProcessEnv
  claudeConnected?: () => boolean
  ensureRegistered?: (adapterId: CodingAgentAdapterId) => boolean
}

/**
 * The HOST's default spawnable coding agent for `spawn_agent`'s fallback when
 * the calling surface's own adapter is the managed-cloud chat engine: the first
 * CONNECTED agent in the canonical order (acp → openclaw → hermes → codex —
 * PRODUCTION_ADAPTER_IDS, the same order the coding-agent task fallback uses).
 * Claude Code ('acp') is bundled and always "activated", so it is additionally
 * gated on real OAuth sign-in (`claudeAuthStatus`) — the same gate Settings →
 * Agents' Test uses. The winner is registered into the kernel registry before
 * being returned; null when nothing is connected.
 *
 * External agents' launch commands are read from env vars here (the renderer's
 * per-user command overrides are not relayed to main); Claude Code needs none.
 */
export function resolveSpawnableCodingAgentAdapterId(
  deps: SpawnableAdapterDeps = {}
): string | null {
  const env = deps.env ?? process.env
  const claudeConnected = deps.claudeConnected ?? ((): boolean => claudeAuthStatus().connected)
  const ensureRegistered = deps.ensureRegistered ?? ensureCodingAgentAdapterRegistered
  for (const adapterId of PRODUCTION_ADAPTER_IDS) {
    if (!adapterIsActivated(adapterId, {}, env)) continue
    if (adapterId === 'acp' && !claudeConnected()) continue
    if (!ensureRegistered(adapterId)) continue
    return adapterId
  }
  return null
}

/**
 * Set the authoritative owner for control-tool calls. MAIN-SIDE ONLY — must never
 * be wired to a plain IPC handler (see the owner-authority note above). Called by
 * the `pimono:setSession` handler with the uid decoded from the relayed Firebase
 * ID token; an empty/null id resets to DEFAULT_LOCAL_OWNER_ID (sign-out or an
 * undecodable token).
 */
export function setControlPlaneOwner(ownerId: string | null | undefined): void {
  activeOwnerId = ownerId?.trim() || DEFAULT_LOCAL_OWNER_ID
}

export function controlPlaneOwnerId(): string {
  return activeOwnerId
}

/**
 * True once a real signed-in owner has been wired — i.e. the active owner is no
 * longer the shared DEFAULT_LOCAL_OWNER_ID constant. The pi-mono main-chat path
 * and control-tool calls gate on this to close the cold-start window: before the
 * auth relay sets the owner, a kernel session opened under the default constant
 * would collide across accounts on a shared profile and could never migrate to
 * the real uid. Refusing while unknown is fail-closed and correct.
 */
export function hasKnownControlPlaneOwner(): boolean {
  return activeOwnerId !== DEFAULT_LOCAL_OWNER_ID
}

/**
 * Context for a call made by the user through the app's own UI. This is the
 * trusted path: the user clicking "Approve" in Omi is exactly the explicit user
 * consent `resolve_desktop_dispatch` requires. Models never reach this — they
 * have no IPC.
 */
export function trustedDirectControlContext(): AgentControlToolContext {
  return {
    kernel: getAgentRuntimeKernel(),
    trustedUserControl: true,
    executionRole: 'coordinator',
    getOwnerId: () => activeOwnerId,
    resolveSpawnableAdapterId: async () => resolveSpawnableCodingAgentAdapterId()
  }
}

/** Run one agent-control tool as trusted direct control. Returns the JSON envelope.
 *
 * Refuses while the owner is unknown (the cold-start window before the auth relay
 * wires the signed-in uid). Running a control tool under the shared default owner
 * would scope its kernel reads/writes to a constant every account collides on — so
 * fail closed with a clear envelope instead of touching the store. */
export async function callAgentControlTool(
  name: string,
  input: Record<string, unknown>
): Promise<string> {
  if (!hasKnownControlPlaneOwner()) {
    return JSON.stringify({
      ok: false,
      error: {
        code: 'owner_not_ready',
        message: 'Sign-in has not completed; the agent control plane has no owner yet.'
      }
    })
  }
  return handleAgentControlToolCall(trustedDirectControlContext(), name, input)
}

/** Test seam: drop the singleton so a test can build a fresh one. */
export function resetControlPlaneForTests(): void {
  // Close the sockets too, or each reset leaks a listening server.
  void mcpBridge?.close()
  void toolRelayBridge?.close()
  mcpBridge = null
  toolRelayBridge = null
  kernel = null
  registry = null
  activeOwnerId = DEFAULT_LOCAL_OWNER_ID
}
