/**
 * ACP Bridge — translates between OMI's JSON-lines protocol and the
 * Agent Client Protocol (ACP) used by claude-code-acp.
 *
 * THIS IS THE DESKTOP APP FLOW. It is unrelated to the VM/agent-cloud flow
 * (agent-cloud/agent.mjs), which runs Claude Code SDK on a remote VM for
 * the Omi Agent feature. This bridge runs locally on the user's Mac.
 *
 * Session lifecycle:
 * 1. warmup  → session/new (system prompt applied here, once)
 * 2. query   → session reused; systemPrompt field in the message is ignored
 *              unless the session was invalidated (cwd change → new session/new)
 * 3. The ACP SDK owns conversation history after session/new — do not inject
 *    it into the system prompt.
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
import { randomUUID } from "crypto";
import { createServer as createNetServer, type Socket } from "net";
import { homedir, tmpdir } from "os";
import { unlinkSync, appendFileSync } from "fs";
import type {
  InboundMessage,
  ControlToolRequestMessage,
  DirectControlToolRequestMessage,
  OutboundMessage,
  OutboundMessageDraft,
  QueryScopedOutbound,
  QueryMessage,
  WarmupMessage,
  RefreshTokenMessage,
  RecordSurfaceTurnMessage,
  GetVoiceSeedContextMessage,
  GetKernelTurnTailMessage,
  ClearOwnerSurfaceStateMessage,
  ProjectCrossSurfaceTurnMessage,
  MergeFloatingChatIntoMainChatMessage,
  AuthMethod,
} from "./protocol.js";
import { PROTOCOL_VERSION, ensureOutboundProtocolVersion, type ProtocolVersion } from "./protocol.js";
import { startOAuthFlow, type OAuthFlowHandle } from "./oauth-flow.js";
import type { PromptBlock, RuntimeAdapter } from "./adapters/interface.js";
import { detectImageMimeType } from "./mime-detect.js";
import { AcpError, AcpRuntimeAdapter } from "./adapters/acp.js";
import { AdapterRegistry } from "./runtime/adapter-registry.js";
import { JsonlTransport, type McpServerBuildContext } from "./runtime/jsonl-transport.js";
import { AgentRuntimeKernel } from "./runtime/kernel.js";
import { resolveToolCallCorrelation } from "./runtime/tool-correlation.js";
import {
  adapterActivationError,
  adapterIdForHarnessMode,
  ensureRegisteredAdapter,
} from "./runtime/adapter-selection.js";
import {
  activeControlToolOwnerId,
  AGENT_CONTROL_TOOL_NAMES,
  SWIFT_ADVERTISED_AGENT_CONTROL_TOOL_NAMES,
  controlRequestKey,
  handleAgentControlToolCall,
  isAgentControlToolName,
  registerSignedDirectControlOwner,
  resolveControlRequestContext,
  withMergedOwnerGuard,
  DEFAULT_LOCAL_OWNER_ID,
  type AgentControlToolContext,
  type ResolvedControlRequestContext,
} from "./runtime/control-tools.js";
import { SqliteAgentStore } from "./runtime/sqlite-store.js";
import { OmiArtifactStorage, defaultArtifactRoot } from "./runtime/artifact-storage.js";
import { configuredPiMonoMaxWorkers } from "./runtime/worker-pool.js";
import { failureFromError } from "./runtime/failures.js";
import type { ConversationTurnImportEntry } from "./runtime/conversation-turns.js";

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

function withQueryCorrelation<T extends OutboundMessageDraft>(
  msg: T,
  query: QueryMessage,
  adapterSessionId?: string
): T {
  return {
    ...msg,
    protocolVersion: PROTOCOL_VERSION,
    requestId: query.requestId,
    clientId: query.clientId,
    sessionId: query.sessionId,
    runId: query.runId,
    attemptId: query.attemptId,
    eventId: query.eventId,
    adapterSessionId,
  };
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
const activeControlToolOwnersByRequest = new Map<string, string>();
const activeControlToolOwnersByRun = new Map<string, string>();
const activeControlToolOwnersByAttempt = new Map<string, string>();
const activeControlToolRequestKeyByRun = new Map<string, string>();
const activeControlToolAttemptIdsByRun = new Map<string, Set<string>>();
let toolCallCorrelation:
  | ((input: { requestId?: string; clientId?: string; adapterId?: string }) => Partial<QueryScopedOutbound>)
  | undefined;

// Pending tool call promises — resolved when Swift sends back results
const pendingToolCalls = new Map<
  string,
  {
    client: Socket;
    callId: string;
    clientId?: string;
    requestId?: string;
    resolve: (result: string) => void;
    timeout: ReturnType<typeof setTimeout>;
  }
>();
const TERMINAL_RUN_EVENT_TYPES = new Set(["run.succeeded", "run.failed", "run.cancelled", "run.timed_out", "run.orphaned"]);
const TERMINAL_ATTEMPT_EVENT_TYPES = new Set(["attempt.failed", "attempt.cancelled", "attempt.timed_out", "attempt.orphaned"]);

function registerActiveControlOwner(requestKey: string, ownerId: string): boolean {
  const existingOwnerId = activeControlToolOwnersByRequest.get(requestKey);
  if (existingOwnerId && existingOwnerId !== ownerId) {
    throw new Error("Request owner context already active for clientId/requestId");
  }
  const inserted = !existingOwnerId;
  activeControlToolOwnersByRequest.set(requestKey, ownerId);
  return inserted;
}

function toolCallPendingKey(input: { callId: string; clientId?: string; requestId?: string }): string {
  return `scoped\0${input.clientId ?? ""}\0${input.requestId ?? ""}\0${input.callId}`;
}

/** Resolve a pending tool call with a result from Swift */
function resolveToolCall(msg: { callId: string; result: string; clientId?: string; requestId?: string }): void {
  const key = toolCallPendingKey(msg);
  const pending = pendingToolCalls.get(key);
  if (pending) {
    pendingToolCalls.delete(key);
    clearTimeout(pending.timeout);
    pending.resolve(msg.result);
  } else {
    logErr(`Warning: no pending tool call for callId=${msg.callId} clientId=${msg.clientId ?? "<missing>"} requestId=${msg.requestId ?? "<missing>"}`);
  }
}

