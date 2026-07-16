// PiMonoAdapter — Windows port of desktop/macos/agent/src/adapters/pi-mono.ts.
//
// pi-mono is Omi's managed-cloud chat harness: the bundled
// `@earendil-works/pi-coding-agent` CLI run as a `--mode rpc` subprocess whose
// model calls route through Omi's own backend using the user's Firebase token
// (server-billed). This file is a near-verbatim port of the macOS adapter — the
// RPC event loop, generation/pending-request correlation, required-control-tool
// tracking, model mapping, and deferred-restart lifecycle are unchanged.
//
// As of PR-D the adapter IS in ADAPTER_CAPABILITY_MATRIX and IS registered into
// the kernel registry on session relay (agentKernel/controlPlane.ts), but it
// stays DARK: nothing ever invokes it (openBinding/executeAttempt) — default chat
// still routes through /v2/messages, and control-tool spawns explicitly refuse
// managed-cloud adapters. Deliberate main_chat routing arrives in PR-E.
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
//   - Capabilities: the wrapper reads `adapterCapabilitiesFor('pi-mono')` from
//     the shared ADAPTER_CAPABILITY_MATRIX (PR-D added the entry; it previously
//     held a local static set equal to what the macOS matrix entry produces).
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
import { adapterCapabilitiesFor } from './interface'
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

/** Ordered candidate paths for pi's `dist/cli.js`, resolved on the filesystem.
 *
 *  Pure so it can be unit-tested without a running Electron app. `moduleDir` is
 *  this module's directory; `resourcesPath` is Electron's `process.resourcesPath`
 *  (undefined outside Electron → the packaged candidate is skipped).
 *
 *   - Packaged: `<resourcesPath>/app.asar.unpacked/node_modules/@earendil-works/
 *     pi-coding-agent/dist/cli.js` (the package is asar-unpacked in
 *     electron-builder.yml so the plain-Node child can read it).
 *   - Dev / vitest: walk up from `moduleDir` to the hoisted node_modules.
 */
export function piCliCandidates(
  moduleDir: string,
  resourcesPath: string | undefined = process.resourcesPath
): string[] {
  const rel = join('node_modules', '@earendil-works', 'pi-coding-agent', 'dist', 'cli.js')
  const candidates: string[] = []
  if (resourcesPath) {
    candidates.push(join(resourcesPath, 'app.asar.unpacked', rel))
  }
  for (let dir = moduleDir; ; ) {
    candidates.push(join(dir, rel))
    const parent = dirname(dir)
    if (parent === dir) break
    dir = parent
  }
  return candidates
}

/** Resolve the pi CLI (`dist/cli.js`) bundled inside the app, on the filesystem.
 *
 *  We CANNOT use `import.meta.resolve` here: the electron-vite MAIN bundle is CJS,
 *  and esbuild compiles `import.meta.resolve(x)` to `(void 0)(x)` — calling it
 *  throws "(void 0) is not a function" at adapter construction (before openBinding,
 *  so the adapter's own catch never fires). Nor can we use
 *  `createRequire(...).resolve(...)`: pi's package.json `exports` map exposes only
 *  the ESM `import` condition for "." (→ dist/index.js) and "./rpc-entry" — no CJS
 *  `require` condition, no `./package.json`, no `./dist/*` subpath — so every
 *  bare/subpath resolve throws ERR_PACKAGE_PATH_NOT_EXPORTED.
 *
 *  So we resolve on the filesystem (see piCliCandidates), which the exports map
 *  can't gate, and which works in dev, vitest, and packaged builds. First existing
 *  candidate wins. `import.meta.url` (not `.resolve`) is safe — esbuild shims it to
 *  `pathToFileURL(__filename)` in the CJS bundle.
 */
export function resolveBundledPi(): string {
  const moduleDir = dirname(fileURLToPath(import.meta.url))
  const candidates = piCliCandidates(moduleDir)
  for (const candidate of candidates) {
    if (existsSync(candidate)) return candidate
  }
  throw new Error(
    `resolveBundledPi: @earendil-works/pi-coding-agent/dist/cli.js not found. Looked in:\n  ${candidates.join('\n  ')}`
  )
}

