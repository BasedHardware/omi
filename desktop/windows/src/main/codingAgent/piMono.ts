// PiMonoAdapter — Windows port of desktop/macos/agent/src/adapters/pi-mono.ts.
//
// pi-mono is Omi's managed-cloud chat harness: the bundled
// `@earendil-works/pi-coding-agent` CLI run as a `--mode rpc` subprocess whose
// model calls route through Omi's own backend using the user's Firebase token
// (server-billed). This file is a near-verbatim port of the macOS adapter — the
// RPC event loop, generation/pending-request correlation, required-control-tool
// tracking, model mapping, and deferred-restart lifecycle are unchanged.
//
// This PR lands the adapter DARK: it is NOT registered in the adapter registry,
// NOT in ADAPTER_CAPABILITY_MATRIX, and nothing routes to it yet. Only tests
// consume it. Registration, the auth relay, the tool-manifest/OMI_BRIDGE_PIPE
// relay, and default-chat routing arrive in later PRs.
//
// Windows deviations from the macOS source, each load-bearing:
//   - Subprocess spawn: macOS spawns pi's `dist/cli.js` directly; Windows spawns
//     Electron's own binary as plain Node (ELECTRON_RUN_AS_NODE=1) with the
//     resolved cli.js as argv[0], mirroring the ACP bridge (acp.ts:288-297).
//   - resolveBundledPi(): macOS walks import.meta.url and prefers the flat
//     cli.js to dodge a ditto `.bin` symlink quirk that does not exist on
//     Windows; Windows resolves the real cli.js via Node module resolution
//     (createRequire), the same pattern agentKernel/store.ts uses for
//     better-sqlite3.
//   - Event vocabulary: Windows' AdapterEventSink is the narrow AdapterStreamEvent
//     union (no `tool_use` / `error` variants), so the RuntimeAdapter wrapper
//     forwards only canonical stream events to the sink; harness `error` still
//     propagates via the rejected sendPrompt promise (matching the ACP adapter),
//     and `tool_use` is display-redundant with `tool_activity`.
//   - Capabilities: pi-mono is not yet in ADAPTER_CAPABILITY_MATRIX (DARK), so
//     the wrapper uses a local static capability set equal to what the macOS
//     matrix entry produces. PR-D moves this into the shared matrix.
//   - The small HarnessConfig / HarnessFeature / HarnessAdapter / SessionOpts /
//     PromptResult / ToolExecutor / EventCallback / WarmupSessionConfig types
//     were trimmed from Windows' interface.ts; they are re-declared locally so
//     the port stays self-contained and does not widen the shared contract.

import { ChildProcess, spawn } from 'child_process'
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'fs'
import { tmpdir } from 'os'
import { dirname, join } from 'path'
import { createInterface, Interface as ReadlineInterface } from 'readline'
import { fileURLToPath } from 'url'
import type {
  AdapterAttemptContext,
  AdapterAttemptResult,
  AdapterBindingHandle,
  AdapterCapabilities,
  AdapterEventSink,
  AdapterStreamEvent,
  CancelAttemptContext,
  CancelDispatchResult,
  OpenBindingInput,
  OpenedBinding,
  PromptBlock,
  ResumeBindingInput,
  RuntimeAdapter,
  ToolDef
} from './interface'

// === Harness-config types (trimmed from Windows interface.ts) ================
// Re-declared locally so the pi-mono port stays self-contained and DARK — it
// does not widen the shared adapter contract. These mirror the macOS
// interface.ts definitions the harness class depends on.

/** Configuration for creating the pi-mono harness adapter. */
export interface HarnessConfig {
  /** Omi API base URL for the pi-mono provider (wired in PR-B). */
  omiApiBaseUrl?: string
  /** Firebase auth token for Omi API authentication (wired in PR-B). */
  authToken?: string
  /**
   * The complete `OMI_BYOK_*` env set to inject at spawn when the user has all
   * four BYOK provider keys, or undefined/`{}` for Omi-managed billing. Built by
   * the pi-mono session store from `ByokKeyStore` (`byokEnvVars`, all-or-nothing)
   * and passed through at spawn — the bundled omi-provider extension reads these
   * and re-emits them as `X-BYOK-*` headers. Separate from `authToken`: the
   * managed `OMI_API_KEY` is always the Firebase token, never a BYOK key.
   */
  byokEnv?: Record<string, string>
}

interface SessionOpts {
  cwd: string
  model?: string
  systemPrompt?: string
  mcpServers?: Record<string, unknown>[]
  executionRole?: 'coordinator' | 'leaf'
}

interface PromptResult {
  text: string
  sessionId: string
  costUsd?: number
  inputTokens?: number
  outputTokens?: number
  cacheReadTokens?: number
  cacheWriteTokens?: number
}

/** Callback for tool execution — harness calls this, host returns the result. */
type ToolExecutor = (name: string, input: Record<string, unknown>) => Promise<string>

interface WarmupSessionConfig {
  model?: string
  systemPrompt?: string
}

/**
 * The harness's own event vocabulary. It is a superset of Windows'
 * AdapterStreamEvent: pi additionally emits `tool_use` (display-redundant with
 * `tool_activity`) and `error` (which also rejects the pending prompt). The
 * RuntimeAdapter wrapper forwards only the AdapterStreamEvent-compatible events
 * to the narrow kernel sink.
 */
type PiStreamEvent =
  | AdapterStreamEvent
  | { type: 'tool_use'; callId: string; name: string; input?: Record<string, unknown> }
  | { type: 'error'; message: string; adapterSessionId?: string }

type EventCallback = (event: PiStreamEvent) => void

