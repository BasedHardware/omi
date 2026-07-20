import { spawn, type ChildProcess } from "child_process";
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

export interface OneShotCliRuntimeAdapterOptions {
  adapterId: ProductionAdapterId;
  envCommandName: string;
  command?: string;
  fixedArgs?: string[];
  /** Flag placed before the prompt (e.g. "--prompt"). Omit to pass the prompt as the trailing positional arg (e.g. `codex exec "<prompt>"`). */
  promptFlag?: string;
  sessionKeyFlag?: string;
  parseJsonPayload?: boolean;
  log?: (message: string) => void;
}

export class OneShotCliRuntimeAdapter implements RuntimeAdapter {
  readonly adapterId: ProductionAdapterId;
  readonly capabilities: AdapterCapabilities;

  private readonly envCommandName: string;
  private readonly commandOverride?: string;
  private readonly fixedArgs: string[];
  private readonly promptFlag?: string;
  private readonly sessionKeyFlag?: string;
  private readonly parseJsonPayload: boolean;
  private readonly log: (message: string) => void;
  private activeProcess: ChildProcess | null = null;

  constructor(options: OneShotCliRuntimeAdapterOptions) {
    this.adapterId = options.adapterId;
    this.capabilities = adapterCapabilitiesFor(options.adapterId);
    this.envCommandName = options.envCommandName;
    this.commandOverride = options.command;
    this.fixedArgs = options.fixedArgs ?? [];
    this.promptFlag = options.promptFlag;
    this.sessionKeyFlag = options.sessionKeyFlag;
    this.parseJsonPayload = options.parseJsonPayload ?? false;
    this.log = options.log ?? (() => {});
  }

  async start(): Promise<void> {
    this.command();
  }

  async stop(): Promise<void> {
    if (!this.activeProcess) return;
    const proc = this.activeProcess;
    const exited = new Promise<void>((resolve) => proc.once("exit", () => resolve()));
    proc.kill("SIGTERM");
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
    const result = await this.runPrompt(context, signal);
    const text = result.text;
    if (text) sink({ type: "text_delta", text });
    return {
      text,
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
        message: `No ${this.adapterId} process is active`,
      };
    }
    this.activeProcess.kill("SIGTERM");
    return {
      accepted: true,
      dispatchAttempted: true,
      adapterAcknowledged: false,
    };
  }

  async closeBinding(_binding: AdapterBindingHandle): Promise<void> {
  }

  private async runPrompt(
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
    const prompt = promptText(context.prompt);
    const args = [
      ...this.fixedArgs,
      ...(this.sessionKeyFlag ? [this.sessionKeyFlag, shellQuote(this.sessionKey(context))] : []),
      ...(context.model ? ["--model", shellQuote(context.model)] : []),
      ...(this.promptFlag ? [this.promptFlag] : []),
      shellQuote(prompt),
    ].join(" ");
    const fullCommand = `${command} ${args}`.trim();

    return new Promise((resolve, reject) => {
      const proc = spawn(fullCommand, {
        shell: true,
        cwd: context.binding.cwd,
        env: {
          ...process.env,
          OMI_ADAPTER_ID: this.adapterId,
        },
        stdio: ["ignore", "pipe", "pipe"],
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
        proc.kill("SIGTERM");
        settle(() => reject(new Error(`${this.adapterId} command aborted`)));
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
        if (trimmed) this.log(`${this.adapterId} stderr: ${trimmed}`);
      });
      proc.on("error", (error) => settle(() => reject(error)));
      proc.on("exit", (code) => {
        if (code === 0) {
          settle(() => resolve(this.resultFromStdout(stdout)));
        } else {
          settle(() => reject(new Error(`${this.adapterId} command exited with code ${code}: ${stderr.trim()}`)));
        }
      });
    });
  }

  private command(): string {
    const command = this.commandOverride ?? process.env[this.envCommandName];
    if (!command?.trim()) {
      throw new Error(`${this.adapterId} adapter requires ${this.envCommandName}`);
    }
    return command.trim();
  }

  private binding(input: OpenBindingInput, adapterNativeSessionId?: string): AdapterBindingHandle {
    return {
      bindingId: input.metadata?.bindingId as string | undefined,
      sessionId: input.sessionId,
      adapterId: this.adapterId,
      adapterNativeSessionId: adapterNativeSessionId ?? `${this.adapterId}:${input.sessionId}`,
      resumeFidelity: this.capabilities.resumeFidelity,
      cwd: input.cwd,
      model: input.model,
      metadata: input.metadata,
    };
  }

  private sessionKey(context: AdapterAttemptContext): string {
    return context.binding.adapterNativeSessionId || `${this.adapterId}:${context.sessionId}`;
  }

  private resultFromStdout(stdout: string): {
    text: string;
    inputTokens?: number;
    outputTokens?: number;
    cacheReadTokens?: number;
    cacheWriteTokens?: number;
  } {
    const clean = cleanStdout(stdout);
    if (!this.parseJsonPayload) return { text: clean };
    const parsed = parseJsonObject(clean);
    const payloads = Array.isArray(parsed?.payloads) ? parsed.payloads : [];
    const text = payloads
      .map((payload) => isRecord(payload) && typeof payload.text === "string" ? payload.text : "")
      .filter(Boolean)
      .join("\n")
      || clean;
    const usage = isRecord(parsed?.meta)
      && isRecord(parsed.meta.agentMeta)
      && isRecord(parsed.meta.agentMeta.usage)
      ? parsed.meta.agentMeta.usage
      : undefined;
    const lastCallUsage = isRecord(parsed?.meta)
      && isRecord(parsed.meta.agentMeta)
      && isRecord(parsed.meta.agentMeta.lastCallUsage)
      ? parsed.meta.agentMeta.lastCallUsage
      : undefined;
    return {
      text,
      inputTokens: numberValue(lastCallUsage?.input ?? usage?.input),
      outputTokens: numberValue(lastCallUsage?.output ?? usage?.output),
      cacheReadTokens: numberValue(lastCallUsage?.cacheRead),
      cacheWriteTokens: numberValue(lastCallUsage?.cacheWrite),
    };
  }
}

function promptText(prompt: AdapterAttemptContext["prompt"]): string {
  if (typeof prompt === "string") return prompt;
  return prompt
    .filter(
      (block): block is { type: "text"; text: string } =>
        block.type === "text" && typeof block.text === "string",
    )
    .map((block) => block.text)
    .join("\n");
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
