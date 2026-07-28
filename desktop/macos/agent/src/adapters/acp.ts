import { spawn, type ChildProcess } from "child_process";
import { createInterface, type Interface as ReadlineInterface } from "readline";
import { dirname, join } from "path";
import { fileURLToPath } from "url";
import {
  classifyAcpPermission,
  failClosedOutcome,
  normalizeAcpPermission,
  type ElicitationOutcome,
  type ElicitationRequest,
  type ElicitationResolver,
} from "../runtime/desktop-elicitation.js";
import { adapterCapabilitiesFor, type ProductionAdapterId } from "./interface.js";
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
  ResumeBindingInput,
  RuntimeAdapter,
} from "./interface.js";
import {
  AdapterRuntimeError,
  failureFromProcessError,
  failureFromProcessExit,
  normalizeRuntimeFailure,
  type RuntimeFailure,
} from "../runtime/failures.js";

type ResponseHandler = {
  resolve: (result: unknown) => void;
  reject: (err: Error) => void;
};

type PendingToolActivity = {
  id: string;
  name: string;
};

/**
 * Minimal environment allowlist for user-installed external adapter
 * subprocesses. Only OS-level essentials needed for a CLI tool to function
 * are forwarded — never the full parent environment. This prevents accidental
 * leakage of cloud credentials, CI tokens, or other host secrets to untrusted
 * third-party commands spawned with `shell: true`.
 */
const EXTERNAL_ADAPTER_ENV_ALLOWLIST = [
  "PATH",
  "HOME",
  "USER",
  "LOGNAME",
  "SHELL",
  "TMPDIR",
  "LANG",
  "LC_ALL",
  "LC_CTYPE",
  "TZ",
  "TERM",
  // Proxy/TLS — external adapters make outbound API calls and need these
  // to function in proxied or custom-CA environments.
  "HTTP_PROXY",
  "HTTPS_PROXY",
  "NO_PROXY",
  "http_proxy",
  "https_proxy",
  "no_proxy",
  "SSL_CERT_FILE",
  "SSL_CERT_DIR",
  "NODE_EXTRA_CA_CERTS",
  // Adapter-specific home directory. Swift seeds HERMES_HOME before launching
  // the Node bridge; forwarding it lets the spawned `hermes acp` subprocess
  // locate its config/state instead of falling back to defaults.
  "HERMES_HOME",
] as const;

/**
 * Proxy environment variable names that may carry embedded credentials
 * (e.g. `http://user:pass@proxy:3128`). Their values are sanitized before
 * being forwarded to untrusted external adapter subprocesses.
 */
const PROXY_ENV_KEYS = new Set([
  "HTTP_PROXY",
  "HTTPS_PROXY",
  "http_proxy",
  "https_proxy",
]);

/**
 * Strip embedded userinfo from a proxy URL before forwarding it to an
 * untrusted external adapter subprocess. Returns the URL without the
 * `user:pass@` component so the subprocess can route through the proxy
 * without receiving proxy credentials.
 *
 *   "http://alice:s3cr3t@proxy:3128" -> "http://proxy:3128"
 */
function sanitizeProxyUrl(value: string): string {
  try {
    const url = new URL(value);
    url.username = "";
    url.password = "";
    return url.toString();
  } catch {
    // Not a valid URL — forward as-is so non-URL proxy configs (e.g.
    // "proxy:3128") still work.
    return value;
  }
}

export class AcpError extends Error {
  code: number;
  data?: unknown;

  constructor(message: string, code: number, data?: unknown) {
    super(message);
    this.code = code;
    this.data = data;
  }
}

const RECOVERABLE_AUTH_ERROR_MARKERS = [
  "authentication_error",
  "authentication_failed",
  "failed to authenticate",
  "invalid authentication credentials",
  "oauth token has been revoked",
  "not logged in",
  "please run /login",
] as const;

/**
 * Detect ACP authentication failures that should re-enter the login flow.
 *
 * Claude ACP reports missing credentials with the canonical -32000 code, but
 * provider 401s during session/prompt are wrapped as -32603 internal errors.
 * Restrict wrapped-error matching to known auth markers so unrelated internal
 * errors remain terminal instead of opening a surprise login flow.
 */
