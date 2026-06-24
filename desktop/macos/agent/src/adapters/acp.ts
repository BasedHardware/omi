import { spawn, type ChildProcess } from "child_process";
import { createInterface, type Interface as ReadlineInterface } from "readline";
import { dirname, join } from "path";
import { fileURLToPath } from "url";
import { legacyPermissionPolicy } from "../legacy-permission-policy.js";
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

type ResponseHandler = {
  resolve: (result: unknown) => void;
  reject: (err: Error) => void;
};

export class AcpError extends Error {
  code: number;
  data?: unknown;

  constructor(message: string, code: number, data?: unknown) {
    super(message);
    this.code = code;
    this.data = data;
  }
}

export type AcpNotificationHandler = (method: string, params: unknown) => void;

export interface AcpRuntimeAdapterOptions {
  log?: (message: string) => void;
  nodeBin?: string;
  acpEntry?: string;
}

const __dirname = dirname(fileURLToPath(import.meta.url));

export class AcpRuntimeAdapter implements RuntimeAdapter {
  readonly adapterId = "acp";
  readonly capabilities: AdapterCapabilities = {
    resumeFidelity: "native",
    supportsNativeResume: true,
    supportsCancellation: true,
  };

  private process: ChildProcess | null = null;
  private readline: ReadlineInterface | null = null;
  private stdinWriter: ((line: string) => void) | null = null;
  private responseHandlers = new Map<number, ResponseHandler>();
  private notificationHandler: AcpNotificationHandler | null = null;
  private nextRpcId = 1;
  private readonly log: (message: string) => void;
  private readonly nodeBin: string;
  private readonly acpEntry: string;

  constructor(options: AcpRuntimeAdapterOptions = {}) {
    this.log = options.log ?? (() => {});
    this.nodeBin = options.nodeBin ?? process.execPath;
    this.acpEntry =
      options.acpEntry ?? join(__dirname, "..", "patched-acp-entry.mjs");
  }

  async start(): Promise<void> {
    if (this.process) return;

    const env = { ...process.env };
    delete env.ANTHROPIC_API_KEY;
    delete env.CLAUDE_CODE_USE_VERTEX;
    delete env.CLAUDECODE;
    env.NODE_NO_WARNINGS = "1";

    this.log(`Starting ACP subprocess [Claude OAuth]: ${this.nodeBin} ${this.acpEntry}`);

    this.process = spawn(this.nodeBin, [this.acpEntry], {
      env,
      stdio: ["pipe", "pipe", "pipe"],
    });

    if (!this.process.stdin || !this.process.stdout || !this.process.stderr) {
      throw new Error("Failed to create ACP subprocess pipes");
    }

    this.process.on("error", (err) => {
      this.log(`ACP process error: ${err.message}`);
      this.process = null;
      this.stdinWriter = null;
      this.readline = null;
      for (const [, handler] of this.responseHandlers) {
        handler.reject(new Error(`ACP process error: ${err.message}`));
      }
      this.responseHandlers.clear();
      this.onProcessExit?.();
    });

    this.stdinWriter = (line: string) => {
      try {
        this.process?.stdin?.write(line + "\n");
      } catch (err) {
        this.log(`Failed to write to ACP stdin: ${err}`);
      }
    };

    this.readline = createInterface({
      input: this.process.stdout,
      terminal: false,
    });

    this.readline.on("line", (line: string) => this.handleLine(line));

    this.process.stderr.on("data", (data: Buffer) => {
      const text = data.toString().trim();
      if (text) {
        this.log(`ACP stderr: ${text}`);
      }
    });

    this.process.on("exit", (code) => {
      this.log(`ACP process exited with code ${code}`);
      this.process = null;
      this.stdinWriter = null;
      this.readline = null;
      for (const [, handler] of this.responseHandlers) {
        handler.reject(new Error(`ACP process exited (code ${code})`));
      }
      this.responseHandlers.clear();
      this.onProcessExit?.();
    });
  }

