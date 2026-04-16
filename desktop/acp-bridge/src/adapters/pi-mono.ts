// PiMonoAdapter — pi-mono harness adapter using SDK in-process
//
// Uses createAgentSession() from pi-mono SDK to run the agent loop
// in the same Node.js process. Custom tools relay back to Swift
// via the existing tool_use/tool_result bridge protocol.
//
// Issue #6594: Pi-mono harness with Omi API proxy for server-side cost control.

import { ChildProcess, spawn } from "child_process";
import { existsSync } from "fs";
import { createInterface, Interface as ReadlineInterface } from "readline";
import {
  HarnessAdapter,
  HarnessConfig,
  HarnessFeature,
  SessionOpts,
  PromptBlock,
  PromptResult,
  ToolDef,
  ToolExecutor,
  EventCallback,
} from "./interface.js";
import type { WarmupSessionConfig } from "../protocol.js";

// Pi-mono RPC command/event types
interface PiRpcCommand {
  id?: string;
  type: string;
  [key: string]: unknown;
}

interface PiRpcEvent {
  type: string;
  [key: string]: unknown;
}

interface PiAssistantMessageEvent {
  type: string;
  contentIndex?: number;
  delta?: string;
  content?: string;
  partial?: PiAssistantMessage;
  message?: PiAssistantMessage;
  toolCall?: PiToolCall;
  reason?: string;
  error?: PiAssistantMessage;
}

interface PiAssistantMessage {
  role: string;
  content: PiContentBlock[];
  usage?: PiUsage;
  stopReason?: string;
  errorMessage?: string;
}

interface PiContentBlock {
  type: string;
  text?: string;
  thinking?: string;
  id?: string;
  name?: string;
  arguments?: Record<string, unknown>;
}

interface PiToolCall {
  id: string;
  name: string;
  arguments: Record<string, unknown>;
}

interface PiUsage {
  input: number;
  output: number;
  cacheRead: number;
  cacheWrite: number;
  totalTokens: number;
  cost?: {
    input: number;
    output: number;
    cacheRead: number;
    cacheWrite: number;
    total: number;
  };
}

/**
 * PiMonoAdapter spawns pi-mono in RPC mode and translates its events
 * into the normalized bridge protocol.
 *
 * Tool execution flows:
 * 1. Pi-mono executes its built-in tools internally (bash, read, write, edit)
 * 2. Custom Omi tools are registered via the extension, which routes them
 *    through the Omi API backend
 *
 * For desktop chat, we disable pi-mono's built-in tools and rely on
 * the omi-provider extension to handle all tool calls server-side.
 */
// Map desktop model IDs (claude-*) to omi provider model IDs.
// Covers short aliases and dated versions used by ChatProvider/ChatLab.
const MODEL_MAP: Record<string, string> = {
  "claude-opus-4-6": "omi-opus",
  "claude-sonnet-4-6": "omi-sonnet",
  "claude-sonnet-4": "omi-sonnet",
  "claude-opus-4": "omi-opus",
  "claude-sonnet-4-20250514": "omi-sonnet",
  "claude-opus-4-20250514": "omi-opus",
};

function mapModel(model: string): string {
  return MODEL_MAP[model] ?? model;
}

/** Resolve the pi binary bundled inside the Mac app.
 *
 *  Resolution order:
 *  1. $PI_MONO_PATH (test/dev override)
 *  2. The actual pi-coding-agent dist/cli.js (bypasses .bin symlinks that
 *     get resolved by ditto during app bundle install)
 *  3. acp-bridge/node_modules/.bin/pi (fallback for dev where symlinks work)
 *  4. Fall back to "pi" on PATH (dev machines only)
 */
function resolveBundledPi(): string {
  // this file compiles to acp-bridge/dist/adapters/pi-mono.js
  // Prefer the direct package path — .bin/pi is a symlink that ditto resolves
  // into a flat copy, breaking its relative import of ./main.js
  const direct = new URL(
    "../../node_modules/@mariozechner/pi-coding-agent/dist/cli.js",
    import.meta.url
  ).pathname;
  if (existsSync(direct)) return direct;
  const binFallback = new URL("../../node_modules/.bin/pi", import.meta.url)
    .pathname;
  if (existsSync(binFallback)) return binFallback;
  return "pi";
}