function resolveClientToolCalls(client: Socket, result: string): void {
  for (const [key, pending] of pendingToolCalls) {
    if (pending.client !== client) continue;
    pendingToolCalls.delete(key);
    clearTimeout(pending.timeout);
    pending.resolve(result);
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
              name?: string;
              input: Record<string, unknown>;
              protocolVersion?: number;
              requestId?: string;
              clientId?: string;
              sessionId?: string;
              runId?: string;
              attemptId?: string;
              adapterSessionId?: string;
              adapterId?: string;
            };

            if (msg.type === "tool_cancel") {
              const requestId = msg.requestId?.trim();
              const clientId = msg.clientId?.trim();
              const resolvedCorrelation =
                requestId && clientId
                  ? toolCallCorrelation?.({ requestId, clientId, adapterId: msg.adapterId }) ?? {}
                  : {};
              const messageRequestIsActive = Boolean(
                requestId &&
                  clientId &&
                  resolvedCorrelation.requestId === requestId &&
                  resolvedCorrelation.clientId === clientId
              );
              const correlation = {
                ...resolvedCorrelation,
                protocolVersion: PROTOCOL_VERSION,
                ...(messageRequestIsActive && requestId ? { requestId } : {}),
                ...(messageRequestIsActive && clientId ? { clientId } : {}),
              };
              const pendingKey = toolCallPendingKey({
                callId: msg.callId,
                clientId: typeof correlation.clientId === "string" ? correlation.clientId : undefined,
                requestId: typeof correlation.requestId === "string" ? correlation.requestId : undefined,
              });
              const pending = pendingToolCalls.get(pendingKey);
              if (pending) {
                pendingToolCalls.delete(pendingKey);
                clearTimeout(pending.timeout);
              }
              send({
                type: "tool_cancel",
                callId: msg.callId,
                ...correlation,
              });
              continue;
            }

            if (msg.type === "tool_use") {
              if (!msg.name) {
                client.write(
                  JSON.stringify({
                    type: "tool_result",
                    callId: msg.callId,
                    result: "Error: missing tool name",
                  }) + "\n"
                );
                continue;
              }
              const toolName = msg.name;
              const requestId = msg.requestId?.trim();
              const clientId = msg.clientId?.trim();
              if (!requestId || !clientId) {
                client.write(
                  JSON.stringify({
                    type: "tool_result",
                    callId: msg.callId,
                    result: "Error: missing active Omi request context for tool relay",
                  }) + "\n"
                );
                continue;
              }
              const resolvedCorrelation =
                toolCallCorrelation?.({ requestId, clientId, adapterId: msg.adapterId }) ?? {};
              const messageRequestIsActive =
                resolvedCorrelation.requestId === requestId && resolvedCorrelation.clientId === clientId;
              if (!messageRequestIsActive) {
                client.write(
                  JSON.stringify({
                    type: "tool_result",
                    callId: msg.callId,
                    result: "Error: missing active Omi request context for tool relay",
                  }) + "\n"
                );
                continue;
              }
              if (isAgentControlToolName(toolName)) {
                void (async () => {
                  const controlToolContext = agentControlToolContext
                    ? {
                        ...agentControlToolContext,
                        getOwnerId: () =>
                          activeControlToolOwnerId({
                            requestKey: controlRequestKey({ requestId, clientId }),
                            ownerIdForRequest: (requestKey) => activeControlToolOwnersByRequest.get(requestKey),
                          }),
                      }
                    : undefined;
                  const result = controlToolContext
                    ? await handleAgentControlToolCall(controlToolContext, toolName, msg.input ?? {})
                    : JSON.stringify({
                        ok: false,
                        error: { code: "runtime_not_ready", message: "Agent runtime kernel is not ready" },
                      });
                  try {
                    client.write(
                      JSON.stringify({
                        type: "tool_result",
                        callId: msg.callId,
                        result,
                      }) + "\n"
                    );
                  } catch (err) {
                    logErr(`Failed to send control tool result to omi-tools: ${err}`);
                  }
                })();
                continue;
              }

              const correlation = {
                ...resolvedCorrelation,
                protocolVersion: PROTOCOL_VERSION,
                requestId,
                clientId,
                ...(msg.sessionId ? { sessionId: msg.sessionId } : {}),
                ...(msg.runId ? { runId: msg.runId } : {}),
                ...(msg.attemptId ? { attemptId: msg.attemptId } : {}),
                ...(msg.adapterSessionId ? { adapterSessionId: msg.adapterSessionId } : {}),
              };

              const callId = msg.callId;
              const pendingKey = toolCallPendingKey({
                callId,
                clientId,
                requestId,
              });
              if (pendingToolCalls.has(pendingKey)) {
                client.write(
                  JSON.stringify({
                    type: "tool_result",
                    callId,
                    result: "Error: duplicate tool call id",
                  }) + "\n"
                );
                continue;
              }

              // Create a promise that will be resolved when Swift responds.
              const timeout = setTimeout(() => {
                const pending = pendingToolCalls.get(pendingKey);
                if (!pending) return;
                pendingToolCalls.delete(pendingKey);
                pending.resolve("Error: timed out waiting for Swift tool result");
              }, 120_000);
              pendingToolCalls.set(pendingKey, {
                client,
                callId,
                clientId: typeof correlation.clientId === "string" ? correlation.clientId : undefined,
                requestId: typeof correlation.requestId === "string" ? correlation.requestId : undefined,
                timeout,
                resolve: (result: string) => {
                  // Send result back to the omi-tools stdio process
                  try {
                    client.write(
                      JSON.stringify({
                        type: "tool_result",
                        callId,
                        result,
                      }) + "\n"
                    );
                  } catch (err) {
                    logErr(`Failed to send tool result to omi-tools: ${err}`);
                  }
                },
              });
              send({
                type: "tool_use",
                callId,
                name: msg.name,
                input: msg.input,
                ...correlation,
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
    if (context) {
      omiToolsEnv.push(
        { name: "OMI_REQUEST_ID", value: context.requestId },
        { name: "OMI_CLIENT_ID", value: context.clientId }
      );
      if (context.protocolVersion) {
        omiToolsEnv.push({ name: "OMI_PROTOCOL_VERSION", value: String(context.protocolVersion) });
      }
      if (context.sessionId) {
        omiToolsEnv.push({ name: "OMI_SESSION_ID", value: context.sessionId });
      }
      if (context.runId) {
        omiToolsEnv.push({ name: "OMI_RUN_ID", value: context.runId });
      }
      if (context.attemptId) {
        omiToolsEnv.push({ name: "OMI_ATTEMPT_ID", value: context.attemptId });
      }
      if (context.surfaceKind) {
        omiToolsEnv.push({ name: "OMI_SURFACE_KIND", value: context.surfaceKind });
      }
      if (context.externalRefKind) {
        omiToolsEnv.push({ name: "OMI_EXTERNAL_REF_KIND", value: context.externalRefKind });
      }
      if (context.externalRefId) {
        omiToolsEnv.push({ name: "OMI_EXTERNAL_REF_ID", value: context.externalRefId });
      }
    }
    if (cwd) {
      omiToolsEnv.push({ name: "OMI_WORKSPACE", value: cwd });
    }
    if (sessionKey === "onboarding") {
      omiToolsEnv.push({ name: "OMI_ONBOARDING", value: "true" });
    }
    if (context?.screenContext === true) {
      omiToolsEnv.push({ name: "OMI_SCREEN_CONTEXT", value: "true" });
    }
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

function withControlRunCorrelation(
  name: string,
  input: Record<string, unknown>,
  fallbackClientId: string | undefined
): { input: Record<string, unknown>; requestId?: string; clientId?: string } {
  if (name !== "send_agent_message" && name !== "spawn_background_agent" && name !== "spawn_agent" && name !== "run_agent_and_wait") {
    return { input };
  }
  const requestId = randomUUID();
  const clientId = fallbackClientId ?? "omi-control-tools";
  return {
    input: {
      ...input,
      requestId,
      clientId,
    },
    requestId,
    clientId,
  };
}

function controlRunAdapterId(name: string, input: Record<string, unknown>, defaultAdapterId: string): string | undefined {
  if (name !== "send_agent_message" && name !== "spawn_background_agent" && name !== "spawn_agent" && name !== "run_agent_and_wait") {
    return undefined;
  }
  const adapterId = typeof input.adapterId === "string" && input.adapterId.trim() ? input.adapterId.trim() : undefined;
  const defaultFromInput =
    typeof input.defaultAdapterId === "string" && input.defaultAdapterId.trim() ? input.defaultAdapterId.trim() : undefined;
  return adapterId ?? defaultFromInput ?? defaultAdapterId;
}

function isLongLivedControlRun(name: string, input: Record<string, unknown>): boolean {
  return name === "spawn_background_agent" || name === "spawn_agent";
}

function controlToolResultOk(result: string): boolean {
  try {
    const parsed = JSON.parse(result) as { ok?: unknown };
    return parsed.ok === true;
  } catch {
    return false;
  }
}

function payloadObject(payloadJson: string): Record<string, unknown> {
  try {
    const parsed = JSON.parse(payloadJson) as unknown;
    return parsed && typeof parsed === "object" ? parsed as Record<string, unknown> : {};
  } catch {
    return {};
  }
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
  registry.register("acp", () => acpAdapter, 1);
  const artifactStorage = new OmiArtifactStorage({ rootDir: agentArtifactsDir() });
  logErr(`Omi artifact root: ${artifactStorage.rootDir}`);
  const kernel = new AgentRuntimeKernel({ store, registry, artifactStorage });
  kernel.subscribe((event) => {
    if (!event.runId) return;
    if (event.type === "run.queued") {
      const payload = payloadObject(event.payloadJson);
      const requestId = typeof payload.requestId === "string" ? payload.requestId : undefined;
      const clientId = typeof payload.clientId === "string" ? payload.clientId : undefined;
      const requestKey = controlRequestKey({ requestId, clientId });
      const ownerId = requestKey ? activeControlToolOwnersByRequest.get(requestKey) : undefined;
      if (requestKey && ownerId) {
        activeControlToolRequestKeyByRun.set(event.runId, requestKey);
        activeControlToolOwnersByRun.set(event.runId, ownerId);
      }
    }
    const runOwnerId = activeControlToolOwnersByRun.get(event.runId);
    if (event.attemptId && runOwnerId) {
      if (event.type === "attempt.created" || event.type === "attempt.started") {
        const previousAttemptIds = activeControlToolAttemptIdsByRun.get(event.runId);
        if (previousAttemptIds) {
          for (const attemptId of previousAttemptIds) {
            if (attemptId !== event.attemptId) {
              activeControlToolOwnersByAttempt.delete(attemptId);
            }
          }
          previousAttemptIds.clear();
        }
      }
      activeControlToolOwnersByAttempt.set(event.attemptId, runOwnerId);
      const attemptIds = activeControlToolAttemptIdsByRun.get(event.runId) ?? new Set<string>();
      attemptIds.add(event.attemptId);
      activeControlToolAttemptIdsByRun.set(event.runId, attemptIds);
    }
    if (event.attemptId && TERMINAL_ATTEMPT_EVENT_TYPES.has(event.type)) {
      activeControlToolOwnersByAttempt.delete(event.attemptId);
      const attemptIds = activeControlToolAttemptIdsByRun.get(event.runId);
      attemptIds?.delete(event.attemptId);
    }
    if (TERMINAL_RUN_EVENT_TYPES.has(event.type)) {
      const requestKey = activeControlToolRequestKeyByRun.get(event.runId);
      if (requestKey) {
        activeControlToolOwnersByRequest.delete(requestKey);
        activeControlToolRequestKeyByRun.delete(event.runId);
      }
      activeControlToolOwnersByRun.delete(event.runId);
      const attemptIds = activeControlToolAttemptIdsByRun.get(event.runId);
      if (attemptIds) {
        for (const attemptId of attemptIds) {
          activeControlToolOwnersByAttempt.delete(attemptId);
        }
        activeControlToolAttemptIdsByRun.delete(event.runId);
      }
    }
  });
  let piMonoClasses: typeof import("./adapters/pi-mono.js") | undefined;
  let piMonoAuthToken = process.env.OMI_AUTH_TOKEN;
  const piMonoAdapters = new Set<import("./adapters/pi-mono.js").PiMonoAdapter>();
  const localAcpAdapters = new Set<RuntimeAdapter>();
  const stopLocalAcpAdapters = async (): Promise<void> => {
    await Promise.all([...localAcpAdapters].map((adapter) => adapter.stop()));
  };
  let currentOwnerId = DEFAULT_LOCAL_OWNER_ID;
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
  if (!piMonoAvailable && defaultAdapterId === "pi-mono") {
    const msg = "pi-mono mode requires OMI_AUTH_TOKEN (Firebase ID token); refusing to start";
    logErr(msg);
    send({ type: "error", message: msg });
    process.exit(1);
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
    getOwnerId: () => currentOwnerId,
    buildMcpServers,
  };
  const transport = new JsonlTransport({
    kernel,
    send,
    log: logErr,
    defaultAdapterId,
    buildMcpServers,
    isRecoverableError: (error) => error instanceof AcpError && error.code === -32000,
    onRecoverableError: async () => {
      logErr("ACP auth required during query; starting OAuth flow before retry");
      await startAuthFlow();
    },
    maxRecoverableRetries: 2,
  });
  toolCallCorrelation = ({ requestId, clientId, adapterId }) => {
    return resolveToolCallCorrelation(
      { requestId, clientId, adapterId },
      {
        forRequest: (scopedRequestId, scopedClientId) =>
          transport.toolCallCorrelationForRequest(scopedRequestId, scopedClientId),
        forAdapter: (scopedAdapterId) => transport.toolCallCorrelationForAdapter(scopedAdapterId),
        unscoped: () => transport.unscopedToolCallCorrelation(),
      }
    );
  };

  // 3. Signal readiness
  send({ type: "init", sessionId: "", agentControlTools: SWIFT_ADVERTISED_AGENT_CONTROL_TOOL_NAMES });
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
          const adapterId = query.adapterId ?? defaultAdapterId;
          if (!query.clientId?.trim()) {
            throw new Error("query requires clientId");
          }
          if (!query.requestId?.trim()) {
            throw new Error("query requires requestId");
          }
          const queryOwnerId = query.ownerId?.trim() || currentOwnerId;
          query.ownerId = queryOwnerId;
          query.requestId = query.requestId.trim();
          const queryRequestId = query.requestId;
          const queryOwnerKey = controlRequestKey({ requestId: queryRequestId, clientId: query.clientId });
          const insertedOwner = queryOwnerKey ? registerActiveControlOwner(queryOwnerKey, queryOwnerId) : false;
          currentOwnerId = queryOwnerId;
          try {
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
          } finally {
            if (queryOwnerKey && insertedOwner) {
              activeControlToolOwnersByRequest.delete(queryOwnerKey);
            }
          }
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
        transport.handleWarmup(wm);
        break;
      }

      case "tool_result":
        resolveToolCall(msg);
        break;

      case "control_tool": {
        const control = msg as ControlToolRequestMessage;
        const requestId = control.requestId.trim();
        const requestKey = controlRequestKey({ requestId, clientId: control.clientId });
        const activeOwnerId = requestKey ? activeControlToolOwnersByRequest.get(requestKey) : undefined;
        let controlContext;
        try {
          controlContext = resolveControlRequestContext({
            ownerGuard: control.ownerId,
            activeOwnerId,
            requireActiveOwner: true,
            requireOwnerGuard: true,
            requestId,
            clientId: control.clientId,
          });
        } catch (error) {
          send({
            type: "control_tool_result",
            protocolVersion: control.protocolVersion,
            requestId,
            clientId: control.clientId,
            name: control.name,
            result: JSON.stringify({
              ok: false,
              error: {
                code: "invalid_owner_id",
                message: error instanceof Error ? error.message : String(error),
              },
            }),
          });
          break;
        }
        const controlOwnerKey = controlContext.requestKey;
        let controlInput;
        let controlRunCorrelation: { requestId?: string; clientId?: string } = {};
        let controlRunOwnerKey: string | undefined;
        let preserveControlRunOwner = false;
        let controlRunOwnerInserted = false;
        try {
          controlInput = withMergedOwnerGuard(control.input ?? {}, controlContext.ownerGuard, controlContext.activeOwnerId);
          const correlated = withControlRunCorrelation(control.name, controlInput, control.clientId);
          controlInput = correlated.input;
          controlRunCorrelation = { requestId: correlated.requestId, clientId: correlated.clientId };
          const adapterId = controlRunAdapterId(control.name, controlInput, defaultAdapterId);
          if (adapterId && correlated.requestId && correlated.clientId) {
            controlRunOwnerKey = controlRequestKey({ requestId: correlated.requestId, clientId: correlated.clientId });
            if (controlRunOwnerKey) {
              controlRunOwnerInserted = registerActiveControlOwner(controlRunOwnerKey, controlContext.activeOwnerId);
            }
            transport.registerExternalRequestContext({
              requestId: correlated.requestId,
              clientId: correlated.clientId,
              ownerId: controlContext.activeOwnerId,
              adapterId,
            });
          }
        } catch (error) {
          if (controlRunOwnerKey && controlRunOwnerInserted) {
            activeControlToolOwnersByRequest.delete(controlRunOwnerKey);
          }
          if (controlRunCorrelation.requestId && controlRunCorrelation.clientId && controlRunOwnerInserted) {
            transport.releaseExternalRequestContext(controlRunCorrelation.requestId, controlRunCorrelation.clientId);
          }
          send({
            type: "control_tool_result",
            protocolVersion: control.protocolVersion,
            requestId,
            clientId: control.clientId,
            name: control.name,
            result: JSON.stringify({
              ok: false,
              error: {
                code: "invalid_owner_id",
                message: error instanceof Error ? error.message : String(error),
              },
            }),
          });
          break;
        }
        try {
          if (controlOwnerKey && activeControlToolOwnersByRequest.get(controlOwnerKey) !== controlContext.activeOwnerId) {
            throw new Error("Request owner context is not active for clientId/requestId");
          }
        } catch (error) {
          if (controlRunOwnerKey && controlRunOwnerInserted) {
            activeControlToolOwnersByRequest.delete(controlRunOwnerKey);
          }
          if (controlRunCorrelation.requestId && controlRunCorrelation.clientId && controlRunOwnerInserted) {
            transport.releaseExternalRequestContext(controlRunCorrelation.requestId, controlRunCorrelation.clientId);
          }
          send({
            type: "control_tool_result",
            protocolVersion: control.protocolVersion,
            requestId,
            clientId: control.clientId,
            name: control.name,
            result: JSON.stringify({
              ok: false,
              error: {
                code: "control_context_conflict",
                message: error instanceof Error ? error.message : String(error),
              },
            }),
          });
          break;
        }
        const result = agentControlToolContext
          ? await (async () => {
              try {
                const toolResult = await handleAgentControlToolCall(
                  {
                    ...agentControlToolContext,
                    trustedUserControl: false,
                    getOwnerId: () =>
                      activeControlToolOwnerId({
                        requestKey: controlOwnerKey,
                        ownerIdForRequest: (key) => activeControlToolOwnersByRequest.get(key),
                      }),
                  },
                  control.name,
                  controlInput,
                );
                preserveControlRunOwner = isLongLivedControlRun(control.name, controlInput) && controlToolResultOk(toolResult);
                return toolResult;
              } finally {
                if (controlRunOwnerKey && !preserveControlRunOwner && controlRunOwnerInserted) {
                  activeControlToolOwnersByRequest.delete(controlRunOwnerKey);
                }
                if (!preserveControlRunOwner && controlRunCorrelation.requestId && controlRunCorrelation.clientId && controlRunOwnerInserted) {
                  transport.releaseExternalRequestContext(controlRunCorrelation.requestId, controlRunCorrelation.clientId);
                }
              }
            })()
          : (() => {
              if (controlRunOwnerKey && !preserveControlRunOwner && controlRunOwnerInserted) {
                activeControlToolOwnersByRequest.delete(controlRunOwnerKey);
              }
              if (!preserveControlRunOwner && controlRunCorrelation.requestId && controlRunCorrelation.clientId && controlRunOwnerInserted) {
                transport.releaseExternalRequestContext(controlRunCorrelation.requestId, controlRunCorrelation.clientId);
              }
              return JSON.stringify({
                ok: false,
                error: { code: "runtime_not_ready", message: "Agent runtime kernel is not ready" },
              });
            })();
        send({
          type: "control_tool_result",
          protocolVersion: control.protocolVersion,
          requestId,
          clientId: control.clientId,
          name: control.name,
          result,
        });
        break;
      }

      case "direct_control_tool": {
        const control = msg as DirectControlToolRequestMessage;
        if (!control.clientId?.trim()) {
          send({
            type: "control_tool_result",
            protocolVersion: PROTOCOL_VERSION,
            requestId: control.requestId?.trim(),
            clientId: control.clientId,
            name: control.name,
            result: JSON.stringify({
              ok: false,
              error: { code: "invalid_request", message: "direct control requires clientId" },
            }),
          });
          break;
        }
        if (!control.requestId?.trim()) {
          send({
            type: "control_tool_result",
            protocolVersion: PROTOCOL_VERSION,
            requestId: control.requestId?.trim(),
            clientId: control.clientId,
            name: control.name,
            result: JSON.stringify({
              ok: false,
              error: { code: "invalid_request", message: "direct control requires requestId" },
            }),
          });
          break;
        }
        const requestId = control.requestId.trim();
        if (!isAgentControlToolName(control.name)) {
          send({
            type: "control_tool_result",
            protocolVersion: control.protocolVersion,
            requestId,
            clientId: control.clientId,
            name: control.name,
            result: JSON.stringify({
              ok: false,
              error: {
                code: "unsupported_direct_control_tool",
                message: `Direct app control cannot execute ${control.name}`,
              },
            }),
          });
          break;
        }

        const requestKey = controlRequestKey({ requestId, clientId: control.clientId });
        let directControlOwnerInserted = registerSignedDirectControlOwner({
          requestKey,
          ownerGuard: control.ownerId,
          ownerIdForRequest: (key) => activeControlToolOwnersByRequest.get(key),
          registerOwner: registerActiveControlOwner,
        });
        const releaseDirectControlOwner = () => {
          if (requestKey && directControlOwnerInserted) {
            activeControlToolOwnersByRequest.delete(requestKey);
            directControlOwnerInserted = false;
          }
        };

        let controlContext: ResolvedControlRequestContext;
        let controlInput: Record<string, unknown>;
        try {
          controlContext = resolveControlRequestContext({
            ownerGuard: control.ownerId,
            activeOwnerId: requestKey ? activeControlToolOwnersByRequest.get(requestKey) : undefined,
            requireActiveOwner: true,
            requireOwnerGuard: true,
            requestId,
            clientId: control.clientId,
          });
          controlInput = withMergedOwnerGuard(control.input ?? {}, controlContext.ownerGuard, controlContext.activeOwnerId);
        } catch (error) {
          releaseDirectControlOwner();
          send({
            type: "control_tool_result",
            protocolVersion: control.protocolVersion,
            requestId,
            clientId: control.clientId,
            name: control.name,
            result: JSON.stringify({
              ok: false,
              error: {
                code: "invalid_owner_id",
                message: error instanceof Error ? error.message : String(error),
              },
            }),
          });
          break;
        }

        const result = await (async () => {
          try {
            return agentControlToolContext
              ? await handleAgentControlToolCall(
                  {
                    ...agentControlToolContext,
                    trustedUserControl: true,
                    getOwnerId: () => controlContext.activeOwnerId,
                  },
                  control.name,
                  controlInput,
                )
              : JSON.stringify({
                  ok: false,
                  error: { code: "runtime_not_ready", message: "Agent runtime kernel is not ready" },
                });
          } finally {
            releaseDirectControlOwner();
          }
        })();
        send({
          type: "control_tool_result",
          protocolVersion: control.protocolVersion,
          requestId,
          clientId: control.clientId,
          name: control.name,
          result,
        });
        break;
      }

      case "interrupt":
        logErr("Interrupt requested by user");
        transport.handleInterrupt(msg).catch((err) => {
          logErr(`Interrupt error: ${err}`);
        });
        break;

      case "clear_owner_state": {
        const ownerId = msg.ownerId?.trim() || currentOwnerId;
        const result = kernel.clearOwnerState(ownerId);
        logErr(
          `Cleared owner state for ${ownerId}: invalidated ${result.invalidatedBindingIds.length} binding(s)`,
        );
        break;
      }

      case "import_legacy_main_chat_sessions": {
        // TODO(desktop-agent-platonic-gap-closure G6): delete handler two desktop releases after platonic ships.
        const ownerId = msg.ownerId?.trim() || currentOwnerId;
        const entries = Array.isArray(msg.entries) ? msg.entries : [];
        const imported = kernel.importLegacyMainChatSessions({ ownerId, entries });
        logErr(`Imported ${imported} main-chat surface session(s) for ${ownerId}`);
        break;
      }

      case "import_conversation_turns": {
        const ownerId = msg.ownerId?.trim() || currentOwnerId;
        const surfaceKind = typeof msg.surfaceKind === "string" ? msg.surfaceKind : "";
        const externalRefKind = typeof msg.externalRefKind === "string" ? msg.externalRefKind : "";
        const externalRefId = typeof msg.externalRefId === "string" ? msg.externalRefId : "";
        const turns = Array.isArray(msg.turns) ? msg.turns : [];
        const imported = kernel.importConversationTurns({
          ownerId,
          surfaceRef: { surfaceKind, externalRefKind, externalRefId },
          turns: turns
            .map((turn): ConversationTurnImportEntry | null => {
              if (!turn || typeof turn !== "object") return null;
              const record = turn as Record<string, unknown>;
              const role = record.role === "assistant" ? "assistant" : record.role === "user" ? "user" : null;
              const content = typeof record.content === "string" ? record.content : "";
              if (!role || !content.trim()) return null;
              return {
                role,
                content,
                surfaceKind: typeof record.surfaceKind === "string" ? record.surfaceKind : undefined,
                createdAtMs: typeof record.createdAtMs === "number" ? record.createdAtMs : undefined,
                metadataJson: typeof record.metadataJson === "string" ? record.metadataJson : undefined,
              };
            })
            .filter((turn): turn is ConversationTurnImportEntry => turn !== null),
        });
        logErr(`Imported ${imported} conversation turn(s) for ${ownerId}/${surfaceKind}`);
        break;
      }

      case "merge_floating_chat_into_main_chat": {
        const merge = msg as MergeFloatingChatIntoMainChatMessage;
        const ownerId = merge.ownerId?.trim() || currentOwnerId;
        const chatId = typeof merge.chatId === "string" ? merge.chatId : "default";
        const result = kernel.mergeFloatingChatIntoMainChat({ ownerId, chatId });
        logErr(
          `Merged floating_chat into main_chat for ${ownerId}/${chatId}: `
            + `${result.mergedTurns} turn(s), removedMapping=${result.removedFloatingMapping}`,
        );
        break;
      }

      case "record_surface_turn": {
        const record = msg as RecordSurfaceTurnMessage;
        const ownerId = record.ownerId?.trim() || currentOwnerId;
        const surfaceKind = typeof record.surfaceKind === "string" ? record.surfaceKind : "";
        const externalRefKind = typeof record.externalRefKind === "string" ? record.externalRefKind : "";
        const externalRefId = typeof record.externalRefId === "string" ? record.externalRefId : "";
        const userText = typeof record.userText === "string" ? record.userText : "";
        const assistantText = typeof record.assistantText === "string" ? record.assistantText : "";
        const origin = typeof record.origin === "string" ? record.origin : "surface";
        const result = kernel.recordSurfaceTurn({
          ownerId,
          surfaceRef: { surfaceKind, externalRefKind, externalRefId },
          userText,
          assistantText,
          origin,
          interrupted: record.interrupted === true,
          idempotencyKey: typeof record.idempotencyKey === "string" ? record.idempotencyKey : undefined,
        });
        if (result.recorded) {
          send({
            type: "turn_recorded",
            protocolVersion: record.protocolVersion,
            requestId: record.requestId,
            clientId: record.clientId,
            conversationId: result.conversationId,
            surfaceKind,
            externalRefKind,
            externalRefId,
            userText: userText.trim(),
            assistantText: assistantText.trim(),
            origin,
            interrupted: record.interrupted === true,
            idempotencyKey: typeof record.idempotencyKey === "string" ? record.idempotencyKey : undefined,
            userTurnId: result.userTurn?.turnId,
            assistantTurnId: result.assistantTurn?.turnId,
          });
        }
        break;
      }

      case "get_voice_seed_context": {
        const seed = msg as GetVoiceSeedContextMessage;
        const ownerId = seed.ownerId?.trim() || currentOwnerId;
        const requestId = seed.requestId.trim();
        let conversationId = typeof seed.conversationId === "string" ? seed.conversationId : "";
        let context = "";
        if (conversationId) {
          context = kernel.getVoiceSeedContext({ conversationId });
        } else {
          const surfaceKind = typeof seed.surfaceKind === "string" ? seed.surfaceKind : "main_chat";
          const externalRefKind = typeof seed.externalRefKind === "string" ? seed.externalRefKind : "chat";
          const externalRefId = typeof seed.externalRefId === "string" ? seed.externalRefId : "default";
          const resolved = kernel.getVoiceSeedContextForSurface({
            ownerId,
            surfaceRef: { surfaceKind, externalRefKind, externalRefId },
          });
          conversationId = resolved.conversationId;
          context = resolved.context;
        }
        send({
          type: "voice_seed_context",
          protocolVersion: seed.protocolVersion,
          requestId,
          clientId: seed.clientId,
          conversationId,
          context,
        });
        break;
      }

      case "clear_owner_surface_state": {
        const clear = msg as ClearOwnerSurfaceStateMessage;
        const ownerId = clear.ownerId?.trim() || currentOwnerId;
        const chatId = typeof clear.chatId === "string" ? clear.chatId : "default";
        const result = kernel.clearOwnerMainChatTurns(ownerId, chatId);
        logErr(
          `Cleared main_chat kernel turns for ${ownerId}/${chatId}: `
            + `conversation=${result.conversationId ?? "none"}, deleted=${result.deletedTurns}`,
        );
        break;
      }

      case "get_kernel_turn_tail": {
        const tail = msg as GetKernelTurnTailMessage;
        const ownerId = tail.ownerId?.trim() || currentOwnerId;
        const requestId = tail.requestId.trim();
        const limit = typeof tail.limit === "number" ? tail.limit : 8;
        const chatId = typeof tail.chatId === "string" ? tail.chatId : "default";
        const resolved = kernel.getMainChatTurnTail(ownerId, limit, chatId);
        const turns = resolved.turns.map((turn) => {
          let origin = "";
          try {
            const metadata = JSON.parse(turn.metadataJson || "{}") as { origin?: unknown };
            origin = typeof metadata.origin === "string" ? metadata.origin : "";
          } catch {
            origin = "";
          }
          return {
            role: turn.role,
            content: turn.content,
            surfaceKind: turn.surfaceKind,
            createdAtMs: turn.createdAtMs,
            metadataJson: turn.metadataJson,
            origin,
          };
        });
        send({
          type: "kernel_turn_tail",
          protocolVersion: tail.protocolVersion,
          requestId,
          clientId: tail.clientId,
          conversationId: resolved.conversationId ?? "",
          turns,
        });
        break;
      }

      case "project_cross_surface_turn": {
        const project = msg as ProjectCrossSurfaceTurnMessage;
        const ownerId = project.ownerId?.trim() || currentOwnerId;
        const surfaceKind = typeof project.surfaceKind === "string" ? project.surfaceKind : "main_chat";
        const externalRefKind = typeof project.externalRefKind === "string" ? project.externalRefKind : "chat";
        const externalRefId = typeof project.externalRefId === "string" ? project.externalRefId : "default";
        const userText = typeof project.userText === "string" ? project.userText : "";
        const assistantText = typeof project.assistantText === "string" ? project.assistantText : "";
        const origin = typeof project.origin === "string" ? project.origin : "surface";
        const result = kernel.projectCrossSurfaceTurn({
          ownerId,
          targetSurfaceRef: { surfaceKind, externalRefKind, externalRefId },
          userText,
          assistantText,
          origin,
          idempotencyKey: typeof project.idempotencyKey === "string" ? project.idempotencyKey : undefined,
        });
        if (result.recorded) {
          send({
            type: "turn_recorded",
            protocolVersion: project.protocolVersion,
            requestId: project.requestId,
            clientId: project.clientId,
            conversationId: result.conversationId,
            surfaceKind,
            externalRefKind,
            externalRefId,
            userText: userText.trim(),
            assistantText: assistantText.trim(),
            origin,
            interrupted: false,
            idempotencyKey: typeof project.idempotencyKey === "string" ? project.idempotencyKey : undefined,
            userTurnId: result.userTurn?.turnId,
            assistantTurnId: result.assistantTurn?.turnId,
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
        currentOwnerId = rtm.ownerId ?? DEFAULT_LOCAL_OWNER_ID;
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