  async stop(): Promise<void> {
    if (!this.process) return;
    const proc = this.process;
    const exitPromise = new Promise<void>((resolve) => {
      proc.once("exit", () => resolve());
    });
    proc.kill();
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
    const id = this.nextRpcId++;
    const msg = JSON.stringify({ jsonrpc: "2.0", id, method, params });

    return new Promise((resolve, reject) => {
      this.responseHandlers.set(id, { resolve, reject });
      if (this.stdinWriter) {
        this.stdinWriter(msg);
      } else {
        this.responseHandlers.delete(id);
        reject(new Error("ACP process stdin not available"));
      }
    });
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
      mcpServers: input.mcpServers ?? [],
      ...(input.systemPrompt ? { _meta: { systemPrompt: input.systemPrompt } } : {}),
    })) as { sessionId: string };

    if (input.model) {
      await this.request("session/set_model", {
        sessionId: result.sessionId,
        modelId: input.model,
      });
    }

    return this.binding(input, result.sessionId);
  }

  async resumeBinding(input: ResumeBindingInput): Promise<OpenedBinding> {
    await this.request("session/resume", {
      sessionId: input.adapterNativeSessionId,
      cwd: input.cwd,
      mcpServers: input.mcpServers ?? [],
    });

    if (input.model) {
      await this.request("session/set_model", {
        sessionId: input.adapterNativeSessionId,
        modelId: input.model,
      });
    }

    return this.binding(input, input.adapterNativeSessionId);
  }

  async executeAttempt(
    context: AdapterAttemptContext,
    sink: AdapterEventSink,
    signal: AbortSignal
  ): Promise<AdapterAttemptResult> {
    const adapterSessionId = context.binding.adapterNativeSessionId;
    let fullText = "";
    const pendingTools: string[] = [];
    const previousHandler = this.notificationHandler;
    this.notificationHandler = (method, params) => {
      previousHandler?.(method, params);
      if (signal.aborted || method !== "session/update") return;
      this.translateSessionUpdate(params as Record<string, unknown>, pendingTools, sink, (text) => {
        fullText += text;
      });
    };

    try {
      const result = (await this.request("session/prompt", {
        sessionId: adapterSessionId,
        prompt: context.prompt,
      })) as {
        usage?: {
          inputTokens?: number;
          outputTokens?: number;
          cachedReadTokens?: number | null;
          cachedWriteTokens?: number | null;
        };
        _meta?: { costUsd?: number };
      };

      return {
        text: fullText,
        sessionId: adapterSessionId,
        adapterSessionId,
        terminalStatus: signal.aborted ? "cancelled" : "succeeded",
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
    return {
      accepted: true,
      dispatchAttempted: true,
      adapterAcknowledged: false,
    };
  }

  async closeBinding(_binding: AdapterBindingHandle): Promise<void> {
    // ACP exposes no explicit close primitive in the compatibility protocol.
  }

  private binding(
    input: OpenBindingInput,
    adapterNativeSessionId: string
  ): AdapterBindingHandle {
    return {
      sessionId: input.sessionId,
      adapterId: this.adapterId,
      adapterNativeSessionId,
      resumeFidelity: "native",
      cwd: input.cwd,
      model: input.model,
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
      this.log(`Failed to parse ACP message: ${line.slice(0, 200)}`);
    }
  }

  private handleRequest(msg: Record<string, unknown>): void {
    const id = msg.id as number;
    const method = msg.method as string;

    if (method === "session/request_permission") {
      const params = msg.params as Record<string, unknown> | undefined;
      const options =
        (params?.options as Array<{ kind: string; optionId: string }>) ?? [];
      const decision = legacyPermissionPolicy.resolveAcpPermission({
        requestId: id,
        options,
      });
      this.log(`ACP permission resolved: ${JSON.stringify(decision.auditEvent)}`);
      this.stdinWriter?.(JSON.stringify({
        jsonrpc: "2.0",
        id,
        result: decision.acpResult,
      }));
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
    pendingTools: string[],
    sink: AdapterEventSink,
    onText: (text: string) => void
  ): void {
    const update = params.update as Record<string, unknown> | undefined;
    if (!update) {
      this.log(`session/update missing 'update' field: ${JSON.stringify(params).slice(0, 200)}`);
      return;
    }

    const sessionUpdate = update.sessionUpdate as string;
    switch (sessionUpdate) {
      case "agent_message_chunk": {
        const content = update.content as { type: string; text?: string } | undefined;
        const text = content?.text ?? "";
        if (!text) return;
        for (const name of pendingTools.splice(0)) {
          sink({ type: "tool_activity", name, status: "completed" });
        }
        onText(text);
        sink({ type: "text_delta", text });
        break;
      }

      case "agent_thought_chunk": {
        const content = update.content as { type: string; text?: string } | undefined;
        const text = content?.text ?? "";
        if (text) {
          sink({ type: "thinking_delta", text });
        }
        break;
      }

      case "tool_call": {
        const toolCallId = (update.toolCallId as string) ?? "";
        const title = this.toolTitle(update);
        const status = (update.status as string) ?? "pending";
        if (status === "pending" || status === "in_progress") {
          pendingTools.push(title);
          const rawInput = update.rawInput as Record<string, unknown> | undefined;
          sink({
            type: "tool_activity",
            name: title,
            status: "started",
            toolUseId: toolCallId,
            input: rawInput,
          });
        }
        break;
      }

      case "tool_call_update": {
        const toolCallId = (update.toolCallId as string) ?? "";
        const status = (update.status as string) ?? "";
        const title = this.toolTitle(update);
        if (status !== "completed" && status !== "failed" && status !== "cancelled") {
          return;
        }
        const idx = pendingTools.indexOf(title);
        if (idx >= 0) pendingTools.splice(idx, 1);
        sink({
          type: "tool_activity",
          name: title,
          status: "completed",
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
        break;
      }

      case "plan": {
        const entries = update.entries as Array<{ content: string }> | undefined;
        if (!Array.isArray(entries)) return;
        for (const entry of entries) {
          if (entry.content) {
            sink({ type: "thinking_delta", text: `${entry.content}\n` });
          }
        }
        break;
      }

      default:
        this.log(`Unknown session update type: ${sessionUpdate}`);
    }
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
