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
// Until main itself owns auth, the owner stays DEFAULT_LOCAL_OWNER_ID — the
// single local user. Wire this to main's auth state when sign-in moves into main;
// never re-expose it over IPC. See ../ipc/agentControl.ts.
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
 * Set the authoritative owner for control-tool calls. MAIN-SIDE ONLY — must never
 * be wired to an IPC handler (see the owner-authority note above).
 */
export function setControlPlaneOwner(ownerId: string | null | undefined): void {
  activeOwnerId = ownerId?.trim() || DEFAULT_LOCAL_OWNER_ID
}

export function controlPlaneOwnerId(): string {
  return activeOwnerId
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
    getOwnerId: () => activeOwnerId
  }
}

/** Run one agent-control tool as trusted direct control. Returns the JSON envelope. */
export async function callAgentControlTool(
  name: string,
  input: Record<string, unknown>
): Promise<string> {
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