/** Resolve the omi-provider extension file bundled alongside the app.
 *
 *  Dev: <repo>/desktop/acp-bridge/dist/adapters/../../.. → <repo>/desktop/pi-mono-extension/index.ts
 *  Shipped: <App>.app/Contents/Resources/acp-bridge/dist/adapters/../../.. → <App>.app/Contents/Resources/pi-mono-extension/index.ts
 */
function resolveBundledExtension(): string {
  return new URL(
    "../../../pi-mono-extension/index.ts",
    import.meta.url
  ).pathname;
}

export class PiMonoAdapter implements HarnessAdapter {
  readonly name = "pi-mono";

  private config: HarnessConfig;
  private process: ChildProcess | null = null;
  private readline: ReadlineInterface | null = null;
  private sessions: Map<
    string,
    { cwd: string; model?: string; systemPrompt?: string }
  > = new Map();
  private nextSessionId = 1;
  /** Per-prompt state — keyed by monotonic prompt generation ID, not session ID.
   *  Pi-mono RPC only processes one prompt at a time, so a generation counter
   *  is sufficient for correlation. Late/stray turn_end events that don't
   *  match the in-flight generation are dropped. */
  private pendingRequests: Map<
    number,
    {
      sessionId: string;
      resolve: (value: unknown) => void;
      reject: (err: Error) => void;
    }
  > = new Map();
  /** Generation of the currently-in-flight prompt (0 = none) */
  private activePromptGeneration = 0;
  /** Monotonic counter for prompt generations */
  private nextPromptGeneration = 1;
  private nextRequestId = 1;
  private eventHandler: EventCallback | null = null;
  private toolExecutor: ToolExecutor | null = null;
  private currentAbortController: AbortController | null = null;
  private piPath: string;
  private extensionPath: string;
  /** Current system prompt baked into the spawned pi process via --system-prompt.
   *  Pi has no set_system_prompt RPC, so changing this requires a subprocess restart. */
  private currentSystemPrompt: string | undefined;
  /** True when a token refresh was deferred because a prompt was active */
  private pendingTokenRefresh = false;
  /** True when a system-prompt change was deferred because a prompt was active */
  private pendingSystemPromptRefresh = false;

  constructor(config: HarnessConfig, piPath?: string, extensionPath?: string) {
    this.config = config;
    this.piPath = piPath || process.env.PI_MONO_PATH || resolveBundledPi();
    this.extensionPath =
      extensionPath ||
      process.env.PI_EXTENSION_PATH ||
      resolveBundledExtension();
  }

