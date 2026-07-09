// ACP (Agent Client Protocol) JSON-RPC-over-stdio client — Windows port of
// desktop/macos/agent/src/adapters/acp.ts. One class covers both spawn shapes:
//   - Default ("acp" / Claude Code): spawn the bundled claude-acp-entry.mjs
//     with Electron's own binary running as Node (ELECTRON_RUN_AS_NODE=1) —
//     no separately installed CLI needed.
//   - External (OpenClaw/Hermes/Codex): spawn a user-configured command string
//     through the shell with a minimal allowlisted environment so host secrets
//     never leak into an untrusted third-party subprocess.
//
// Windows-specific deviations from the macOS source, each load-bearing:
//   - The env allowlist swaps POSIX vars (HOME/SHELL/TMPDIR/LOGNAME) for the
//     Windows set; ComSpec/SystemRoot are required for shell:true to work at
//     all, and PATHEXT for npm-global `.cmd` shims to resolve.
//   - stop() kills the external adapter's process TREE with `taskkill /t /f`:
//     a shell:true spawn's pid is cmd.exe, and POSIX process-group kill
//     (process.kill(-pid)) does not exist on Windows — a plain kill would
//     orphan the real agent process.
//   - windowsHide:true so external spawns never flash a console window.

import { spawn, execFile, type ChildProcess } from 'child_process'
import { createInterface, type Interface as ReadlineInterface } from 'readline'
import { resolveAcpPermission, resolveExternalAcpPermission } from './toolPolicyStub'
import { adapterCapabilitiesFor } from './interface'
import type {
  AdapterAttemptContext,
  AdapterAttemptResult,
  AdapterBindingHandle,
  AdapterCapabilities,
  AdapterEventSink,
  CancelAttemptContext,
  CancelDispatchResult,
  OpenBindingInput,
  OpenedBinding,
  ProductionAdapterId,
  ResumeBindingInput,
  RuntimeAdapter
} from './interface'
import { AdapterRuntimeError, failureFromProcessError, failureFromProcessExit } from './failures'

type ResponseHandler = {
  resolve: (result: unknown) => void
  reject: (err: Error) => void
}

type PendingToolActivity = {
  id: string
  name: string
}

/**
 * Minimal environment allowlist for user-installed external adapter
 * subprocesses. Only OS-level essentials needed for a CLI tool to function
 * are forwarded — never the full parent environment. This prevents accidental
 * leakage of cloud credentials, CI tokens, or other host secrets to untrusted
 * third-party commands spawned with `shell: true`.
 */
const EXTERNAL_ADAPTER_ENV_ALLOWLIST = [
  'PATH',
  'Path', // Windows env keys are case-insensitive but Node preserves the OS casing
  'PATHEXT',
  'USERPROFILE',
  'HOMEDRIVE',
  'HOMEPATH',
  'HOME',
  'APPDATA',
  'LOCALAPPDATA',
  'ProgramData',
  'ProgramFiles',
  'ComSpec',
  'SystemRoot',
  'SystemDrive',
  'WINDIR',
  'TEMP',
  'TMP',
  'USERNAME',
  'COMPUTERNAME',
  'LANG',
  'TZ',
  // Proxy/TLS — external adapters make outbound API calls and need these
  // to function in proxied or custom-CA environments.
  'HTTP_PROXY',
  'HTTPS_PROXY',
  'NO_PROXY',
  'http_proxy',
  'https_proxy',
  'no_proxy',
  'SSL_CERT_FILE',
  'SSL_CERT_DIR',
  'NODE_EXTRA_CA_CERTS'
] as const

/**
 * Proxy environment variable names that may carry embedded credentials
 * (e.g. `http://user:pass@proxy:3128`). Their values are sanitized before
 * being forwarded to untrusted external adapter subprocesses.
 */
const PROXY_ENV_KEYS = new Set(['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy'])

