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
  promptFlag: string;
  log?: (message: string) => void;
}

export class OneShotCliRuntimeAdapter implements RuntimeAdapter {
  readonly adapterId: ProductionAdapterId;
  readonly capabilities: AdapterCapabilities;

  private readonly envCommandName: string;
  private readonly commandOverride?: string;
  private readonly promptFlag: string;
  private readonly log: (message: string) => void;
  private activeProcess: ChildProcess | null = null;

  constructor(options: OneShotCliRuntimeAdapterOptions) {
    this.adapterId = options.adapterId;
    this.capabilities = adapterCapabilitiesFor(options.adapterId);
    this.envCommandName = options.envCommandName;
    this.commandOverride = options.command;
    this.promptFlag = options.promptFlag;
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
    const text = await this.runPrompt(context, signal);
    if (text) sink({ type: "text_delta", text });
    return {
      text,
      adapterSessionId: context.binding.adapterNativeSessionId,
      terminalStatus: signal.aborted ? "cancelled" : "succeeded",
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

  private async runPrompt(context: AdapterAttemptContext, signal: AbortSignal): Promise<string> {
    const command = this.command();
    const prompt = promptText(context.prompt);
    const args = [
      ...(context.model ? ["--model", shellQuote(context.model)] : []),
      this.promptFlag,
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
          settle(() => resolve(cleanStdout(stdout)));
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
}

function promptText(prompt: AdapterAttemptContext["prompt"]): string {
  return typeof prompt === "string" ? prompt : JSON.stringify(prompt);
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