  async start(): Promise<void> {
    if (this.process) {
      return;
    }

    const args = [
      "--mode",
      "rpc",
      "-e",
      this.extensionPath,
      "--provider",
      "omi",
      "--model",
      "omi-sonnet",
      "--no-extensions", // disable auto-discovered extensions
    ];
    // Pi has no set_system_prompt RPC — system prompt must be baked at spawn
    // time via the --system-prompt CLI flag. To change it, restart the process.
    if (this.currentSystemPrompt) {
      args.push("--system-prompt", this.currentSystemPrompt);
    }

    // SECURITY: require a Firebase ID token. We MUST NOT fall back to
    // ANTHROPIC_API_KEY — the Omi backend rejects provider keys and forwarding
    // one here would leak the upstream secret to api.omi.me.
    if (!this.config.authToken) {
      throw new Error(
        "pi-mono adapter requires config.authToken (Firebase ID token)"
      );
    }

    // Scrub any ANTHROPIC_API_KEY from the child env so the extension cannot
    // accidentally read it as a credential. pi-mono talks to api.omi.me with
    // OMI_API_KEY only.
    const env: Record<string, string> = {
      ...process.env as Record<string, string>,
    };
    delete env.ANTHROPIC_API_KEY;

    // SECURITY: OMI_YOLO_MODE bypasses the extension's entire tool denylist.
    // Scrub it from the subprocess env, then only re-inject when explicitly
    // set in the parent. Production (Omi Beta via Codemagic) launches from
    // Finder without custom env vars so this is a safety net against
    // ambient shell leakage. Log when active so usage is auditable.
    delete env.OMI_YOLO_MODE;
    if (process.env.OMI_YOLO_MODE === "1") {
      env.OMI_YOLO_MODE = "1";
      process.stderr.write("[pi-mono] WARNING: OMI_YOLO_MODE=1 — denylist bypass active\n");
    }

    // Pass the raw Firebase ID token. pi's openai-completions client already
    // prepends `Authorization: Bearer ${apiKey}` — adding our own "Bearer "
    // prefix here would produce a malformed `Bearer Bearer <token>` header.
    env.OMI_API_KEY = this.config.authToken;
    if (this.config.omiApiBaseUrl) {
      env.OMI_API_BASE_URL = this.config.omiApiBaseUrl;
    }
    // Forward OMI_BRIDGE_PIPE so the extension can register omi-tools
    // (execute_sql, semantic_search, etc.) that forward to Swift.
    // The pipe is already set in process.env by runPiMonoMode().

    this.process = spawn(this.piPath, args, {
      stdio: ["pipe", "pipe", "pipe"],
      env,
    });

    if (!this.process.stdout || !this.process.stdin) {
      throw new Error("Failed to create pi-mono subprocess pipes");
    }

    // Read JSONL events from stdout
    this.readline = createInterface({ input: this.process.stdout });
    this.readline.on("line", (line: string) => {
      this.handleEvent(line);
    });

    // Log stderr
    if (this.process.stderr) {
      this.process.stderr.on("data", (data: Buffer) => {
        const msg = data.toString().trim();
        if (msg) {
          process.stderr.write(`[pi-mono] ${msg}\n`);
        }
      });
    }

    this.process.on("exit", (code: number | null) => {
      process.stderr.write(`[pi-mono] process exited with code ${code}\n`);
      this.process = null;
      this.readline = null;
      this.sessions.clear();
      // Reject pending requests
      for (const [, req] of this.pendingRequests) {
        req.reject(new Error(`pi-mono process exited (code ${code})`));
      }
      this.pendingRequests.clear();
      this.activePromptGeneration = 0;
    });
  }

  async stop(): Promise<void> {
    if (this.process) {
      // Remove all listeners from the old process FIRST so its delayed exit
      // event can't fire the exit handler after we've already spawned a
      // replacement. Without this, a stop()/start() cycle that interleaves
      // with an incoming sendPrompt can race: the old process's exit event
      // arrives after the new pendingRequest is registered, and the handler
      // rejects the fresh request with "pi-mono process exited (code null)".
      this.process.removeAllListeners("exit");
      if (this.process.stdout) this.process.stdout.removeAllListeners();
      if (this.process.stderr) this.process.stderr.removeAllListeners();
      this.process.kill("SIGTERM");
      this.process = null;
      if (this.readline) {
        this.readline.removeAllListeners();
        this.readline.close();
        this.readline = null;
      }
    }
    this.sessions.clear();
    this.pendingRequests.clear();
    this.activePromptGeneration = 0;
  }

  async createSession(opts: SessionOpts): Promise<string> {
    const mapped = opts.model ? mapModel(opts.model) : undefined;

    // Pi bakes the system prompt at spawn time via --system-prompt. If the
    // caller requested a different prompt than the currently-running process,
    // restart the subprocess with the new flag. Callers that want this handled
    // eagerly across session switches should call setSystemPrompt() before
    // createSession().
    if (opts.systemPrompt && opts.systemPrompt !== this.currentSystemPrompt) {
      await this.setSystemPrompt(opts.systemPrompt);
    }

    const sessionId = `pi-session-${this.nextSessionId++}`;
    this.sessions.set(sessionId, {
      cwd: opts.cwd,
      model: mapped,
      systemPrompt: opts.systemPrompt,
    });

    // Set model if specified (map claude-* → omi-*)
    if (mapped) {
      this.sendCommand({
        type: "set_model",
        provider: "omi",
        modelId: mapped,
      });
    }

    return sessionId;
  }