/**
 * Strip embedded userinfo from a proxy URL before forwarding it to an
 * untrusted external adapter subprocess.
 *
 *   "http://alice:s3cr3t@proxy:3128" -> "http://proxy:3128"
 */
function sanitizeProxyUrl(value: string): string {
  try {
    const url = new URL(value)
    if (url.username || url.password) {
      url.username = ''
      url.password = ''
      return url.toString()
    }
  } catch {
    /* fall through to the manual strip below */
  }
  // URL() didn't expose an authority — either the value isn't a URL, or it
  // parsed with an accidental scheme (e.g. "alice:pass@proxy:3128", where
  // "alice:" reads as the protocol). Strip any user[:pass]@ prefix manually,
  // tolerating an optional scheme://; host-only values pass through unchanged.
  return value.replace(/^([a-z][a-z0-9+.-]*:\/\/)?[^@\s/]+@/i, '$1')
}

export class AcpError extends Error {
  code: number
  data?: unknown

  constructor(message: string, code: number, data?: unknown) {
    super(message)
    this.code = code
    this.data = data
  }
}

const MAX_RECENT_STDERR_CHARS = 2_000

function appendRecentStderr(current: string, next: string): string {
  const combined = `${current}${next}`
  if (combined.length <= MAX_RECENT_STDERR_CHARS) {
    return combined
  }
  return combined.slice(combined.length - MAX_RECENT_STDERR_CHARS)
}

export type AcpNotificationHandler = (method: string, params: unknown) => void

export interface AcpRuntimeAdapterOptions {
  adapterId?: ProductionAdapterId
  log?: (message: string) => void
  /** Binary used to run the bundled entry; defaults to Electron/Node's own executable. */
  nodeBin?: string
  /** Path to the bundled ACP entry script — required for the default ("acp") adapter. */
  acpEntry?: string
  command?: string
  envCommandName?: string
  /**
   * Extra env var names forwarded to THIS external adapter on top of the
   * shared allowlist (e.g. HERMES_HOME for Hermes, OPENAI_API_KEY/CODEX_* for
   * the Codex bridge). Adapter-specific by design — never widen the shared list.
   */
  extraEnvPassthrough?: readonly string[]
  sessionMcpServersMode?: 'passthrough' | 'empty'
  supportsSessionSetModel?: boolean
  noProgressTimeoutMs?: number
}

const DEFAULT_EXTERNAL_NO_PROGRESS_TIMEOUT_MS = 150_000

function parsePositiveInt(value: string | undefined): number | undefined {
  if (!value) return undefined
  const parsed = Number.parseInt(value, 10)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : undefined
}

export class AcpRuntimeAdapter implements RuntimeAdapter {
  readonly adapterId: ProductionAdapterId
  readonly capabilities: AdapterCapabilities

  private process: ChildProcess | null = null
  private processIsExternal = false
  // Cumulative session cost last reported by a usage_update notification,
  // per adapter session — the bridge reports totals, results need per-attempt
  // deltas.
  private cumulativeCostUsdBySession = new Map<string, number>()
  private readline: ReadlineInterface | null = null
  private stdinWriter: ((line: string) => void) | null = null
  private responseHandlers = new Map<number, ResponseHandler>()
  private notificationHandler: AcpNotificationHandler | null = null
  private nextRpcId = 1
  private initialized = false
  private initializePromise: Promise<void> | null = null
  private readonly log: (message: string) => void
  private readonly nodeBin: string
  private readonly acpEntry?: string
  private readonly command?: string
  private readonly envCommandName?: string
  private readonly extraEnvPassthrough: readonly string[]
  private readonly sessionMcpServersMode: 'passthrough' | 'empty'
  private readonly supportsSessionSetModel: boolean
  private readonly noProgressTimeoutMs: number

