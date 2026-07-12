/**
 * ACP Bridge — translates between OMI's JSON-lines protocol and the
 * Agent Client Protocol (ACP) used by claude-code-acp.
 *
 * THIS IS THE DESKTOP APP FLOW. It is unrelated to the VM/agent-cloud flow
 * (agent-cloud/agent.mjs), which runs Claude Code SDK on a remote VM for
 * the Omi Agent feature. This bridge runs locally on the user's Mac.
 *
 * Session lifecycle:
 * 1. resolve_surface_session pins an immutable kernel-owned execution profile.
 * 2. warmup validates that session/profile generation without configuring it.
 * 3. query names only the session and user input; the kernel supplies provider,
 *    model, working directory, system policy, and the admitted context snapshot.
 *
 * Token counts:
 * session/prompt drives one or more internal Anthropic API calls (initial
 * response + one per tool-use round). The usage returned in the result is
 * the AGGREGATE across all those rounds. There are no separate sub-agents.
 *
 * Implementation flow:
 * 1. Create Unix socket server for omi-tools relay
 * 2. Spawn claude-code-acp as subprocess (JSON-RPC over stdio)
 * 3. Initialize ACP connection
 * 4. Handle auth if required (forward to Swift, wait for user action)
 * 5. On query: reuse or create session, send prompt, translate notifications → JSON-lines
 * 6. On interrupt: cancel the session
 */

import { createInterface } from "readline";
import { dirname, join } from "path";
import { fileURLToPath } from "url";
import { createServer as createNetServer, type Socket } from "net";
import { homedir, tmpdir } from "os";
import { unlinkSync, appendFileSync } from "fs";
import type {
  InboundMessage,
  ControlToolRequestMessage,
  DirectControlToolRequestMessage,
  ExternalSurfaceRunBeginMessage,
  ExternalSurfaceToolInvokeMessage,
  ExternalSurfaceRunCompleteMessage,
  OutboundMessage,
  OutboundMessageDraft,
  QueryMessage,
  WarmupMessage,
  AuthorizedToolExecutionResultMessage,
  ConfigureDefaultExecutionProfileMessage,
  ResolveSurfaceSessionMessage,
  MigrateSessionExecutionProfileMessage,
  ContextSourceUpdateMessage,
  ImportLegacyMainChatSessionsMessage,
  JournalRecordTurnMessage,
  JournalUpdateTurnMessage,
  JournalListTurnsMessage,
  JournalClearTurnsMessage,
  EnsureAgentSpawnJournalMessage,
  JournalBackendSyncResultMessage,
  JournalBackendDeleteResultMessage,
  JournalBackendReconcileResultMessage,
  RefreshTokenMessage,
  AuthMethod,
} from "./protocol.js";
import { PROTOCOL_VERSION, ensureOutboundProtocolVersion } from "./protocol.js";
import { startOAuthFlow, type OAuthFlowHandle } from "./oauth-flow.js";
import { isProductionAdapterId, type PromptBlock, type RuntimeAdapter } from "./adapters/interface.js";
import { detectImageMimeType } from "./mime-detect.js";
import { AcpError, AcpRuntimeAdapter, isRecoverableAcpAuthError } from "./adapters/acp.js";
import { AdapterRegistry } from "./runtime/adapter-registry.js";
import { JsonlTransport, type McpServerBuildContext } from "./runtime/jsonl-transport.js";
import { AgentRuntimeKernel } from "./runtime/kernel.js";
import {
  adapterActivationError,
  adapterIdForHarnessMode,
  ensureRegisteredAdapter,
} from "./runtime/adapter-selection.js";
import {
  SWIFT_ADVERTISED_AGENT_CONTROL_TOOL_NAMES,
  handleAgentControlToolCall,
  isAgentControlToolName,
  withMergedOwnerGuard,
  DEFAULT_LOCAL_OWNER_ID,
  type AgentControlToolContext,
} from "./runtime/control-tools.js";
import { SqliteAgentStore } from "./runtime/sqlite-store.js";
import { OmiArtifactStorage, defaultArtifactRoot } from "./runtime/artifact-storage.js";
import { configuredPiMonoMaxWorkers } from "./runtime/worker-pool.js";
import { failureFromError } from "./runtime/failures.js";
import { providerBoundaryForAdapter } from "./runtime/execution-policy.js";
import { executionRoleForSurface } from "./runtime/execution-policy.js";
import type { AuthorizedRunToolInvocation } from "./runtime/run-tool-capability.js";
import {
  attachAgentSpawnJournalReceipt,
  parseAgentSpawnProducerJournalDescriptor,
} from "./runtime/agent-spawn-journal.js";
import { LEGACY_MAIN_CHAT_SESSION_COMPATIBILITY } from "./runtime/surface-session.js";
import {
  ackBackendConversationDeleteOutbox,
  ackBackendTurnOutboxWithWakes,
  applyBackendReconcilePage,
  beginBackendReconcilesForOwner,
  clearJournalConversation,
  drainBackendConversationDeleteOutbox,
  drainBackendTurnOutbox,
  failBackendConversationDeleteOutbox,
  failBackendReconcile,
  failBackendTurnOutbox,
  journalTurnChangedWakes,
  listJournalTurns,
  recordJournalTurn,
  settleClearedBackendTurnClaim,
  updateJournalTurn,
} from "./runtime/conversation-journal.js";
import type {
  ConversationContentBlock,
  ConversationResource,
  ConversationTurn,
  ConversationTurnOrigin,
  ConversationTurnStatus,
} from "./runtime/types.js";

const __dirname = dirname(fileURLToPath(import.meta.url));

// Resolve paths to bundled tools
const playwrightCli = join(
  __dirname,
  "..",
  "node_modules",
  "@playwright",
  "mcp",
  "cli.js"
);

const omiToolsStdioScript = join(__dirname, "omi-tools-stdio.js");

// --- Helpers ---

function send(msg: OutboundMessageDraft): void {
  try {
    process.stdout.write(JSON.stringify(ensureOutboundProtocolVersion(msg)) + "\n");
  } catch (err) {
    logErr(`Failed to write to stdout: ${err}`);
  }
}

function runtimeErrorEnvelope(error: unknown): { message: string; failure: ReturnType<typeof failureFromError> } {
  const failure = failureFromError(error, {
    code: "runtime_error",
    source: "runtime",
    userMessage: error instanceof Error ? error.message : String(error),
  });
  return { message: failure.userMessage, failure };
}

function logErr(msg: string): void {
  // Wrap to swallow EPIPE/ERR_STREAM_DESTROYED so a closed parent pipe
  // doesn't bubble out as an uncaughtException and re-enter our handlers.
  try {
    process.stderr.write(`[agent] ${msg}\n`);
  } catch {
    // ignore — parent pipe is gone; we'll exit shortly anyway
  }
}

function agentStateDir(): string {
  return process.env.OMI_AGENT_STATE_DIR ?? join(homedir(), "Library", "Application Support", "Omi", "agent");
}

function agentArtifactsDir(): string {
  return defaultArtifactRoot(process.env);
}

// --- OMI tools relay via Unix socket ---

let omiToolsPipePath = "";
let omiToolsClients: Socket[] = [];
let agentControlToolContext: AgentControlToolContext | undefined;
let runtimeKernel: AgentRuntimeKernel | undefined;
let currentOwnerId = DEFAULT_LOCAL_OWNER_ID;
const capabilityRejectionCounts = new Map<string, number>();

function resolveActiveOwner(requestedOwnerId: string | undefined): string {
  const requested = requestedOwnerId?.trim();
  if (requested && requested !== currentOwnerId) {
    throw new Error("owner_mismatch: request owner does not match the active runtime owner");
  }
  return currentOwnerId;
}

function journalOrigin(raw: unknown): ConversationTurnOrigin {
  switch (raw) {
    case "typed_chat":
    case "floating_chat":
    case "realtime_voice":
    case "agent_runtime":
    case "notification":
    case "tool_runtime":
    case "task_chat":
    case "workstream":
    case "swift_backfill":
    case "legacy":
      return raw;
    case "proactive_notification":
      return "notification";
    case "floating_spawn":
      return "agent_runtime";
    case "floating_provider_unavailable":
    case "floating_invalid_brief":
      return "floating_chat";
    default:
      throw new Error("Unknown journal turn origin");
  }
}

// Pending Swift execution is keyed only by the canonical run capability tuple.
const pendingToolCalls = new Map<
  string,
  {
    client: Socket;
    callId: string;
    invocation: AuthorizedRunToolInvocation;
    timeout: ReturnType<typeof setTimeout>;
  }
>();

const pendingExternalToolCalls = new Map<
  string,
  {
    request: ExternalSurfaceToolInvokeMessage;
    invocation: AuthorizedRunToolInvocation;
    timeout: ReturnType<typeof setTimeout>;
  }
>();

function toolCallPendingKey(input: {
  invocationId: string;
}): string {
  return input.invocationId;
}

/** Resolve a pending tool call with a result from Swift */
function resolveToolCall(msg: AuthorizedToolExecutionResultMessage): void {
  const key = toolCallPendingKey(msg);
  const pending = pendingToolCalls.get(key);
  if (pending) {
    try {
      runtimeKernel?.completeRunToolInvocation({
        invocationId: msg.invocationId,
        ownerId: msg.ownerId,
        sessionId: msg.sessionId,
        runId: msg.runId,
        attemptId: msg.attemptId,
        profileGeneration: msg.profileGeneration,
        manifestVersion: msg.manifestVersion,
        manifestDigest: msg.manifestDigest,
        daemonBootEpoch: msg.daemonBootEpoch,
        executionGeneration: msg.executionGeneration,
        inputHash: msg.inputHash,
        capabilityRef: pending.invocation.capabilityRef,
        outcome: msg.outcome,
        result: msg.result,
      });
      pendingToolCalls.delete(key);
      clearTimeout(pending.timeout);
      pending.client.write(JSON.stringify({ type: "tool_result", callId: pending.callId, result: msg.result }) + "\n");
    } catch (error) {
      logErr(`Rejected authorized tool execution result invocation=${msg.invocationId}: ${error}`);
    }
    return;
  }
  const external = pendingExternalToolCalls.get(key);
  if (external) {
    try {
      runtimeKernel?.completeRunToolInvocation({
        invocationId: msg.invocationId,
        ownerId: msg.ownerId,
        sessionId: msg.sessionId,
        runId: msg.runId,
        attemptId: msg.attemptId,
        profileGeneration: msg.profileGeneration,
        manifestVersion: msg.manifestVersion,
        manifestDigest: msg.manifestDigest,
        daemonBootEpoch: msg.daemonBootEpoch,
        executionGeneration: msg.executionGeneration,
        inputHash: msg.inputHash,
        capabilityRef: external.invocation.capabilityRef,
        outcome: msg.outcome,
        result: msg.result,
      });
      pendingExternalToolCalls.delete(key);
      clearTimeout(external.timeout);
      send({
        type: "external_surface_tool_result",
        requestId: external.request.requestId,
        clientId: external.request.clientId,
        ownerId: external.invocation.ownerId,
        sessionId: external.invocation.sessionId,
        runId: external.invocation.runId,
        attemptId: external.invocation.attemptId,
        invocationId: external.invocation.invocationId,
        ok: true,
        result: msg.result,
      });
    } catch (error) {
      logErr(`Rejected external authorized tool result invocation=${msg.invocationId}: ${error}`);
    }
    return;
  }
  logErr(`Warning: no pending tool invocation for invocation=${msg.invocationId}`);
}

