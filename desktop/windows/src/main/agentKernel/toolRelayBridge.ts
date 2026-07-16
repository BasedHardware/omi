// The pi-mono-facing product/control tool relay — the second model-facing edge of
// the agent control plane (the first is controlMcpBridge.ts).
//
// WHAT THIS IS. When pi-mono runs inside a subprocess adapter, its Omi extension
// connects to THIS server over a local pipe and forwards every Omi tool call as a
// bespoke newline-delimited JSON `tool_use` frame. The host dispatches it and
// writes back a `tool_result`. This is the Windows analog of macOS'
// `startOmiToolsRelay()` (desktop/macos/agent/src/index.ts) — but pi-mono's path,
// not the ACP/omi-tools-stdio path, and with the same host-authoritative identity
// posture the control bridge already uses.
//
// WHY A SECOND CLASS. AgentControlMcpBridge speaks a DIFFERENT frame vocabulary
// (`hello`/`list`/`call`) and its `call` branch hardcodes handleAgentControlToolCall
// with NO pending-call bookkeeping (control tools resolve fully in-process,
// synchronously). This relay speaks `tool_use`/`tool_result`, and product tools
// may be async/cross-boundary, so it needs a per-socket pending map + timeout +
// reject-on-disconnect that the control bridge has no model for. It reuses the
// control bridge's transport IDIOM (random pipe path, per-binding token, hello
// handshake, host-side contextFor) but is not a subclass of it.
//
// ── SECURITY MODEL (identical posture to controlMcpBridge.ts — read that file) ──
//
// AUTHORITY IS HOST-SIDE, NEVER OFF THE WIRE. A connection authenticates to a
// binding via its random token; every field that decides what a call may do is
// read FRESH from that binding's session row (`executionPolicyForSession`) at call
// time. The `tool_use` frame carries correlation fields (sessionId/ownerId/runId,
// per macOS' omiRelayCorrelation) — this relay IGNORES all of them for authority
// and uses only `name`/`input`. A model with shell access can read its own token;
// that grants exactly its own authority and nothing else, because the pipe name is
// random and each binding's token is random. Leaf gating, the trusted-control
// gate, and Zod validation all apply because control tools go through
// handleAgentControlToolCall unchanged — there is deliberately no second copy of
// any of those checks here.
//
// DARK / additive: nothing spawns pi with this pipe/token in production yet (that
// env wiring is a later PR). The bridge is constructed and listens in the control
// plane singleton, but no live client connects. Tests drive it with a mock socket.

import { createServer, type Server, type Socket } from 'node:net'
import { randomBytes } from 'node:crypto'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import type { AgentRuntimeKernel } from './kernel'
import {
  handleAgentControlToolCall,
  isAgentControlToolName,
  type AgentControlToolContext
} from './controlTools'
import { productManifestEntry, type OmiToolTimeoutClass } from './omiToolManifest'
import { createCaptureScreenExecutor } from './captureScreenExecutor'
import { tierAProductToolExecutors, tierBProductToolExecutors } from './productToolExecutors'

/** A single frame may not exceed this. Hostile input must not exhaust main's heap. */
const MAX_FRAME_BYTES = 1024 * 1024

/** macOS' 30s / 10min split (manifest `timeoutClass`). Host-side backstop so a
 *  hung product-tool executor cannot leak a pending entry forever; the extension
 *  owns its own client-side timeout too (see the wire contract). */
const DEFAULT_NORMAL_TIMEOUT_MS = 30_000
const DEFAULT_LONG_TIMEOUT_MS = 10 * 60_000

/** What a registered binding gets handed, to put in its pi subprocess's env. */
export interface ToolRelayRegistration {
  pipePath: string
  token: string
}

interface BindingAuthority {
  sessionId: string
  adapterId: string
}

/** The context a product-tool executor is invoked with. Identity is host-derived
 *  from the binding — NEVER from the wire frame. */
export interface ProductToolContext {
  sessionId: string
  adapterId: string
  /** Aborted when the client socket disconnects mid-call, so a well-behaved
   *  executor can stop work it can no longer deliver. */
  signal: AbortSignal
}