  constructor(options: AcpRuntimeAdapterOptions = {}) {
    this.adapterId = options.adapterId ?? 'acp'
    this.capabilities = adapterCapabilitiesFor(this.adapterId)
    this.log = options.log ?? (() => {})
    this.nodeBin = options.nodeBin ?? process.execPath
    this.acpEntry = options.acpEntry
    this.command = options.command
    this.envCommandName = options.envCommandName
    this.extraEnvPassthrough = options.extraEnvPassthrough ?? []
    this.sessionMcpServersMode = options.sessionMcpServersMode ?? 'passthrough'
    this.supportsSessionSetModel =
      options.supportsSessionSetModel ?? this.capabilities.supportsModelSwitching
    this.noProgressTimeoutMs =
      options.noProgressTimeoutMs ??
      parsePositiveInt(process.env.OMI_ACP_NO_PROGRESS_TIMEOUT_MS) ??
      (this.adapterId === 'acp' ? 0 : DEFAULT_EXTERNAL_NO_PROGRESS_TIMEOUT_MS)
  }

  async start(): Promise<void> {
    if (this.process) return

    const configuredCommand =
      this.command ?? (this.envCommandName ? process.env[this.envCommandName] : undefined)
    const command = configuredCommand?.trim()
    if (this.adapterId !== 'acp' && !command) {
      throw new Error(`${this.adapterId} adapter requires ${this.envCommandName ?? 'command'}`)
    }

    if (command) {
      // Construct a minimal environment from an allowlist rather than spreading
      // the full process.env. User-installed external adapters run untrusted
      // commands with `shell: true`; a denylist leaves cloud credentials, CI
      // tokens, and other host secrets exposed.
      const externalEnv: NodeJS.ProcessEnv = {
        OMI_ADAPTER_ID: this.adapterId
      }
      for (const key of [...EXTERNAL_ADAPTER_ENV_ALLOWLIST, ...this.extraEnvPassthrough]) {
        if (process.env[key] !== undefined) {
          externalEnv[key] = PROXY_ENV_KEYS.has(key)
            ? sanitizeProxyUrl(process.env[key]!)
            : process.env[key]
        }
      }
      this.log(`Starting ${this.adapterId} ACP subprocess: ${command}`)
      this.processIsExternal = true
      this.process = spawn(command, {
        shell: true,
        env: externalEnv,
        stdio: ['pipe', 'pipe', 'pipe'],
        // POSIX: detach into a new process group so the whole tree can be
        // signalled. Windows has no process groups — tree kill is taskkill's
        // job in stop(), and detaching there only risks a stray console.
        detached: process.platform !== 'win32',
        windowsHide: true
      })
    } else {
      if (!this.acpEntry) {
        throw new Error('acp adapter requires an acpEntry path to the bundled ACP bridge')
      }
      const env = { ...process.env }
      delete env.ANTHROPIC_API_KEY
      delete env.CLAUDE_CODE_USE_VERTEX
      delete env.CLAUDECODE
      env.NODE_NO_WARNINGS = '1'
      // In Electron, process.execPath is the app binary, not node. This flag
      // makes the spawned copy run as plain Node so it executes the entry
      // script (and is inherited, so the SDK's own nested spawns work too).
      env.ELECTRON_RUN_AS_NODE = '1'

      this.log(`Starting ${this.adapterId} ACP subprocess: ${this.nodeBin} ${this.acpEntry}`)
      this.processIsExternal = false
      this.process = spawn(this.nodeBin, [this.acpEntry], {
        shell: false,
        env,
        stdio: ['pipe', 'pipe', 'pipe'],
        windowsHide: true
      })
    }
    const proc = this.process
    let finalized = false
    let recentStderr = ''
    const finalizeProcess = (error: Error): void => {
      if (finalized || this.process !== proc) return
      finalized = true
      this.log(error.message)
      this.process = null
      this.stdinWriter = null
      this.readline = null
      this.initialized = false
      this.initializePromise = null
      for (const [, handler] of this.responseHandlers) {
        handler.reject(error)
      }
      this.responseHandlers.clear()
      this.onProcessExit?.()
    }

    if (!proc.stdin || !proc.stdout || !proc.stderr) {
      throw new Error(`Failed to create ${this.adapterId} ACP subprocess pipes`)
    }

    proc.on('error', (err) => {
      finalizeProcess(
        new AdapterRuntimeError(
          failureFromProcessError({
            adapterId: this.adapterId,
            message: err.message
          })
        )
      )
    })

    this.stdinWriter = (line: string) => {
      try {
        this.process?.stdin?.write(line + '\n')
      } catch (err) {
        this.log(`Failed to write to ACP stdin: ${err}`)
      }
    }

    this.readline = createInterface({
      input: proc.stdout,
      terminal: false
    })

    this.readline.on('line', (line: string) => this.handleLine(line))

    proc.stderr.on('data', (data: Buffer) => {
      const text = data.toString().trim()
      if (text) {
        recentStderr = appendRecentStderr(recentStderr, `${text}\n`)
        this.log(`ACP stderr: ${text}`)
      }
    })

    proc.on('exit', (code) => {
      finalizeProcess(
        new AdapterRuntimeError(
          failureFromProcessExit({
            adapterId: this.adapterId,
            exitCode: code,
            recentStderr
          })
        )
      )
    })
  }

