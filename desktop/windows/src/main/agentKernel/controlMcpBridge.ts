// The model-facing edge of the agent control plane — the coding agent's `omi` MCP.
//
// WHAT THIS IS. This module is the door that lets a MODEL running inside a
// subprocess adapter (Claude Code / ACP) call Omi's tools. It IS the
// `omi-tools-stdio` adapter surface, so it serves what macOS' omi-tools-stdio
// server serves: the 18 agent-control tools AND the serviceable PRODUCT tools
// (get_goals, get_memories, execute_sql, semantic_search, the task/conversation/
// screen tools, …). It is the transport, and nothing more — every tool, schema,
// policy decision and guard already lives in `controlTools.ts` /
// `toolRelayBridge.ts`, and every call from here goes through `executeHostTool`,
// which routes a control tool through `handleAgentControlToolCall` (leaf guard,
// trusted-control gate, Zod validation) and a product tool through its executor,
// both under HOST-derived identity — the SAME code path the pi-mono relay uses.
//
// HISTORY. This bridge originally advertised and dispatched ONLY the 18 control
// tools; the product-tool half of omi-tools-stdio was never ported, so the coding
// agent could not call get_goals / get_memories / execute_sql / … at all (they were
// invisible in tools/list and rejected as "unknown_control_tool" at dispatch). That
// gap was reachable only once the packaged agent could spawn (fix #241); before it
// nobody could ask the coding agent to run a product tool. Product tools now flow
// through the shared `executeHostTool` door alongside the control tools.
//
// WHY A PIPE. The kernel runs in-process in Electron main, but an MCP server has
// to be a *spawnable command* — the ACP bridge starts it as its own subprocess
// (see `omi-mcp-entry.mjs`). So the subprocess speaks MCP on its stdio and
// relays each call back here over a local socket. This is the Windows analog of
// macOS' `OMI_BRIDGE_PIPE` (agent/src/omi-tools-stdio.ts); the kernel's
// `REQUEST_SCOPED_MCP_ENV_KEYS` already excludes `OMI_BRIDGE_PIPE` from the
// binding hash, so a per-binding pipe/token does not invalidate binding reuse.
//
// ── SECURITY MODEL (read before changing anything here) ─────────────────────
//
// 1. AUTHORITY IS HOST-SIDE, NEVER OFF THE WIRE. A connection authenticates to a
//    *binding*, and every field that decides what a call may do — `ownerId`,
//    `executionRole`, `providerBoundary` — is read FRESH from that binding's
//    session row at call time (`executionPolicyForSession`). The child sends a
//    tool name and its input; it does not get to say who it is.
//
//    DELIBERATE DEVIATION FROM macOS. The Mac server reads an OMI_CONTEXT_FILE
//    and relays `ownerId`/`sessionId`/`runId` back over the pipe with each call
//    (omi-tools-stdio.ts `activeOmiContext()`), i.e. identity arrives from the
//    child. A model with shell access can read and edit that file. Windows binds
//    identity host-side instead. Do not "restore parity" by trusting the wire.
//
// 2. `trustedUserControl` IS HARD-CODED FALSE. It gates `resolve_desktop_dispatch`
//    — the tool that MINTS CONSENT APPROVALS. A model that could set it could
//    approve its own access to the user's screen. There is deliberately no code
//    path here that reads it from input, and the tool inputs are strict Zod
//    objects, so a `trustedUserControl` key on the wire is rejected as unknown.
//
// 3. THE TOKEN STOPS LATERAL MOVEMENT. A model can run shell commands, so it can
//    read its own environment — and therefore its own pipe path and token. That
//    is fine: they grant it exactly its own authority. What it must NOT be able
//    to do is reach a *different* binding's authority (e.g. a leaf agent acting
//    as the coordinator that spawned it). Hence the pipe name is random rather
//    than derived, and each binding gets its own random token; there is nothing
//    to guess and nothing to enumerate.
//
// 4. `callerSessionId` IS ALWAYS SET. `backgroundSpawnAuthority` in controlTools
//    hands the kernel `trustedUserSpawn: true` for any non-leaf caller that omits
//    it. Omitting it here would silently grant every model-facing coordinator
//    unlimited background-spawn rights. It is load-bearing, not bookkeeping.

import { createServer, type Server, type Socket } from 'node:net'
import { randomBytes } from 'node:crypto'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import type { AgentRuntimeKernel } from './kernel'
import { agentControlToolDefinitionsFor, type AgentControlToolDefinition } from './controlTools'
import { executeHostTool, WINDOWS_SERVICEABLE_PRODUCT_TOOLS } from './toolRelayBridge'
import { mcpToolDefinitionsForAdapter } from './omiToolManifest'