function externalAuthorityError(error: unknown, fallbackCode: string): { code: string; message: string } {
  const rawCode = error && typeof error === "object" && "code" in error
    ? String((error as { code: unknown }).code)
    : fallbackCode;
  const code = /^[a-z0-9_]{1,64}$/.test(rawCode) ? rawCode : fallbackCode;
  return {
    code,
    message: error instanceof Error ? error.message : "External surface authority rejected the request",
  };
}

function registerPendingExternalToolCall(
  request: ExternalSurfaceToolInvokeMessage,
  invocation: AuthorizedRunToolInvocation,
): { request: ExternalSurfaceToolInvokeMessage; invocation: AuthorizedRunToolInvocation; timeout: ReturnType<typeof setTimeout> } {
  const key = toolCallPendingKey(invocation);
  if (pendingExternalToolCalls.has(key) || pendingToolCalls.has(key)) {
    throw Object.assign(new Error("Duplicate tool invocation"), { code: "invocation_replayed" });
  }
  const pending = {
    request,
    invocation,
    timeout: setTimeout(() => {
      const active = pendingExternalToolCalls.get(key);
      if (!active) return;
      pendingExternalToolCalls.delete(key);
      try {
        runtimeKernel?.markRunToolInvocationOutcomeUnknown(active.invocation, "swift_tool_timeout");
      } catch (error) {
        logErr(`Failed to mark external invocation outcome unknown: ${error}`);
      }
      send({
        type: "external_surface_tool_result",
        requestId: active.request.requestId,
        clientId: active.request.clientId,
        ownerId: active.invocation.ownerId,
        sessionId: active.invocation.sessionId,
        runId: active.invocation.runId,
        attemptId: active.invocation.attemptId,
        invocationId: active.invocation.invocationId,
        ok: false,
        error: { code: "swift_tool_timeout", message: "Timed out waiting for the authorized tool executor" },
      });
    }, 120_000),
  };
  pendingExternalToolCalls.set(key, pending);
  return pending;
}

function cancelPendingExternalToolCallsForAttempt(input: {
  ownerId: string;
  runId: string;
  attemptId: string;
  errorCode: string;
}): void {
  for (const [key, pending] of pendingExternalToolCalls) {
    if (
      pending.invocation.ownerId !== input.ownerId
      || pending.invocation.runId !== input.runId
      || pending.invocation.attemptId !== input.attemptId
    ) continue;
    pendingExternalToolCalls.delete(key);
    clearTimeout(pending.timeout);
    try {
      runtimeKernel?.markRunToolInvocationOutcomeUnknown(pending.invocation, input.errorCode);
    } catch (error) {
      logErr(`Failed to terminalize external invocation: ${error}`);
    }
    send({
      type: "external_surface_tool_result",
      requestId: pending.request.requestId,
      clientId: pending.request.clientId,
      ownerId: pending.invocation.ownerId,
      sessionId: pending.invocation.sessionId,
      runId: pending.invocation.runId,
      attemptId: pending.invocation.attemptId,
      invocationId: pending.invocation.invocationId,
      ok: false,
      error: { code: input.errorCode, message: "External surface run terminated during tool execution" },
    });
  }
}

function rejectPendingToolCallsForOwner(ownerId: string): void {
  for (const [key, pending] of pendingToolCalls) {
    if (pending.invocation.ownerId !== ownerId) continue;
    pendingToolCalls.delete(key);
    clearTimeout(pending.timeout);
    try {
      runtimeKernel?.markRunToolInvocationOutcomeUnknown(pending.invocation, "owner_changed");
    } catch (error) {
      logErr(`Failed to mark owner-switched relay invocation outcome unknown: ${error}`);
    }
    writeRelayToolResult(
      pending.client,
      pending.callId,
      relayError("owner_changed", "Active owner changed during tool execution"),
    );
  }
  for (const [key, pending] of pendingExternalToolCalls) {
    if (pending.invocation.ownerId !== ownerId) continue;
    pendingExternalToolCalls.delete(key);
    clearTimeout(pending.timeout);
    try {
      runtimeKernel?.markRunToolInvocationOutcomeUnknown(pending.invocation, "owner_changed");
    } catch (error) {
      logErr(`Failed to mark owner-switched external invocation outcome unknown: ${error}`);
    }
    send({
      type: "external_surface_tool_result",
      requestId: pending.request.requestId,
      clientId: pending.request.clientId,
      ownerId: pending.invocation.ownerId,
      sessionId: pending.invocation.sessionId,
      runId: pending.invocation.runId,
      attemptId: pending.invocation.attemptId,
      invocationId: pending.invocation.invocationId,
      ok: false,
      error: { code: "owner_changed", message: "Active owner changed during tool execution" },
    });
  }
}

function resolveClientToolCalls(client: Socket, result: string): void {
  for (const [key, pending] of pendingToolCalls) {
    if (pending.client !== client) continue;
    pendingToolCalls.delete(key);
    clearTimeout(pending.timeout);
    try {
      runtimeKernel?.markRunToolInvocationOutcomeUnknown(pending.invocation, "relay_client_disconnected");
    } catch (error) {
      logErr(`Failed to mark disconnected tool invocation outcome unknown: ${error}`);
    }
    try {
      client.write(JSON.stringify({ type: "tool_result", callId: pending.callId, result }) + "\n");
    } catch {
      // The relay client is already closing.
    }
  }
}

function relayError(code: string, message: string): string {
  return JSON.stringify({ ok: false, error: { code, message } });
}

function writeRelayToolResult(client: Socket, callId: string, result: string): void {
  try {
    client.write(JSON.stringify({ type: "tool_result", callId, result }) + "\n");
  } catch (error) {
    logErr(`Failed to write relay tool result: ${error}`);
  }
}

/** Start Unix socket server for omi-tools stdio processes to connect to */
function startOmiToolsRelay(): Promise<string> {
  const pipePath = join(tmpdir(), `omi-tools-${process.pid}.sock`);

  // Clean up any stale socket
  try {
    unlinkSync(pipePath);
  } catch {
    // ignore
  }

  return new Promise((resolve, reject) => {
    const server = createNetServer((client: Socket) => {
      omiToolsClients.push(client);
      let buffer = "";

      client.on("data", (data: Buffer) => {
        buffer += data.toString();
        let newlineIdx;
        while ((newlineIdx = buffer.indexOf("\n")) >= 0) {
          const line = buffer.slice(0, newlineIdx);
          buffer = buffer.slice(newlineIdx + 1);
          if (!line.trim()) continue;

          try {
            const msg = JSON.parse(line) as {
              type: string;
              callId: string;
              invocationId?: string;
              name: string;
              input: Record<string, unknown>;
              capabilityRef?: string;
            };

            if (msg.type === "tool_use") {
              const capabilityRef = msg.capabilityRef?.trim();
              const invocationId = msg.invocationId?.trim() || msg.callId?.trim();
              if (!runtimeKernel || !capabilityRef || !invocationId) {
                writeRelayToolResult(
                  client,
                  msg.callId,
                  relayError("missing_run_capability", "Tool relay requires an active run capability"),
                );
                continue;
              }
              let authorized;
              let routedProposal;
              try {
                routedProposal = runtimeKernel.routeRelayedRunToolProposal({
                  capabilityRef,
                  toolName: msg.name,
                  toolInput: msg.input ?? {},
                  activeOwnerId: currentOwnerId,
                });
                authorized = runtimeKernel.authorizeRelayedRunToolInvocation({
                  capabilityRef,
                  invocationId,
                  toolName: routedProposal.toolName,
                  toolInput: routedProposal.toolInput,
                  activeOwnerId: currentOwnerId,
                });
              } catch (error) {
                const code = error && typeof error === "object" && "code" in error
                  ? String((error as { code: unknown }).code)
                  : "capability_rejected";
                writeRelayToolResult(
                  client,
                  msg.callId,
                  relayError(code, error instanceof Error ? error.message : "Tool capability rejected"),
                );
                continue;
              }

              if (isAgentControlToolName(authorized.canonicalToolName)) {
                void (async () => {
                  let result: string;
                  let outcome: "succeeded" | "failed" = "succeeded";
                  try {
                    runtimeKernel?.markRunToolInvocationDispatched(authorized);
                    if (!agentControlToolContext) {
                      throw new Error("Agent runtime kernel is not ready");
                    }
                    const activeSession = requireControlSessionPolicy(
                      authorized.sessionId,
                      authorized.ownerId,
                    );
                    const preparedSpawn = authorized.canonicalToolName === "spawn_agent"
                      ? runtimeKernel?.prepareAuthorizedSpawnAgentControlInvocation({
                          ownerId: authorized.ownerId,
                          sessionId: authorized.sessionId,
                          runId: authorized.runId,
                          attemptId: authorized.attemptId,
                          invocationId: authorized.invocationId,
                          surfaceKind: authorized.surfaceKind,
                          toolInput: routedProposal.toolInput,
                        })
                      : undefined;
                    result = await handleAgentControlToolCall(
                      {
                        ...agentControlToolContext,
                        callerSessionId: authorized.sessionId,
                        executionRole: activeSession.executionRole,
                        providerBoundary: activeSession.providerBoundary,
                        defaultAdapterId: activeSession.defaultAdapterId,
                        authorizedProducerJournal: preparedSpawn?.producerJournal,
                        authorizedCallerRunId: preparedSpawn?.parentRunId,
                        getOwnerId: () => authorized.ownerId,
                      },
                      authorized.canonicalToolName,
                      preparedSpawn?.toolInput ?? routedProposal.toolInput,
                    );
                  } catch (error) {
                    outcome = "failed";
                    result = relayError(
                      error instanceof Error && error.message === "Agent runtime kernel is not ready"
                        ? "runtime_not_ready"
                        : "control_tool_failed",
                      error instanceof Error ? error.message : String(error),
                    );
                  }
                  try {
                    runtimeKernel?.completeRunToolInvocation({
                      invocationId: authorized.invocationId,
                      ownerId: authorized.ownerId,
                      sessionId: authorized.sessionId,
                      runId: authorized.runId,
                      attemptId: authorized.attemptId,
                      profileGeneration: authorized.profileGeneration,
                      manifestVersion: authorized.manifestVersion,
                      manifestDigest: authorized.manifestDigest,
                      daemonBootEpoch: authorized.daemonBootEpoch,
                      executionGeneration: authorized.executionGeneration,
                      inputHash: authorized.inputHash,
                      capabilityRef: authorized.capabilityRef,
                      outcome,
                      result,
                    });
                  } catch (error) {
                    logErr(`Failed to complete runtime control invocation ${authorized.invocationId}: ${error}`);
                  }
                  writeRelayToolResult(client, msg.callId, result);
                })();
                continue;
              }

              const callId = msg.callId;
              const pendingKey = toolCallPendingKey({
                invocationId,
              });
              if (pendingToolCalls.has(pendingKey)) {
                writeRelayToolResult(client, callId, relayError("invocation_replayed", "Duplicate tool invocation"));
                continue;
              }

              const timeout = setTimeout(() => {
                const pending = pendingToolCalls.get(pendingKey);
                if (!pending) return;
                pendingToolCalls.delete(pendingKey);
                try {
                  runtimeKernel?.markRunToolInvocationOutcomeUnknown(pending.invocation, "swift_tool_timeout");
                } catch (error) {
                  logErr(`Failed to mark timed-out tool invocation outcome unknown: ${error}`);
                }
                writeRelayToolResult(
                  pending.client,
                  pending.callId,
                  relayError("swift_tool_timeout", "Timed out waiting for the Swift tool executor"),
                );
              }, 120_000);
              pendingToolCalls.set(pendingKey, {
                client,
                callId,
                invocation: authorized,
                timeout,
              });
              runtimeKernel.markRunToolInvocationDispatched(authorized);
              send({
                type: "authorized_tool_execution",
                invocationId,
                ownerId: authorized.ownerId,
                sessionId: authorized.sessionId,
                runId: authorized.runId,
                attemptId: authorized.attemptId,
                profileGeneration: authorized.profileGeneration,
                manifestVersion: authorized.manifestVersion,
                manifestDigest: authorized.manifestDigest,
                daemonBootEpoch: authorized.daemonBootEpoch,
                executionGeneration: authorized.executionGeneration,
                toolName: authorized.canonicalToolName,
                input: routedProposal.toolInput,
                inputHash: authorized.inputHash,
                effectClass: authorized.effectClass,
                retryPolicy: authorized.retryPolicy,
                surfaceKind: authorized.surfaceKind,
                externalRefKind: authorized.externalRefKind,
                externalRefId: authorized.externalRefId,
                originatingUserText: authorized.originatingUserText,
                precedingAssistantText: authorized.precedingAssistantText,
                runMode: authorized.runMode,
                chatMode: authorized.chatMode,
              });
            }
          } catch {
            logErr(`Failed to parse omi-tools message: ${line.slice(0, 200)}`);
          }
        }
      });

      client.on("close", () => {
        omiToolsClients = omiToolsClients.filter((c) => c !== client);
        resolveClientToolCalls(client, "Error: omi-tools relay client disconnected");
      });

      client.on("error", (err) => {
        logErr(`omi-tools client error: ${err.message}`);
        resolveClientToolCalls(client, "Error: omi-tools relay client error");
      });
    });

    server.listen(pipePath, () => {
      logErr(`omi-tools relay socket: ${pipePath}`);
      resolve(pipePath);
    });

    server.on("error", reject);

    // Clean up on exit
    process.on("exit", () => {
      server.close();
      try {
        unlinkSync(pipePath);
      } catch {
        // ignore
      }
    });
  });
}