  async stop(): Promise<void> {
    if (!this.process) return
    const proc = this.process
    const exitPromise = new Promise<void>((resolve) => {
      proc.once('exit', () => resolve())
    })
    if (process.platform === 'win32') {
      if (this.processIsExternal && proc.pid) {
        // shell:true means proc.pid is cmd.exe — kill the whole tree or the
        // real adapter process is orphaned. taskkill is the Windows analog of
        // the POSIX process-group SIGTERM below.
        execFile('taskkill', ['/pid', String(proc.pid), '/t', '/f'], () => {
          // Best-effort: if taskkill itself failed (already exited, access
          // denied), fall back to killing the direct child.
          proc.kill()
        })
      } else {
        proc.kill()
      }
    } else {
      // For shell-spawned external commands (detached process group), send the
      // signal to the entire group so the real adapter child is terminated too.
      try {
        if (proc.pid) {
          process.kill(-proc.pid, 'SIGTERM')
        }
      } catch {
        // EPERM/ESRCH — fall back to direct kill.
        proc.kill()
      }
    }
    await exitPromise
  }

  async restart(): Promise<void> {
    if (this.process) {
      await this.stop()
    }
    await this.start()
  }

  async request(method: string, params: Record<string, unknown> = {}): Promise<unknown> {
    await this.start()
    if (method !== 'initialize') {
      await this.ensureInitialized()
    }
    const result = await this.rawRequest(method, params)
    if (method === 'initialize') {
      this.initialized = true
      this.initializePromise = null
    }
    return result
  }

  private async rawRequest(method: string, params: Record<string, unknown> = {}): Promise<unknown> {
    const id = this.nextRpcId++
    const msg = JSON.stringify({ jsonrpc: '2.0', id, method, params })

    return new Promise((resolve, reject) => {
      this.responseHandlers.set(id, { resolve, reject })
      if (this.stdinWriter) {
        this.stdinWriter(msg)
      } else {
        this.responseHandlers.delete(id)
        reject(new Error(`${this.adapterId} ACP process stdin not available`))
      }
    })
  }

  private async ensureInitialized(): Promise<void> {
    if (this.initialized) return
    if (!this.initializePromise) {
      this.initializePromise = this.rawRequest('initialize', { protocolVersion: 1 })
        .then(() => {
          this.initialized = true
          this.initializePromise = null
        })
        .catch((error) => {
          this.initializePromise = null
          throw error
        })
    }
    await this.initializePromise
  }

  notify(method: string, params: Record<string, unknown> = {}): void {
    const msg = JSON.stringify({ jsonrpc: '2.0', method, params })
    this.stdinWriter?.(msg)
  }

  setNotificationHandler(handler: AcpNotificationHandler | null): void {
    this.notificationHandler = handler
  }

  onProcessExit?: () => void

