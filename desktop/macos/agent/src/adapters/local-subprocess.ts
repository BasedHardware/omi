import { spawn, type ChildProcess } from "child_process";
import { createInterface, type Interface as ReadlineInterface } from "readline";
import { adapterCapabilitiesFor, type ProductionAdapterId } from "./interface.js";
import type {
  AdapterArtifactReference,
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
import type { ArtifactRole } from "../runtime/types.js";
import { normalizeRuntimeFailure, type RuntimeFailure } from "../runtime/failures.js";
import type { OutboundMessageDraft } from "../protocol.js";

type LocalSubprocessRequest = {
  type: "open" | "resume" | "execute" | "cancel" | "close";
  requestId: string;
  adapterRequestId?: string;
  clientId?: string;
  adapterId: ProductionAdapterId;
  omiSessionId?: string;
  ownerId?: string;
  adapterNativeSessionId?: string;
  runId?: string;
  attemptId?: string;
  cwd?: string;
  model?: string;
  systemPrompt?: string;
  mcpServers?: Record<string, unknown>[];
  prompt?: AdapterAttemptContext["prompt"];
  mode?: AdapterAttemptContext["mode"];
  tools?: AdapterAttemptContext["tools"];
  metadata?: Record<string, unknown>;
};

type LocalSubprocessMessage = {
  type?: string;
  requestId?: string;
  adapterRequestId?: string;
  ok?: boolean;
  error?: string | { message?: string };
  event?: unknown;
  result?: unknown;
  accepted?: boolean;
  dispatchAttempted?: boolean;
  adapterAcknowledged?: boolean;
  message?: string;
  adapterNativeSessionId?: string;
  adapterSessionId?: string;
  text?: string;
  terminalStatus?: AdapterAttemptResult["terminalStatus"];
  artifacts?: unknown;
  costUsd?: number;
  inputTokens?: number;
  outputTokens?: number;
  cacheReadTokens?: number;
  cacheWriteTokens?: number;
  failure?: unknown;
};

type PendingRequest = {
  resolve: (message: LocalSubprocessMessage) => void;
  reject: (error: Error) => void;
  eventSink?: AdapterEventSink;
  artifacts?: AdapterArtifactReference[];
  textParts?: string[];
  abortSignal?: AbortSignal;
  abortHandler?: () => void;
};

export interface LocalSubprocessRuntimeAdapterOptions {
  adapterId: ProductionAdapterId;
  envCommandName: string;
  command?: string;
  log?: (message: string) => void;
}

const artifactRoles = new Set<ArtifactRole>([
  "input",
  "result",
  "checkpoint",
  "tool_output",
  "log",
  "other",
]);

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

export class LocalSubprocessRuntimeAdapter implements RuntimeAdapter {
  readonly adapterId: ProductionAdapterId;
  readonly capabilities: AdapterCapabilities;

  private readonly envCommandName: string;
  private readonly commandOverride?: string;
  private readonly log: (message: string) => void;
  private process: ChildProcess | null = null;
  private readline: ReadlineInterface | null = null;
  private nextRequestId = 1;
  private pending = new Map<string, PendingRequest>();

  constructor(options: LocalSubprocessRuntimeAdapterOptions) {
    this.adapterId = options.adapterId;
    this.capabilities = adapterCapabilitiesFor(options.adapterId);
    this.envCommandName = options.envCommandName;
    this.commandOverride = options.command;
    this.log = options.log ?? (() => {});
  }

  async start(): Promise<void> {
    if (this.process) return;

    const command = this.commandOverride ?? process.env[this.envCommandName];
    if (!command?.trim()) {
      throw new Error(`${this.adapterId} adapter requires ${this.envCommandName}`);
    }

    // Construct a minimal environment from an allowlist rather than spreading
    // the full process.env and then deleting known credentials. User-installed
    // external adapters run untrusted commands with `shell: true`; a denylist
    // leaves cloud credentials, CI tokens, and other host secrets exposed.
    const scrubbedEnv: NodeJS.ProcessEnv = {
      OMI_ADAPTER_ID: this.adapterId,
    };
    for (const key of EXTERNAL_ADAPTER_ENV_ALLOWLIST) {
      if (process.env[key] !== undefined) {
        // Proxy URLs may carry embedded credentials (user:pass@host).
        // Strip them before forwarding to untrusted subprocesses.
        scrubbedEnv[key] = PROXY_ENV_KEYS.has(key)
          ? sanitizeProxyUrl(process.env[key]!)
          : process.env[key];
      }
    }

    this.process = spawn(command, {
      shell: true,
      stdio: ["pipe", "pipe", "pipe"],
      env: scrubbedEnv,
      detached: true,
    });
    const proc = this.process;

    if (!proc.stdin || !proc.stdout || !proc.stderr) {
      throw new Error(`Failed to create ${this.adapterId} subprocess pipes`);
    }

    this.readline = createInterface({ input: proc.stdout, terminal: false });
    this.readline.on("line", (line) => this.handleLine(line));

    proc.stderr.on("data", (data: Buffer) => {
      const text = data.toString().trim();
      if (text) this.log(`${this.adapterId} stderr: ${text}`);
    });

    const finalize = (reason: string): void => {
      if (this.process !== proc) return;
      this.process = null;
      this.readline = null;
      for (const [, pending] of this.pending) {
        pending.reject(new Error(reason));
      }
      this.pending.clear();
    };

    proc.on("error", (error) => finalize(`${this.adapterId} process error: ${error.message}`));
    proc.on("exit", (code) => finalize(`${this.adapterId} process exited with code ${code}`));
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
      proc.kill("SIGTERM");
    }
    await exitPromise;
  }

  async openBinding(input: OpenBindingInput): Promise<OpenedBinding> {
    const response = await this.request({
      type: "open",
      requestId: "",
      adapterId: this.adapterId,
      omiSessionId: input.sessionId,
      cwd: input.cwd,
      model: input.model,
      systemPrompt: input.systemPrompt,
      mcpServers: input.mcpServers,
      metadata: input.metadata,
    });
    const adapterNativeSessionId = this.adapterSessionIdFrom(response, `${this.adapterId}.open`);
    return this.binding(input, adapterNativeSessionId);
  }

  async resumeBinding(input: ResumeBindingInput): Promise<OpenedBinding> {
    const response = await this.request({
      type: "resume",
      requestId: "",
      adapterId: this.adapterId,
      omiSessionId: input.sessionId,
      adapterNativeSessionId: input.adapterNativeSessionId,
      cwd: input.cwd,
      model: input.model,
      systemPrompt: input.systemPrompt,
      mcpServers: input.mcpServers,
      metadata: input.metadata,
    });
    const adapterNativeSessionId =
      this.optionalAdapterSessionIdFrom(response) ?? input.adapterNativeSessionId;
    return this.binding(input, adapterNativeSessionId);
  }

  async executeAttempt(
    context: AdapterAttemptContext,
    sink: AdapterEventSink,
    signal: AbortSignal
  ): Promise<AdapterAttemptResult> {
    const request = this.buildExecuteRequest(context);
    const streamState = {
      artifacts: [] as AdapterArtifactReference[],
      textParts: [] as string[],
    };
    const responsePromise = this.request(request, {
      eventSink: sink,
      artifacts: streamState.artifacts,
      textParts: streamState.textParts,
    }, signal);

    const response = await responsePromise;
    const result = this.resultFrom(response, context, streamState);
    return signal.aborted ? { ...result, terminalStatus: "cancelled" } : result;
  }

  async cancelAttempt(context: CancelAttemptContext): Promise<CancelDispatchResult> {
    const adapterNativeSessionId = context.binding?.adapterNativeSessionId;
    if (!adapterNativeSessionId) {
      return {
        accepted: true,
        dispatchAttempted: false,
        adapterAcknowledged: false,
        message: `No ${this.adapterId} native session is active`,
      };
    }

    const response = await this.request({
      type: "cancel",
      requestId: context.requestId ?? "",
      adapterId: this.adapterId,
      omiSessionId: context.sessionId,
      ownerId: context.ownerId,
      clientId: context.clientId,
      adapterNativeSessionId,
      runId: context.runId,
      attemptId: context.attemptId,
    });

    return {
      accepted: response.accepted === false ? false : true,
      dispatchAttempted: response.dispatchAttempted === false ? false : true,
      adapterAcknowledged: response.adapterAcknowledged === true,
      message: typeof response.message === "string" ? response.message : undefined,
    };
  }

  async closeBinding(binding: AdapterBindingHandle): Promise<void> {
    if (!binding.adapterNativeSessionId) return;
    await this.request({
      type: "close",
      requestId: "",
      adapterId: this.adapterId,
      omiSessionId: binding.sessionId,
      adapterNativeSessionId: binding.adapterNativeSessionId,
    });
  }

  private buildExecuteRequest(context: AdapterAttemptContext): LocalSubprocessRequest {
    return {
      type: "execute",
      requestId: context.requestId,
      adapterId: this.adapterId,
      omiSessionId: context.sessionId,
      ownerId: context.ownerId,
      clientId: context.clientId,
      adapterNativeSessionId: context.binding.adapterNativeSessionId,
      runId: context.runId,
      attemptId: context.attemptId,
      cwd: context.binding.cwd,
      model: context.model ?? context.binding.model,
      prompt: context.prompt,
      mode: context.mode,
      tools: context.tools,
      metadata: context.metadata,
    };
  }

  private async request(
    request: LocalSubprocessRequest,
    pendingOverrides: Partial<PendingRequest> = {},
    signal?: AbortSignal
  ): Promise<LocalSubprocessMessage> {
    await this.start();
    const adapterRequestId = `${this.adapterId}-${this.nextRequestId++}`;
    const message = {
      ...request,
      adapterRequestId,
      requestId: request.requestId || adapterRequestId,
    };

    return new Promise((resolve, reject) => {
      const pending: PendingRequest = { resolve, reject, ...pendingOverrides };
      if (signal) {
        const abortHandler = (): void => {
          this.pending.delete(adapterRequestId);
          reject(new Error(`${this.adapterId} adapter request aborted`));
        };
        pending.abortSignal = signal;
        pending.abortHandler = abortHandler;
        if (signal.aborted) {
          reject(new Error(`${this.adapterId} adapter request aborted`));
          return;
        }
        signal.addEventListener("abort", abortHandler, { once: true });
      }
      this.pending.set(adapterRequestId, pending);
      try {
        this.write(message);
      } catch (error) {
        this.pending.delete(adapterRequestId);
        if (signal && pending.abortHandler) {
          signal.removeEventListener("abort", pending.abortHandler);
        }
        reject(error instanceof Error ? error : new Error(String(error)));
      }
    });
  }

  private write(message: LocalSubprocessRequest): void {
    if (!this.process?.stdin?.writable) {
      throw new Error(`${this.adapterId} process not running`);
    }
    this.process.stdin.write(`${JSON.stringify(message)}\n`);
  }

  private handleLine(line: string): void {
    if (!line.trim()) return;

    let message: LocalSubprocessMessage;
    try {
      message = JSON.parse(line) as LocalSubprocessMessage;
    } catch {
      this.log(`Failed to parse ${this.adapterId} message: ${line.slice(0, 200)}`);
      return;
    }

    const requestId = message.adapterRequestId ?? message.requestId;
    if (!requestId) {
      this.log(`Ignoring ${this.adapterId} message without requestId`);
      return;
    }
    const pending = this.pending.get(requestId);
    if (!pending) return;

    if (message.type === "event") {
      this.handleEventMessage(message.event, pending);
      return;
    }

    if (this.isCanonicalEvent(message)) {
      this.handleEventMessage(message, pending);
      return;
    }

    this.pending.delete(requestId);
    if (pending.abortSignal && pending.abortHandler) {
      pending.abortSignal.removeEventListener("abort", pending.abortHandler);
    }
    if (message.ok === false || message.type === "error") {
      pending.reject(new Error(this.errorMessage(message)));
      return;
    }
    pending.resolve(message);
  }

  private handleEventMessage(event: unknown, pending: PendingRequest): void {
    if (!isRecord(event)) return;

    if (event.type === "artifact") {
      if (!this.capabilities.supportsArtifactEmission) return;
      const artifact = this.artifactFrom(event.artifact ?? event);
      if (artifact) pending.artifacts?.push(artifact);
      return;
    }

    const canonicalEvent = this.canonicalEventFrom(event);
    if (!canonicalEvent) return;

    if (canonicalEvent.type === "text_delta") {
      pending.textParts?.push(canonicalEvent.text);
    }
    pending.eventSink?.(canonicalEvent);
  }

  private canonicalEventFrom(event: Record<string, unknown>): OutboundMessageDraft | null {
    switch (event.type) {
      case "text_delta":
        return { type: "text_delta", text: stringValue(event.text) };
      case "thinking_delta":
        return { type: "thinking_delta", text: stringValue(event.text) };
      case "tool_use":
        return {
          type: "tool_use",
          callId: stringValue(event.callId ?? event.toolUseId),
          name: stringValue(event.name),
          input: recordValue(event.input),
        };
      case "tool_activity": {
        const status = event.status === "completed" || event.status === "failed" ? event.status : "started";
        return {
          type: "tool_activity",
          name: stringValue(event.name),
          status,
          toolUseId: optionalString(event.toolUseId),
          input: isRecord(event.input) ? event.input : undefined,
        };
      }
      case "tool_result_display":
        return {
          type: "tool_result_display",
          toolUseId: stringValue(event.toolUseId ?? event.callId),
          name: stringValue(event.name),
          output: stringValue(event.output),
        };
      case "error":
        return { type: "error", message: stringValue(event.message) };
      default:
        return null;
    }
  }

  private resultFrom(
    response: LocalSubprocessMessage,
    context: AdapterAttemptContext,
    streamState: {
      artifacts: AdapterArtifactReference[];
      textParts: string[];
    }
  ): AdapterAttemptResult {
    const result = isRecord(response.result) ? response.result : response;
    const terminalStatus = this.terminalStatusFrom(result.terminalStatus);
    const artifacts = this.capabilities.supportsArtifactEmission
      ? [
          ...streamState.artifacts,
          ...this.artifactsFrom(result.artifacts),
        ]
      : [];
    const text = optionalString(result.text)
      ?? streamState.textParts.join("")
      ?? "";

    return {
      text,
      adapterSessionId: this.optionalAdapterSessionIdFrom(result) ?? context.binding.adapterNativeSessionId,
      terminalStatus,
      costUsd: optionalNumber(result.costUsd),
      inputTokens: optionalNumber(result.inputTokens),
      outputTokens: optionalNumber(result.outputTokens),
      cacheReadTokens: optionalNumber(result.cacheReadTokens),
      cacheWriteTokens: optionalNumber(result.cacheWriteTokens),
      failure: this.failureFrom(result.failure),
      artifacts: artifacts.length > 0 ? artifacts : undefined,
    };
  }

  private failureFrom(value: unknown): RuntimeFailure | undefined {
    if (!isRecord(value)) return undefined;
    const code = optionalString(value.code);
    const userMessage = optionalString(value.userMessage);
    if (!code || !userMessage) return undefined;
    return normalizeRuntimeFailure({
      code,
      userMessage,
      technicalMessage: optionalString(value.technicalMessage),
      source: value.source === "adapter_process" || value.source === "adapter_execution" || value.source === "runtime"
        ? value.source
        : undefined,
      adapterId: optionalString(value.adapterId) ?? this.adapterId,
      provider: optionalString(value.provider),
      retryable: typeof value.retryable === "boolean" ? value.retryable : undefined,
    });
  }

  private artifactFrom(value: unknown): AdapterArtifactReference | null {
    if (!isRecord(value)) return null;
    const uri = optionalString(value.uri);
    if (!uri) return null;
    const role = artifactRoles.has(value.role as ArtifactRole) ? value.role as ArtifactRole : "other";
    return {
      kind: optionalString(value.kind) ?? "file",
      role,
      uri,
      displayName: nullableString(value.displayName),
      mimeType: nullableString(value.mimeType),
      contentHash: nullableString(value.contentHash),
      sizeBytes: nullableNumber(value.sizeBytes),
      metadata: isRecord(value.metadata) ? value.metadata : undefined,
    };
  }

  private terminalStatusFrom(value: unknown): AdapterAttemptResult["terminalStatus"] {
    if (value === "succeeded" || value === "failed" || value === "cancelled") {
      return value;
    }
    throw new Error(`${this.adapterId} result missing valid terminalStatus`);
  }

  private artifactsFrom(value: unknown): AdapterArtifactReference[] {
    if (!Array.isArray(value)) return [];
    return value.flatMap((entry) => {
      const artifact = this.artifactFrom(entry);
      return artifact ? [artifact] : [];
    });
  }

  private binding(input: OpenBindingInput, adapterNativeSessionId: string): AdapterBindingHandle {
    return {
      bindingId: input.metadata?.bindingId as string | undefined,
      sessionId: input.sessionId,
      adapterId: this.adapterId,
      adapterNativeSessionId,
      resumeFidelity: this.capabilities.resumeFidelity,
      cwd: input.cwd,
      model: input.model,
      metadata: input.metadata,
    };
  }

  private adapterSessionIdFrom(message: LocalSubprocessMessage, operation: string): string {
    const adapterSessionId = this.optionalAdapterSessionIdFrom(message.result) ?? this.optionalAdapterSessionIdFrom(message);
    if (!adapterSessionId) {
      throw new Error(`${operation} response missing adapterNativeSessionId`);
    }
    return adapterSessionId;
  }

  private optionalAdapterSessionIdFrom(value: unknown): string | undefined {
    if (!isRecord(value)) return undefined;
    return optionalString(value.adapterNativeSessionId) ?? optionalString(value.adapterSessionId);
  }

  private isCanonicalEvent(message: LocalSubprocessMessage): boolean {
    return message.type === "text_delta"
      || message.type === "thinking_delta"
      || message.type === "tool_use"
      || message.type === "tool_activity"
      || message.type === "tool_result_display"
      || message.type === "error";
  }

  private errorMessage(message: LocalSubprocessMessage): string {
    if (typeof message.error === "string") return message.error;
    if (isRecord(message.error) && typeof message.error.message === "string") {
      return message.error.message;
    }
    if (typeof message.message === "string") return message.message;
    return `${this.adapterId} adapter request failed`;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function stringValue(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function optionalString(value: unknown): string | undefined {
  return typeof value === "string" && value.length > 0 ? value : undefined;
}

function nullableString(value: unknown): string | null | undefined {
  return value === null ? null : optionalString(value);
}

function optionalNumber(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function nullableNumber(value: unknown): number | null | undefined {
  return value === null ? null : optionalNumber(value);
}

function recordValue(value: unknown): Record<string, unknown> {
  return isRecord(value) ? value : {};
}