/** A single frame may not exceed this. Hostile input must not exhaust main's heap. */
const MAX_FRAME_BYTES = 1024 * 1024

/** What a registered binding gets handed, to put in its MCP server's env. */
export interface ControlMcpRegistration {
  pipePath: string
  token: string
}

interface BindingAuthority {
  sessionId: string
  adapterId: string
}

export interface ControlMcpBridgeOptions {
  kernel: AgentRuntimeKernel
  log?: (message: string) => void
}

/**
 * Host half of the model-facing tool transport. Owns one local socket server for
 * the whole runtime node; each binding registers to get a token that identifies
 * it on that socket.
 */
export class AgentControlMcpBridge {
  private readonly kernel: AgentRuntimeKernel
  private readonly log: (message: string) => void
  /** token -> the binding whose authority that token carries. */
  private readonly authorities = new Map<string, BindingAuthority>()
  /** `${sessionId}\0${adapterId}` -> token, so re-registering a binding is idempotent. */
  private readonly tokensByBinding = new Map<string, string>()
  private readonly sockets = new Set<Socket>()
  private server: Server | null = null
  private listening: Promise<string> | null = null
  private readonly pipePath: string

  constructor(options: ControlMcpBridgeOptions) {
    this.kernel = options.kernel
    this.log = options.log ?? (() => {})
    this.pipePath = randomPipePath()
  }

  /**
   * Start listening. Idempotent and safe to race — the first call owns the
   * promise, everyone else awaits it.
   */
  async start(): Promise<string> {
    if (!this.listening) {
      this.listening = new Promise<string>((resolve, reject) => {
        const server = createServer((socket) => this.acceptConnection(socket))
        server.once('error', reject)
        server.listen(this.pipePath, () => {
          server.removeListener('error', reject)
          this.server = server
          this.log(`[agent-mcp] listening on ${this.pipePath}`)
          resolve(this.pipePath)
        })
      })
    }
    return this.listening
  }

  /**
   * Mint (or reuse) the token that lets this binding's MCP subprocess act with
   * this binding's authority. Reused rather than re-minted so a resumed binding
   * keeps a stable env — and so the token map stays bounded.
   */
  register(sessionId: string, adapterId: string): ControlMcpRegistration {
    const key = bindingKey(sessionId, adapterId)
    const existing = this.tokensByBinding.get(key)
    if (existing) {
      return { pipePath: this.pipePath, token: existing }
    }
    const token = randomBytes(32).toString('hex')
    this.tokensByBinding.set(key, token)
    this.authorities.set(token, { sessionId, adapterId })
    return { pipePath: this.pipePath, token }
  }

  async close(): Promise<void> {
    for (const socket of this.sockets) {
      socket.destroy()
    }
    this.sockets.clear()
    this.authorities.clear()
    this.tokensByBinding.clear()
    const server = this.server
    this.server = null
    this.listening = null
    if (!server) return
    await new Promise<void>((resolve) => server.close(() => resolve()))
  }

  private acceptConnection(socket: Socket): void {
    this.sockets.add(socket)
    socket.setEncoding('utf8')

    // Unauthenticated until a valid `hello` arrives. A connection that never
    // authenticates can do nothing but be dropped.
    let authority: BindingAuthority | null = null
    let buffer = ''

    const fail = (message: string): void => {
      this.log(`[agent-mcp] dropping connection: ${message}`)
      socket.destroy()
    }

    socket.on('data', (chunk: string) => {
      buffer += chunk
      if (buffer.length > MAX_FRAME_BYTES) {
        fail('frame exceeded the maximum size')
        buffer = ''
        return
      }
      let newline = buffer.indexOf('\n')
      while (newline >= 0) {
        const line = buffer.slice(0, newline)
        buffer = buffer.slice(newline + 1)
        if (line.trim()) {
          const frame = parseFrame(line)
          if (!frame) {
            fail('malformed frame')
            return
          }
          if (!authority) {
            // The only frame a fresh connection may send is `hello`.
            const resolved = this.resolveHello(frame)
            if (!resolved) {
              fail('bad or unknown token')
              return
            }
            authority = resolved
            write(socket, { type: 'hello_ok' })
          } else {
            void this.handleFrame(socket, authority, frame)
          }
        }
        newline = buffer.indexOf('\n')
      }
    })

    socket.on('error', () => socket.destroy())
    socket.on('close', () => this.sockets.delete(socket))
  }