  async openBinding(input: OpenBindingInput): Promise<OpenedBinding> {
    const result = (await this.request('session/new', {
      cwd: input.cwd,
      mcpServers: this.sessionMcpServersMode === 'empty' ? [] : (input.mcpServers ?? []),
      ...(input.systemPrompt ? { _meta: { systemPrompt: input.systemPrompt } } : {})
    })) as { sessionId: string }

    if (input.model && this.supportsSessionSetModel) {
      await this.request('session/set_model', {
        sessionId: result.sessionId,
        modelId: input.model
      })
    }

    return this.binding(input, result.sessionId, this.supportsSessionSetModel)
  }

  async resumeBinding(input: ResumeBindingInput): Promise<OpenedBinding> {
    await this.request('session/resume', {
      sessionId: input.adapterNativeSessionId,
      cwd: input.cwd,
      mcpServers: this.sessionMcpServersMode === 'empty' ? [] : (input.mcpServers ?? [])
    })

    if (input.model && this.supportsSessionSetModel) {
      await this.request('session/set_model', {
        sessionId: input.adapterNativeSessionId,
        modelId: input.model
      })
    }

    return this.binding(input, input.adapterNativeSessionId, this.supportsSessionSetModel)
  }

  async executeAttempt(
    context: AdapterAttemptContext,
    sink: AdapterEventSink,
    signal: AbortSignal
  ): Promise<AdapterAttemptResult> {
    const adapterSessionId = context.binding.adapterNativeSessionId
    let fullText = ''
    // Cumulative session cost from the bridge's standard usage_update
    // notifications (the public protocol surface for cost — no package
    // internals involved).
    let latestCumulativeCostUsd: number | null = null
    const pendingTools: PendingToolActivity[] = []
    let syntheticToolIdCounter = 0
    const previousHandler = this.notificationHandler
    let lastProgressAt = Date.now()
    this.notificationHandler = (method, params) => {
      previousHandler?.(method, params)
      if (signal.aborted || method !== 'session/update') return
      // One ACP process can host several sessions — never let another
      // session's (or a stale) update stream into this attempt. Updates
      // without a session id (older adapters) are accepted as before.
      const updateSessionId = (params as { sessionId?: unknown } | undefined)?.sessionId
      if (typeof updateSessionId === 'string' && updateSessionId !== adapterSessionId) return
      const update = (
        params as { update?: { sessionUpdate?: string; cost?: { amount?: unknown } } }
      )?.update
      if (update?.sessionUpdate === 'usage_update' && typeof update.cost?.amount === 'number') {
        latestCumulativeCostUsd = update.cost.amount
      }
      const didProgress = this.translateSessionUpdate(
        params as Record<string, unknown>,
        pendingTools,
        () => `acp-tool-${++syntheticToolIdCounter}`,
        sink,
        (text) => {
          fullText += text
        }
      )
      if (didProgress) {
        lastProgressAt = Date.now()
      }
    }

    try {
      const promptRequest = this.request('session/prompt', {
        sessionId: adapterSessionId,
        prompt: context.prompt
      })
      const result = (await this.withNoProgressTimeout(
        promptRequest,
        adapterSessionId,
        () => lastProgressAt,
        signal
      )) as {
        usage?: {
          inputTokens?: number
          outputTokens?: number
          cachedReadTokens?: number | null
          cachedWriteTokens?: number | null
        }
        _meta?: { costUsd?: number }
      }

      // usage_update reports the CUMULATIVE session cost; the attempt's cost
      // is the delta against the last attempt on this session. Adapters that
      // instead attach per-turn cost to the prompt response (_meta) win when
      // no usage_update was seen.
      let costUsd = result._meta?.costUsd ?? 0
      if (latestCumulativeCostUsd !== null) {
        const previous = this.cumulativeCostUsdBySession.get(adapterSessionId) ?? 0
        costUsd = Math.max(0, latestCumulativeCostUsd - previous)
        this.cumulativeCostUsdBySession.set(adapterSessionId, latestCumulativeCostUsd)
      }

      return {
        text: fullText,
        adapterSessionId,
        terminalStatus: signal.aborted ? 'cancelled' : 'succeeded',
        costUsd,
        inputTokens: result.usage?.inputTokens ?? 0,
        outputTokens: result.usage?.outputTokens ?? 0,
        cacheReadTokens: result.usage?.cachedReadTokens ?? 0,
        cacheWriteTokens: result.usage?.cachedWriteTokens ?? 0
      }
    } finally {
      this.notificationHandler = previousHandler
    }
  }