/** A serviceable product tool: takes the tool input + host-derived context, returns
 *  the opaque string that becomes `tool_result.result`. Errors should be thrown (or
 *  returned as an `"Error: …"` string) — the relay never lets a throw crash the
 *  socket. */
export type ProductToolExecutor = (
  input: Record<string, unknown>,
  ctx: ProductToolContext
) => Promise<string>

/**
 * The set of product ("swift") tool names Windows can actually service in-process,
 * and the executor for each. SOURCE OF TRUTH for "serviceable" — the extension's
 * tool-registration projection should advertise only these to pi so the model does
 * not waste turns on tools that will only degrade.
 *
 * `capture_screen` (PR-F) captures the screen locally and returns a file PATH,
 * mirroring macOS' capture tool; its "Screen Sharing in Chat" consent gate lives
 * inside the executor (captureScreenExecutor.ts), enforced here at dispatch.
 *
 * The Tier-A bundle (PR-3, productToolExecutors.ts) adds the thin tasks + screen-
 * search executors whose data layer already exists on Windows: `semantic_search`,
 * `search_tasks`, `get_action_items`, `create_action_item`, `update_action_item`,
 * `complete_task`, `delete_task`. `load_skill` needs no host executor — the pi-mono
 * extension answers it in-process (node-tools.ts), never over this relay.
 *
 * The Tier-B bundle (PR-4..7) adds `execute_sql` (read-only, table-allowlisted),
 * the backend-backed `get_memories` / `search_memories` / `get_conversations` /
 * `search_conversations`, the local composition tools `get_work_context` /
 * `get_daily_recap`, and `save_knowledge_graph`.
 *
 * Every still-unmapped product tool degrades cleanly (the "not available on Windows
 * yet" path) with fallback telemetry — macOS services those by handing them to Swift
 * over a second process boundary Windows does not have; later PRs port the rest.
 */
export const defaultProductToolExecutors: ReadonlyMap<string, ProductToolExecutor> = new Map<
  string,
  ProductToolExecutor
>([
  ['capture_screen', createCaptureScreenExecutor()],
  ...tierAProductToolExecutors(),
  ...tierBProductToolExecutors()
])

/** The advertised-serviceable allowlist, derived from the default registry so the
 *  two can never drift. Consumed by the extension's projection layer. */
export const WINDOWS_SERVICEABLE_PRODUCT_TOOLS: ReadonlySet<string> = new Set(
  defaultProductToolExecutors.keys()
)

/** Structured event for a relay fail-open/degrade path. There is no shared Windows
 *  recordFallback emitter yet (AGENTS.md fallback telemetry: emitters are
 *  Python/Swift/Rust only), so the default emitter matches the established Windows
 *  pattern (a single structured console.warn — see billing.ts, aiUserProfile). */
export interface ToolRelayFallbackEvent {
  component: 'tool_relay'
  from: string
  to: string
  reason: string
  outcome: 'recovered' | 'degraded' | 'exhausted'
  tool: string
}

export type RecordToolRelayFallback = (event: ToolRelayFallbackEvent) => void

const defaultRecordFallback: RecordToolRelayFallback = (event) => {
  console.warn('[tool-relay] fallback', event)
}

export interface ToolRelayBridgeOptions {
  kernel: AgentRuntimeKernel
  log?: (message: string) => void
  /** Serviceable product-tool executors. Defaults to the empty production registry. */
  productExecutors?: ReadonlyMap<string, ProductToolExecutor>
  /** Fail-open/degrade telemetry sink. Defaults to a structured console.warn. */
  recordFallback?: RecordToolRelayFallback
  /** Override the host-side pending-call timeouts (tests use short values). */
  timeouts?: { normalMs?: number; longMs?: number }
}

/** One in-flight product-tool call awaiting its executor (or a timeout/disconnect). */
interface PendingCall {
  readonly name: string
  timer: ReturnType<typeof setTimeout> | null
  readonly controller: AbortController
  /** Writes the single `tool_result` for this call. Idempotent — the first of
   *  {executor resolve, executor throw, timeout, disconnect} wins. */
  finish: (result: string) => void
}