/** Ordered candidate paths for the omi-provider extension's `index.ts`.
 *
 *  Pure so it can be unit-tested. `moduleDir` is this module's directory;
 *  `resourcesPath` is Electron's `process.resourcesPath`.
 *
 *   - Packaged: the extension is bundled to `out/main/pi-mono-extension/index.ts`
 *     (scripts/bundle-pimono-extension.mjs) and asar-unpacked (electron-builder)
 *     so pi's plain-Node child can read it →
 *     `<resourcesPath>/app.asar.unpacked/out/main/pi-mono-extension/index.ts`.
 *   - Dev / vitest: the bundle step does NOT run, so pi loads the raw `.ts` from
 *     its SOURCE location (jiti resolves the relative `./node-tools` etc. imports
 *     from there). We can't use `dirname(import.meta.url)` — in the electron-vite
 *     bundle that is `out/main`, where nothing was copied in dev. So walk up to the
 *     checkout that holds `src/main/codingAgent/pi-mono-extension/index.ts`.
 */
export function piExtensionCandidates(
  moduleDir: string,
  resourcesPath: string | undefined = process.resourcesPath
): string[] {
  const candidates: string[] = []
  if (resourcesPath) {
    candidates.push(
      join(resourcesPath, 'app.asar.unpacked', 'out', 'main', 'pi-mono-extension', 'index.ts')
    )
  }
  const srcRel = join('src', 'main', 'codingAgent', 'pi-mono-extension', 'index.ts')
  for (let dir = moduleDir; ; ) {
    candidates.push(join(dir, srcRel))
    const parent = dirname(dir)
    if (parent === dir) break
    dir = parent
  }
  return candidates
}

/** Resolve the omi-provider extension file (`index.ts`) pi loads via jiti.
 *
 *  The pi-mono-extension registers the `omi` provider + Windows denylist + the
 *  OMI_BRIDGE_PIPE relay client. Resolved on the filesystem (see
 *  piExtensionCandidates) so it works in dev, vitest, and packaged builds; first
 *  existing candidate wins. `import.meta.url` (not `.resolve`) is safe — esbuild
 *  shims it to `pathToFileURL(__filename)` in the CJS bundle.
 */
export function resolveBundledExtension(): string {
  const moduleDir = dirname(fileURLToPath(import.meta.url))
  const candidates = piExtensionCandidates(moduleDir)
  for (const candidate of candidates) {
    if (existsSync(candidate)) return candidate
  }
  throw new Error(
    `resolveBundledExtension: pi-mono-extension/index.ts not found. Looked in:\n  ${candidates.join('\n  ')}`
  )
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

  /** Whether the pi subprocess is currently spawned. */
  get isRunning(): boolean {
    return this.process !== null
  }

  /** Force pi to start a fresh conversation, discarding all accumulated turns.
   *
   *  pi holds ONE accumulating conversation per subprocess (rpc.md: every
   *  `prompt` continues the same message list). When a pinned worker's live
   *  subprocess is reassigned to a DIFFERENT chat binding (pool eviction under
   *  multichat load), reusing it without a reset would let the new chat's model
   *  see the evicted chat's turns — a narrow same-user context bleed. pi
   *  natively supports `new_session` (rpc.md) and the omi extension registers no
   *  `session_before_switch` handler, so it is never cancelled. No-op when the
   *  subprocess is not running (a fresh spawn already starts with no history);
   *  the kernel's full-tail injection (resumeFidelity:'none') then re-seeds the
   *  reassigned chat's own history from the durable transcript. */
  resetConversation(): void {
    if (!this.process) return
    this.sendCommand({ type: 'new_session' })
    process.stderr.write('[pi-mono] new_session sent (worker reassigned to a new chat)\n')
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

export class PiMonoRuntimeAdapter implements RuntimeAdapter {
  readonly adapterId = 'pi-mono'
  // Derived from the ADAPTER_CAPABILITY_MATRIX 'pi-mono' entry (PR-D). Was a
  // local PI_MONO_CAPABILITIES const while pi-mono was intentionally absent from
  // the matrix; that constant is now the matrix entry.
  readonly capabilities: AdapterCapabilities = adapterCapabilitiesFor('pi-mono')

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
    // Pool-eviction reassignment guard. Opening a binding on a worker whose pi
    // subprocess is ALREADY running means the pool evicted this pinned worker
    // from a prior chat and reassigned it here (a chat that keeps its own worker
    // resumes — resumeBinding — and never re-opens, so a live process at
    // openBinding time is always a different-chat reassignment). Reset pi's
    // accumulated conversation before the new chat's first prompt so it cannot
    // inherit the evicted chat's turns; the kernel re-seeds this chat's own
    // history via the full-tail injection (resumeFidelity:'none'). No-op on a
    // fresh worker (subprocess not yet spawned → nothing accumulated).
    if (this.harness.isRunning) {
      this.harness.resetConversation()
    }
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