/** Features a harness may or may not support (parity with macOS HarnessFeature). */
export enum HarnessFeature {
  MCP_CLIENT = 'mcp_client',
  BIDIRECTIONAL_RPC = 'bidirectional_rpc',
  SESSION_RESUME = 'session_resume',
  COST_TRACKING = 'cost_tracking',
  OAUTH = 'oauth',
  MODEL_SWITCH = 'model_switch'
}

type PiMonoConfig = HarnessConfig & {
  onRestart?: (reason: string) => void
}

/**
 * Test/wiring seams for the harness. `nodeBin` defaults to Electron's own
 * binary (run as Node); `piPath` / `extensionPath` default to the bundled
 * resolvers. Tests inject all three so no real subprocess or package resolution
 * is exercised.
 */
export interface PiMonoAdapterOptions {
  piPath?: string
  extensionPath?: string
  nodeBin?: string
}

// Pi-mono RPC command/event types
interface PiRpcCommand {
  id?: string
  type: string
  [key: string]: unknown
}

interface PiRpcEvent {
  type: string
  [key: string]: unknown
}

interface PiMonoRelayContext {
  protocolVersion: 2
  requestId: string
  clientId: string
  sessionId: string
  runId: string
  attemptId: string
  adapterSessionId?: string
  disableSwiftBackedTools?: boolean
}

interface PiAssistantMessageEvent {
  type: string
  contentIndex?: number
  delta?: string
  content?: string
  partial?: PiAssistantMessage
  message?: PiAssistantMessage
  toolCall?: PiToolCall
  reason?: string
  error?: PiAssistantMessage
}

interface PiAssistantMessage {
  role: string
  content: PiContentBlock[]
  usage?: PiUsage
  stopReason?: string
  errorMessage?: string
}

interface PiContentBlock {
  type: string
  text?: string
  thinking?: string
  id?: string
  name?: string
  arguments?: Record<string, unknown>
}

interface PiToolCall {
  id: string
  name: string
  arguments: Record<string, unknown>
}

interface PiUsage {
  input: number
  output: number
  cacheRead: number
  cacheWrite: number
  totalTokens: number
  cost?: {
    input: number
    output: number
    cacheRead: number
    cacheWrite: number
    total: number
  }
}

const REQUIRED_AGENT_CONTROL_TOOLS = new Set([
  'send_agent_message',
  'spawn_background_agent',
  'spawn_agent',
  'run_agent_and_wait'
])

function requiredAgentControlFailure(toolName: string, output: string): string | undefined {
  if (!REQUIRED_AGENT_CONTROL_TOOLS.has(toolName)) return undefined
  if (output.startsWith('Error:')) return output
  try {
    const parsed = JSON.parse(output) as { ok?: unknown; error?: { message?: unknown } }
    if (parsed.ok === false) {
      const detail = typeof parsed.error?.message === 'string' ? parsed.error.message : output
      return `Required ${toolName} operation failed: ${detail}`
    }
  } catch {
    // A successful control tool always returns the canonical JSON envelope.
    // Preserve a prior failure until an explicit successful retry clears it.
  }
  return undefined
}

function requiredControlOperationKey(
  toolName: string,
  input: Record<string, unknown> | undefined
): string {
  const ignored = new Set(['adapterId', 'provider', 'defaultAdapterId', 'requestId', 'clientId'])
  const normalized = Object.fromEntries(
    Object.entries(input ?? {})
      .filter(([key]) => !ignored.has(key))
      .sort(([left], [right]) => left.localeCompare(right))
  )
  return `${toolName}:${JSON.stringify(normalized)}`
}

// Map desktop model IDs (claude-*) to omi provider model IDs.
// Covers short aliases and dated versions used by the chat provider/ChatLab.
const MODEL_MAP: Record<string, string> = {
  'claude-opus-4-6': 'omi-opus',
  'claude-sonnet-4-6': 'omi-sonnet',
  'claude-sonnet-4': 'omi-sonnet',
  'claude-opus-4': 'omi-opus',
  'claude-sonnet-4-20250514': 'omi-sonnet',
  'claude-opus-4-20250514': 'omi-opus'
}

function mapModel(model: string): string {
  return MODEL_MAP[model] ?? model
}

/** Resolve the pi CLI bundled inside the app.
 *
 *  Resolution order:
 *  1. $PI_MONO_PATH (test/dev override)
 *  2. `@earendil-works/pi-coding-agent/dist/cli.js` via Node module resolution.
 *
 *  Unlike macOS, Windows has no ditto `.bin` symlink quirk, so we resolve the
 *  real cli.js directly and spawn it under ELECTRON_RUN_AS_NODE. createRequire
 *  is the same seam agentKernel/store.ts uses for better-sqlite3; it works in
 *  both dev (out/) and packaged (asar-unpacked) builds. The package must be
 *  asar-unpacked (electron-builder.yml) so the plain-Node child can read it.
 */
function resolveBundledPi(): string {
  // The package's `exports` map exposes only the ESM `import` condition for "."
  // (→ dist/index.js) and "./rpc-entry"; it defines NO CJS `require` condition
  // and does NOT expose ./dist/cli.js. So a `createRequire().resolve` fails on
  // both counts — we must use ESM resolution of the package root and derive the
  // sibling cli.js (bin.pi = dist/cli.js, same dist/ directory as index.js).
  // import.meta.resolve is synchronous and preserved through the electron-vite
  // ESM main bundle.
  const indexUrl = import.meta.resolve('@earendil-works/pi-coding-agent')
  return join(dirname(fileURLToPath(indexUrl)), 'cli.js')
}