/**
 * Host half of the pi-mono product/control tool relay. Owns one local socket server
 * for the runtime node; each binding registers to get a token that identifies it on
 * that socket.
 */
export class AgentToolRelayBridge {
  private readonly kernel: AgentRuntimeKernel
  private readonly log: (message: string) => void
  private readonly productExecutors: ReadonlyMap<string, ProductToolExecutor>
  private readonly recordFallback: RecordToolRelayFallback
  private readonly normalTimeoutMs: number
  private readonly longTimeoutMs: number
  /** token -> the binding whose authority that token carries. */
  private readonly authorities = new Map<string, BindingAuthority>()
  /** `${sessionId}\0${adapterId}` -> token, so re-registering a binding is idempotent. */
  private readonly tokensByBinding = new Map<string, string>()
  private readonly sockets = new Set<Socket>()
  /** socket -> (callId -> pending). Per-socket so one client's disconnect never
   *  touches another client's in-flight calls. */
  private readonly pendingBySocket = new Map<Socket, Map<string, PendingCall>>()
  private server: Server | null = null
  private listening: Promise<string> | null = null
  private readonly pipePath: string

  constructor(options: ToolRelayBridgeOptions) {
    this.kernel = options.kernel
    this.log = options.log ?? (() => {})
    this.productExecutors = options.productExecutors ?? defaultProductToolExecutors
    this.recordFallback = options.recordFallback ?? defaultRecordFallback
    this.normalTimeoutMs = options.timeouts?.normalMs ?? DEFAULT_NORMAL_TIMEOUT_MS
    this.longTimeoutMs = options.timeouts?.longMs ?? DEFAULT_LONG_TIMEOUT_MS
    this.pipePath = randomPipePath()
  }

  /** Start listening. Idempotent and safe to race — the first call owns the promise. */
  async start(): Promise<string> {
    if (!this.listening) {
      this.listening = new Promise<string>((resolve, reject) => {
        const server = createServer((socket) => this.acceptConnection(socket))
        server.once('error', reject)
        server.listen(this.pipePath, () => {
          server.removeListener('error', reject)
          this.server = server
          this.log(`[tool-relay] listening on ${this.pipePath}`)
          resolve(this.pipePath)
        })
      })
    }
    return this.listening
  }