// --- ACP subprocess management ---

const acpAdapter = new AcpRuntimeAdapter({ log: logErr });

/** Send a JSON-RPC request to the ACP subprocess and wait for the response */
async function acpRequest(
  method: string,
  params: Record<string, unknown> = {}
): Promise<unknown> {
  return acpAdapter.request(method, params);
}

/** Send a JSON-RPC notification (no response expected) to ACP */
function acpNotify(
  method: string,
  params: Record<string, unknown> = {}
): void {
  acpAdapter.notify(method, params);
}

/** Start the ACP subprocess */
async function startAcpProcess(): Promise<void> {
  await acpAdapter.start();
}

acpAdapter.onProcessExit = () => {
  isInitialized = false;
};

// --- State ---

let isInitialized = false;
let authMethods: AuthMethod[] = [];
let authResolve: (() => void) | null = null;
let activeAuthPromise: Promise<void> | null = null;
let activeOAuthFlow: OAuthFlowHandle | null = null;

// --- Auth flow (OAuth) ---

/** Restart the ACP subprocess so it picks up freshly-stored credentials */
async function restartAcpProcess(): Promise<void> {
  logErr("Restarting ACP subprocess to pick up new credentials...");
  // State is cleaned up by the exit handler (sessions, handlers, etc.)
  await acpAdapter.restart();
}

/**
 * Start the OAuth flow: spin up a local callback server, send the auth URL
 * to Swift (so it can open the browser), wait for the user to complete auth,
 * store credentials in Keychain, and restart the ACP subprocess.
 *
 * Idempotent: if a flow is already running, returns the same promise.
 */
async function startAuthFlow(): Promise<void> {
  if (activeAuthPromise) {
    logErr("Auth flow already in progress, waiting for it...");
    return activeAuthPromise;
  }

  activeAuthPromise = (async () => {
    try {
      logErr("Starting OAuth flow...");
      const flow = await startOAuthFlow(logErr);
      activeOAuthFlow = flow;

      // Send auth URL to Swift so it can open the browser
      send({ type: "auth_required", methods: authMethods, authUrl: flow.authUrl });

      // Wait for OAuth callback + token exchange + credential storage
      await flow.complete;
      logErr("OAuth flow completed successfully");

      // Restart ACP subprocess so it picks up new credentials from Keychain
      await restartAcpProcess();

      // Notify Swift
      send({ type: "auth_success" });
    } catch (err) {
      logErr(`OAuth flow failed: ${err}`);
      throw err;
    } finally {
      activeOAuthFlow = null;
      activeAuthPromise = null;
    }
  })();

  return activeAuthPromise;
}

// --- ACP initialization ---

async function initializeAcp(): Promise<void> {
  if (isInitialized) return;

  try {
    const result = (await acpRequest("initialize", {
      protocolVersion: 1,
    })) as {
      protocolVersion: number;
      agentCapabilities?: Record<string, unknown>;
      agentInfo?: { name: string; version: string };
      authMethods?: Array<{
        id: string;
        name: string;
        description?: string;
        type?: string;
        args?: string[];
        env?: Record<string, string>;
      }>;
    };

    logErr(
      `ACP initialized: protocol=${result.protocolVersion}, capabilities=${JSON.stringify(result.agentCapabilities)}`
    );

    // Store auth methods for potential later use
    if (result.authMethods && result.authMethods.length > 0) {
      authMethods = result.authMethods.map((m) => ({
        id: m.id,
        type: (m.type ?? "agent_auth") as AuthMethod["type"],
        displayName: m.name || m.description || m.id,
        args: m.args,
        env: m.env,
      }));
      logErr(
        `Auth methods: ${authMethods.map((m) => `${m.id}(${m.displayName})`).join(", ")}`
      );
    }

    isInitialized = true;
  } catch (err) {
    if (err instanceof AcpError && err.code === -32000) {
      // AUTH_REQUIRED
      const data = err.data as {
        authMethods?: Array<{
          id: string;
          name: string;
          description?: string;
          type?: string;
        }>;
      };
      if (data?.authMethods) {
        authMethods = data.authMethods.map((m) => ({
          id: m.id,
          type: (m.type ?? "agent_auth") as AuthMethod["type"],
          displayName: m.name || m.description || m.id,
        }));
      }
      logErr(`ACP requires authentication: ${JSON.stringify(authMethods)}`);
      await startAuthFlow();

      // Retry initialization after auth (ACP subprocess already restarted)
      await initializeAcp();
      return;
    }
    throw err;
  }
}

// --- MCP server config builder ---

type McpServerConfig = {
  name: string;
  command: string;
  args: string[];
  env: Array<{ name: string; value: string }>;
};

function buildMcpServers(
  mode: string,
  cwd?: string,
  sessionKey?: string,
  context?: McpServerBuildContext
): McpServerConfig[] {
  const servers: McpServerConfig[] = [];

  if (context?.includeSwiftBackedTools !== false) {
    // omi-tools (stdio, connects back via Unix socket)
    const omiToolsEnv: Array<{ name: string; value: string }> = [
      { name: "OMI_BRIDGE_PIPE", value: omiToolsPipePath },
      { name: "OMI_QUERY_MODE", value: mode },
      { name: "OMI_ADAPTER_ID", value: context?.adapterId ?? "acp" },
    ];
    if (cwd) {
      omiToolsEnv.push({ name: "OMI_WORKSPACE", value: cwd });
    }
    if (sessionKey === "onboarding") {
      omiToolsEnv.push({ name: "OMI_ONBOARDING", value: "true" });
    }
    if (context?.screenContext === true) {
      omiToolsEnv.push({ name: "OMI_SCREEN_CONTEXT", value: "true" });
    }
    omiToolsEnv.push({
      name: "OMI_EXECUTION_ROLE",
      value: context?.executionRole === "leaf" ? "leaf" : "coordinator",
    });
    servers.push({
      name: "omi-tools",
      command: process.execPath,
      args: [omiToolsStdioScript],
      env: omiToolsEnv,
    });
  }

  // Playwright MCP server. Only expose it when the desktop app has verified
  // the user already configured the Playwright bridge; otherwise the agent
  // must use app-native tools instead of opening a fresh Playwright browser.
  if (process.env.PLAYWRIGHT_MCP_ENABLED === "true") {
    const playwrightArgs = [playwrightCli];
    if (process.env.PLAYWRIGHT_USE_EXTENSION === "true") {
      playwrightArgs.push("--extension");
    }
    const playwrightEnv: Array<{ name: string; value: string }> = [];
    if (process.env.PLAYWRIGHT_MCP_EXTENSION_TOKEN) {
      playwrightEnv.push({
        name: "PLAYWRIGHT_MCP_EXTENSION_TOKEN",
        value: process.env.PLAYWRIGHT_MCP_EXTENSION_TOKEN,
      });
    }
    servers.push({
      name: "playwright",
      command: process.execPath,
      args: playwrightArgs,
      env: playwrightEnv,
    });
  }

  return servers;
}