/** Resolve the omi-provider extension file bundled alongside the app.
 *
 *  The pi-mono-extension (omi provider registration + Windows denylist + the
 *  OMI_BRIDGE_PIPE relay client) lives at ./pi-mono-extension/index.ts, a raw
 *  `.ts` file pi loads on the fly via jiti (no precompile). This resolver
 *  returns its on-disk path relative to this module's source.
 *
 *  DARK: the adapter is still unregistered, so this resolver is never called in
 *  production yet — every production path either injects an explicit
 *  extensionPath or does not spawn pi at all. Final packaging (asar-unpack of
 *  the extension source + its .ts dep tree so the plain-Node child can read it)
 *  is finished when the adapter is activated in PR-D/E.
 */
function resolveBundledExtension(): string {
  return join(dirname(fileURLToPath(import.meta.url)), 'pi-mono-extension', 'index.ts')
}

/**
 * PiMonoAdapter spawns pi-mono in RPC mode and translates its events into the
 * normalized adapter events.
 *
 * Tool execution flows:
 * 1. Pi-mono executes its built-in tools internally (bash, read, write, edit).
 * 2. Custom Omi tools are registered via the extension, which routes them
 *    through the Omi API backend / the OMI_BRIDGE_PIPE relay (PR-C).
 */
export class PiMonoAdapter {
  private static nextAdapterInstanceId = 1

  readonly name = 'pi-mono'

  private config: PiMonoConfig
  private process: ChildProcess | null = null
  private readline: ReadlineInterface | null = null
  private sessions: Map<string, { cwd: string; model?: string; systemPrompt?: string }> = new Map()
  private nextSessionId = 1
  /** Per-prompt state — keyed by monotonic prompt generation ID, not session ID.
   *  Pi-mono RPC only processes one prompt at a time, so a generation counter
   *  is sufficient for correlation. Late/stray turn_end events that don't
   *  match the in-flight generation are dropped. */
  private pendingRequests: Map<
    number,
    {
      sessionId: string
      resolve: (value: unknown) => void
      reject: (err: Error) => void
    }
  > = new Map()
  /** Generation of the currently-in-flight prompt (0 = none) */
  private activePromptGeneration = 0
  /** Monotonic counter for prompt generations */
  private nextPromptGeneration = 1
  private nextRequestId = 1
  private eventHandler: EventCallback | null = null
  /** Unresolved required control obligations for the active turn. */
  private requiredAgentControlFailures = new Map<string, string>()
  private requiredControlInputs = new Map<string, Record<string, unknown>>()
  private currentAbortController: AbortController | null = null
  private readonly nodeBin: string
  private piPath: string
  private extensionPath: string
  private readonly contextFilePath = join(
    tmpdir(),
    `omi-pi-mono-context-${process.pid}-${Math.random().toString(36).slice(2)}.json`
  )
  /** Current system prompt baked into the spawned pi process via --system-prompt.
   *  Pi has no set_system_prompt RPC, so changing this requires a subprocess restart. */
  private currentSystemPrompt: string | undefined
  private currentExecutionRole: 'coordinator' | 'leaf' = 'coordinator'
  private readonly sessionPrefix: string
  /** True when a token refresh was deferred because a prompt was active */
  private pendingTokenRefresh = false
  /** True when a system-prompt change was deferred because a prompt was active */
  private pendingSystemPromptRefresh = false

  constructor(config: PiMonoConfig, options: PiMonoAdapterOptions = {}) {
    this.config = config
    this.sessionPrefix = `pi-worker-${PiMonoAdapter.nextAdapterInstanceId++}`
    this.nodeBin = options.nodeBin ?? process.execPath
    this.piPath = options.piPath || process.env.PI_MONO_PATH || resolveBundledPi()
    this.extensionPath =
      options.extensionPath || process.env.PI_EXTENSION_PATH || resolveBundledExtension()
  }

