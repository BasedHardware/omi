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
import { createServer as createNetServer, type Socket } from "net";
import { homedir, tmpdir } from "os";
import { unlinkSync, appendFileSync } from "fs";
import type {
  InboundMessage,
  OutboundMessage,
  QueryScopedOutbound,
  QueryMessage,
  ProtocolVersion,
  WarmupMessage,
  RefreshTokenMessage,
  AuthMethod,
} from "./protocol.js";
import { requestIdFor } from "./protocol.js";
import { startOAuthFlow, type OAuthFlowHandle } from "./oauth-flow.js";
import type { PromptBlock } from "./adapters/interface.js";
import { detectImageMimeType } from "./mime-detect.js";
import { AcpError, AcpRuntimeAdapter } from "./adapters/acp.js";
import { AdapterRegistry } from "./runtime/adapter-registry.js";
import { JsonlCompatibilityFacade, type McpServerBuildContext } from "./runtime/compatibility-facade.js";
import { AgentRuntimeKernel } from "./runtime/kernel.js";
import { handleAgentControlToolCall, isAgentControlToolName, type AgentControlToolContext } from "./runtime/control-tools.js";
import { SqliteAgentStore } from "./runtime/sqlite-store.js";

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

function send(msg: OutboundMessage): void {
  try {
    process.stdout.write(JSON.stringify(msg) + "\n");
  } catch (err) {
    logErr(`Failed to write to stdout: ${err}`);
  }
}