  async sendPrompt(
    sessionId: string,
    prompt: PromptBlock[],
    _tools: ToolDef[],
    _mode: "ask" | "act",
    onEvent: EventCallback,
    onToolCall: ToolExecutor,
    signal?: AbortSignal
  ): Promise<PromptResult> {
    // Serialization invariant: pi-mono RPC only handles one prompt at a time.
    // Any stray in-flight request here indicates a caller contract violation
    // or a missed abort — drop it so a late turn_end can't leak into this one.
    if (this.activePromptGeneration !== 0) {
      const stale = this.pendingRequests.get(this.activePromptGeneration);
      if (stale) {
        this.pendingRequests.delete(this.activePromptGeneration);
        stale.reject(
          new Error(
            "pi-mono prompt superseded before turn_end (previous request dropped)"
          )
        );
      }
      this.activePromptGeneration = 0;
    }

    this.eventHandler = onEvent;
    this.toolExecutor = onToolCall;
    this.currentAbortController = new AbortController();

    const generation = this.nextPromptGeneration++;
    this.activePromptGeneration = generation;

    if (signal) {
      signal.addEventListener("abort", () => {
        this.abort(sessionId);
      });
    }

    // Extract text and image from prompt blocks
    const textParts: string[] = [];
    const images: { type: string; data: string; mimeType: string }[] = [];

    for (const block of prompt) {
      if (block.type === "text") {
        textParts.push(block.text);
      } else if (block.type === "image") {
        images.push({
          type: "image",
          data: block.data,
          mimeType: block.mimeType,
        });
      }
    }

    const message = textParts.join("\n");

    const cmd: PiRpcCommand = {
      type: "prompt",
      message,
    };
    if (images.length > 0) {
      cmd.images = images;
    }

    this.sendCommand(cmd);

    // Wait for turn_end event mapped to THIS generation
    return new Promise<PromptResult>((resolve, reject) => {
      this.pendingRequests.set(generation, {
        sessionId,
        resolve: (value: unknown) => resolve(value as PromptResult),
        reject,
      });
    });
  }

  abort(sessionId: string): void {
    this.sendCommand({ type: "abort" });
    this.currentAbortController?.abort();

    // Resolve the in-flight prompt (by generation) with a partial result and
    // CLEAR activePromptGeneration so a stray late turn_end is dropped instead
    // of completing whatever comes next.
    const generation = this.activePromptGeneration;
    if (generation === 0) return;
    const pending = this.pendingRequests.get(generation);
    if (pending) {
      this.pendingRequests.delete(generation);
      pending.resolve({
        text: "",
        sessionId: pending.sessionId || sessionId,
        costUsd: 0,
        inputTokens: 0,
        outputTokens: 0,
      });
    }
    this.activePromptGeneration = 0;
  }

  async setModel(sessionId: string, model: string): Promise<void> {
    const mapped = mapModel(model);
    const session = this.sessions.get(sessionId);
    if (session) {
      session.model = mapped;
    }
    this.sendCommand({
      type: "set_model",
      provider: "omi",
      modelId: mapped,
    });
  }

  async warmup(cwd: string, sessions: WarmupSessionConfig[]): Promise<void> {
    // Pre-create sessions
    for (const config of sessions) {
      await this.createSession({
        cwd,
        model: config.model,
        systemPrompt: config.systemPrompt,
      });
    }
  }