  async start(): Promise<void> {
    if (this.process) {
      return
    }

    const args = [
      '--mode',
      'rpc',
      '-e',
      this.extensionPath,
      '--provider',
      'omi',
      '--model',
      'omi-sonnet'
      // Auto-discover extensions and MCP servers from the user's machine
      // to maximize pi-mono's capabilities (e.g. Playwright, filesystem tools).
      // SECURITY NOTE: auto-discovered extensions run in the pi subprocess and
      // can read process.env (including OMI_API_KEY). This is acceptable because:
      // 1. OMI_API_KEY is a short-lived Firebase ID token (~1 hour expiry)
      // 2. Extensions are user-installed — the trust boundary is the user's machine
      // 3. ANTHROPIC_API_KEY is always scrubbed (never exposed to extensions)
    ]
    // Pi has no set_system_prompt RPC — system prompt must be baked at spawn
    // time via the --system-prompt CLI flag. To change it, restart the process.
    if (this.currentSystemPrompt) {
      args.push('--system-prompt', this.currentSystemPrompt)
    }

    // SECURITY: require a Firebase ID token. We MUST NOT fall back to
    // ANTHROPIC_API_KEY — the Omi backend rejects provider keys and forwarding
    // one here would leak the upstream secret to api.omi.me.
    if (!this.config.authToken) {
      throw new Error('pi-mono adapter requires config.authToken (Firebase ID token)')
    }

    // Scrub any ANTHROPIC_API_KEY from the child env so the extension cannot
    // accidentally read it as a credential. pi-mono talks to api.omi.me with
    // OMI_API_KEY only.
    const env: Record<string, string> = {
      ...(process.env as Record<string, string>)
    }
    delete env.ANTHROPIC_API_KEY

    // SECURITY: OMI_YOLO_MODE bypasses the extension's entire tool denylist.
    // Scrub it from the subprocess env, then only re-inject when explicitly
    // set in the parent. Log when active so usage is auditable.
    delete env.OMI_YOLO_MODE
    if (process.env.OMI_YOLO_MODE === '1') {
      env.OMI_YOLO_MODE = '1'
      process.stderr.write('[pi-mono] WARNING: OMI_YOLO_MODE=1 — denylist bypass active\n')
    }

    // BYOK: scrub every inherited OMI_BYOK_* first (parity with macOS
    // removeInheritedBYOKEnvironment), so a stale/partial set from the parent env
    // can never leak into the subprocess, then inject only the complete set the
    // session store built (all-or-nothing — see byokEnvVars). Key material is
    // never logged.
    for (const key of Object.keys(env)) {
      if (key.toUpperCase().startsWith('OMI_BYOK_')) delete env[key]
    }
    if (this.config.byokEnv) {
      Object.assign(env, this.config.byokEnv)
    }

    // In Electron, process.execPath is the app binary, not node. This flag makes
    // the spawned copy run as plain Node so it executes pi's cli.js (and is
    // inherited, so pi's own nested spawns work too). Mirrors acp.ts.
    env.ELECTRON_RUN_AS_NODE = '1'
    env.NODE_NO_WARNINGS = '1'

    // Pass the raw Firebase ID token. pi's openai-completions client already
    // prepends `Authorization: Bearer ${apiKey}` — adding our own "Bearer "
    // prefix here would produce a malformed `Bearer Bearer <token>` header.
    env.OMI_API_KEY = this.config.authToken
    if (this.config.omiApiBaseUrl) {
      env.OMI_API_BASE_URL = this.config.omiApiBaseUrl
    }
    env.OMI_ADAPTER_ID = 'pi-mono'
    env.OMI_EXECUTION_ROLE = this.currentExecutionRole
    env.OMI_CONTEXT_FILE = this.contextFilePath
    // OMI_BRIDGE_PIPE is inherited from process.env when the host relay is
    // running (PR-C); the extension registers omi-tools that forward over it.

    this.process = spawn(this.nodeBin, [this.piPath, ...args], {
      stdio: ['pipe', 'pipe', 'pipe'],
      env,
      shell: false,
      windowsHide: true
    })

    if (!this.process.stdout || !this.process.stdin) {
      throw new Error('Failed to create pi-mono subprocess pipes')
    }

    // Read JSONL events from stdout
    this.readline = createInterface({ input: this.process.stdout })
    this.readline.on('line', (line: string) => {
      this.handleEvent(line)
    })

    // Log stderr
    if (this.process.stderr) {
      this.process.stderr.on('data', (data: Buffer) => {
        const msg = data.toString().trim()
        if (msg) {
          process.stderr.write(`[pi-mono] ${msg}\n`)
        }
      })
    }

    this.process.on('exit', (code: number | null) => {
      process.stderr.write(`[pi-mono] process exited with code ${code}\n`)
      this.process = null
      this.readline = null
      this.sessions.clear()
      // Reject pending requests
      for (const [, req] of this.pendingRequests) {
        req.reject(new Error(`pi-mono process exited (code ${code})`))
      }
      this.pendingRequests.clear()
      this.activePromptGeneration = 0
      rmSync(this.contextFilePath, { force: true })
    })
  }

  async stop(): Promise<void> {
    if (this.process) {
      // Remove all listeners from the old process FIRST so its delayed exit
      // event can't fire the exit handler after we've already spawned a
      // replacement. Without this, a stop()/start() cycle that interleaves
      // with an incoming sendPrompt can race: the old process's exit event
      // arrives after the new pendingRequest is registered, and the handler
      // rejects the fresh request with "pi-mono process exited (code null)".
      this.process.removeAllListeners('exit')
      if (this.process.stdout) this.process.stdout.removeAllListeners()
      if (this.process.stderr) this.process.stderr.removeAllListeners()
      this.process.kill('SIGTERM')
      this.process = null
      if (this.readline) {
        this.readline.removeAllListeners()
        this.readline.close()
        this.readline = null
      }
    }
    this.sessions.clear()
    this.pendingRequests.clear()
    this.activePromptGeneration = 0
    rmSync(this.contextFilePath, { force: true })
  }

  async createSession(opts: SessionOpts): Promise<string> {
    const mapped = opts.model ? mapModel(opts.model) : undefined
    await this.setExecutionRole(opts.executionRole ?? 'coordinator')

    // Pi bakes the system prompt at spawn time via --system-prompt. If the
    // caller requested a different prompt than the currently-running process,
    // restart the subprocess with the new flag. Callers that want this handled
    // eagerly across session switches should call setSystemPrompt() before
    // createSession().
    if (opts.systemPrompt && opts.systemPrompt !== this.currentSystemPrompt) {
      await this.setSystemPrompt(opts.systemPrompt)
    }

    const sessionId = `${this.sessionPrefix}-session-${this.nextSessionId++}`
    this.sessions.set(sessionId, {
      cwd: opts.cwd,
      model: mapped,
      systemPrompt: opts.systemPrompt
    })

    await this.start()

    // Set model if specified (map claude-* → omi-*)
    if (mapped) {
      this.sendCommand({
        type: 'set_model',
        provider: 'omi',
        modelId: mapped
      })
    }

    return sessionId
  }

  async setExecutionRole(role: 'coordinator' | 'leaf'): Promise<void> {
    if (role === this.currentExecutionRole) return
    this.currentExecutionRole = role
    if (this.process) {
      await this.stop()
    }
  }

