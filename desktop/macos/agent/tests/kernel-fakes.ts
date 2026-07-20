import type {
  AdapterArtifactReference,
  AdapterAttemptContext,
  AdapterAttemptResult,
  AdapterEventSink,
  AdapterCapabilities,
  CancelAttemptContext,
  CancelDispatchResult,
  OpenBindingInput,
  OpenedBinding,
  ResumeBindingInput,
  RuntimeAdapter,
} from "../src/adapters/interface.js";
import type { OutboundMessage } from "../src/protocol.js";
import { AdapterRegistry } from "../src/runtime/adapter-registry.js";
import { OmiArtifactStorage } from "../src/runtime/artifact-storage.js";
import { AgentRuntimeKernel, StaleAdapterBindingError } from "../src/runtime/kernel.js";
import { SqliteAgentStore } from "../src/runtime/sqlite-store.js";
import { readSessionExecutionProfile } from "../src/runtime/session-execution-profile.js";
import { writeFileSync } from "node:fs";
import { join } from "node:path";

export interface KernelHarness {
  store: SqliteAgentStore;
  adapter: FakeRuntimeAdapter;
  kernel: AgentRuntimeKernel;
}

export class FakeRuntimeAdapter implements RuntimeAdapter {
  readonly adapterId: string;
  readonly capabilities: AdapterCapabilities = {
    resumeFidelity: "native" as const,
    supportsNativeResume: true,
    supportsCancellation: true,
    acknowledgesCancellation: false,
    requiresPinnedWorker: false,
    supportsModelSwitching: true,
    supportsArtifactEmission: true,
    supportsTools: true,
    restartBehavior: "native_bindings_survive",
  };

  started = 0;
  stopped = 0;
  opened: OpenBindingInput[] = [];
  resumed: ResumeBindingInput[] = [];
  executed: AdapterAttemptContext[] = [];
  cancelled: CancelAttemptContext[] = [];
  sinks = new Map<string, AdapterEventSink>();
  failNextOpenError: unknown;
  failNextExecutionError: unknown;
  failNextResume = false;
  failNextExecutionAsStale = false;
  deferOnlyPromptIncludes: string | undefined;
  nextArtifacts: AdapterArtifactReference[] | undefined;
  nextText: string | undefined;
  writeFileOnExecute: { name: string; contents: string } | undefined;
  /** When set, FakeRuntimeAdapter reports this as the adapter-effective MCP set. */
  effectiveMcpServersOverride: Record<string, unknown>[] | null = null;
  pendingResult:
    | {
        promise: Promise<AdapterAttemptResult>;
        resolve: (result: AdapterAttemptResult) => void;
      }
    | undefined;

  private nextNativeSession = 1;

  constructor(adapterId = "fake") {
    this.adapterId = adapterId;
  }

  async start(): Promise<void> {
    this.started += 1;
  }

  async stop(): Promise<void> {
    this.stopped += 1;
  }

  async openBinding(input: OpenBindingInput): Promise<OpenedBinding> {
    this.opened.push(input);
    if (this.failNextOpenError) {
      const error = this.failNextOpenError;
      this.failNextOpenError = undefined;
      throw error;
    }
    return {
      sessionId: input.sessionId,
      adapterId: this.adapterId,
      adapterNativeSessionId: `native-${this.nextNativeSession++}`,
      resumeFidelity: "native",
      cwd: input.cwd,
      model: input.model,
    };
  }

  async resumeBinding(input: ResumeBindingInput): Promise<OpenedBinding> {
    this.resumed.push(input);
    if (this.failNextResume) {
      this.failNextResume = false;
      throw new StaleAdapterBindingError("native session missing");
    }
    return {
      sessionId: input.sessionId,
      adapterId: this.adapterId,
      adapterNativeSessionId: input.adapterNativeSessionId,
      resumeFidelity: "native",
      cwd: input.cwd,
      model: input.model,
    };
  }

