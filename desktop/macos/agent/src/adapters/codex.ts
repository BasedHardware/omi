import { spawn, type ChildProcess } from "child_process";
import { adapterCapabilitiesFor } from "./interface.js";
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

export interface CodexRuntimeAdapterOptions {
  command?: string;
  envCommandName?: string;
  log?: (message: string) => void;
}

const CODEX_ADAPTER_ENV_ALLOWLIST = [
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
  "CODEX_HOME",
  "CODEX_API_KEY",
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

const PROXY_ENV_KEYS = new Set([
  "HTTP_PROXY",
  "HTTPS_PROXY",
  "http_proxy",
  "https_proxy",
]);

export class CodexRuntimeAdapter implements RuntimeAdapter {
  readonly adapterId = "codex";
  readonly capabilities: AdapterCapabilities = adapterCapabilitiesFor("codex");

  private readonly commandOverride?: string;
  private readonly envCommandName: string;
  private readonly log: (message: string) => void;
  private activeProcess: ChildProcess | null = null;

  constructor(options: CodexRuntimeAdapterOptions = {}) {
    this.commandOverride = options.command;
    this.envCommandName = options.envCommandName ?? "OMI_CODEX_ADAPTER_COMMAND";
    this.log = options.log ?? (() => {});
  }

  async start(): Promise<void> {
    this.command();
  }

  async stop(): Promise<void> {
    if (!this.activeProcess) return;
    const proc = this.activeProcess;
    const exited = new Promise<void>((resolve) => proc.once("exit", () => resolve()));
    this.terminate(proc);
    await exited;
  }

  async openBinding(input: OpenBindingInput): Promise<OpenedBinding> {
    return this.binding(input);
  }

  async resumeBinding(input: ResumeBindingInput): Promise<OpenedBinding> {
    return this.binding(input, input.adapterNativeSessionId);
  }

  async executeAttempt(
    context: AdapterAttemptContext,
    sink: AdapterEventSink,
    signal: AbortSignal
  ): Promise<AdapterAttemptResult> {
    const result = await this.runCodexExec(context, signal);
    if (result.text) {
      sink({ type: "text_delta", text: result.text });
    }
    return {
      text: result.text,
      adapterSessionId: context.binding.adapterNativeSessionId,
      terminalStatus: signal.aborted ? "cancelled" : "succeeded",
      inputTokens: result.inputTokens,
      outputTokens: result.outputTokens,
      cacheReadTokens: result.cacheReadTokens,
      cacheWriteTokens: result.cacheWriteTokens,
    };
  }

  async cancelAttempt(_context: CancelAttemptContext): Promise<CancelDispatchResult> {
    if (!this.activeProcess) {
      return {
        accepted: true,
        dispatchAttempted: false,
        adapterAcknowledged: false,
        message: "No Codex process is active",
      };
    }
    this.terminate(this.activeProcess);
    return {
      accepted: true,
      dispatchAttempted: true,
      adapterAcknowledged: false,
    };
  }

  async closeBinding(_binding: AdapterBindingHandle): Promise<void> {
  }

  effectiveMcpServers(_mcpServers: Record<string, unknown>[]): Record<string, unknown>[] {
    return [];
  }

  private async runCodexExec(
    context: AdapterAttemptContext,
    signal: AbortSignal
  ): Promise<{
    text: string;
    inputTokens?: number;
    outputTokens?: number;
    cacheReadTokens?: number;
    cacheWriteTokens?: number;
  }> {
    const command = this.command();
    const args = [
      "exec",
      "--json",
      "--color",
      "never",
      "--skip-git-repo-check",
      "--cd",
      shellQuote(context.binding.cwd),
      "-",
    ].join(" ");
    const fullCommand = `${command} ${args}`;
    const prompt = promptText(context);

    return new Promise((resolve, reject) => {
      const proc = spawn(fullCommand, {
        shell: true,
        cwd: context.binding.cwd,
        env: this.codexEnv(),
        stdio: ["pipe", "pipe", "pipe"],
        detached: true,
      });
      this.activeProcess = proc;
      let stdout = "";
      let stderr = "";
      let settled = false;

      const settle = (fn: () => void): void => {
        if (settled) return;
        settled = true;
        if (this.activeProcess === proc) this.activeProcess = null;
        signal.removeEventListener("abort", abortHandler);
        fn();
      };

      const abortHandler = (): void => {
        this.terminate(proc);
        settle(() => reject(new Error("Codex command aborted")));
      };

      if (signal.aborted) {
        abortHandler();
        return;
      }
      signal.addEventListener("abort", abortHandler, { once: true });

      proc.stdout?.on("data", (data: Buffer) => {
        stdout += data.toString();
      });
      proc.stderr?.on("data", (data: Buffer) => {
        const text = data.toString();
        stderr += text;
        const trimmed = text.trim();
        if (trimmed) this.log(`codex stderr: ${trimmed}`);
      });
      proc.on("error", (error) => settle(() => reject(error)));
      proc.on("exit", (code) => {
        if (code === 0) {
          settle(() => resolve(resultFromJsonl(stdout)));
        } else {
          const diagnostic = stderr.trim() || stdout.trim();
          settle(() => reject(new Error(`Codex command exited with code ${code}: ${diagnostic}`)));
        }
      });

      proc.stdin?.end(prompt);
    });
  }

  private command(): string {
    const command = this.commandOverride ?? process.env[this.envCommandName];
    if (!command?.trim()) {
      throw new Error(`codex adapter requires ${this.envCommandName}`);
    }
    return command.trim();
  }

  private binding(input: OpenBindingInput, adapterNativeSessionId?: string): AdapterBindingHandle {
    return {
      bindingId: input.metadata?.bindingId as string | undefined,
      sessionId: input.sessionId,
      adapterId: this.adapterId,
      adapterNativeSessionId: adapterNativeSessionId ?? `codex:${input.sessionId}`,
      resumeFidelity: this.capabilities.resumeFidelity,
      cwd: input.cwd,
      model: input.model,
      metadata: {
        ...input.metadata,
        systemPrompt: input.systemPrompt,
      },
    };
  }

  private codexEnv(): NodeJS.ProcessEnv {
    const env: NodeJS.ProcessEnv = {
      OMI_ADAPTER_ID: this.adapterId,
    };
    for (const key of CODEX_ADAPTER_ENV_ALLOWLIST) {
      if (process.env[key] !== undefined) {
        env[key] = PROXY_ENV_KEYS.has(key)
          ? sanitizeProxyUrl(process.env[key]!)
          : process.env[key];
      }
    }
    return env;
  }

  private terminate(proc: ChildProcess): void {
    try {
      if (proc.pid) {
        process.kill(-proc.pid, "SIGTERM");
        return;
      }
    } catch {
      // Fall through to killing the shell process.
    }
    proc.kill("SIGTERM");
  }
}

function promptText(context: AdapterAttemptContext): string {
  const userPrompt = context.prompt
    .filter(
      (block): block is { type: "text"; text: string } =>
        block.type === "text" && typeof block.text === "string"
    )
    .map((block) => block.text)
    .join("\n");
  const systemPrompt = context.binding.metadata?.systemPrompt;
  if (typeof systemPrompt !== "string" || systemPrompt.trim() === "") {
    return userPrompt;
  }
  return [
    "Omi system instructions:",
    systemPrompt,
    "",
    "User task:",
    userPrompt,
  ].join("\n");
}

function resultFromJsonl(stdout: string): {
  text: string;
  inputTokens?: number;
  outputTokens?: number;
  cacheReadTokens?: number;
  cacheWriteTokens?: number;
} {
  const messages: string[] = [];
  let inputTokens: number | undefined;
  let outputTokens: number | undefined;
  let cacheReadTokens: number | undefined;
  let cacheWriteTokens: number | undefined;
  const errors: string[] = [];

  for (const line of stdout.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    const event = parseJsonObject(trimmed);
    if (!event) continue;
    if (event.type === "error") {
      const message = stringValue(event.message) ?? stringValue(event.error);
      if (message) errors.push(message);
      continue;
    }
    if (event.type === "item.completed" && isRecord(event.item)) {
      const item = event.item;
      if (item.type === "agent_message") {
        const text = stringValue(item.text);
        if (text) messages.push(text);
      }
      continue;
    }
    if ((event.type === "turn.completed" || event.type === "turn.failed") && isRecord(event.usage)) {
      inputTokens = numberValue(event.usage.input_tokens ?? event.usage.input);
      outputTokens = numberValue(event.usage.output_tokens ?? event.usage.output);
      cacheReadTokens = numberValue(event.usage.cached_input_tokens ?? event.usage.cache_read_tokens);
      cacheWriteTokens = numberValue(event.usage.cache_write_tokens);
    }
    if (event.type === "turn.failed") {
      const message = stringValue(event.message) ?? stringValue(event.error);
      if (message) errors.push(message);
    }
  }

  if (messages.length > 0) {
    return {
      text: messages.join("\n"),
      inputTokens,
      outputTokens,
      cacheReadTokens,
      cacheWriteTokens,
    };
  }
  if (errors.length > 0) {
    throw new Error(`Codex failed: ${errors.join("; ")}`);
  }
  return { text: cleanStdout(stdout), inputTokens, outputTokens, cacheReadTokens, cacheWriteTokens };
}

function shellQuote(value: string): string {
  return `'${value.replaceAll("'", "'\\''")}'`;
}

function cleanStdout(stdout: string): string {
  return stdout
    .split("\n")
    .filter((line) => !/^\d{4}-\d{2}-\d{2}T.*\b(?:TRACE|DEBUG|INFO|WARN|ERROR)\b/.test(line))
    .join("\n")
    .trim();
}

function parseJsonObject(text: string): Record<string, unknown> | undefined {
  try {
    const parsed = JSON.parse(text) as unknown;
    return isRecord(parsed) ? parsed : undefined;
  } catch {
    return undefined;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function numberValue(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function stringValue(value: unknown): string | undefined {
  return typeof value === "string" ? value : undefined;
}

function sanitizeProxyUrl(value: string): string {
  try {
    const url = new URL(value);
    url.username = "";
    url.password = "";
    return url.toString();
  } catch {
    return value;
  }
}