  private withNoProgressTimeout<T>(
    promise: Promise<T>,
    adapterSessionId: string,
    getLastProgressAt: () => number,
    signal: AbortSignal
  ): Promise<T> {
    const timeoutMs = this.noProgressTimeoutMs
    if (timeoutMs <= 0) {
      // No watchdog, but cancellation must still settle the attempt even if
      // the adapter never answers session/cancel with a prompt response.
      return new Promise<T>((resolve, reject) => {
        let settled = false
        const finish = (fn: () => void): void => {
          if (settled) return
          settled = true
          signal.removeEventListener('abort', onAbort)
          fn()
        }
        const onAbort = (): void => finish(() => reject(new Error('ACP attempt cancelled')))
        // Observe the in-flight request FIRST: even when already aborted, a
        // later rejection of the underlying session/prompt promise must not
        // surface as an unhandled rejection. finish() guards double-settling.
        promise.then(
          (value) => finish(() => resolve(value)),
          (error) => finish(() => reject(error instanceof Error ? error : new Error(String(error))))
        )
        if (signal.aborted) {
          onAbort()
          return
        }
        signal.addEventListener('abort', onAbort, { once: true })
      })
    }

    return new Promise<T>((resolve, reject) => {
      let settled = false
      const finish = (fn: () => void): void => {
        if (settled) return
        settled = true
        clearInterval(timer)
        signal.removeEventListener('abort', onAbort)
        fn()
      }
      const onAbort = (): void => {
        finish(() => reject(new Error('ACP attempt cancelled')))
      }
      const timer = setInterval(
        () => {
          if (signal.aborted) {
            onAbort()
            return
          }
          const idleMs = Date.now() - getLastProgressAt()
          if (idleMs < timeoutMs) {
            return
          }
          this.log(
            `${this.adapterId} ACP session ${adapterSessionId} produced no recognized progress for ${idleMs}ms; cancelling`
          )
          this.notify('session/cancel', { sessionId: adapterSessionId })
          finish(() =>
            reject(
              new Error(
                `${this.adapterId} produced no progress for ${Math.round(timeoutMs / 1000)} seconds`
              )
            )
          )
        },
        Math.min(5_000, Math.max(1_000, Math.floor(timeoutMs / 6)))
      )

      signal.addEventListener('abort', onAbort, { once: true })
      promise.then(
        (value) => finish(() => resolve(value)),
        (error) => finish(() => reject(error instanceof Error ? error : new Error(String(error))))
      )
    })
  }

  async cancelAttempt(context: CancelAttemptContext): Promise<CancelDispatchResult> {
    const sessionId = context.binding?.adapterNativeSessionId ?? context.sessionId
    if (!sessionId) {
      return {
        accepted: true,
        dispatchAttempted: false,
        adapterAcknowledged: false,
        message: 'No ACP session is active'
      }
    }
    this.notify('session/cancel', { sessionId })
    return {
      accepted: true,
      dispatchAttempted: true,
      adapterAcknowledged: false
    }
  }

  async closeBinding(): Promise<void> {
    // ACP exposes no explicit close primitive.
  }

  private binding(
    input: OpenBindingInput,
    adapterNativeSessionId: string,
    modelApplied: boolean
  ): AdapterBindingHandle {
    return {
      sessionId: input.sessionId,
      adapterId: this.adapterId,
      adapterNativeSessionId,
      resumeFidelity: this.capabilities.resumeFidelity,
      cwd: input.cwd,
      model: modelApplied ? input.model : undefined,
      metadata: input.metadata
    }
  }