  private resolveHello(frame: Record<string, unknown>): BindingAuthority | null {
    if (frame.type !== 'hello' || typeof frame.token !== 'string') return null
    return this.authorities.get(frame.token) ?? null
  }

  private async handleFrame(
    socket: Socket,
    authority: BindingAuthority,
    frame: Record<string, unknown>
  ): Promise<void> {
    const callId = typeof frame.callId === 'string' ? frame.callId : null
    if (!callId) return

    try {
      if (frame.type === 'list') {
        write(socket, { type: 'list_result', callId, tools: this.toolsFor(authority) })
        return
      }
      if (frame.type === 'call') {
        const name = typeof frame.name === 'string' ? frame.name : ''
        const input = plainObject(frame.input)
        // One shared host-tool door for both kinds: a control tool goes through
        // handleAgentControlToolCall (leaf guard, trusted-control gate, owner guard,
        // Zod validation), a serviceable product tool through its executor — with
        // HOST-derived identity (trustedUserControl:false) bound from this binding's
        // session. Same code path the pi-mono relay + voice hub use. Never throws;
        // a denial/error is returned as the tool result string, not a transport fault.
        const result = await executeHostTool(name, input, {
          kernel: this.kernel,
          sessionId: authority.sessionId,
          adapterId: authority.adapterId
        })
        write(socket, { type: 'call_result', callId, result })
        return
      }
      write(socket, { type: 'error', callId, message: `Unknown frame type: ${String(frame.type)}` })
    } catch (error) {
      // A tool that throws must not take main down with it.
      write(socket, {
        type: 'error',
        callId,
        message: error instanceof Error ? error.message : String(error)
      })
    }
  }

  /**
   * The tools this caller may SEE. Listing is a convenience, not a gate — the same
   * policy is re-applied at dispatch inside `executeHostTool`, so a model that names
   * a tool it was never shown is still rejected (control tools) or degraded (a
   * non-serviceable product tool).
   *
   * This `omi` MCP IS the `omi-tools-stdio` adapter surface, so it advertises the
   * full set macOS' omi-tools-stdio server does: the role-gated CONTROL tools AND the
   * serviceable PRODUCT tools (get_goals, get_memories, execute_sql, semantic_search,
   * the task/conversation/screen tools, …). Product tools carry no coordinator/leaf
   * restriction, so both roles see them; only the fanout control tools are role-gated.
   * The list is limited to WINDOWS_SERVICEABLE_PRODUCT_TOOLS so a tool the bridge
   * cannot dispatch is never advertised (load_skill, still pi-extension-only, is thus
   * correctly withheld).
   */
  private toolsFor(authority: BindingAuthority): McpAdvertisedTool[] {
    const policy = this.kernel.executionPolicyForSession(authority.sessionId)
    const control = agentControlToolDefinitionsFor({
      executionRole: policy.executionRole,
      trustedUserControl: false
    })
    const controlNames = new Set<string>(control.map((tool) => tool.name))
    const product = mcpToolDefinitionsForAdapter('omi-tools-stdio', {
      executionRole: policy.executionRole,
      screenContext: true
    }).filter(
      (tool) => !controlNames.has(tool.name) && WINDOWS_SERVICEABLE_PRODUCT_TOOLS.has(tool.name)
    )
    return [...control, ...product]
  }
}

/** A `tools/list` entry the model-facing MCP entry relays verbatim. Structurally
 *  shared by control-tool and product-tool definitions. */
type McpAdvertisedTool = AgentControlToolDefinition | { name: string; description: string }

function bindingKey(sessionId: string, adapterId: string): string {
  return `${sessionId}\0${adapterId}`
}

/**
 * Random, not derived. A derivable name (pid + session + adapter, as the context
 * file uses) would let one agent's shell find another agent's socket.
 */
function randomPipePath(): string {
  const id = randomBytes(16).toString('hex')
  return process.platform === 'win32'
    ? `\\\\.\\pipe\\omi-agent-mcp-${id}`
    : join(tmpdir(), `omi-agent-mcp-${id}.sock`)
}

function parseFrame(line: string): Record<string, unknown> | null {
  try {
    const parsed: unknown = JSON.parse(line)
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed)
      ? (parsed as Record<string, unknown>)
      : null
  } catch {
    return null
  }
}

function plainObject(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {}
}

function write(socket: Socket, payload: Record<string, unknown>): void {
  if (socket.destroyed) return
  socket.write(`${JSON.stringify(payload)}\n`)
}