  /**
   * Mint (or reuse) the token that lets this binding's pi subprocess act with this
   * binding's authority. Reused rather than re-minted so a resumed binding keeps a
   * stable env and the token map stays bounded.
   */
  register(sessionId: string, adapterId: string): ToolRelayRegistration {
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
      this.rejectPending(socket, 'Error: omi tool relay bridge closing')
      socket.destroy()
    }
    this.sockets.clear()
    this.pendingBySocket.clear()
    this.authorities.clear()
    this.tokensByBinding.clear()
    const server = this.server
    this.server = null
    this.listening = null
    if (!server) return
    await new Promise<void>((resolve) => server.close(() => resolve()))
  }

  /** Test/diagnostic seam: total in-flight product-tool calls across all sockets. */
  pendingCallCount(): number {
    let total = 0
    for (const perSocket of this.pendingBySocket.values()) total += perSocket.size
    return total
  }

  private acceptConnection(socket: Socket): void {
    this.sockets.add(socket)
    socket.setEncoding('utf8')

    // Unauthenticated until a valid `hello` arrives.
    let authority: BindingAuthority | null = null
    let buffer = ''

    const fail = (message: string): void => {
      this.log(`[tool-relay] dropping connection: ${message}`)
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
    socket.on('close', () => {
      this.sockets.delete(socket)
      this.rejectPending(socket, 'Error: omi tool relay client disconnected')
    })
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
    if (frame.type !== 'tool_use') return // pi only ever sends tool_use; ignore anything else
    const callId = typeof frame.callId === 'string' ? frame.callId : null
    if (!callId) return
    const name = typeof frame.name === 'string' ? frame.name : ''
    const input = plainObject(frame.input)

    if (isAgentControlToolName(name)) {
      // Synchronous/in-process: leaf guard, trusted-control gate, owner guard, Zod
      // validation and dispatch all live inside handleAgentControlToolCall. No
      // pending map — a control call cannot span a boundary that could hang.
      try {
        const result = await handleAgentControlToolCall(this.contextFor(authority), name, input)
        write(socket, { type: 'tool_result', callId, result })
      } catch (error) {
        write(socket, {
          type: 'tool_result',
          callId,
          result: `Error: ${error instanceof Error ? error.message : String(error)}`
        })
      }
      return
    }

    const executor = this.productExecutors.get(name)
    if (!executor) {
      // Not serviceable on Windows yet: degrade cleanly + surface it (silent UX
      // healing is allowed, silent ops is not — AGENTS.md fallback telemetry).
      write(socket, {
        type: 'tool_result',
        callId,
        result: `Error: ${name} is not available on Windows yet`
      })
      this.recordFallback({
        component: 'tool_relay',
        from: authority.adapterId,
        to: 'none',
        reason: 'unsupported_tool',
        outcome: 'exhausted',
        tool: name
      })
      return
    }

    this.dispatchProductTool(socket, authority, callId, name, input, executor)
  }

  private dispatchProductTool(
    socket: Socket,
    authority: BindingAuthority,
    callId: string,
    name: string,
    input: Record<string, unknown>,
    executor: ProductToolExecutor
  ): void {
    let perSocket = this.pendingBySocket.get(socket)
    if (perSocket?.has(callId)) {
      // A duplicate callId on a still-pending key is a client bug — reject it
      // rather than overwrite the live entry (macOS index.ts:360-369).
      write(socket, { type: 'tool_result', callId, result: `Error: duplicate callId ${callId}` })
      return
    }
    if (!perSocket) {
      perSocket = new Map<string, PendingCall>()
      this.pendingBySocket.set(socket, perSocket)
    }

    const controller = new AbortController()
    let done = false
    const finish = (result: string): void => {
      if (done) return
      done = true
      if (pending.timer) clearTimeout(pending.timer)
      const owning = this.pendingBySocket.get(socket)
      if (owning) {
        owning.delete(callId)
        if (owning.size === 0) this.pendingBySocket.delete(socket)
      }
      write(socket, { type: 'tool_result', callId, result })
    }
    const pending: PendingCall = { name, timer: null, controller, finish }

    const timeoutMs = this.timeoutFor(name)
    pending.timer = setTimeout(() => {
      finish(`Error: tool '${name}' timed out after ${timeoutMs}ms`)
    }, timeoutMs)
    if (typeof pending.timer.unref === 'function') pending.timer.unref()
    perSocket.set(callId, pending)

    void (async () => {
      try {
        const result = await executor(input, {
          sessionId: authority.sessionId,
          adapterId: authority.adapterId,
          signal: controller.signal
        })
        finish(typeof result === 'string' ? result : String(result))
      } catch (error) {
        finish(`Error: ${error instanceof Error ? error.message : String(error)}`)
      }
    })()
  }

  private timeoutFor(name: string): number {
    const timeoutClass: OmiToolTimeoutClass = productManifestEntry(name)?.timeoutClass ?? 'normal'
    return timeoutClass === 'long' ? this.longTimeoutMs : this.normalTimeoutMs
  }

  /** Resolve every in-flight call on this socket with an error. Only this socket's
   *  pending map is touched — an active client's calls are never clobbered
   *  (macOS resolveClientToolCalls, index.ts:215-222). */
  private rejectPending(socket: Socket, message: string): void {
    const perSocket = this.pendingBySocket.get(socket)
    if (!perSocket) return
    this.pendingBySocket.delete(socket)
    for (const pending of perSocket.values()) {
      pending.controller.abort()
      pending.finish(message) // clears the timer; the write is a no-op on a dead socket
    }
    perSocket.clear()
  }

  private contextFor(authority: BindingAuthority): AgentControlToolContext {
    return buildControlToolContext(this.kernel, authority)
  }
}