  invalidateSession(sessionKey: string): void {
    this.sessions.delete(sessionKey);
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
      return true; // no-op
    }
    this.currentSystemPrompt = systemPrompt;
    if (!this.process) {
      // Not started yet — nothing to restart; start() will bake the new value.
      return true;
    }
    if (this.pendingRequests.size > 0) {
      this.pendingSystemPromptRefresh = true;
      process.stderr.write(
        "[pi-mono] system prompt stored (restart deferred, prompt active)\n"
      );
      return false;
    }
    await this.stop();
    await this.start();
    this.pendingSystemPromptRefresh = false;
    process.stderr.write(
      "[pi-mono] subprocess restarted with new system prompt\n"
    );
    return true;
  }

  /** Update auth token by restarting the subprocess when idle.
   *  The pi-mono extension bakes OMI_API_KEY at startup, so the only way
   *  to refresh is to restart the process. If a prompt is active, marks a
   *  pending restart that handleTurnEnd will execute after the prompt completes.
   *  Returns true if restart happened immediately, false if deferred. */
  async updateAuthToken(token: string): Promise<boolean> {
    this.config.authToken = token;
    if (this.pendingRequests.size > 0) {
      this.pendingTokenRefresh = true;
      process.stderr.write("[pi-mono] auth token stored (restart deferred, prompt active)\n");
      return false;
    }
    await this.stop();
    await this.start();
    this.pendingTokenRefresh = false;
    process.stderr.write("[pi-mono] subprocess restarted with refreshed auth token\n");
    return true;
  }

  /** Whether a prompt is currently in-flight */
  get isIdle(): boolean {
    return this.pendingRequests.size === 0;
  }

  /** Whether a deferred restart is pending (token or system prompt) */
  get hasPendingRestart(): boolean {
    return this.pendingTokenRefresh || this.pendingSystemPromptRefresh;
  }

  /** Execute the deferred restart (call after prompt completes).
   *  Handles both token refresh and system-prompt change — both baked at
   *  spawn time, both requiring a restart. */
  async executePendingRestart(): Promise<void> {
    if (!this.pendingTokenRefresh && !this.pendingSystemPromptRefresh) return;
    const reasons: string[] = [];
    if (this.pendingTokenRefresh) reasons.push("token");
    if (this.pendingSystemPromptRefresh) reasons.push("systemPrompt");
    this.pendingTokenRefresh = false;
    this.pendingSystemPromptRefresh = false;
    await this.stop();
    await this.start();
    process.stderr.write(
      `[pi-mono] deferred restart executed (${reasons.join("+")}; subprocess restarted)\n`
    );
  }

  supportsFeature(feature: HarnessFeature): boolean {
    switch (feature) {
      case HarnessFeature.BIDIRECTIONAL_RPC:
        return true;
      case HarnessFeature.MODEL_SWITCH:
        return true;
      case HarnessFeature.COST_TRACKING:
        return true; // Server-side via Omi API
      case HarnessFeature.MCP_CLIENT:
        return false; // Pi-mono doesn't use MCP
      case HarnessFeature.SESSION_RESUME:
        return true;
      case HarnessFeature.OAUTH:
        return false; // Uses Firebase token, not OAuth
      default:
        return false;
    }
  }

  // ── Private helpers ──────────────────────────────────────────────────

  private sendCommand(cmd: PiRpcCommand): void {
    if (!this.process?.stdin?.writable) {
      throw new Error("pi-mono process not running");
    }
    const id = `req-${this.nextRequestId++}`;
    cmd.id = id;
    this.process.stdin.write(JSON.stringify(cmd) + "\n");
  }

  private handleEvent(line: string): void {
    let event: PiRpcEvent;
    try {
      event = JSON.parse(line);
    } catch {
      process.stderr.write(`[pi-mono] invalid JSON: ${line}\n`);
      return;
    }

    switch (event.type) {
      case "message_update":
        this.handleMessageUpdate(event);
        break;

      case "tool_execution_start":
        this.handleToolStart(event);
        break;

      case "tool_execution_update":
        // Partial tool output — emit as tool_activity
        break;

      case "tool_execution_end":
        this.handleToolEnd(event);
        break;

      case "turn_end":
        this.handleTurnEnd(event);
        break;

      case "agent_start":
      case "agent_end":
      case "turn_start":
      case "message_start":
      case "message_end":
      case "response":
      case "compaction_start":
      case "compaction_end":
      case "auto_retry_start":
      case "auto_retry_end":
        // Protocol control events the adapter observes but does not act on.
        // Turn boundaries and streaming state are already tracked via
        // message_update / turn_end; no action needed here.
        // auto_retry_* events fire when pi retries after a transient provider
        // error (rate limit, 5xx). They do NOT end the in-flight turn — the
        // subsequent turn_end is still authoritative for completion.
        break;

      default:
        process.stderr.write(
          `[pi-mono] unknown event type: ${event.type}\n`
        );
    }
  }

  private handleMessageUpdate(event: PiRpcEvent): void {
    const msgEvent = event.assistantMessageEvent as
      | PiAssistantMessageEvent
      | undefined;
    if (!msgEvent) return;

    switch (msgEvent.type) {
      case "text_delta":
        if (msgEvent.delta) {
          this.eventHandler?.({
            type: "text_delta",
            text: msgEvent.delta,
          });
        }
        break;

      case "thinking_delta":
        if (msgEvent.delta) {
          this.eventHandler?.({
            type: "thinking_delta",
            text: msgEvent.delta,
          });
        }
        break;

      case "toolcall_start":
        if (msgEvent.partial?.content) {
          const block = msgEvent.partial.content[msgEvent.contentIndex ?? 0];
          if (block?.type === "toolCall" && block.name) {
            this.eventHandler?.({
              type: "tool_activity",
              name: block.name,
              status: "started",
              toolUseId: block.id,
              input: block.arguments,
            });
          }
        }
        break;

      case "toolcall_end":
        if (msgEvent.toolCall) {
          const tc = msgEvent.toolCall;
          this.eventHandler?.({
            type: "tool_use",
            callId: tc.id,
            name: tc.name,
            input: tc.arguments,
          });
        }
        break;

      case "done":
      case "error":
        // Handled by turn_end
        break;
    }
  }

  private handleToolStart(event: PiRpcEvent): void {
    const name = event.toolName as string;
    const toolCallId = event.toolCallId as string;
    this.eventHandler?.({
      type: "tool_activity",
      name,
      status: "started",
      toolUseId: toolCallId,
      input: event.args as Record<string, unknown> | undefined,
    });
  }

  private handleToolEnd(event: PiRpcEvent): void {
    const name = event.toolName as string;
    const toolCallId = event.toolCallId as string;
    const result = event.result as {
      content?: { type: string; text?: string }[];
    };
    const output = result?.content
      ?.filter((c) => c.type === "text")
      .map((c) => c.text || "")
      .join("") || "";

    this.eventHandler?.({
      type: "tool_activity",
      name,
      status: "completed",
      toolUseId: toolCallId,
    });

    this.eventHandler?.({
      type: "tool_result_display",
      toolUseId: toolCallId,
      name,
      output,
    });
  }

  private handleTurnEnd(event: PiRpcEvent): void {
    // Drop stray turn_end events that don't belong to an in-flight prompt.
    // This happens after abort() or when the subprocess emits a late
    // completion for a prompt that was superseded by another sendPrompt.
    const generation = this.activePromptGeneration;
    if (generation === 0) {
      process.stderr.write(
        "[pi-mono] dropping stray turn_end (no in-flight prompt)\n"
      );
      return;
    }
    const pending = this.pendingRequests.get(generation);
    if (!pending) {
      process.stderr.write(
        `[pi-mono] dropping stray turn_end for generation ${generation}\n`
      );
      this.activePromptGeneration = 0;
      return;
    }

    const message = event.message as PiAssistantMessage | undefined;

    // Extract text from content blocks
    let text = "";
    if (message?.content) {
      text = message.content
        .filter((b) => b.type === "text")
        .map((b) => b.text || "")
        .join("");
    }

    // Extract usage
    const usage = message?.usage;
    const costUsd = usage?.cost?.total ?? 0;

    const result: PromptResult = {
      text,
      sessionId: pending.sessionId,
      costUsd,
      inputTokens: usage?.input ?? 0,
      outputTokens: usage?.output ?? 0,
      cacheReadTokens: usage?.cacheRead ?? 0,
      cacheWriteTokens: usage?.cacheWrite ?? 0,
    };

    // Emit result event
    this.eventHandler?.({
      type: "result",
      ...result,
    });

    // Resolve + clear the in-flight state
    this.pendingRequests.delete(generation);
    this.activePromptGeneration = 0;
    pending.resolve(result);

    this.eventHandler = null;
    this.toolExecutor = null;
  }
}