  private handleLine(line: string): void {
    if (!line.trim()) return
    try {
      const msg = JSON.parse(line) as Record<string, unknown>

      if ('method' in msg && 'id' in msg && msg.id !== null && msg.id !== undefined) {
        this.handleRequest(msg)
      } else if ('id' in msg && msg.id !== null && msg.id !== undefined) {
        this.handleResponse(msg)
      } else if ('method' in msg) {
        this.notificationHandler?.(msg.method as string, msg.params)
      }
    } catch {
      this.log(`Failed to parse ${this.adapterId} ACP message: ${line.slice(0, 200)}`)
    }
  }

  private handleRequest(msg: Record<string, unknown>): void {
    const id = msg.id as number
    const method = msg.method as string

    if (method === 'session/request_permission') {
      const params = msg.params as Record<string, unknown> | undefined
      const options = (params?.options as Array<{ kind: string; optionId: string }>) ?? []
      const decision =
        this.adapterId === 'acp'
          ? resolveAcpPermission({ requestId: id, options })
          : resolveExternalAcpPermission({ adapterId: this.adapterId, requestId: id, options })
      this.log(`ACP permission resolved: ${JSON.stringify(decision.auditEvent)}`)
      if ('acpError' in decision) {
        this.stdinWriter?.(
          JSON.stringify({
            jsonrpc: '2.0',
            id,
            error: decision.acpError
          })
        )
        return
      }
      this.stdinWriter?.(
        JSON.stringify({
          jsonrpc: '2.0',
          id,
          result: decision.acpResult
        })
      )
      return
    }

    if (method === 'session/update') {
      this.notificationHandler?.(method, msg.params)
      this.stdinWriter?.(JSON.stringify({ jsonrpc: '2.0', id, result: null }))
      return
    }

    this.log(`Unhandled ACP request: ${method} (id=${id})`)
    this.stdinWriter?.(
      JSON.stringify({
        jsonrpc: '2.0',
        id,
        error: { code: -32601, message: `Method not handled: ${method}` }
      })
    )
  }

  private handleResponse(msg: Record<string, unknown>): void {
    const id = msg.id as number
    const handler = this.responseHandlers.get(id)
    if (!handler) return
    this.responseHandlers.delete(id)
    if ('error' in msg) {
      const err = msg.error as { code: number; message: string; data?: unknown }
      handler.reject(new AcpError(err.message, err.code, err.data))
    } else {
      handler.resolve(msg.result)
    }
  }