/** Build a control-tool context with HOST-DERIVED authority. Read fresh on every
 *  call: a session whose role or owner changed must not keep acting under the
 *  authority it had when its subprocess started. Shared by the socket relay and
 *  the in-process `executeHostTool` dispatcher so both enforce the identical
 *  posture (a model is never trusted user control). */
function buildControlToolContext(
  kernel: AgentRuntimeKernel,
  authority: BindingAuthority
): AgentControlToolContext {
  const policy = kernel.executionPolicyForSession(authority.sessionId)
  return {
    kernel,
    // A model is never trusted user control.
    trustedUserControl: false,
    executionRole: policy.executionRole,
    providerBoundary: policy.providerBoundary,
    defaultAdapterId: policy.defaultAdapterId,
    // Load-bearing — see controlMcpBridge.ts note 4.
    callerSessionId: authority.sessionId,
    getOwnerId: () => policy.ownerId
  }
}

/** In-process host-tool dispatch context. Identity is HOST-DERIVED: the caller
 *  supplies the kernel plus the sessionId/adapterId of the surface's OWN kernel
 *  session (never a wire-claimed id), and role/owner are resolved fresh from
 *  `executionPolicyForSession`. */
export interface HostToolDispatchContext {
  kernel: AgentRuntimeKernel
  sessionId: string
  adapterId: string
  /** Aborted when the caller no longer wants the result (optional). */
  signal?: AbortSignal
  /** Serviceable product executors. Defaults to the production registry. */
  productExecutors?: ReadonlyMap<string, ProductToolExecutor>
}

/**
 * Dispatch one Omi tool IN-PROCESS, without the pi socket relay. This is the shared
 * entry the voice-kernel hub dispatcher reuses so voice and chat answer from one
 * code path (macOS parity — same executor functions, no second process hop). Same
 * host-authoritative posture as the socket relay: control tools go through
 * `handleAgentControlToolCall` with a `trustedUserControl:false` context whose
 * role/owner are read fresh from the session; product tools look up the registry.
 * Errors are RETURNED as `"Error: …"` strings, never thrown — matching the relay's
 * `tool_result` contract.
 *
 * SECURITY (INV-AGENT): callers MUST pass the surface's own kernel session id and
 * must NEVER route model-driven calls through the renderer's trusted-direct-control
 * door (`agentControlCall`). This is that door's opposite: a model-authority
 * dispatch that can never be trusted user control.
 */
export async function executeHostTool(
  name: string,
  input: Record<string, unknown>,
  ctx: HostToolDispatchContext
): Promise<string> {
  const authority: BindingAuthority = { sessionId: ctx.sessionId, adapterId: ctx.adapterId }
  try {
    if (isAgentControlToolName(name)) {
      // Leaf guard, trusted-control gate, owner guard, and Zod validation all live
      // inside handleAgentControlToolCall — there is deliberately no second copy.
      return await handleAgentControlToolCall(
        buildControlToolContext(ctx.kernel, authority),
        name,
        input
      )
    }
    const registry = ctx.productExecutors ?? defaultProductToolExecutors
    const executor = registry.get(name)
    if (!executor) {
      return `Error: ${name} is not available on Windows yet`
    }
    const result = await executor(input, {
      sessionId: ctx.sessionId,
      adapterId: ctx.adapterId,
      signal: ctx.signal ?? new AbortController().signal
    })
    return typeof result === 'string' ? result : String(result)
  } catch (error) {
    return `Error: ${error instanceof Error ? error.message : String(error)}`
  }
}

function bindingKey(sessionId: string, adapterId: string): string {
  return `${sessionId}\0${adapterId}`
}

/**
 * Random, not derived. A derivable name would let one agent's shell find another
 * agent's socket. Distinct prefix from controlMcpBridge's `omi-agent-mcp-` so the
 * two servers are never confused. Named pipes on win32 are not filesystem entries,
 * so there is nothing to unlink (contrast macOS' Unix-socket path).
 */
function randomPipePath(): string {
  const id = randomBytes(16).toString('hex')
  return process.platform === 'win32'
    ? `\\\\.\\pipe\\omi-tool-relay-${id}`
    : join(tmpdir(), `omi-tool-relay-${id}.sock`)
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