  async sendPrompt(
    sessionId: string,
    prompt: PromptBlock[],
    _tools: ToolDef[],
    _mode: 'ask' | 'act',
    onEvent: EventCallback,
    // Tools are relayed to the host via the extension over OMI_BRIDGE_PIPE
    // (PR-C), not through this in-process executor, so the callback is accepted
    // for signature parity but not invoked here.
    _onToolCall: ToolExecutor,
    signal?: AbortSignal,
    relayContext?: PiMonoRelayContext
  ): Promise<PromptResult> {
    if (!this.sessions.has(sessionId)) {
      throw new Error(`pi-mono session is no longer active: ${sessionId}`)
    }
    // Serialization invariant: pi-mono RPC only handles one prompt at a time.
    // Do not supersede an in-flight prompt: pi-mono turn_end events do not carry
    // a request id, so a late completion could be misattributed to the new prompt.
    if (this.activePromptGeneration !== 0) {
      throw new Error('pi-mono prompt already in flight')
    }

    this.eventHandler = onEvent
    this.requiredAgentControlFailures.clear()
    this.requiredControlInputs.clear()
    this.currentAbortController = new AbortController()
    this.writeRelayContext(relayContext)

    const generation = this.nextPromptGeneration++
    this.activePromptGeneration = generation

    if (signal) {
      signal.addEventListener('abort', () => {
        this.abort(sessionId)
      })
    }

    // Extract text and image from prompt blocks. Images ride pi's separate
    // `cmd.images` RPC field — they are NEVER concatenated into the text
    // `message`, so raw screenshot bytes can't leak into the text context.
    const textParts: string[] = []
    const images: { type: string; data: string; mimeType: string }[] = []

    for (const block of prompt) {
      if (block.type === 'text') {
        textParts.push(block.text)
      } else if (block.type === 'image') {
        images.push({
          type: 'image',
          data: block.data,
          mimeType: block.mimeType
        })
      }
    }

    const message = textParts.join('\n')

    const cmd: PiRpcCommand = {
      type: 'prompt',
      message
    }
    if (images.length > 0) {
      cmd.images = images
    }

    this.sendCommand(cmd)

    // Wait for turn_end event mapped to THIS generation
    return new Promise<PromptResult>((resolve, reject) => {
      this.pendingRequests.set(generation, {
        sessionId,
        resolve: (value: unknown) => resolve(value as PromptResult),
        reject
      })
    })
  }

  abort(sessionId: string): void {
    this.sendCommand({ type: 'abort' })
    this.currentAbortController?.abort()

    // Resolve the in-flight prompt (by generation) with a partial result and
    // CLEAR activePromptGeneration so a stray late turn_end is dropped instead
    // of completing whatever comes next.
    const generation = this.activePromptGeneration
    if (generation === 0) return
    const pending = this.pendingRequests.get(generation)
    if (pending) {
      this.pendingRequests.delete(generation)
      pending.resolve({
        text: '',
        sessionId: pending.sessionId || sessionId,
        costUsd: 0,
        inputTokens: 0,
        outputTokens: 0
      })
    }
    this.activePromptGeneration = 0
  }

  clearRelayContextForAttempt(attemptId: string): void {
    this.clearRelayContext(attemptId)
  }

  async setModel(sessionId: string, model: string): Promise<void> {
    const mapped = mapModel(model)
    const session = this.sessions.get(sessionId)
    if (session) {
      session.model = mapped
    }
    this.sendCommand({
      type: 'set_model',
      provider: 'omi',
      modelId: mapped
    })
  }

  async warmup(cwd: string, sessions: WarmupSessionConfig[]): Promise<void> {
    // Pre-create sessions
    for (const config of sessions) {
      await this.createSession({
        cwd,
        model: config.model,
        systemPrompt: config.systemPrompt
      })
    }
  }

  invalidateSession(sessionKey: string): void {
    this.sessions.delete(sessionKey)
  }

  hasSession(sessionId: string): boolean {
    return this.sessions.has(sessionId)
  }

  /** Update the system prompt baked into the pi subprocess.
   *
   *  Pi's RPC protocol has no set_system_prompt command — the system prompt
   *  is a startup-only CLI flag (--system-prompt). To change it, we must
   *  restart the subprocess. If a prompt is currently in flight, we stash the
   *  new value and restart after turn_end via the same pending-refresh path
   *  used by auth token rotation.
   *
   *  Returns true if the restart happened immediately, false if deferred. */
  async setSystemPrompt(systemPrompt: string | undefined): Promise<boolean> {
    if (systemPrompt === this.currentSystemPrompt) {
      return true // no-op
    }
    this.currentSystemPrompt = systemPrompt
    if (!this.process) {
      // Not started yet — nothing to restart; start() will bake the new value.
      return true
    }
    if (this.pendingRequests.size > 0) {
      this.pendingSystemPromptRefresh = true
      process.stderr.write('[pi-mono] system prompt stored (restart deferred, prompt active)\n')
      return false
    }
    await this.stop()
    await this.start()
    this.config.onRestart?.('systemPrompt')
    this.pendingSystemPromptRefresh = false
    process.stderr.write('[pi-mono] subprocess restarted with new system prompt\n')
    return true
  }