  private translateSessionUpdate(
    params: Record<string, unknown>,
    pendingTools: PendingToolActivity[],
    nextSyntheticToolId: () => string,
    sink: AdapterEventSink,
    onText: (text: string) => void
  ): boolean {
    const update = params.update as Record<string, unknown> | undefined
    if (!update) {
      this.log(`session/update missing 'update' field: ${JSON.stringify(params).slice(0, 200)}`)
      return false
    }

    const sessionUpdate = update.sessionUpdate as string
    switch (sessionUpdate) {
      case 'agent_message_chunk': {
        const content = update.content as { type: string; text?: string } | undefined
        const text = content?.text ?? ''
        if (!text) return false
        for (const tool of pendingTools.splice(0)) {
          sink({ type: 'tool_activity', name: tool.name, status: 'completed', toolUseId: tool.id })
        }
        onText(text)
        sink({ type: 'text_delta', text })
        return true
      }

      case 'agent_thought_chunk': {
        const content = update.content as { type: string; text?: string } | undefined
        const text = content?.text ?? ''
        if (text) {
          sink({ type: 'thinking_delta', text })
          return true
        }
        return false
      }

      case 'tool_call': {
        const toolCallId = this.resolveToolCallStartId(update, nextSyntheticToolId)
        const title = this.toolTitle(update)
        const status = (update.status as string) ?? 'pending'
        if (status === 'pending' || status === 'in_progress') {
          if (!pendingTools.some((tool) => tool.id === toolCallId)) {
            pendingTools.push({ id: toolCallId, name: title })
          }
          const rawInput = update.rawInput as Record<string, unknown> | undefined
          sink({
            type: 'tool_activity',
            name: title,
            status: 'started',
            toolUseId: toolCallId,
            input: rawInput
          })
          return true
        }
        return false
      }

      case 'tool_call_update': {
        const status = (update.status as string) ?? ''
        const title = this.toolTitle(update)
        if (status !== 'completed' && status !== 'failed' && status !== 'cancelled') {
          return false
        }
        const toolCallId = this.resolveToolCallUpdateId(update, pendingTools, nextSyntheticToolId)
        const idx = pendingTools.findIndex((tool) => tool.id === toolCallId)
        if (idx >= 0) pendingTools.splice(idx, 1)
        sink({
          type: 'tool_activity',
          name: title,
          status: status === 'completed' ? 'completed' : 'failed',
          toolUseId: toolCallId
        })

        const output = this.toolOutput(update)
        if (output) {
          sink({
            type: 'tool_result_display',
            toolUseId: toolCallId,
            name: title,
            output: output.length > 2000 ? `${output.slice(0, 2000)}\n... (truncated)` : output
          })
        }
        return true
      }

      case 'plan': {
        const entries = update.entries as Array<{ content: string }> | undefined
        if (!Array.isArray(entries)) return false
        let emitted = false
        for (const entry of entries) {
          if (entry.content) {
            sink({ type: 'thinking_delta', text: `${entry.content}\n` })
            emitted = true
          }
        }
        return emitted
      }

      case 'available_commands_update':
      case 'usage_update': {
        return false
      }

      default:
        this.log(`Unknown session update type: ${sessionUpdate}`)
        return false
    }
  }

  private resolveToolCallStartId(
    update: Record<string, unknown>,
    nextSyntheticToolId: () => string
  ): string {
    const explicitId = typeof update.toolCallId === 'string' ? update.toolCallId.trim() : ''
    if (explicitId) return explicitId
    return nextSyntheticToolId()
  }

  private resolveToolCallUpdateId(
    update: Record<string, unknown>,
    pendingTools: PendingToolActivity[],
    nextSyntheticToolId: () => string
  ): string {
    const explicitId = typeof update.toolCallId === 'string' ? update.toolCallId.trim() : ''
    if (explicitId) return explicitId

    const title = this.toolTitle(update)
    const existing = pendingTools.find((tool) => tool.name === title)
    if (existing) return existing.id
    return nextSyntheticToolId()
  }

  private toolTitle(update: Record<string, unknown>): string {
    let title = (update.title as string) ?? 'unknown'
    if (title !== 'unknown' && !title.includes('undefined')) {
      return title
    }
    const meta = update._meta as { claudeCode?: { toolName?: string } } | undefined
    const toolName = meta?.claudeCode?.toolName
    const rawInput = update.rawInput as Record<string, unknown> | undefined
    if (toolName === 'WebSearch' && rawInput?.query) {
      title = `WebSearch: "${rawInput.query}"`
    } else if (toolName === 'WebFetch' && rawInput?.url) {
      title = `WebFetch: ${rawInput.url}`
    } else if (toolName) {
      title = toolName
    }
    return title
  }

  private toolOutput(update: Record<string, unknown>): string {
    const contentArr = update.content as Array<{ type: string; text?: string }> | undefined
    if (Array.isArray(contentArr)) {
      const output = contentArr
        .filter((content) => content.type === 'text' && content.text)
        .map((content) => content.text)
        .join('\n')
      if (output) return output
    }
    const rawOutput = update.rawOutput as Record<string, unknown> | undefined
    return rawOutput ? JSON.stringify(rawOutput) : ''
  }
}