/** Classifies ACP provider auth failures. Classification-only — never retry OAuth in-band. */
export function isAcpProviderAuthFailure(error: unknown): boolean {
  if (!(error instanceof AcpError)) return false;
  if (error.code === -32000) return true;
  if (error.code !== -32603) return false;

  let data = "";
  if (error.data !== undefined) {
    try {
      data = typeof error.data === "string" ? error.data : JSON.stringify(error.data);
    } catch {
      // The message remains authoritative when error data is not serializable.
    }
  }
  const searchable = `${error.message}\n${data}`.toLowerCase();
  return RECOVERABLE_AUTH_ERROR_MARKERS.some((marker) => searchable.includes(marker));
}

/** @deprecated Renamed to {@link isAcpProviderAuthFailure}; classify-only, no in-band recovery. */
export const isRecoverableAcpAuthError = isAcpProviderAuthFailure;

const MAX_RECENT_STDERR_CHARS = 2_000;

const EXTERNAL_TERMINAL_HTTP_FAILURE = /^\s*HTTP\s+([45]\d{2})\s*:\s*(?:\{|\[)/i;

/**
 * Some external ACP servers emit an HTTP provider failure as their final text
 * while still returning ACP `end_turn`.  Treat that exact terminal wire shape
 * as a failure so the runtime never projects a green Done state for it.
 *
 * We keep this deliberately narrow: only local external adapters and only a
 * leading 4xx/5xx JSON response are classified.  A normal agent discussion of
 * an HTTP status therefore remains ordinary assistant text.
 */
/** Human-facing agent name. Shown to the user on permission cards. */
function adapterLabel(adapterId: ProductionAdapterId): string {
  switch (adapterId) {
    case "hermes": return "Hermes";
    case "openclaw": return "OpenClaw";
    default: return "The agent";
  }
}

function externalTerminalHttpFailure(
  adapterId: ProductionAdapterId,
  text: string,
): RuntimeFailure | undefined {
  if (adapterId !== "hermes" && adapterId !== "openclaw") return undefined;
  const match = EXTERNAL_TERMINAL_HTTP_FAILURE.exec(text);
  if (!match) return undefined;
  const statusCode = Number(match[1]);
  const label = adapterLabel(adapterId);
  return normalizeRuntimeFailure({
    code: "adapter_terminal_http_failure",
    source: "adapter_execution",
    adapterId,
    retryable: statusCode >= 500,
    userMessage: `${label} could not complete the request. Try again.`,
    technicalMessage: `${adapterId} ACP reported terminal HTTP ${statusCode}`,
  });
}

function appendRecentStderr(current: string, next: string): string {
  const combined = `${current}${next}`;
  if (combined.length <= MAX_RECENT_STDERR_CHARS) {
    return combined;
  }
  return combined.slice(combined.length - MAX_RECENT_STDERR_CHARS);
}

export type AcpNotificationHandler = (method: string, params: unknown) => void;

export interface AcpRuntimeAdapterOptions {
  adapterId?: ProductionAdapterId;
  log?: (message: string) => void;
  nodeBin?: string;
  acpEntry?: string;
  command?: string;
  envCommandName?: string;
  sessionMcpServersMode?: "passthrough" | "empty";
  supportsSessionSetModel?: boolean;
  noProgressTimeoutMs?: number;
}

const __dirname = dirname(fileURLToPath(import.meta.url));
const DEFAULT_EXTERNAL_NO_PROGRESS_TIMEOUT_MS = 150_000;

function parsePositiveInt(value: string | undefined): number | undefined {
  if (!value) return undefined;
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : undefined;
}

export class AcpRuntimeAdapter implements RuntimeAdapter {
  readonly adapterId: ProductionAdapterId;
  readonly capabilities: AdapterCapabilities;

  private process: ChildProcess | null = null;
  private readline: ReadlineInterface | null = null;
  private stdinWriter: ((line: string) => void) | null = null;
  private responseHandlers = new Map<number, ResponseHandler>();
  private notificationHandler: AcpNotificationHandler | null = null;
  /**
   * Asks a human when policy will not auto-resolve a permission request.
   * Installed by the runtime, which owns the kernel; left null the adapter
   * fails closed rather than approving on the user's behalf.
   */
  elicitationResolver: ElicitationResolver | null = null;
  /**
   * In-flight permission requests, keyed by the ACP session they belong to.
   *
   * ACP requires a client that cancels a prompt turn to answer every pending
   * `session/request_permission` with the `cancelled` outcome, so cancellation
   * has to reach requests that are still waiting on a person.
   */
  private pendingPermissions = new Map<string, Set<(outcome: ElicitationOutcome) => void>>();
  private nextRpcId = 1;
  private initialized = false;
  private initializePromise: Promise<void> | null = null;
  private readonly log: (message: string) => void;
  private readonly nodeBin: string;
  private readonly acpEntry: string;
  private readonly command?: string;
  private readonly envCommandName?: string;
  private readonly sessionMcpServersMode: "passthrough" | "empty";
  private readonly supportsSessionSetModel: boolean;
  private readonly noProgressTimeoutMs: number;

  constructor(options: AcpRuntimeAdapterOptions = {}) {
    this.adapterId = options.adapterId ?? "acp";
    this.capabilities = adapterCapabilitiesFor(this.adapterId);
    this.log = options.log ?? (() => {});
    this.nodeBin = options.nodeBin ?? process.execPath;
    this.acpEntry =
      options.acpEntry ?? join(__dirname, "..", "patched-acp-entry.mjs");
    this.command = options.command;
    this.envCommandName = options.envCommandName;
    this.sessionMcpServersMode = options.sessionMcpServersMode ?? "passthrough";
    this.supportsSessionSetModel = options.supportsSessionSetModel ?? this.capabilities.supportsModelSwitching;
    this.noProgressTimeoutMs = options.noProgressTimeoutMs
      ?? parsePositiveInt(process.env.OMI_ACP_NO_PROGRESS_TIMEOUT_MS)
      ?? (this.adapterId === "hermes" || this.adapterId === "openclaw" ? DEFAULT_EXTERNAL_NO_PROGRESS_TIMEOUT_MS : 0);
  }

  async start(): Promise<void> {
    if (this.process) return;

    const env = { ...process.env };
    delete env.ANTHROPIC_API_KEY;
    delete env.CLAUDE_CODE_USE_VERTEX;
    delete env.CLAUDECODE;
    env.NODE_NO_WARNINGS = "1";

    const configuredCommand = this.command ?? (this.envCommandName ? process.env[this.envCommandName] : undefined);
    const command = configuredCommand?.trim();
    if (this.adapterId !== "acp" && !command) {
      throw new Error(`${this.adapterId} adapter requires ${this.envCommandName ?? "command"}`);
    }

    if (command) {
      // Construct a minimal environment from an allowlist rather than spreading
      // the full process.env. User-installed external adapters (Hermes,
      // OpenClaw) run untrusted commands with `shell: true`; a denylist leaves
      // cloud credentials, CI tokens, and other host secrets exposed.
      const externalEnv: NodeJS.ProcessEnv = {
        OMI_ADAPTER_ID: this.adapterId,
      };
      for (const key of EXTERNAL_ADAPTER_ENV_ALLOWLIST) {
        if (process.env[key] !== undefined) {
          // Proxy URLs may carry embedded credentials (user:pass@host).
          // Strip them before forwarding to untrusted subprocesses.
          externalEnv[key] = PROXY_ENV_KEYS.has(key)
            ? sanitizeProxyUrl(process.env[key]!)
            : process.env[key];
        }
      }
      this.log(`Starting ${this.adapterId} ACP subprocess: ${command}`);
      this.process = spawn(command, {
        shell: true,
        env: externalEnv,
        stdio: ["pipe", "pipe", "pipe"],
        detached: true,
      });
    } else {
      this.log(`Starting ${this.adapterId} ACP subprocess: ${this.nodeBin} ${this.acpEntry}`);
      this.process = spawn(this.nodeBin, [this.acpEntry], {
        shell: false,
        env,
        stdio: ["pipe", "pipe", "pipe"],
      });
    }
    const proc = this.process;
    let finalized = false;
    let recentStderr = "";
    const finalizeProcess = (error: Error): void => {
      if (finalized || this.process !== proc) return;
      finalized = true;
      this.log(error.message);
      this.process = null;
      this.stdinWriter = null;
      this.readline = null;
      this.initialized = false;
      this.initializePromise = null;
      for (const [, handler] of this.responseHandlers) {
        handler.reject(error);
      }
      this.responseHandlers.clear();
      // The subprocess that was blocked on these is gone, so nothing remains to
      // answer. Releasing the waiters here is what keeps a dead request from
      // holding a card the user can never usefully act on.
      this.cancelPendingPermissions(undefined, "adapter_process_exited");
      this.onProcessExit?.();
    };

    if (!proc.stdin || !proc.stdout || !proc.stderr) {
      throw new Error(`Failed to create ${this.adapterId} ACP subprocess pipes`);
    }

    proc.on("error", (err) => {
      finalizeProcess(new AdapterRuntimeError(failureFromProcessError({
        adapterId: this.adapterId,
        message: err.message,
      })));
    });

    this.stdinWriter = (line: string) => {
      try {
        this.process?.stdin?.write(line + "\n");
      } catch (err) {
        this.log(`Failed to write to ACP stdin: ${err}`);
      }
    };

    this.readline = createInterface({
      input: proc.stdout,
      terminal: false,
    });

    this.readline.on("line", (line: string) => this.handleLine(line));

    proc.stderr.on("data", (data: Buffer) => {
      const text = data.toString().trim();
      if (text) {
        recentStderr = appendRecentStderr(recentStderr, `${text}\n`);
        this.log(`ACP stderr: ${text}`);
      }
    });

    proc.on("exit", (code) => {
      finalizeProcess(new AdapterRuntimeError(failureFromProcessExit({
        adapterId: this.adapterId,
        exitCode: code,
        recentStderr,
      })));
    });
  }

  async stop(): Promise<void> {
    if (!this.process) return;
    const proc = this.process;
    const exitPromise = new Promise<void>((resolve) => {
      proc.once("exit", () => resolve());
    });
    // For shell-spawned external commands (detached process group), send the
    // signal to the entire group so the real adapter child is terminated too.
    try {
      if (proc.pid) {
        process.kill(-proc.pid, "SIGTERM");
      }
    } catch {
      // EPERM/E SRCH — fall back to direct kill.
      proc.kill();
    }
    await exitPromise;
  }

  async restart(): Promise<void> {
    if (this.process) {
      await this.stop();
    }
    await this.start();
  }

  async request(
    method: string,
    params: Record<string, unknown> = {}
  ): Promise<unknown> {
    await this.start();
    if (method !== "initialize") {
      await this.ensureInitialized();
    }
    const result = await this.rawRequest(method, params);
    if (method === "initialize") {
      this.initialized = true;
      this.initializePromise = null;
    }
    return result;
  }

  private async rawRequest(
    method: string,
    params: Record<string, unknown> = {}
  ): Promise<unknown> {
    const id = this.nextRpcId++;
    const msg = JSON.stringify({ jsonrpc: "2.0", id, method, params });

    return new Promise((resolve, reject) => {
      this.responseHandlers.set(id, { resolve, reject });
      if (this.stdinWriter) {
        this.stdinWriter(msg);
      } else {
        this.responseHandlers.delete(id);
        reject(new Error(`${this.adapterId} ACP process stdin not available`));
      }
    });
  }

  private async ensureInitialized(): Promise<void> {
    if (this.initialized) return;
    if (!this.initializePromise) {
      this.initializePromise = this.rawRequest("initialize", { protocolVersion: 1 })
        .then(() => {
          this.initialized = true;
          this.initializePromise = null;
        })
        .catch((error) => {
          this.initializePromise = null;
          throw error;
        });
    }
    await this.initializePromise;
  }

  notify(method: string, params: Record<string, unknown> = {}): void {
    const msg = JSON.stringify({ jsonrpc: "2.0", method, params });
    this.stdinWriter?.(msg);
  }

  setNotificationHandler(handler: AcpNotificationHandler | null): void {
    this.notificationHandler = handler;
  }

  onProcessExit?: () => void;

  async openBinding(input: OpenBindingInput): Promise<OpenedBinding> {
    const result = (await this.request("session/new", {
      cwd: input.cwd,
      mcpServers: this.sessionMcpServersMode === "empty" ? [] : input.mcpServers ?? [],
      ...(input.systemPrompt ? { _meta: { systemPrompt: input.systemPrompt } } : {}),
    })) as { sessionId: string };

    if (input.model && this.supportsSessionSetModel) {
      await this.request("session/set_model", {
        sessionId: result.sessionId,
        modelId: input.model,
      });
    }

    return this.binding(input, result.sessionId, this.supportsSessionSetModel);
  }

  async resumeBinding(input: ResumeBindingInput): Promise<OpenedBinding> {
    await this.request("session/resume", {
      sessionId: input.adapterNativeSessionId,
      cwd: input.cwd,
      mcpServers: this.sessionMcpServersMode === "empty" ? [] : input.mcpServers ?? [],
    });

    if (input.model && this.supportsSessionSetModel) {
      await this.request("session/set_model", {
        sessionId: input.adapterNativeSessionId,
        modelId: input.model,
      });
    }

    return this.binding(input, input.adapterNativeSessionId, this.supportsSessionSetModel);
  }

  async executeAttempt(
    context: AdapterAttemptContext,
    sink: AdapterEventSink,
    signal: AbortSignal
  ): Promise<AdapterAttemptResult> {
    const adapterSessionId = context.binding.adapterNativeSessionId;
    let fullText = "";
    const pendingTools: PendingToolActivity[] = [];
    let syntheticToolIdCounter = 0;
    const previousHandler = this.notificationHandler;
    let lastProgressAt = Date.now();
    this.notificationHandler = (method, params) => {
      previousHandler?.(method, params);
      if (signal.aborted || method !== "session/update") return;
      const didProgress = this.translateSessionUpdate(
        params as Record<string, unknown>,
        pendingTools,
        () => `acp-tool-${++syntheticToolIdCounter}`,
        sink,
        (text) => {
          fullText += text;
        }
      );
      if (didProgress) {
        lastProgressAt = Date.now();
      }
    };

    try {
      const promptRequest = this.request("session/prompt", {
        sessionId: adapterSessionId,
        prompt: context.prompt,
      });
      const result = (await this.withNoProgressTimeout(
        promptRequest,
        adapterSessionId,
        () => lastProgressAt,
        signal
      )) as {
        usage?: {
          inputTokens?: number;
          outputTokens?: number;
          cachedReadTokens?: number | null;
          cachedWriteTokens?: number | null;
        };
        _meta?: { costUsd?: number };
      };

      const failure = signal.aborted ? undefined : externalTerminalHttpFailure(this.adapterId, fullText);
      return {
        // Preserve only a bounded diagnostic in runtime/UI state when an
        // external adapter has reported an HTTP failure as text.  The raw
        // provider body stays in the adapter's local logs rather than being
        // rendered as a successful agent answer.
        text: failure?.userMessage ?? fullText,
        adapterSessionId,
        terminalStatus: signal.aborted ? "cancelled" : failure ? "failed" : "succeeded",
        failure,
        costUsd: result._meta?.costUsd ?? 0,
        inputTokens: result.usage?.inputTokens ?? 0,
        outputTokens: result.usage?.outputTokens ?? 0,
        cacheReadTokens: result.usage?.cachedReadTokens ?? 0,
        cacheWriteTokens: result.usage?.cachedWriteTokens ?? 0,
      };
    } finally {
      this.notificationHandler = previousHandler;
    }
  }

  private withNoProgressTimeout<T>(
    promise: Promise<T>,
    adapterSessionId: string,
    getLastProgressAt: () => number,
    signal: AbortSignal
  ): Promise<T> {
    const timeoutMs = this.noProgressTimeoutMs;
    if (timeoutMs <= 0) {
      return promise;
    }

    return new Promise<T>((resolve, reject) => {
      let settled = false;
      const finish = (fn: () => void): void => {
        if (settled) return;
        settled = true;
        clearInterval(timer);
        signal.removeEventListener("abort", onAbort);
        fn();
      };
      const onAbort = (): void => {
        this.cancelPendingPermissions(adapterSessionId, "attempt_aborted");
        finish(() => reject(new Error("ACP attempt cancelled")));
      };
      const timer = setInterval(() => {
        if (signal.aborted) {
          onAbort();
          return;
        }
        const idleMs = Date.now() - getLastProgressAt();
        if (idleMs < timeoutMs) {
          return;
        }
        this.log(`${this.adapterId} ACP session ${adapterSessionId} produced no recognized progress for ${idleMs}ms; cancelling`);
        this.notify("session/cancel", { sessionId: adapterSessionId });
        this.cancelPendingPermissions(adapterSessionId, "no_progress_timeout");
        finish(() => reject(new Error(`${this.adapterId} produced no progress for ${Math.round(timeoutMs / 1000)} seconds`)));
      }, Math.min(5_000, Math.max(1_000, Math.floor(timeoutMs / 6))));

      signal.addEventListener("abort", onAbort, { once: true });
      promise.then(
        (value) => finish(() => resolve(value)),
        (error) => finish(() => reject(error instanceof Error ? error : new Error(String(error))))
      );
    });
  }

  async cancelAttempt(context: CancelAttemptContext): Promise<CancelDispatchResult> {
    const sessionId = context.binding?.adapterNativeSessionId ?? context.sessionId;
    if (!sessionId) {
      return {
        accepted: true,
        dispatchAttempted: false,
        adapterAcknowledged: false,
        message: "No ACP session is active",
      };
    }
    this.notify("session/cancel", { sessionId });
    this.cancelPendingPermissions(sessionId, "turn_cancelled");
    return {
      accepted: true,
      dispatchAttempted: true,
      adapterAcknowledged: false,
    };
  }

  async closeBinding(_binding: AdapterBindingHandle): Promise<void> {
    // ACP exposes no explicit close primitive.
  }

  /**
   * OpenClaw (and any adapter configured with {@code sessionMcpServersMode:
   * "empty"}) strips per-session MCP servers before creating a session, so the
   * adapter-effective MCP set is always empty. Returning `[]` here lets the
   * kernel's binding hash reflect what the adapter actually saw,
   * preventing spurious binding replacements when a request-scoped env var
   * (e.g. OMI_QUERY_MODE) changes in the raw input.
   */
  effectiveMcpServers(mcpServers: Record<string, unknown>[]): Record<string, unknown>[] {
    if (this.sessionMcpServersMode === "empty") {
      return [];
    }
    return mcpServers;
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
      metadata: input.metadata,
    };
  }

  private handleLine(line: string): void {
    if (!line.trim()) return;
    try {
      const msg = JSON.parse(line) as Record<string, unknown>;

      if ("method" in msg && "id" in msg && msg.id !== null && msg.id !== undefined) {
        this.handleRequest(msg);
      } else if ("id" in msg && msg.id !== null && msg.id !== undefined) {
        this.handleResponse(msg);
      } else if ("method" in msg) {
        this.notificationHandler?.(msg.method as string, msg.params);
      }
    } catch {
      this.log(`Failed to parse ${this.adapterId} ACP message: ${line.slice(0, 200)}`);
    }
  }

  private handleRequest(msg: Record<string, unknown>): void {
    const id = msg.id as number;
    const method = msg.method as string;

    if (method === "session/request_permission") {
      void this.handlePermissionRequest(id, msg.params);
      return;
    }

    if (method === "session/update") {
      this.notificationHandler?.(method, msg.params);
      this.stdinWriter?.(JSON.stringify({ jsonrpc: "2.0", id, result: null }));
      return;
    }

    this.log(`Unhandled ACP request: ${method} (id=${id})`);
    this.stdinWriter?.(JSON.stringify({
      jsonrpc: "2.0",
      id,
      error: { code: -32601, message: `Method not handled: ${method}` },
    }));
  }

  /**
   * Answer `session/request_permission`.
   *
   * The agent subprocess is blocked on this JSON-RPC id until a response is
   * written, which is the contract that lets a person decide. Only one branch
   * resolves without them: a one-time grant on a read-shaped tool. Everything
   * else goes to `elicitationResolver`, and when no resolver is reachable the
   * request fails closed instead of approving unattended.
   */
  private async handlePermissionRequest(id: number, rawParams: unknown): Promise<void> {
    const request = normalizeAcpPermission({
      adapterId: this.adapterId,
      agentLabel: adapterLabel(this.adapterId),
      params: rawParams,
    });

    if (!request) {
      // An ACP permission response may only name an option the agent offered.
      // With no usable option there is nothing valid to answer, and inventing
      // one would fabricate consent.
      this.log(`${this.adapterId} ACP permission request carried no usable option; cancelling`);
      this.writePermissionOutcome(id, { kind: "cancelled", reason: "no_usable_option" });
      return;
    }

    const toolKind = (rawParams as Record<string, unknown> | undefined)?.toolCall;
    const classification = classifyAcpPermission(
      request,
      (toolKind as Record<string, unknown> | undefined)?.kind,
    );
    if (classification.decision === "auto") {
      this.log(`${this.adapterId} ACP permission auto-resolved: ${classification.reason}`);
      this.writePermissionOutcome(id, { kind: "selected", optionId: classification.optionId });
      return;
    }

    const resolver = this.elicitationResolver;
    if (!resolver) {
      this.log(
        `${this.adapterId} ACP permission needs a user but no resolver is installed; failing closed`,
      );
      this.writePermissionOutcome(id, failClosedOutcome(request, "no_resolver"));
      return;
    }

    this.log(`${this.adapterId} ACP permission asking the user: ${classification.reason}`);
    const outcome = await this.awaitPermissionOutcome(request, resolver);
    this.writePermissionOutcome(id, outcome);
  }

  /**
   * Wait on the user while remaining answerable to `session/cancel`, which ACP
   * requires be honoured for permission requests still in flight.
   */
  private awaitPermissionOutcome(
    request: ElicitationRequest,
    resolver: ElicitationResolver,
  ): Promise<ElicitationOutcome> {
    const sessionKey = request.externalSessionId ?? "";
    return new Promise<ElicitationOutcome>((resolve) => {
      let settled = false;
      const settle = (outcome: ElicitationOutcome) => {
        if (settled) return;
        settled = true;
        this.pendingPermissions.get(sessionKey)?.delete(settle);
        resolve(outcome);
      };

      let waiters = this.pendingPermissions.get(sessionKey);
      if (!waiters) {
        waiters = new Set();
        this.pendingPermissions.set(sessionKey, waiters);
      }
      waiters.add(settle);

      resolver(request).then(settle, (error: unknown) => {
        this.log(`${this.adapterId} ACP permission resolver failed: ${String(error)}`);
        settle(failClosedOutcome(request, "resolver_failed"));
      });
    });
  }

  /**
   * Cancel permission requests still awaiting a person.
   *
   * Passing no session id cancels every pending request, which is what process
   * teardown needs: the blocked JSON-RPC call cannot outlive the subprocess.
   */
  private cancelPendingPermissions(sessionId?: string, reason = "cancelled"): void {
    const keys = sessionId === undefined ? [...this.pendingPermissions.keys()] : [sessionId, ""];
    for (const key of keys) {
      const waiters = this.pendingPermissions.get(key);
      if (!waiters) continue;
      this.pendingPermissions.delete(key);
      for (const settle of waiters) settle({ kind: "cancelled", reason });
    }
  }

  /**
   * ACP accepts only `selected` or `cancelled`. A typed answer has no place in
   * the permission response shape, so it is recorded and treated as a
   * cancellation rather than silently coerced into an option the user did not
   * pick.
   */
  private writePermissionOutcome(id: number, outcome: ElicitationOutcome): void {
    if (outcome.kind === "answered") {
      this.log(`${this.adapterId} ACP permission received free text; answering cancelled`);
    }
    const result = outcome.kind === "selected"
      ? { outcome: { outcome: "selected", optionId: outcome.optionId } }
      : { outcome: { outcome: "cancelled" } };
    this.stdinWriter?.(JSON.stringify({ jsonrpc: "2.0", id, result }));
  }

  private handleResponse(msg: Record<string, unknown>): void {
    const id = msg.id as number;
    const handler = this.responseHandlers.get(id);
    if (!handler) return;
    this.responseHandlers.delete(id);
    if ("error" in msg) {
      const err = msg.error as { code: number; message: string; data?: unknown };
      handler.reject(new AcpError(err.message, err.code, err.data));
    } else {
      handler.resolve(msg.result);
    }
  }

  private translateSessionUpdate(
    params: Record<string, unknown>,
    pendingTools: PendingToolActivity[],
    nextSyntheticToolId: () => string,
    sink: AdapterEventSink,
    onText: (text: string) => void
  ): boolean {
    const update = params.update as Record<string, unknown> | undefined;
    if (!update) {
      this.log(`session/update missing 'update' field: ${JSON.stringify(params).slice(0, 200)}`);
      return false;
    }

    const sessionUpdate = update.sessionUpdate as string;
    switch (sessionUpdate) {
      case "agent_message_chunk": {
        const content = update.content as { type: string; text?: string } | undefined;
        const text = content?.text ?? "";
        if (!text) return false;
        for (const tool of pendingTools.splice(0)) {
          sink({ type: "tool_activity", name: tool.name, status: "completed", toolUseId: tool.id });
        }
        onText(text);
        sink({ type: "text_delta", text });
        return true;
      }

      case "agent_thought_chunk": {
        const content = update.content as { type: string; text?: string } | undefined;
        const text = content?.text ?? "";
        if (text) {
          sink({ type: "thinking_delta", text });
          return true;
        }
        return false;
      }

      case "tool_call": {
        const toolCallId = this.resolveToolCallStartId(update, nextSyntheticToolId);
        const title = this.toolTitle(update);
        const status = (update.status as string) ?? "pending";
        if (status === "pending" || status === "in_progress") {
          if (!pendingTools.some((tool) => tool.id === toolCallId)) {
            pendingTools.push({ id: toolCallId, name: title });
          }
          const rawInput = update.rawInput as Record<string, unknown> | undefined;
          sink({
            type: "tool_activity",
            name: title,
            status: "started",
            toolUseId: toolCallId,
            input: rawInput,
          });
          return true;
        }
        return false;
      }

      case "tool_call_update": {
        const status = (update.status as string) ?? "";
        const title = this.toolTitle(update);
        if (status !== "completed" && status !== "failed" && status !== "cancelled") {
          return false;
        }
        const toolCallId = this.resolveToolCallUpdateId(update, pendingTools, nextSyntheticToolId);
        const idx = pendingTools.findIndex((tool) => tool.id === toolCallId);
        if (idx >= 0) pendingTools.splice(idx, 1);
        sink({
          type: "tool_activity",
          name: title,
          status,
          toolUseId: toolCallId,
        });

        const output = this.toolOutput(update);
        if (output) {
          sink({
            type: "tool_result_display",
            toolUseId: toolCallId,
            name: title,
            output: output.length > 2000 ? `${output.slice(0, 2000)}\n... (truncated)` : output,
          });
        }
        return true;
      }

      case "plan": {
        const entries = update.entries as Array<{ content: string }> | undefined;
        if (!Array.isArray(entries)) return false;
        let emitted = false;
        for (const entry of entries) {
          if (entry.content) {
            sink({ type: "thinking_delta", text: `${entry.content}\n` });
            emitted = true;
          }
        }
        return emitted;
      }

      case "available_commands_update":
      case "usage_update": {
        return false;
      }

      default:
        this.log(`Unknown session update type: ${sessionUpdate}`);
        return false;
    }
  }

  private resolveToolCallStartId(
    update: Record<string, unknown>,
    nextSyntheticToolId: () => string
  ): string {
    const explicitId = typeof update.toolCallId === "string" ? update.toolCallId.trim() : "";
    if (explicitId) return explicitId;
    return nextSyntheticToolId();
  }

  private resolveToolCallUpdateId(
    update: Record<string, unknown>,
    pendingTools: PendingToolActivity[],
    nextSyntheticToolId: () => string
  ): string {
    const explicitId = typeof update.toolCallId === "string" ? update.toolCallId.trim() : "";
    if (explicitId) return explicitId;

    const title = this.toolTitle(update);
    const existing = pendingTools.find((tool) => tool.name === title);
    if (existing) return existing.id;
    return nextSyntheticToolId();
  }

  private toolTitle(update: Record<string, unknown>): string {
    let title = (update.title as string) ?? "unknown";
    if (title !== "unknown" && !title.includes("undefined")) {
      return title;
    }
    const meta = update._meta as { claudeCode?: { toolName?: string } } | undefined;
    const toolName = meta?.claudeCode?.toolName;
    const rawInput = update.rawInput as Record<string, unknown> | undefined;
    if (toolName === "WebSearch" && rawInput?.query) {
      title = `WebSearch: "${rawInput.query}"`;
    } else if (toolName === "WebFetch" && rawInput?.url) {
      title = `WebFetch: ${rawInput.url}`;
    } else if (toolName) {
      title = toolName;
    }
    return title;
  }

  private toolOutput(update: Record<string, unknown>): string {
    const contentArr = update.content as Array<{ type: string; text?: string }> | undefined;
    if (Array.isArray(contentArr)) {
      const output = contentArr
        .filter((content) => content.type === "text" && content.text)
        .map((content) => content.text)
        .join("\n");
      if (output) return output;
    }
    const rawOutput = update.rawOutput as Record<string, unknown> | undefined;
    return rawOutput ? JSON.stringify(rawOutput) : "";
  }
}