  async executeAttempt(
    context: AdapterAttemptContext,
    sink: AdapterEventSink,
    _signal: AbortSignal
  ): Promise<AdapterAttemptResult> {
    this.executed.push(context);
    this.sinks.set(context.attemptId, sink);
    sink({
      type: "text_delta",
      text: `delta-${context.attemptId}`,
      adapterSessionId: context.binding.adapterNativeSessionId,
    });
    if (this.failNextExecutionAsStale) {
      this.failNextExecutionAsStale = false;
      throw new StaleAdapterBindingError("execute found stale binding");
    }
    if (this.failNextExecutionError) {
      const error = this.failNextExecutionError;
      this.failNextExecutionError = undefined;
      throw error;
    }
    const promptText = context.prompt
      .filter((block): block is Extract<(typeof context.prompt)[number], { type: "text" }> => block.type === "text")
      .map((block) => block.text)
      .join("\n");
    if (this.pendingResult && (!this.deferOnlyPromptIncludes || promptText.includes(this.deferOnlyPromptIncludes))) {
      return this.pendingResult.promise;
    }
    if (this.writeFileOnExecute) {
      writeFileSync(join(context.binding.cwd, this.writeFileOnExecute.name), this.writeFileOnExecute.contents);
      this.writeFileOnExecute = undefined;
    }
    const artifacts = this.nextArtifacts;
    this.nextArtifacts = undefined;
    const text = this.nextText ?? `done-${context.attemptId}`;
    this.nextText = undefined;
    return {
      text,
      adapterSessionId: context.binding.adapterNativeSessionId,
      terminalStatus: "succeeded",
      inputTokens: 1,
      outputTokens: 2,
      artifacts,
    };
  }

  async cancelAttempt(context: CancelAttemptContext): Promise<CancelDispatchResult> {
    this.cancelled.push(context);
    return {
      accepted: true,
      dispatchAttempted: true,
      adapterAcknowledged: false,
    };
  }

  effectiveMcpServers(_mcpServers: Record<string, unknown>[]): Record<string, unknown>[] {
    return this.effectiveMcpServersOverride ?? _mcpServers;
  }

  deferResult(): void {
    this.pendingResult = {} as typeof this.pendingResult;
    this.pendingResult!.promise = new Promise<AdapterAttemptResult>((resolve) => {
      this.pendingResult!.resolve = resolve;
    });
  }

  resolveDeferred(result: Partial<AdapterAttemptResult> = {}): void {
    if (!this.pendingResult) {
      throw new Error("No deferred result exists");
    }
    this.pendingResult.resolve({
      text: result.text ?? "cancelled text",
      adapterSessionId: result.adapterSessionId ?? "native-cancelled",
      terminalStatus: result.terminalStatus ?? "cancelled",
      ...result,
    });
    this.pendingResult = undefined;
  }

  emitLate(attemptId: string, event: OutboundMessage): void {
    const sink = this.sinks.get(attemptId);
    if (!sink) {
      throw new Error(`No sink for attempt ${attemptId}`);
    }
    sink(event);
  }
}

export function createKernelHarness(
  databasePath: string,
  adapterId = "fake",
  maxWorkers = 4,
  artifactStorage?: OmiArtifactStorage,
  recoverRunInput?: (adapterId: string) => {
    maxAttempts?: number;
    recoverAfterError?: (error: unknown) => Promise<boolean>;
  },
): KernelHarness {
  const store = new SqliteAgentStore({ databasePath, reconcileOnOpen: false });
  const adapter = new FakeRuntimeAdapter(adapterId);
  const registry = new AdapterRegistry();
  registry.register(adapterId, () => adapter, maxWorkers);
  const kernel = new AgentRuntimeKernel({
    store,
    registry,
    artifactStorage,
    recoverRunInput,
    toolCapabilityProfileForSession: (sessionId) => {
      const profile = readSessionExecutionProfile(store, sessionId);
      const adapterId = ["pi-mono", "acp", "hermes", "openclaw"].includes(profile.adapterId)
        ? profile.adapterId
        : "acp";
      return { ...profile, adapterId };
    },
  });
  return { store, adapter, kernel };
}

export const baseRunInput = {
  ownerId: "owner",
  surfaceKind: "task_chat",
  externalRefKind: "task",
  externalRefId: "task-1",
  defaultAdapterId: "fake",
  adapterId: "fake",
  clientId: "client",
  requestId: "request-1",
  prompt: "hello",
  cwd: "/tmp/work",
} as const;

export async function waitUntil(predicate: () => boolean, timeoutMs = 1000): Promise<void> {
  const started = Date.now();
  while (!predicate()) {
    if (Date.now() - started > timeoutMs) {
      throw new Error("Timed out waiting for predicate");
    }
    await new Promise((resolve) => setTimeout(resolve, 1));
  }
}