  /** Update auth token by restarting the subprocess when idle.
   *  The pi-mono extension bakes OMI_API_KEY at startup, so the only way
   *  to refresh is to restart the process. If a prompt is active, marks a
   *  pending restart that handleTurnEnd will execute after the prompt completes.
   *  Returns true if restart happened immediately, false if deferred. */
  async updateAuthToken(token: string): Promise<boolean> {
    this.config.authToken = token
    if (this.pendingRequests.size > 0) {
      this.pendingTokenRefresh = true
      process.stderr.write('[pi-mono] auth token stored (restart deferred, prompt active)\n')
      return false
    }
    await this.stop()
    await this.start()
    this.config.onRestart?.('token_refresh')
    this.pendingTokenRefresh = false
    process.stderr.write('[pi-mono] subprocess restarted with refreshed auth token\n')
    return true
  }

  /** Whether a prompt is currently in-flight */
  get isIdle(): boolean {
    return this.pendingRequests.size === 0
  }

  /** Whether a deferred restart is pending (token or system prompt) */
  get hasPendingRestart(): boolean {
    return this.pendingTokenRefresh || this.pendingSystemPromptRefresh
  }

  /** Execute the deferred restart (call after prompt completes).
   *  Handles both token refresh and system-prompt change — both baked at
   *  spawn time, both requiring a restart. */
  async executePendingRestart(): Promise<void> {
    if (!this.pendingTokenRefresh && !this.pendingSystemPromptRefresh) return
    const reasons: string[] = []
    if (this.pendingTokenRefresh) reasons.push('token')
    if (this.pendingSystemPromptRefresh) reasons.push('systemPrompt')
    this.pendingTokenRefresh = false
    this.pendingSystemPromptRefresh = false
    await this.stop()
    await this.start()
    this.config.onRestart?.(reasons.join('+'))
    process.stderr.write(
      `[pi-mono] deferred restart executed (${reasons.join('+')}; subprocess restarted)\n`
    )
  }

  supportsFeature(feature: HarnessFeature): boolean {
    switch (feature) {
      case HarnessFeature.BIDIRECTIONAL_RPC:
        return true
      case HarnessFeature.MODEL_SWITCH:
        return true
      case HarnessFeature.COST_TRACKING:
        return true // Server-side via Omi API
      case HarnessFeature.MCP_CLIENT:
        return false // Pi-mono doesn't use MCP
      case HarnessFeature.SESSION_RESUME:
        return false
      case HarnessFeature.OAUTH:
        return false // Uses Firebase token, not OAuth
      default:
        return false
    }
  }

  // ── Private helpers ──────────────────────────────────────────────────

  private sendCommand(cmd: PiRpcCommand): void {
    if (!this.process?.stdin?.writable) {
      throw new Error('pi-mono process not running')
    }
    const id = `req-${this.nextRequestId++}`
    cmd.id = id
    this.process.stdin.write(JSON.stringify(cmd) + '\n')
  }

  private writeRelayContext(context: PiMonoRelayContext | undefined): void {
    if (!context) {
      rmSync(this.contextFilePath, { force: true })
      return
    }
    mkdirSync(dirname(this.contextFilePath), { recursive: true })
    writeFileSync(
      this.contextFilePath,
      JSON.stringify({
        adapterId: 'pi-mono',
        ...context
      })
    )
  }

  private clearRelayContext(expectedAttemptId?: string): void {
    if (!expectedAttemptId) {
      rmSync(this.contextFilePath, { force: true })
      return
    }
    if (!existsSync(this.contextFilePath)) return

    try {
      const parsed = JSON.parse(readFileSync(this.contextFilePath, 'utf8')) as Record<
        string,
        unknown
      >
      if (parsed.attemptId !== expectedAttemptId) return
    } catch {
      // Invalid context is unusable by the extension; remove it as stale.
    }

    rmSync(this.contextFilePath, { force: true })
  }

  private handleEvent(line: string): void {
    let event: PiRpcEvent
    try {
      event = JSON.parse(line)
    } catch {
      process.stderr.write(`[pi-mono] invalid JSON: ${line}\n`)
      return
    }

    // Log key events for diagnostic visibility
    if (event.type === 'turn_end') {
      const msg = event.message as PiAssistantMessage | undefined
      const errMsg = msg?.errorMessage
      if (errMsg) {
        process.stderr.write(`[pi-mono] turn_end ERROR: ${errMsg}\n`)
      }
    }

    switch (event.type) {
      case 'message_update':
        this.handleMessageUpdate(event)
        break

      case 'tool_execution_start':
        this.handleToolStart(event)
        break

      case 'tool_execution_update':
        // Partial tool output — emit as tool_activity
        break

      case 'tool_execution_end':
        this.handleToolEnd(event)
        break

      case 'turn_end':
        this.handleTurnEnd(event)
        break

      case 'agent_start':
      case 'agent_end':
      case 'turn_start':
      case 'message_start':
      case 'message_end':
      case 'response':
      case 'compaction_start':
      case 'compaction_end':
      case 'auto_retry_start':
      case 'auto_retry_end':
        // Protocol control events the adapter observes but does not act on.
        // Turn boundaries and streaming state are already tracked via
        // message_update / turn_end; no action needed here.
        // auto_retry_* events fire when pi retries after a transient provider
        // error (rate limit, 5xx). They do NOT end the in-flight turn — the
        // subsequent turn_end is still authoritative for completion.
        break

      default:
        process.stderr.write(`[pi-mono] unknown event type: ${event.type}\n`)
    }
  }