function requireControlSessionPolicy(sessionId: string | undefined, ownerId: string | undefined) {
  if (!sessionId || !ownerId || !agentControlToolContext) {
    throw new Error("missing active control session policy");
  }
  return agentControlToolContext.kernel.executionPolicyForOwnedSession(sessionId, ownerId);
}

// --- Error handling ---

/**
 * Write to /tmp/agent-crash.log as fallback when stderr might be lost.
 * Hard-capped at CRASH_LOG_MAX_LINES per process to prevent runaway disk
 * fill (we shipped a build that wrote 100s of GBs into this file in a tight
 * EPIPE re-entry loop).
 */
const CRASH_LOG_MAX_LINES = 100;
let crashLogLineCount = 0;
function logCrash(msg: string): void {
  if (crashLogLineCount >= CRASH_LOG_MAX_LINES) return;
  crashLogLineCount += 1;
  try {
    const ts = new Date().toISOString();
    appendFileSync("/tmp/agent-crash.log", `[${ts}] ${msg}\n`);
  } catch {
    // ignore
  }
}

// Once we've decided to bail because the parent pipe is gone, suppress all
// further error handling so logErr/logCrash don't keep re-entering on
// every subsequent failed write while the runtime tears down.
let shuttingDown = false;
function bailOnBrokenPipe(reason: string): void {
  if (shuttingDown) return;
  shuttingDown = true;
  logErr(reason);
  logCrash(reason);
  process.exit(0);
}

process.on("unhandledRejection", (reason) => {
  if (shuttingDown) return;
  const code = (reason as NodeJS.ErrnoException | undefined)?.code;
  if (code === "EPIPE" || code === "ERR_STREAM_DESTROYED") {
    bailOnBrokenPipe(`Unhandled rejection (${code}, pipe closed)`);
    return;
  }
  logErr(`Unhandled rejection: ${reason}`);
  logCrash(`Unhandled rejection: ${reason}`);
});

process.on("uncaughtException", (err) => {
  if (shuttingDown) return;
  const code = (err as NodeJS.ErrnoException).code;
  if (code === "EPIPE" || code === "ERR_STREAM_DESTROYED") {
    // Parent has gone away; staying alive without a pipe just produces
    // more EPIPEs. Exit cleanly instead of returning (the previous
    // `return` left the process running and looping on every retry).
    bailOnBrokenPipe(`Caught ${code} in uncaughtException (pipe closed)`);
    return;
  }
  logErr(`Uncaught exception: ${err.message}\n${err.stack ?? ""}`);
  logCrash(`Uncaught exception: ${err.message}\n${err.stack ?? ""}`);
  try {
    const envelope = runtimeErrorEnvelope(err);
    send({ type: "error", message: envelope.message, failure: envelope.failure });
  } catch {
    // already broken
  }
  process.exit(1);
});

process.stdout.on("error", (err) => {
  if ((err as NodeJS.ErrnoException).code === "EPIPE") {
    bailOnBrokenPipe("stdout EPIPE — parent disconnected");
    return;
  }
  logErr(`stdout error: ${err.message}`);
  logCrash(`stdout error: ${err.message}`);
});

process.stderr.on("error", (err) => {
  // If stderr is also gone, we have nothing to write to. Bail silently.
  const code = (err as NodeJS.ErrnoException).code;
  if (code === "EPIPE" || code === "ERR_STREAM_DESTROYED") {
    if (!shuttingDown) {
      shuttingDown = true;
      logCrash("stderr EPIPE — parent disconnected");
      process.exit(0);
    }
  }
});

// --- Main ---