function withQueryCorrelation<T extends OutboundMessage>(
  msg: T,
  query: QueryMessage,
  adapterSessionId?: string
): T {
  if (query.protocolVersion !== 2) return msg;
  return {
    ...msg,
    protocolVersion: 2,
    requestId: requestIdFor(query),
    clientId: query.clientId,
    sessionId: query.sessionId,
    runId: query.runId,
    attemptId: query.attemptId,
    eventId: query.eventId,
    adapterSessionId,
    legacyAdapterSessionId: query.legacyAdapterSessionId ?? query.resume,
  };
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

// --- OMI tools relay via Unix socket ---

let omiToolsPipePath = "";
let omiToolsClients: Socket[] = [];
let agentControlToolContext: AgentControlToolContext | undefined;
let unscopedToolCallCorrelation: (() => Partial<QueryScopedOutbound>) | undefined;

// Pending tool call promises — resolved when Swift sends back results
const pendingToolCalls = new Map<
  string,
  { resolve: (result: string) => void }
>();

/** Resolve a pending tool call with a result from Swift */
function resolveToolCall(msg: { callId: string; result: string }): void {
  const pending = pendingToolCalls.get(msg.callId);
  if (pending) {
    pending.resolve(msg.result);
    pendingToolCalls.delete(msg.callId);
  } else {
    logErr(`Warning: no pending tool call for callId=${msg.callId}`);
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
              name: string;
              input: Record<string, unknown>;
              protocolVersion?: number;
              requestId?: string;
              clientId?: string;
              sessionId?: string;
              runId?: string;
              attemptId?: string;
              adapterSessionId?: string;
              legacyAdapterSessionId?: string;
            };

            if (msg.type === "tool_use") {
              if (isAgentControlToolName(msg.name)) {
                void (async () => {
                  const result = agentControlToolContext
                    ? await handleAgentControlToolCall(agentControlToolContext, msg.name, msg.input ?? {})
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

              // Forward tool call to Swift via stdout
              const protocolVersion: ProtocolVersion | undefined =
                msg.protocolVersion === 1 || msg.protocolVersion === 2 ? msg.protocolVersion : undefined;
              const correlation = msg.requestId
                ? {
                    protocolVersion,
                    requestId: msg.requestId,
                    clientId: msg.clientId,
                    sessionId: msg.sessionId,
                    runId: msg.runId,
                    attemptId: msg.attemptId,
                    adapterSessionId: msg.adapterSessionId,
                    legacyAdapterSessionId: msg.legacyAdapterSessionId,
                  }
                : unscopedToolCallCorrelation?.() ?? {};
              send({
                type: "tool_use",
                callId: msg.callId,
                name: msg.name,
                input: msg.input,
                ...correlation,
              });

              // Create a promise that will be resolved when Swift responds
              const callId = msg.callId;
              pendingToolCalls.set(callId, {
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
            }
          } catch {
            logErr(`Failed to parse omi-tools message: ${line.slice(0, 200)}`);
          }
        }
      });

      client.on("close", () => {
        omiToolsClients = omiToolsClients.filter((c) => c !== client);
      });

      client.on("error", (err) => {
        logErr(`omi-tools client error: ${err.message}`);
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

  // omi-tools (stdio, connects back via Unix socket)
  const omiToolsEnv: Array<{ name: string; value: string }> = [
    { name: "OMI_BRIDGE_PIPE", value: omiToolsPipePath },
    { name: "OMI_QUERY_MODE", value: mode },
  ];
  if (context) {
    omiToolsEnv.push(
      { name: "OMI_OWNER_ID", value: context.ownerId },
      { name: "OMI_REQUEST_ID", value: context.requestId },
      { name: "OMI_CLIENT_ID", value: context.clientId }
    );
    if (context.protocolVersion) {
      omiToolsEnv.push({ name: "OMI_PROTOCOL_VERSION", value: String(context.protocolVersion) });
    }
    if (context.sessionId) {
      omiToolsEnv.push({ name: "OMI_SESSION_ID", value: context.sessionId });
    }
  }
  if (cwd) {
    omiToolsEnv.push({ name: "OMI_WORKSPACE", value: cwd });
  }
  if (sessionKey === "onboarding") {
    omiToolsEnv.push({ name: "OMI_ONBOARDING", value: "true" });
  }
  servers.push({
    name: "omi-tools",
    command: process.execPath,
    args: [omiToolsStdioScript],
    env: omiToolsEnv,
  });

  // Playwright MCP server
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

  return servers;
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
    send({ type: "error", message: `Uncaught: ${err.message}` });
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
  const defaultAdapterId = defaultHarnessMode === "piMono" ? "pi-mono" : "acp";
  logErr(`Default harness mode: ${defaultHarnessMode}`);

  // 1. Start Unix socket for omi-tools relay
  omiToolsPipePath = await startOmiToolsRelay();
  logErr("omi-tools relay started");
  process.env.OMI_BRIDGE_PIPE = omiToolsPipePath;

  // 2. Start the ACP subprocess
  await startAcpProcess();
  logErr("ACP subprocess spawned");

  const store = new SqliteAgentStore({ stateDir: agentStateDir() });
  const registry = new AdapterRegistry();
  registry.register("acp", () => acpAdapter, 1);
  const kernel = new AgentRuntimeKernel({ store, registry });
  let piMonoAdapter: import("./adapters/pi-mono.js").PiMonoAdapter | undefined;
  let piMonoRuntimeAdapter: import("./adapters/pi-mono.js").PiMonoRuntimeAdapter | undefined;
  let currentOwnerId = "desktop-local-user";
  let piMonoOwnerId = "desktop-local-user";
  const invalidatePiMonoBindings = (reason: string) => {
    kernel.invalidateBindings({
      ownerId: piMonoOwnerId,
      surfaceKind: "legacy_jsonl",
      defaultAdapterId: "pi-mono",
      adapterId: "pi-mono",
      reason,
    });
    logErr(`Pi-mono: subprocess restarted; active bindings invalidated (${reason})`);
  };
  const ensurePiMonoAdapter = async (authToken: string | undefined): Promise<boolean> => {
    if (piMonoRuntimeAdapter) return true;
    if (!authToken) return false;
    const { PiMonoAdapter, PiMonoRuntimeAdapter } = await import("./adapters/pi-mono.js");
    piMonoAdapter = new PiMonoAdapter({
      omiApiBaseUrl: process.env.OMI_API_BASE_URL,
      authToken,
      onRestart: (reason) => invalidatePiMonoBindings(`pi_mono_restart_${reason}`),
    });
    piMonoRuntimeAdapter = new PiMonoRuntimeAdapter(piMonoAdapter);
    await piMonoRuntimeAdapter.start();
    registry.register("pi-mono", () => piMonoRuntimeAdapter!, 1);
    logErr("Pi-mono adapter started");
    return true;
  };

  const piMonoAvailable = await ensurePiMonoAdapter(process.env.OMI_AUTH_TOKEN);
  if (!piMonoAvailable && defaultAdapterId === "pi-mono") {
    const msg = "pi-mono mode requires OMI_AUTH_TOKEN (Firebase ID token); refusing to start";
    logErr(msg);
    send({ type: "error", message: msg });
    process.exit(1);
  }
  agentControlToolContext = { kernel, getOwnerId: () => currentOwnerId };
  const facade = new JsonlCompatibilityFacade({
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
  unscopedToolCallCorrelation = () => facade.unscopedToolCallCorrelation();

  // 3. Signal readiness
  send({ type: "init", sessionId: "" });
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
          if (query.ownerId) {
            currentOwnerId = query.ownerId;
            if (adapterId === "pi-mono") {
              piMonoOwnerId = query.ownerId;
            }
          }
          if (adapterId === "acp") {
            await initializeAcp();
          }
          await facade.handleQuery(query);
        })().catch((err) => {
          logErr(`Unhandled query error: ${err}`);
          const query = msg as QueryMessage;
          send({
            type: "error",
            message: String(err),
            protocolVersion: query.protocolVersion,
            requestId: requestIdFor(query),
            clientId: query.clientId,
          });
        });
        break;

      case "warmup": {
        const wm = msg as WarmupMessage;
        facade.handleWarmup(wm);
        break;
      }

      case "tool_result":
        resolveToolCall(msg);
        break;

      case "interrupt":
        logErr("Interrupt requested by user");
        facade.handleInterrupt(msg).catch((err) => {
          logErr(`Interrupt error: ${err}`);
        });
        break;

      case "invalidate_session":
        facade.handleInvalidateSession(msg);
        break;

      case "refresh_token": {
        const rtm = msg as RefreshTokenMessage;
        process.env.OMI_AUTH_TOKEN = rtm.token;
        currentOwnerId = rtm.ownerId ?? currentOwnerId;
        piMonoOwnerId = rtm.ownerId ?? piMonoOwnerId;
        try {
          if (!piMonoAdapter) {
            await ensurePiMonoAdapter(rtm.token);
            break;
          }
          const restarted = await piMonoAdapter.updateAuthToken(rtm.token);
          if (restarted) {
            logErr("Pi-mono: token refresh restarted subprocess");
          }
        } catch (err) {
          logErr(`Pi-mono token refresh error: ${err}`);
        }
        break;
      }

      case "authenticate": {
        // Legacy fallback: OAuth flow now handles auth internally.
        // This handler is kept for backward compatibility.
        logErr(`Authentication message received from Swift (legacy fallback)`);
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
        await piMonoRuntimeAdapter?.stop();
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
    void piMonoRuntimeAdapter?.stop();
    process.exit(0);
  });
}

main().catch((err) => {
  logErr(`Fatal error: ${err}`);
  logCrash(`Fatal error: ${err}`);
  send({ type: "error", message: `Fatal: ${err}` });
  process.exit(1);
});