  private handleMessageUpdate(event: PiRpcEvent): void {
    const msgEvent = event.assistantMessageEvent as PiAssistantMessageEvent | undefined
    if (!msgEvent) return

    switch (msgEvent.type) {
      case 'text_delta':
        if (msgEvent.delta) {
          this.eventHandler?.({
            type: 'text_delta',
            text: msgEvent.delta
          })
        }
        break

      case 'thinking_delta':
        if (msgEvent.delta) {
          this.eventHandler?.({
            type: 'thinking_delta',
            text: msgEvent.delta
          })
        }
        break

      case 'toolcall_start':
        if (msgEvent.partial?.content) {
          const block = msgEvent.partial.content[msgEvent.contentIndex ?? 0]
          if (block?.type === 'toolCall' && block.name) {
            this.eventHandler?.({
              type: 'tool_activity',
              name: block.name,
              status: 'started',
              toolUseId: block.id,
              input: block.arguments
            })
          }
        }
        break

      case 'toolcall_end':
        if (msgEvent.toolCall) {
          const tc = msgEvent.toolCall
          this.eventHandler?.({
            type: 'tool_use',
            callId: tc.id,
            name: tc.name,
            input: tc.arguments
          })
        }
        break

      case 'done':
      case 'error':
        // Handled by turn_end
        break
    }
  }

  private handleToolStart(event: PiRpcEvent): void {
    const name = event.toolName as string
    const toolCallId = event.toolCallId as string
    if (REQUIRED_AGENT_CONTROL_TOOLS.has(name)) {
      this.requiredControlInputs.set(
        toolCallId,
        (event.args as Record<string, unknown> | undefined) ?? {}
      )
    }
    this.eventHandler?.({
      type: 'tool_activity',
      name,
      status: 'started',
      toolUseId: toolCallId,
      input: event.args as Record<string, unknown> | undefined
    })
  }

  private handleToolEnd(event: PiRpcEvent): void {
    const name = event.toolName as string
    const toolCallId = event.toolCallId as string
    const result = event.result as {
      content?: { type: string; text?: string }[]
    }
    const output =
      result?.content
        ?.filter((c) => c.type === 'text')
        .map((c) => c.text || '')
        .join('') || ''

    if (REQUIRED_AGENT_CONTROL_TOOLS.has(name)) {
      const operationKey = requiredControlOperationKey(
        name,
        this.requiredControlInputs.get(toolCallId)
      )
      this.requiredControlInputs.delete(toolCallId)
      const failure = requiredAgentControlFailure(name, output)
      if (failure) {
        this.requiredAgentControlFailures.set(operationKey, failure)
      } else {
        // Only a successful retry of the same logical operation resolves its
        // obligation; unrelated control success cannot erase a prior failure.
        try {
          if ((JSON.parse(output) as { ok?: unknown }).ok === true) {
            this.requiredAgentControlFailures.delete(operationKey)
          }
        } catch {
          // Non-canonical output cannot clear a prior control-operation failure.
        }
      }
    }

    this.eventHandler?.({
      type: 'tool_activity',
      name,
      status: 'completed',
      toolUseId: toolCallId
    })

    this.eventHandler?.({
      type: 'tool_result_display',
      toolUseId: toolCallId,
      name,
      output
    })
  }

  private handleTurnEnd(event: PiRpcEvent): void {
    // Drop stray turn_end events that don't belong to an in-flight prompt.
    // This happens after abort() or when the subprocess emits a late
    // completion for a prompt that was superseded by another sendPrompt.
    const generation = this.activePromptGeneration
    if (generation === 0) {
      process.stderr.write('[pi-mono] dropping stray turn_end (no in-flight prompt)\n')
      return
    }
    const pending = this.pendingRequests.get(generation)
    if (!pending) {
      process.stderr.write(`[pi-mono] dropping stray turn_end for generation ${generation}\n`)
      this.activePromptGeneration = 0
      return
    }

    const message = event.message as PiAssistantMessage | undefined
    const errorMessage =
      typeof message?.errorMessage === 'string' && message.errorMessage.trim()
        ? message.errorMessage.trim()
        : undefined
    if (errorMessage) {
      this.eventHandler?.({
        type: 'error',
        message: errorMessage,
        adapterSessionId: pending.sessionId
      })
      this.pendingRequests.delete(generation)
      this.activePromptGeneration = 0
      pending.reject(new Error(errorMessage))
      this.eventHandler = null
      return
    }

    // When pi-mono stops to execute a tool, this is an intermediate turn —
    // the model will continue after the tool executes. Keep the prompt state
    // alive so subsequent text_delta events and the final turn_end are
    // properly handled.
    // Pi-mono uses camelCase "toolUse" (via pi-ai SDK), not Anthropic's
    // snake_case "tool_use". Check both for robustness.
    const stopReason = message?.stopReason
    if (stopReason === 'toolUse' || stopReason === 'tool_use') {
      process.stderr.write(
        `[pi-mono] intermediate turn_end (${stopReason}) — keeping prompt alive\n`
      )
      return
    }

    const controlFailure = this.requiredAgentControlFailures.values().next().value as
      | string
      | undefined
    if (controlFailure) {
      this.eventHandler?.({
        type: 'error',
        message: controlFailure,
        adapterSessionId: pending.sessionId
      })
      this.pendingRequests.delete(generation)
      this.activePromptGeneration = 0
      pending.reject(new Error(controlFailure))
      this.eventHandler = null
      return
    }

    // Extract text from content blocks
    let text = ''
    if (message?.content) {
      text = message.content
        .filter((b) => b.type === 'text')
        .map((b) => b.text || '')
        .join('')
    }

    // Extract usage
    const usage = message?.usage
    const costUsd = usage?.cost?.total ?? 0

    const result: PromptResult = {
      text,
      sessionId: pending.sessionId,
      costUsd,
      inputTokens: usage?.input ?? 0,
      outputTokens: usage?.output ?? 0,
      cacheReadTokens: usage?.cacheRead ?? 0,
      cacheWriteTokens: usage?.cacheWrite ?? 0
    }

    // Resolve + clear the in-flight state
    this.pendingRequests.delete(generation)
    this.activePromptGeneration = 0
    pending.resolve(result)

    this.eventHandler = null
  }
}