async function main(): Promise<void> {
  logErr(`Bridge main() starting (pid=${process.pid}, node=${process.version}, execPath=${process.execPath})`);

  const defaultHarnessMode = process.env.HARNESS_MODE || "acp";
  const defaultAdapterId = adapterIdForHarnessMode(defaultHarnessMode);
  logErr(`Default harness mode: ${defaultHarnessMode}`);

  // 1. Start Unix socket for omi-tools relay
  omiToolsPipePath = await startOmiToolsRelay();
  logErr("omi-tools relay started");
  process.env.OMI_BRIDGE_PIPE = omiToolsPipePath;

  // 2. Start ACP only when selected or lazily needed by an ACP query.
  if (defaultAdapterId === "acp") {
    await startAcpProcess();
    logErr("ACP subprocess spawned");
  }

  const store = new SqliteAgentStore({ stateDir: agentStateDir() });
  const registry = new AdapterRegistry();
  // Adapter registration is availability, not execution authority. Immutable
  // session profiles decide which registered adapter a run may use.
  registry.register("acp", () => acpAdapter, 1);
  const artifactStorage = new OmiArtifactStorage({ rootDir: agentArtifactsDir() });
  logErr(`Omi artifact root: ${artifactStorage.rootDir}`);
  const recoverRunInput = (adapterId: string) => {
    if (adapterId !== "acp") return {};
    let recoveries = 0;
    return {
      maxAttempts: 3,
      recoverAfterError: async (error: unknown) => {
        if (recoveries >= 2 || !isRecoverableAcpAuthError(error)) return false;
        recoveries += 1;
        logErr("ACP auth required during run; starting OAuth flow before retry");
        await startAuthFlow();
        return true;
      },
    };
  };
  const kernel = new AgentRuntimeKernel({
    store,
    registry,
    artifactStorage,
    recoverRunInput,
    onToolCapabilityRejected: (code) => {
      const count = (capabilityRejectionCounts.get(code) ?? 0) + 1;
      capabilityRejectionCounts.set(code, count);
      logErr(`run_tool_capability_rejected code=${code} count=${count}`);
    },
  });
  runtimeKernel = kernel;
  let piMonoClasses: typeof import("./adapters/pi-mono.js") | undefined;
  let piMonoAuthToken = process.env.OMI_AUTH_TOKEN;
  const piMonoAdapters = new Set<import("./adapters/pi-mono.js").PiMonoAdapter>();
  const localAcpAdapters = new Set<RuntimeAdapter>();
  const stopLocalAcpAdapters = async (): Promise<void> => {
    await Promise.all([...localAcpAdapters].map((adapter) => adapter.stop()));
  };
  const ensurePiMonoAdapter = async (authToken: string | undefined): Promise<boolean> => {
    if (!authToken) return false;
    piMonoAuthToken = authToken;
    piMonoClasses ??= await import("./adapters/pi-mono.js");
    if (!registry.has("pi-mono")) {
      registry.register("pi-mono", () => {
        const harness = new piMonoClasses!.PiMonoAdapter({
          omiApiBaseUrl: process.env.OMI_API_BASE_URL,
          authToken: piMonoAuthToken,
        });
        piMonoAdapters.add(harness);
        return new piMonoClasses!.PiMonoRuntimeAdapter(harness);
      }, configuredPiMonoMaxWorkers());
      logErr(`Pi-mono adapter registered (maxWorkers=${configuredPiMonoMaxWorkers()})`);
    }
    return true;
  };

  const piMonoAvailable = await ensurePiMonoAdapter(process.env.OMI_AUTH_TOKEN);
  const ensureHermesAdapter = async (): Promise<boolean> => {
    return ensureRegisteredAdapter(registry, "hermes", {
      log: logErr,
      maxWorkers: 1,
      onCreate: (adapter) => localAcpAdapters.add(adapter),
    });
  };
  const ensureOpenClawAdapter = async (): Promise<boolean> => {
    return ensureRegisteredAdapter(registry, "openclaw", {
      log: logErr,
      maxWorkers: configuredPiMonoMaxWorkers(),
      onCreate: (adapter) => localAcpAdapters.add(adapter),
    });
  };
  const hermesAvailable = await ensureHermesAdapter();
  const openClawAvailable = await ensureOpenClawAdapter();
  if (!piMonoAvailable && defaultAdapterId === "pi-mono" && process.env.OMI_AGENT_ALLOW_CONTROL_ONLY !== "1") {
    const msg = "pi-mono mode requires OMI_AUTH_TOKEN (Firebase ID token); refusing to start";
    logErr(msg);
    send({ type: "error", message: msg });
    process.exit(1);
  } else if (!piMonoAvailable && defaultAdapterId === "pi-mono") {
    logErr("Pi-mono adapter unavailable; starting the non-production control-only runtime");
  }
  if (!hermesAvailable && defaultAdapterId === "hermes") {
    const msg = adapterActivationError("hermes") ?? "Hermes adapter is unavailable.";
    logErr(msg);
    send({ type: "error", message: msg });
    process.exit(1);
  }
  if (!openClawAvailable && defaultAdapterId === "openclaw") {
    const msg = adapterActivationError("openclaw") ?? "OpenClaw adapter is unavailable.";
    logErr(msg);
    send({ type: "error", message: msg });
    process.exit(1);
  }
  agentControlToolContext = {
    kernel,
    defaultAdapterId,
    providerBoundary: providerBoundaryForAdapter(defaultAdapterId),
    executionRole: "coordinator",
    getOwnerId: () => currentOwnerId,
    buildMcpServers,
    recoverRunInput,
  };
  const transport = new JsonlTransport({
    kernel,
    send,
    log: logErr,
    defaultAdapterId,
    buildMcpServers,
    isRecoverableError: (error, adapterId) => adapterId === "acp" && isRecoverableAcpAuthError(error),
    onRecoverableError: async (_error, adapterId) => {
      if (adapterId !== "acp") return;
      logErr("ACP auth required during query; starting OAuth flow before retry");
      await startAuthFlow();
    },
    maxRecoverableRetries: 2,
    activeOwnerId: () => currentOwnerId,
  });
  const preferenceForOwner = (ownerId: string) => kernel.defaultExecutionProfilePreference(ownerId)
    ?? kernel.configureDefaultExecutionProfile({
      ownerId,
      adapterId: defaultAdapterId,
      modelProfile: defaultAdapterId === "pi-mono"
        ? "omi-sonnet"
        : defaultAdapterId === "acp" ? "claude-sonnet-4-6" : null,
      workingDirectory: agentArtifactsDir(),
    });
  const resolveJournalSurface = (input: {
    ownerId: string;
    surfaceKind: string;
    externalRefKind: string;
    externalRefId: string;
  }) => {
    const preference = preferenceForOwner(input.ownerId);
    return kernel.resolveSurfaceSession({
      ownerId: input.ownerId,
      surfaceRef: {
        surfaceKind: input.surfaceKind,
        externalRefKind: input.externalRefKind,
        externalRefId: input.externalRefId,
      },
      defaultAdapterId: preference.adapterId,
      providerBoundary: providerBoundaryForAdapter(preference.adapterId),
      modelProfile: preference.modelProfile,
      defaultCwd: preference.workingDirectory,
      executionRole: executionRoleForSurface(input),
    });
  };
  const journalTurnProjection = (turn: ConversationTurn) => ({ ...turn });
  const sendBackendReconcile = (request: ReturnType<typeof beginBackendReconcilesForOwner>[number]) => {
    send({
      type: "journal_backend_reconcile",
      requestId: request.reconcileId,
      clientId: "kernel-journal",
      ...request,
    });
  };
  const triggerBackendReconcile = (input: { ownerId: string; conversationId?: string }) => {
    for (const reconcile of beginBackendReconcilesForOwner(store, {
      ownerId: input.ownerId,
      conversationId: input.conversationId,
      limit: input.conversationId ? 1 : 5,
    })) {
      sendBackendReconcile(reconcile);
    }
  };
  let pumpingJournalOutbox = false;
  const pumpJournalOutbox = () => {
    if (pumpingJournalOutbox) return;
    pumpingJournalOutbox = true;
    try {
      const activeOwnerId = currentOwnerId;
      for (const deletion of drainBackendConversationDeleteOutbox(store, {
        ownerId: activeOwnerId,
        limit: 20,
      })) {
        send({
          type: "journal_backend_delete",
          requestId: `journal-delete:${deletion.operationId}:${deletion.deliveryGeneration}`,
          clientId: "kernel-journal",
          ownerId: deletion.ownerId,
          operationId: deletion.operationId,
          conversationId: deletion.conversationId,
          conversationGeneration: deletion.conversationGeneration,
          attemptCount: deletion.attemptCount,
          deliveryGeneration: deletion.deliveryGeneration,
          payloadHash: deletion.payloadHash,
          targetKind: deletion.targetKind,
          targetId: deletion.targetId,
        });
      }
      for (const delivery of drainBackendTurnOutbox(store, { ownerId: activeOwnerId, limit: 20 })) {
        send({
          type: "journal_backend_sync",
          requestId: `journal:${delivery.turnId}:${delivery.deliveryGeneration}`,
          clientId: "kernel-journal",
          ownerId: delivery.ownerId,
          ...delivery.payload,
          turnId: delivery.turnId,
          conversationId: delivery.conversationId,
          conversationGeneration: delivery.conversationGeneration,
          attemptCount: delivery.attemptCount,
          deliveryGeneration: delivery.deliveryGeneration,
          payloadHash: delivery.payloadHash,
        });
      }
    } catch (error) {
      logErr(`Journal outbox pump failed: ${error}`);
    } finally {
      pumpingJournalOutbox = false;
    }
  };
  const journalPumpTimer = setInterval(pumpJournalOutbox, 1_000);
  journalPumpTimer.unref();
  // 3. Signal readiness
  send({ type: "init", sessionId: "", agentControlTools: SWIFT_ADVERTISED_AGENT_CONTROL_TOOL_NAMES });
  triggerBackendReconcile({ ownerId: currentOwnerId });
  logErr("Agent runtime bridge started, waiting for queries...");

  // 4. Read JSON lines from Swift
  const rl = createInterface({ input: process.stdin, terminal: false });

  rl.on("line", async (line: string) => {
    if (!line.trim()) return;

    let msg: InboundMessage;
    try {
      msg = JSON.parse(line) as InboundMessage;
    } catch {
      logErr(`Invalid JSON: ${line}`);
      return;
    }

    switch (msg.type) {
      case "query":
        (async () => {
          const query = msg as QueryMessage;
          if (!query.clientId?.trim()) {
            throw new Error("query requires clientId");
          }
          if (!query.requestId?.trim()) {
            throw new Error("query requires requestId");
          }
          const queryOwnerId = resolveActiveOwner(query.ownerId);
          query.ownerId = queryOwnerId;
          query.requestId = query.requestId.trim();
          const adapterId = kernel.sessionExecutionProfile(query.sessionId, queryOwnerId).adapterId;
          if (adapterId === "acp") {
            await startAcpProcess();
            await initializeAcp();
          } else if (adapterId === "pi-mono") {
            await ensurePiMonoAdapter(process.env.OMI_AUTH_TOKEN);
          } else if (adapterId === "hermes") {
            if (!(await ensureHermesAdapter())) {
              throw new Error(adapterActivationError("hermes"));
            }
          } else if (adapterId === "openclaw") {
            if (!(await ensureOpenClawAdapter())) {
              throw new Error(adapterActivationError("openclaw"));
            }
          }
          await transport.handleQuery(query);
        })().catch((err) => {
          logErr(`Unhandled query error: ${err}`);
          const query = msg as QueryMessage;
          const envelope = runtimeErrorEnvelope(err);
          send({
            type: "error",
            message: envelope.message,
            failure: envelope.failure,
            protocolVersion: PROTOCOL_VERSION,
            requestId: query.requestId,
            clientId: query.clientId,
          });
        });
        break;

      case "warmup": {
        const wm = msg as WarmupMessage;
        wm.ownerId = resolveActiveOwner(wm.ownerId);
        transport.handleWarmup(wm);
        break;
      }

      case "configure_default_execution_profile": {
        const config = msg as ConfigureDefaultExecutionProfileMessage;
        const ownerId = resolveActiveOwner(config.ownerId);
        const preference = kernel.configureDefaultExecutionProfile({
          ownerId,
          adapterId: config.adapterId,
          modelProfile: config.modelProfile,
          workingDirectory: config.workingDirectory,
          expectedPreferenceGeneration: config.expectedPreferenceGeneration,
        });
        send({
          type: "default_execution_profile_configured",
          protocolVersion: config.protocolVersion,
          requestId: config.requestId,
          clientId: config.clientId,
          preferenceGeneration: preference.generation,
          adapterId: preference.adapterId,
          credentialScope: preference.credentialScope,
          modelProfile: preference.modelProfile,
          workingDirectory: preference.workingDirectory,
          appliesTo: "new_sessions",
        });
        break;
      }

      case "resolve_surface_session": {
        const resolve = msg as ResolveSurfaceSessionMessage;
        const ownerId = resolveActiveOwner(resolve.ownerId);
        const existing = store.getOptionalRow(
          `SELECT agent_session_id FROM surface_conversations
           WHERE owner_id = ? AND surface_kind = ? AND external_ref_kind = ? AND external_ref_id = ?`,
          [ownerId, resolve.surfaceKind, resolve.externalRefKind, resolve.externalRefId],
        );
        const preference = kernel.defaultExecutionProfilePreference(ownerId)
          ?? kernel.configureDefaultExecutionProfile({
            ownerId,
            adapterId: defaultAdapterId,
            modelProfile: defaultAdapterId === "pi-mono"
              ? "omi-sonnet"
              : defaultAdapterId === "acp" ? "claude-sonnet-4-6" : null,
            workingDirectory: agentArtifactsDir(),
          });
        const creationProfile = existing ? undefined : resolve.creationProfile;
        if (creationProfile) {
          if (!isProductionAdapterId(creationProfile.adapterId)) {
            throw new Error(`Unknown production adapter ${creationProfile.adapterId}`);
          }
          if (!kernel.isAdapterRegistered(creationProfile.adapterId)) {
            throw new Error(`Requested creation adapter is unavailable: ${creationProfile.adapterId}`);
          }
          if (!creationProfile.workingDirectory.trim()) {
            throw new Error("Session creation profile requires workingDirectory");
          }
        }
        const selectedProfile = creationProfile ?? preference;
        const resolved = kernel.resolveSurfaceSession({
          ownerId,
          surfaceRef: {
            surfaceKind: resolve.surfaceKind,
            externalRefKind: resolve.externalRefKind,
            externalRefId: resolve.externalRefId,
          },
          defaultAdapterId: selectedProfile.adapterId,
          providerBoundary: providerBoundaryForAdapter(selectedProfile.adapterId),
          modelProfile: selectedProfile.modelProfile,
          defaultCwd: selectedProfile.workingDirectory,
          executionRole: executionRoleForSurface(resolve),
          title: resolve.title ?? null,
        });
        const profile = kernel.sessionExecutionProfile(resolved.agentSessionId, ownerId);
        send({
          type: "surface_session_resolved",
          protocolVersion: resolve.protocolVersion,
          requestId: resolve.requestId,
          clientId: resolve.clientId,
          created: !existing,
          conversationId: resolved.conversationId,
          sessionId: resolved.agentSessionId,
          profile: {
            profileGeneration: profile.generation,
            adapterId: profile.adapterId,
            credentialScope: profile.credentialScope,
            modelProfile: profile.modelProfile,
            workingDirectory: profile.workingDirectory,
            executionRole: profile.executionRole,
          },
        });
        if (resolve.surfaceKind === "main_chat") {
          triggerBackendReconcile({ ownerId, conversationId: resolved.conversationId });
        }
        break;
      }

      case "migrate_session_execution_profile": {
        const migrate = msg as MigrateSessionExecutionProfileMessage;
        const ownerId = resolveActiveOwner(migrate.ownerId);
        const result = kernel.migrateSessionExecutionProfile({
          sessionId: migrate.sessionId,
          ownerId,
          expectedProfileGeneration: migrate.expectedProfileGeneration,
          adapterId: migrate.adapterId,
          modelProfile: migrate.modelProfile,
          workingDirectory: migrate.workingDirectory,
          reason: migrate.reason,
        });
        send({
          type: "session_execution_profile_migrated",
          protocolVersion: migrate.protocolVersion,
          requestId: migrate.requestId,
          clientId: migrate.clientId,
          sessionId: migrate.sessionId,
          previousProfileGeneration: result.previous.generation,
          profile: {
            profileGeneration: result.profile.generation,
            adapterId: result.profile.adapterId,
            credentialScope: result.profile.credentialScope,
            modelProfile: result.profile.modelProfile,
            workingDirectory: result.profile.workingDirectory,
            executionRole: result.profile.executionRole,
          },
          staleBindingIds: result.staleBindingIds,
        });
        break;
      }

      case "context_source_update": {
        const update = msg as ContextSourceUpdateMessage;
        const ownerId = resolveActiveOwner(update.ownerId);
        const result = kernel.updateContextSource({
          ownerId,
          sessionId: update.sessionId,
          surfaceKind: update.surfaceKind,
          source: update.source,
          sourceRevision: update.sourceRevision,
          outcome: update.outcome,
          capturedAtMs: update.capturedAtMs,
          expiresAtMs: update.expiresAtMs,
          payload: update.payload,
        });
        send({
          type: "context_source_updated",
          protocolVersion: update.protocolVersion,
          requestId: update.requestId,
          clientId: update.clientId,
          sessionId: update.sessionId,
          source: update.source,
          sourceRevision: update.sourceRevision,
          changed: result.changed,
          snapshotVersion: result.snapshot.version,
          snapshotGeneration: result.snapshot.snapshotGeneration,
          rendererFingerprint: result.snapshot.rendererFingerprint,
          capabilityVersion: result.snapshot.capabilityVersion,
        });
        break;
      }

      case "get_context_snapshot": {
        const ownerId = resolveActiveOwner(msg.ownerId);
        send({
          type: "context_snapshot",
          protocolVersion: msg.protocolVersion,
          requestId: msg.requestId,
          clientId: msg.clientId,
          snapshot: kernel.contextSnapshot(msg.sessionId, ownerId, msg.surfaceKind),
        });
        break;
      }

      case "authorized_tool_execution_result":
        resolveToolCall(msg);
        break;

      case "external_surface_run_begin": {
        const request = msg as ExternalSurfaceRunBeginMessage;
        const requestId = request.requestId?.trim();
        const clientId = request.clientId?.trim();
        try {
          if (!requestId || !clientId) throw new Error("External surface begin requires requestId and clientId");
          const ownerId = resolveActiveOwner(request.ownerId);
          const result = kernel.beginExternalSurfaceRun({
            ownerId,
            sessionId: request.sessionId,
            turnId: request.turnId,
            prompt: request.prompt,
            mode: request.mode,
            clientId,
            requestId,
          });
          send({
            type: "external_surface_run_begin_result",
            requestId,
            clientId,
            ownerId,
            sessionId: result.sessionId,
            turnId: result.turnId,
            ok: true,
            runId: result.runId,
            attemptId: result.attemptId,
            duplicate: result.duplicate,
          });
        } catch (error) {
          send({
            type: "external_surface_run_begin_result",
            requestId,
            clientId,
            ownerId: request.ownerId ?? "",
            sessionId: request.sessionId ?? "",
            turnId: request.turnId ?? "",
            ok: false,
            error: externalAuthorityError(error, "external_run_begin_rejected"),
          });
        }
        break;
      }

      case "external_surface_tool_invoke": {
        const request = msg as ExternalSurfaceToolInvokeMessage;
        const requestId = request.requestId?.trim();
        const clientId = request.clientId?.trim();
        try {
          if (!requestId || !clientId) throw new Error("External tool invocation requires requestId and clientId");
          const ownerId = resolveActiveOwner(request.ownerId);
          if (!request.input || typeof request.input !== "object" || Array.isArray(request.input)) {
            throw new Error("External tool invocation input must be an object");
          }
          const routed = kernel.routeExternalSurfaceToolInvocation({
            ownerId,
            sessionId: request.sessionId,
            runId: request.runId,
            attemptId: request.attemptId,
            invocationId: request.invocationId,
            toolName: request.toolName,
            toolInput: request.input,
          });
          const authorized = kernel.authorizeExternalSurfaceToolInvocation({
            ownerId,
            sessionId: request.sessionId,
            runId: request.runId,
            attemptId: request.attemptId,
            invocationId: request.invocationId,
            toolName: routed.toolName,
            toolInput: routed.toolInput,
            activeOwnerId: currentOwnerId,
          });
          if (isAgentControlToolName(authorized.canonicalToolName)) {
            kernel.markRunToolInvocationDispatched(authorized);
            const pending = registerPendingExternalToolCall(request, authorized);
            const spawnDescriptor = routed.toolName === "spawn_agent"
              ? parseAgentSpawnProducerJournalDescriptor(
                  ((routed.toolInput.metadata as Record<string, unknown> | undefined) ?? {}).producerJournal,
                )
              : undefined;
            let result: string;
            let outcome: "succeeded" | "failed" = "succeeded";
            try {
              if (!agentControlToolContext) throw new Error("Agent runtime kernel is not ready");
              const activeSession = requireControlSessionPolicy(authorized.sessionId, authorized.ownerId);
              result = await handleAgentControlToolCall(
                {
                  ...agentControlToolContext,
                  callerSessionId: authorized.sessionId,
                  executionRole: activeSession.executionRole,
                  providerBoundary: activeSession.providerBoundary,
                  defaultAdapterId: activeSession.defaultAdapterId,
                  authorizedProducerJournal: spawnDescriptor,
                  authorizedCallerRunId: routed.toolName === "spawn_agent" ? request.runId : undefined,
                  getOwnerId: () => authorized.ownerId,
                },
                authorized.canonicalToolName,
                routed.toolInput,
              );
            } catch (error) {
              outcome = "failed";
              result = relayError(
                "control_tool_failed",
                error instanceof Error ? error.message : "Control tool execution failed",
              );
            }
            if (outcome === "succeeded" && spawnDescriptor) {
              result = attachAgentSpawnJournalReceipt(result, spawnDescriptor);
            }
            const pendingKey = toolCallPendingKey(authorized);
            if (pendingExternalToolCalls.get(pendingKey) !== pending) break;
            pendingExternalToolCalls.delete(pendingKey);
            clearTimeout(pending.timeout);
            kernel.completeRunToolInvocation({
              invocationId: authorized.invocationId,
              ownerId: authorized.ownerId,
              sessionId: authorized.sessionId,
              runId: authorized.runId,
              attemptId: authorized.attemptId,
              profileGeneration: authorized.profileGeneration,
              manifestVersion: authorized.manifestVersion,
              manifestDigest: authorized.manifestDigest,
              daemonBootEpoch: authorized.daemonBootEpoch,
              executionGeneration: authorized.executionGeneration,
              inputHash: authorized.inputHash,
              capabilityRef: authorized.capabilityRef,
              outcome,
              result,
            });
            send({
              type: "external_surface_tool_result",
              requestId,
              clientId,
              ownerId: authorized.ownerId,
              sessionId: authorized.sessionId,
              runId: authorized.runId,
              attemptId: authorized.attemptId,
              invocationId: authorized.invocationId,
              ok: true,
              result,
            });
            break;
          }

          kernel.markRunToolInvocationDispatched(authorized);
          registerPendingExternalToolCall(request, authorized);
          send({
            type: "authorized_tool_execution",
            invocationId: authorized.invocationId,
            ownerId: authorized.ownerId,
            sessionId: authorized.sessionId,
            runId: authorized.runId,
            attemptId: authorized.attemptId,
            profileGeneration: authorized.profileGeneration,
            manifestVersion: authorized.manifestVersion,
            manifestDigest: authorized.manifestDigest,
            daemonBootEpoch: authorized.daemonBootEpoch,
            executionGeneration: authorized.executionGeneration,
            toolName: authorized.canonicalToolName,
            input: routed.toolInput,
            inputHash: authorized.inputHash,
            effectClass: authorized.effectClass,
            retryPolicy: authorized.retryPolicy,
            surfaceKind: authorized.surfaceKind,
            externalRefKind: authorized.externalRefKind,
            externalRefId: authorized.externalRefId,
            originatingUserText: authorized.originatingUserText,
            precedingAssistantText: authorized.precedingAssistantText,
            runMode: authorized.runMode,
            chatMode: authorized.chatMode,
            ...(routed.recoveredFromDelegation
              ? { policyRecovery: "permission_delegation_to_native" as const }
              : {}),
          });
        } catch (error) {
          send({
            type: "external_surface_tool_result",
            requestId,
            clientId,
            ownerId: request.ownerId ?? "",
            sessionId: request.sessionId ?? "",
            runId: request.runId ?? "",
            attemptId: request.attemptId ?? "",
            invocationId: request.invocationId ?? "",
            ok: false,
            error: externalAuthorityError(error, "external_tool_rejected"),
          });
        }
        break;
      }

      case "external_surface_run_complete": {
        const request = msg as ExternalSurfaceRunCompleteMessage;
        const requestId = request.requestId?.trim();
        const clientId = request.clientId?.trim();
        try {
          if (!requestId || !clientId) throw new Error("External surface completion requires requestId and clientId");
          const ownerId = resolveActiveOwner(request.ownerId);
          if (request.terminalStatus === "failed" || request.terminalStatus === "cancelled") {
            cancelPendingExternalToolCallsForAttempt({
              ownerId,
              runId: request.runId,
              attemptId: request.attemptId,
              errorCode: "external_run_terminal",
            });
          }
          const result = kernel.completeExternalSurfaceRun({
            ownerId,
            sessionId: request.sessionId,
            runId: request.runId,
            attemptId: request.attemptId,
            terminalStatus: request.terminalStatus,
            errorCode: request.errorCode,
          });
          send({
            type: "external_surface_run_complete_result",
            requestId,
            clientId,
            ownerId,
            sessionId: result.sessionId,
            runId: result.runId,
            attemptId: result.attemptId,
            ok: true,
            terminalStatus: result.terminalStatus,
            duplicate: result.duplicate,
          });
        } catch (error) {
          send({
            type: "external_surface_run_complete_result",
            requestId,
            clientId,
            ownerId: request.ownerId ?? "",
            sessionId: request.sessionId ?? "",
            runId: request.runId ?? "",
            attemptId: request.attemptId ?? "",
            ok: false,
            error: externalAuthorityError(error, "external_run_complete_rejected"),
          });
        }
        break;
      }

      case "journal_record_turn": {
        const request = msg as JournalRecordTurnMessage;
        const ownerId = resolveActiveOwner(request.ownerId);
        const resolved = resolveJournalSurface({
          ownerId,
          surfaceKind: request.surfaceKind,
          externalRefKind: request.externalRefKind,
          externalRefId: request.externalRefId,
        });
        const turn = request.turn ?? {};
        const result = recordJournalTurn(store, {
          ownerId,
          conversationId: resolved.conversationId,
          turnId: typeof turn.turnId === "string" ? turn.turnId : undefined,
          producerId: typeof turn.producerId === "string" ? turn.producerId : undefined,
          role: turn.role === "assistant" ? "assistant" : "user",
          surfaceKind: request.surfaceKind,
          origin: journalOrigin(turn.origin ?? "typed_chat"),
          status: (typeof turn.status === "string" ? turn.status : "pending") as ConversationTurnStatus,
          content: typeof turn.content === "string" ? turn.content : "",
          contentBlocks: Array.isArray(turn.contentBlocks)
            ? turn.contentBlocks as ConversationContentBlock[]
            : [],
          resources: Array.isArray(turn.resources) ? turn.resources as ConversationResource[] : [],
          producingRunId: typeof turn.producingRunId === "string" ? turn.producingRunId : null,
          metadataJson: typeof turn.metadataJson === "string" ? turn.metadataJson : "{}",
          delivery: turn.delivery === "local" ? "local" : "backend",
          createdAtMs: typeof turn.createdAtMs === "number" ? turn.createdAtMs : undefined,
        });
        const range = listJournalTurns(store, {
          ownerId,
          conversationId: resolved.conversationId,
          afterTurnSeq: Math.max(0, result.turn.turnSeq - 1),
          limit: 1,
        });
        send({
          type: "journal_operation_result",
          protocolVersion: request.protocolVersion,
          requestId: request.requestId,
          clientId: request.clientId,
          operation: "record",
          conversationId: resolved.conversationId,
          surfaceKind: request.surfaceKind,
          externalRefKind: request.externalRefKind,
          externalRefId: request.externalRefId,
          turn: journalTurnProjection(result.turn),
          turns: [],
          clearedCount: 0,
          highWaterTurnSeq: range.highWaterTurnSeq,
          generationBaseTurnSeq: range.generationBaseTurnSeq,
          conversationGeneration: range.generation,
        });
        if (result.created) {
          send({
            type: "journal_turn_changed",
            conversationGeneration: range.generation,
            generationBaseTurnSeq: range.generationBaseTurnSeq,
            surfaceKind: request.surfaceKind,
            externalRefKind: request.externalRefKind,
            externalRefId: request.externalRefId,
            turn: journalTurnProjection(result.turn),
          });
        }
        pumpJournalOutbox();
        break;
      }

      case "journal_update_turn": {
        const request = msg as JournalUpdateTurnMessage;
        const ownerId = resolveActiveOwner(request.ownerId);
        const resolved = resolveJournalSurface({
          ownerId,
          surfaceKind: request.surfaceKind,
          externalRefKind: request.externalRefKind,
          externalRefId: request.externalRefId,
        });
        const update = request.update ?? {};
        const turnId = typeof update.turnId === "string" ? update.turnId : "";
        const before = store.getRow(
          "SELECT turn_seq FROM conversation_turns WHERE conversation_id = ? AND turn_id = ?",
          [resolved.conversationId, turnId],
        );
        const turn = updateJournalTurn(store, {
          ownerId,
          conversationId: resolved.conversationId,
          turnId,
          status: typeof update.status === "string" ? update.status as ConversationTurnStatus : undefined,
          content: typeof update.content === "string" ? update.content : undefined,
          replaceContentBlocks: Array.isArray(update.replaceContentBlocks)
            ? update.replaceContentBlocks as ConversationContentBlock[]
            : undefined,
          appendContentBlocks: Array.isArray(update.appendContentBlocks)
            ? update.appendContentBlocks as ConversationContentBlock[]
            : undefined,
          replaceResources: Array.isArray(update.replaceResources)
            ? update.replaceResources as ConversationResource[]
            : undefined,
          appendResources: Array.isArray(update.appendResources)
            ? update.appendResources as ConversationResource[]
            : undefined,
          producingRunId: typeof update.producingRunId === "string" ? update.producingRunId : undefined,
          metadataJson: typeof update.metadataJson === "string" ? update.metadataJson : undefined,
        });
        const range = listJournalTurns(store, {
          ownerId,
          conversationId: resolved.conversationId,
          afterTurnSeq: Math.max(0, turn.turnSeq - 1),
          limit: 1,
        });
        send({
          type: "journal_operation_result",
          protocolVersion: request.protocolVersion,
          requestId: request.requestId,
          clientId: request.clientId,
          operation: "update",
          conversationId: resolved.conversationId,
          surfaceKind: request.surfaceKind,
          externalRefKind: request.externalRefKind,
          externalRefId: request.externalRefId,
          turn: journalTurnProjection(turn),
          turns: [],
          clearedCount: 0,
          highWaterTurnSeq: range.highWaterTurnSeq,
          generationBaseTurnSeq: range.generationBaseTurnSeq,
          conversationGeneration: range.generation,
        });
        if (turn.turnSeq !== Number(before.turn_seq)) {
          send({
            type: "journal_turn_changed",
            conversationGeneration: range.generation,
            generationBaseTurnSeq: range.generationBaseTurnSeq,
            surfaceKind: request.surfaceKind,
            externalRefKind: request.externalRefKind,
            externalRefId: request.externalRefId,
            turn: journalTurnProjection(turn),
          });
        }
        pumpJournalOutbox();
        break;
      }

      case "journal_list_turns": {
        const request = msg as JournalListTurnsMessage;
        const ownerId = resolveActiveOwner(request.ownerId);
        const resolved = resolveJournalSurface({
          ownerId,
          surfaceKind: request.surfaceKind,
          externalRefKind: request.externalRefKind,
          externalRefId: request.externalRefId,
        });
        const range = listJournalTurns(store, {
          ownerId,
          conversationId: resolved.conversationId,
          afterTurnSeq: request.afterTurnSeq,
          limit: request.limit,
        });
        send({
          type: "journal_operation_result",
          protocolVersion: request.protocolVersion,
          requestId: request.requestId,
          clientId: request.clientId,
          operation: "list",
          conversationId: resolved.conversationId,
          surfaceKind: request.surfaceKind,
          externalRefKind: request.externalRefKind,
          externalRefId: request.externalRefId,
          turns: range.turns.map(journalTurnProjection),
          clearedCount: 0,
          highWaterTurnSeq: range.highWaterTurnSeq,
          generationBaseTurnSeq: range.generationBaseTurnSeq,
          conversationGeneration: range.generation,
        });
        if (request.surfaceKind === "main_chat") {
          triggerBackendReconcile({ ownerId, conversationId: resolved.conversationId });
        }
        break;
      }

      case "journal_clear_turns": {
        const request = msg as JournalClearTurnsMessage;
        const ownerId = resolveActiveOwner(request.ownerId);
        const resolved = resolveJournalSurface({
          ownerId,
          surfaceKind: request.surfaceKind,
          externalRefKind: request.externalRefKind,
          externalRefId: request.externalRefId,
        });
        const result = clearJournalConversation(store, {
          ownerId,
          conversationId: resolved.conversationId,
          expectedGeneration: request.expectedGeneration,
        });
        send({
          type: "journal_operation_result",
          protocolVersion: request.protocolVersion,
          requestId: request.requestId,
          clientId: request.clientId,
          operation: "clear",
          conversationId: resolved.conversationId,
          surfaceKind: request.surfaceKind,
          externalRefKind: request.externalRefKind,
          externalRefId: request.externalRefId,
          turns: [],
          clearedCount: result.deletedTurns,
          highWaterTurnSeq: result.highWaterTurnSeq,
          generationBaseTurnSeq: result.generationBaseTurnSeq,
          conversationGeneration: result.generation,
          backendDeleteOperationId: result.backendDeleteOperationId ?? undefined,
        });
        pumpJournalOutbox();
        break;
      }

      case "ensure_agent_spawn_journal": {
        const request = msg as EnsureAgentSpawnJournalMessage;
        const ownerId = resolveActiveOwner(request.ownerId);
        const result = kernel.ensureAgentSpawnJournal({
          ownerId,
          sessionId: request.sessionId,
          runId: request.runId,
        });
        send({
          type: "agent_spawn_journal_ensured",
          protocolVersion: request.protocolVersion,
          requestId: request.requestId,
          clientId: request.clientId,
          ownerId,
          sessionId: result.sessionId,
          runId: result.runId,
          conversationId: result.conversationId,
          userTurn: journalTurnProjection(result.userTurn),
          assistantTurn: journalTurnProjection(result.assistantTurn),
        });
        for (const turn of [result.userTurn, result.assistantTurn]) {
          for (const wake of journalTurnChangedWakes(store, ownerId, turn)) {
            send({ type: "journal_turn_changed", ...wake, turn: journalTurnProjection(wake.turn) });
          }
        }
        pumpJournalOutbox();
        break;
      }

      case "journal_backend_sync_result": {
        const result = msg as JournalBackendSyncResultMessage;
        const claimOwner = store.getOptionalRow(
          "SELECT owner_id, conversation_id FROM backend_turn_outbox WHERE turn_id = ?",
          [result.turnId],
        );
        if (!claimOwner) {
          const settled = settleClearedBackendTurnClaim(store, {
            ownerId: result.ownerId,
            turnId: result.turnId,
            conversationId: result.conversationId,
            attemptCount: result.attemptCount,
            deliveryGeneration: result.deliveryGeneration,
            conversationGeneration: result.conversationGeneration,
            payloadHash: result.payloadHash,
            ok: result.ok,
          });
          if (!settled) throw new Error("Backend sync result has no active or preserved claim");
          pumpJournalOutbox();
          break;
        }
        if (String(claimOwner.conversation_id) !== result.conversationId) {
          throw new Error("Backend sync result conversation does not match the active claim");
        }
        const ownerId = String(claimOwner.owner_id);
        if (result.ownerId !== ownerId) throw new Error("Backend sync result owner does not match the claim owner");
        if (result.ok && result.remoteId) {
          if (ownerId !== currentOwnerId) throw new Error("Backend sync success is outside the active owner");
          const acknowledged = ackBackendTurnOutboxWithWakes(store, {
            ownerId,
            turnId: result.turnId,
            remoteId: result.remoteId,
            attemptCount: result.attemptCount,
            deliveryGeneration: result.deliveryGeneration,
            conversationGeneration: result.conversationGeneration,
            payloadHash: result.payloadHash,
          });
          for (const wake of acknowledged.wakes) {
            send({ type: "journal_turn_changed", ...wake });
          }
        } else {
          failBackendTurnOutbox(store, {
            ownerId,
            turnId: result.turnId,
            attemptCount: result.attemptCount,
            deliveryGeneration: result.deliveryGeneration,
            conversationGeneration: result.conversationGeneration,
            payloadHash: result.payloadHash,
            errorCode: result.errorCode ?? "backend_sync_failed",
            retryAtMs: result.attemptCount < 5
              && [
                "backend_sync_failed",
                "backend_sync_owner_changed",
                "backend_sync_http_retryable",
                "network_unavailable",
                "timeout",
                "connection_lost",
              ].includes(
                result.errorCode ?? "backend_sync_failed",
              )
              ? Date.now() + Math.min(60_000, 1_000 * 2 ** result.attemptCount)
              : undefined,
          });
        }
        pumpJournalOutbox();
        break;
      }

      case "journal_backend_delete_result": {
        const result = msg as JournalBackendDeleteResultMessage;
        const claim = store.getRow(
          `SELECT owner_id, conversation_id
           FROM backend_conversation_delete_outbox WHERE operation_id = ?`,
          [result.operationId],
        );
        const claimOwnerId = String(claim.owner_id);
        if (result.ownerId !== claimOwnerId || String(claim.conversation_id) !== result.conversationId) {
          throw new Error("Backend conversation delete result does not match the active owner or conversation");
        }
        if (result.ok) {
          if (claimOwnerId !== currentOwnerId) throw new Error("Backend delete success is outside the active owner");
          ackBackendConversationDeleteOutbox(store, {
            ownerId: claimOwnerId,
            operationId: result.operationId,
            conversationGeneration: result.conversationGeneration,
            attemptCount: result.attemptCount,
            deliveryGeneration: result.deliveryGeneration,
            payloadHash: result.payloadHash,
          });
        } else {
          const errorCode = result.errorCode ?? "backend_delete_failed";
          failBackendConversationDeleteOutbox(store, {
            ownerId: claimOwnerId,
            operationId: result.operationId,
            conversationGeneration: result.conversationGeneration,
            attemptCount: result.attemptCount,
            deliveryGeneration: result.deliveryGeneration,
            payloadHash: result.payloadHash,
            errorCode,
            retryAtMs: result.attemptCount < 5
              && [
                "backend_delete_failed",
                "backend_sync_owner_changed",
                "backend_sync_http_retryable",
                "network_unavailable",
                "timeout",
                "connection_lost",
              ].includes(errorCode)
              ? Date.now() + Math.min(60_000, 1_000 * 2 ** result.attemptCount)
              : undefined,
          });
        }
        pumpJournalOutbox();
        if (result.ok && claimOwnerId === currentOwnerId) {
          triggerBackendReconcile({ ownerId: claimOwnerId, conversationId: result.conversationId });
        }
        break;
      }

      case "journal_backend_reconcile_result": {
        const result = msg as JournalBackendReconcileResultMessage;
        const claim = store.getOptionalRow(
          `SELECT owner_id, in_flight_id, status FROM backend_reconcile_state
           WHERE conversation_id = ?`,
          [result.conversationId],
        );
        if (
          !claim
          || String(claim.owner_id) !== result.ownerId
          || String(claim.status) !== "fetching"
          || String(claim.in_flight_id) !== result.reconcileId
        ) {
          logErr(`Dropping stale backend reconcile result reconcile=${result.reconcileId}`);
          break;
        }
        if (!result.ok) {
          failBackendReconcile(store, {
            ownerId: result.ownerId,
            reconcileId: result.reconcileId,
            conversationId: result.conversationId,
            errorCode: result.errorCode ?? "backend_reconcile_failed",
          });
          pumpJournalOutbox();
          break;
        }
        if (result.ownerId !== currentOwnerId) {
          throw new Error("Backend reconcile success is outside the active owner");
        }
        const page = applyBackendReconcilePage(store, {
          ownerId: result.ownerId,
          reconcileId: result.reconcileId,
          conversationId: result.conversationId,
          pageCursor: result.pageCursor,
          nextCursor: result.nextCursor,
          turns: (result.turns ?? []).map((turn) => ({
            remoteId: typeof turn.remoteId === "string" ? turn.remoteId : "",
            canonicalTurnId: typeof turn.canonicalTurnId === "string" ? turn.canonicalTurnId : null,
            role: turn.role === "assistant" ? "assistant" : "user",
            content: typeof turn.content === "string" ? turn.content : "",
            contentBlocks: Array.isArray(turn.contentBlocks)
              ? turn.contentBlocks as ConversationContentBlock[]
              : [],
            resources: Array.isArray(turn.resources) ? turn.resources as ConversationResource[] : [],
            metadataJson: typeof turn.metadataJson === "string" ? turn.metadataJson : "{}",
            createdAtMs: typeof turn.createdAtMs === "number" ? turn.createdAtMs : Date.now(),
          })),
          hasMore: result.hasMore === true,
        });
        for (const turn of page.importedTurns) {
          for (const wake of journalTurnChangedWakes(store, result.ownerId, turn)) {
            send({ type: "journal_turn_changed", ...wake, turn: journalTurnProjection(wake.turn) });
          }
        }
        if (page.nextRequest) sendBackendReconcile(page.nextRequest);
        break;
      }

      case "control_tool": {
        const control = msg as ControlToolRequestMessage;
        send({
          type: "control_tool_result",
          protocolVersion: control.protocolVersion,
          requestId: control.requestId?.trim(),
          clientId: control.clientId,
          name: control.name,
          result: relayError(
            "legacy_control_tool_removed",
            "Agent-originated control tools require a registered run capability",
          ),
        });
        break;
      }

      case "direct_control_tool": {
        const control = msg as DirectControlToolRequestMessage;
        const requestId = control.requestId?.trim();
        const clientId = control.clientId?.trim();
        const ownerGuard = control.ownerId?.trim();
        if (!requestId || !clientId) {
          send({
            type: "control_tool_result",
            protocolVersion: PROTOCOL_VERSION,
            requestId,
            clientId,
            name: control.name,
            result: relayError("invalid_request", "Direct control requires tracing requestId and clientId"),
          });
          break;
        }
        if (!isAgentControlToolName(control.name)) {
          send({
            type: "control_tool_result",
            protocolVersion: control.protocolVersion,
            requestId,
            clientId,
            name: control.name,
            result: relayError(
              "unsupported_direct_control_tool",
              "Direct app control cannot execute " + control.name,
            ),
          });
          break;
        }
        if (!ownerGuard || ownerGuard !== currentOwnerId) {
          send({
            type: "control_tool_result",
            protocolVersion: control.protocolVersion,
            requestId,
            clientId,
            name: control.name,
            result: relayError("invalid_owner_id", "Direct control owner does not match the active signed-in owner"),
          });
          break;
        }

        let controlInput: Record<string, unknown>;
        try {
          controlInput = withMergedOwnerGuard(control.input ?? {}, ownerGuard, currentOwnerId);
          controlInput = {
            ...controlInput,
            requestId:
              typeof controlInput.requestId === "string" && controlInput.requestId.trim()
                ? controlInput.requestId
                : requestId,
            clientId:
              typeof controlInput.clientId === "string" && controlInput.clientId.trim()
                ? controlInput.clientId
                : clientId,
          };
        } catch (error) {
          send({
            type: "control_tool_result",
            protocolVersion: control.protocolVersion,
            requestId,
            clientId,
            name: control.name,
            result: relayError("invalid_owner_id", error instanceof Error ? error.message : String(error)),
          });
          break;
        }

        const result = agentControlToolContext
          ? await handleAgentControlToolCall(
              {
                ...agentControlToolContext,
                trustedUserControl: true,
                getOwnerId: () => currentOwnerId,
              },
              control.name,
              controlInput,
            )
          : relayError("runtime_not_ready", "Agent runtime kernel is not ready");
        send({
          type: "control_tool_result",
          protocolVersion: control.protocolVersion,
          requestId,
          clientId,
          name: control.name,
          result,
        });
        break;
      }

      case "interrupt":
        logErr("Interrupt requested by user");
        transport.handleInterrupt({ ...msg, ownerId: resolveActiveOwner(msg.ownerId) }).catch((err) => {
          logErr(`Interrupt error: ${err}`);
        });
        break;

      case "clear_owner_state": {
        const ownerId = resolveActiveOwner(msg.ownerId);
        const result = kernel.clearOwnerState(ownerId);
        logErr(
          `Cleared owner state for ${ownerId}: invalidated ${result.invalidatedBindingIds.length} binding(s)`,
        );
        break;
      }

      case "import_legacy_main_chat_sessions": {
        // Compatibility contract is owner-scoped and removal-bounded in
        // LEGACY_MAIN_CHAT_SESSION_COMPATIBILITY; this handler owns no fallback authority.
        const request = msg as ImportLegacyMainChatSessionsMessage;
        try {
          if (!request.requestId?.trim() || !request.clientId?.trim()) {
            throw new Error("legacy_main_chat_session_import_requires_correlation");
          }
          if (!Array.isArray(request.entries) || request.entries.length === 0) {
            throw new Error("legacy_main_chat_session_import_requires_entries");
          }
          const ownerId = resolveActiveOwner(request.ownerId);
          const receipt = kernel.importLegacyMainChatSessions({ ownerId, entries: request.entries });
          send({
            type: "legacy_main_chat_sessions_imported",
            protocolVersion: request.protocolVersion,
            requestId: request.requestId,
            clientId: request.clientId,
            ownerId,
            acceptedEntries: receipt.acceptedEntries,
            acceptedCount: receipt.acceptedEntries.length,
            importedCount: receipt.importedCount,
          });
          logErr(
            `Accepted ${receipt.acceptedEntries.length} legacy main-chat alias(es); `
            + `imported ${receipt.importedCount} (compat-owner=${LEGACY_MAIN_CHAT_SESSION_COMPATIBILITY.owner})`,
          );
        } catch (error) {
          const envelope = runtimeErrorEnvelope(error);
          send({
            type: "error",
            protocolVersion: request.protocolVersion,
            requestId: request.requestId,
            clientId: request.clientId,
            message: envelope.message,
            failure: envelope.failure,
          });
        }
        break;
      }

      case "invalidate_session":
        transport.handleInvalidateSession(msg);
        break;

      case "refresh_token": {
        const rtm = msg as RefreshTokenMessage;
        process.env.OMI_AUTH_TOKEN = rtm.token;
        const nextOwnerId = rtm.ownerId?.trim() || DEFAULT_LOCAL_OWNER_ID;
        if (nextOwnerId !== currentOwnerId) {
          rejectPendingToolCallsForOwner(currentOwnerId);
          kernel.revokeRunToolCapabilitiesForOwner(currentOwnerId, "owner_changed");
          currentOwnerId = nextOwnerId;
          triggerBackendReconcile({ ownerId: currentOwnerId });
        }
        try {
          await ensurePiMonoAdapter(rtm.token);
          for (const adapter of piMonoAdapters) {
            const restarted = await adapter.updateAuthToken(rtm.token);
            if (restarted) {
              logErr("Pi-mono: token refresh restarted subprocess");
            }
          }
        } catch (err) {
          logErr(`Pi-mono token refresh error: ${err}`);
        }
        break;
      }

      case "authenticate": {
        logErr(`Authentication message received from Swift`);
        send({ type: "auth_success" });
        if (authResolve) {
          authResolve();
          authResolve = null;
        }
        break;
      }

      case "stop":
        logErr("Received stop signal, exiting");
        clearInterval(journalPumpTimer);
        store.close();
        await acpAdapter.stop();
        await Promise.all([...piMonoAdapters].map((adapter) => adapter.stop()));
        await stopLocalAcpAdapters();
        process.exit(0);
        break;

      default:
        logErr(`Unknown message type: ${(msg as any).type}`);
    }
  });

  rl.on("close", () => {
    logErr("stdin closed, exiting");
    logCrash("stdin closed, exiting");
    store.close();
    void acpAdapter.stop();
    void Promise.all([...piMonoAdapters].map((adapter) => adapter.stop()));
    void stopLocalAcpAdapters();
    process.exit(0);
  });
}

main().catch((err) => {
  logErr(`Fatal error: ${err}`);
  logCrash(`Fatal error: ${err}`);
  const envelope = runtimeErrorEnvelope(err);
  send({ type: "error", message: envelope.message, failure: envelope.failure });
  process.exit(1);
});