/**
 * Capabilities for pi-mono. Equal to what `adapterCapabilitiesFor('pi-mono')`
 * would produce from the macOS ADAPTER_CAPABILITY_MATRIX entry. Held locally
 * because pi-mono is intentionally NOT in Windows' ADAPTER_CAPABILITY_MATRIX in
 * this DARK PR; PR-D adds the matrix entry and this constant is replaced by
 * `adapterCapabilitiesFor('pi-mono')`.
 */
const PI_MONO_CAPABILITIES: AdapterCapabilities = {
  resumeFidelity: 'none',
  supportsNativeResume: false,
  supportsCancellation: true,
  acknowledgesCancellation: false,
  requiresPinnedWorker: true,
  supportsModelSwitching: true,
  supportsArtifactEmission: false,
  supportsTools: true,
  restartBehavior: 'process_local_bindings_stale'
}

export class PiMonoRuntimeAdapter implements RuntimeAdapter {
  readonly adapterId = 'pi-mono'
  readonly capabilities: AdapterCapabilities = PI_MONO_CAPABILITIES

  private readonly harness: PiMonoAdapter
  private readonly cancelledAttempts = new Set<string>()

  constructor(harness: PiMonoAdapter) {
    this.harness = harness
  }

  start(): Promise<void> {
    return this.harness.start()
  }

  stop(): Promise<void> {
    return this.harness.stop()
  }

  async openBinding(input: OpenBindingInput): Promise<OpenedBinding> {
    const adapterNativeSessionId = await this.harness.createSession({
      cwd: input.cwd,
      model: input.model,
      systemPrompt: input.systemPrompt,
      mcpServers: input.mcpServers,
      executionRole: input.metadata?.executionRole === 'leaf' ? 'leaf' : 'coordinator'
    })
    return this.binding(input, adapterNativeSessionId)
  }

  async resumeBinding(input: ResumeBindingInput): Promise<OpenedBinding> {
    await this.harness.setExecutionRole(
      input.metadata?.executionRole === 'leaf' ? 'leaf' : 'coordinator'
    )
    await this.start()
    // pi-mono has no native resume after daemon/process loss, but while this
    // RuntimeAdapter instance is alive the opaque session id is still usable as
    // process-local state. Startup reconciliation marks these bindings stale.
    if (!this.harness.hasSession(input.adapterNativeSessionId)) {
      throw new Error(`pi-mono binding is stale: ${input.adapterNativeSessionId}`)
    }
    return this.binding(input, input.adapterNativeSessionId)
  }

  async executeAttempt(
    context: AdapterAttemptContext,
    sink: AdapterEventSink,
    signal: AbortSignal
  ): Promise<AdapterAttemptResult> {
    // Windows' AdapterEventSink is the narrow AdapterStreamEvent union. Forward
    // only canonical stream events; `error` still surfaces via the rejected
    // sendPrompt promise (matching the ACP adapter), and `tool_use` is
    // display-redundant with the `tool_activity` events the sink already gets.
    const onEvent: EventCallback = (event) => {
      if (event.type === 'tool_use' || event.type === 'error') return
      sink(event)
    }
    try {
      const result = await this.harness.sendPrompt(
        context.binding.adapterNativeSessionId,
        context.prompt,
        context.tools ?? [],
        context.mode,
        onEvent,
        async () => '',
        signal,
        {
          protocolVersion: 2,
          requestId: context.requestId ?? '',
          clientId: context.clientId ?? '',
          sessionId: context.sessionId,
          runId: context.runId,
          attemptId: context.attemptId,
          adapterSessionId: context.binding.adapterNativeSessionId,
          disableSwiftBackedTools: context.metadata?.disableSwiftBackedTools === true
        }
      )

      return {
        text: result.text,
        costUsd: result.costUsd,
        inputTokens: result.inputTokens,
        outputTokens: result.outputTokens,
        cacheReadTokens: result.cacheReadTokens,
        cacheWriteTokens: result.cacheWriteTokens,
        adapterSessionId: result.sessionId,
        terminalStatus:
          signal.aborted || this.cancelledAttempts.has(context.attemptId)
            ? 'cancelled'
            : 'succeeded'
      }
    } finally {
      this.harness.clearRelayContextForAttempt(context.attemptId)
      this.cancelledAttempts.delete(context.attemptId)
      if (this.harness.hasPendingRestart) {
        await this.harness.executePendingRestart()
      }
    }
  }

  async cancelAttempt(context: CancelAttemptContext): Promise<CancelDispatchResult> {
    const sessionId = context.binding?.adapterNativeSessionId ?? context.sessionId
    if (context.attemptId) {
      this.cancelledAttempts.add(context.attemptId)
    }
    this.harness.abort(sessionId)
    return {
      accepted: true,
      dispatchAttempted: true,
      adapterAcknowledged: false
    }
  }

  async closeBinding(binding: AdapterBindingHandle): Promise<void> {
    this.harness.invalidateSession?.(binding.adapterNativeSessionId)
  }

  private binding(input: OpenBindingInput, adapterNativeSessionId: string): AdapterBindingHandle {
    return {
      bindingId: input.metadata?.bindingId as string | undefined,
      sessionId: input.sessionId,
      adapterId: this.adapterId,
      adapterNativeSessionId,
      resumeFidelity: 'none',
      cwd: input.cwd,
      model: input.model,
      metadata: input.metadata
    }
  }
}
