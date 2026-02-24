/**
 * ACP Bridge — translates between OMI's JSON-lines protocol and the
 * Agent Client Protocol (ACP) used by claude-code-acp.
 *
 * Flow:
 * 1. Create Unix socket server for omi-tools relay
 * 2. Spawn claude-code-acp as subprocess (JSON-RPC over stdio)
 * 3. Initialize ACP connection
 * 4. Handle auth if required (forward to Swift, wait for user action)
 * 5. On query: create session, send prompt, translate notifications → JSON-lines
 * 6. On interrupt: cancel the session
 */

import { spawn, type ChildProcess } from "child_process";
import { createInterface } from "readline";
import { dirname, join } from "path";
import { fileURLToPath } from "url";
import { createServer as createNetServer, type Socket } from "net";
import { tmpdir } from "os";
import { unlinkSync, appendFileSync } from "fs";
import type {
  InboundMessage,
  OutboundMessage,
  QueryMessage,
  WarmupMessage,
  AuthMethod,
} from "./protocol.js";
import { startOAuthFlow, type OAuthFlowHandle } from "./oauth-flow.js";

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

function logErr(msg: string): void {
  process.stderr.write(`[acp-bridge] ${msg}\n`);
}

// --- OMI tools relay via Unix socket ---

let omiToolsPipePath = "";
let omiToolsClients: Socket[] = [];

// Pending tool call promises — resolved when Swift sends back results
const pendingToolCalls = new Map<
  string,
  { resolve: (result: string) => void }
>();

let currentMode: "ask" | "act" = "act";

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
            };

            if (msg.type === "tool_use") {
              // Forward tool call to Swift via stdout
              send({
                type: "tool_use",
                callId: msg.callId,
                name: msg.name,
                input: msg.input,
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

let acpProcess: ChildProcess | null = null;
let acpStdinWriter: ((line: string) => void) | null = null;
let acpResponseHandlers = new Map<
  number,
  { resolve: (result: unknown) => void; reject: (err: Error) => void }
>();
let acpNotificationHandler: ((method: string, params: unknown) => void) | null =
  null;
let nextRpcId = 1;

/** Send a JSON-RPC request to the ACP subprocess and wait for the response */
async function acpRequest(
  method: string,
  params: Record<string, unknown> = {}
): Promise<unknown> {
  const id = nextRpcId++;
  const msg = JSON.stringify({ jsonrpc: "2.0", id, method, params });

  return new Promise((resolve, reject) => {
    acpResponseHandlers.set(id, { resolve, reject });
    if (acpStdinWriter) {
      acpStdinWriter(msg);
    } else {
      reject(new Error("ACP process stdin not available"));
    }
  });
}

/** Send a JSON-RPC notification (no response expected) to ACP */
function acpNotify(
  method: string,
  params: Record<string, unknown> = {}
): void {
  const msg = JSON.stringify({ jsonrpc: "2.0", method, params });
  if (acpStdinWriter) {
    acpStdinWriter(msg);
  }
}

/** Start the ACP subprocess */
function startAcpProcess(): void {
  // Build environment for ACP subprocess
  // If ANTHROPIC_API_KEY is present (Mode A), keep it so ACP uses OMI's key.
  // If absent (Mode B), ACP will use user's own OAuth.
  const env = { ...process.env };
  delete env.CLAUDE_CODE_USE_VERTEX;
  // Remove CLAUDECODE so the ACP subprocess (and the Claude Code it spawns) don't
  // inherit the nested-session guard. Without this, `--resume` silently fails when
  // Claude Code detects it's being launched from inside another Claude Code session.
  delete env.CLAUDECODE;
  env.NODE_NO_WARNINGS = "1";

  // Use our patched ACP entry point (adds model selection support)
  // Located in dist/ (same as __dirname) so it's included in the app bundle
  const acpEntry = join(__dirname, "patched-acp-entry.mjs");
  const nodeBin = process.execPath;

  const mode = env.ANTHROPIC_API_KEY ? "Mode A (Omi API key)" : "Mode B (Your Claude Account / OAuth)";
  logErr(`Starting ACP subprocess [${mode}]: ${nodeBin} ${acpEntry}`);

  acpProcess = spawn(nodeBin, [acpEntry], {
    env,
    stdio: ["pipe", "pipe", "pipe"],
  });

  if (!acpProcess.stdin || !acpProcess.stdout || !acpProcess.stderr) {
    throw new Error("Failed to create ACP subprocess pipes");
  }

  // Write to ACP stdin
  acpStdinWriter = (line: string) => {
    try {
      acpProcess?.stdin?.write(line + "\n");
    } catch (err) {
      logErr(`Failed to write to ACP stdin: ${err}`);
    }
  };

  // Read ACP stdout (JSON-RPC responses and notifications)
  const rl = createInterface({
    input: acpProcess.stdout,
    terminal: false,
  });

  rl.on("line", (line: string) => {
    if (!line.trim()) return;
    try {
      const msg = JSON.parse(line) as Record<string, unknown>;

      if ("method" in msg && "id" in msg && msg.id !== null && msg.id !== undefined) {
        // Server-initiated JSON-RPC request (has both method and id, expects a response)
        const id = msg.id as number;
        const method = msg.method as string;

        if (method === "session/request_permission") {
          // Auto-approve all tool permissions (matches agent-bridge's bypassPermissions behavior)
          const params = msg.params as Record<string, unknown> | undefined;
          const options = (params?.options as Array<{ kind: string; optionId: string }>) ?? [];
          const allowAlways = options.find((o) => o.kind === "allow_always");
          const allowOnce = options.find((o) => o.kind === "allow_once");
          const optionId = allowAlways?.optionId ?? allowOnce?.optionId ?? "allow";
          logErr(`Auto-approving permission for tool (id=${id})`);
          acpStdinWriter?.(JSON.stringify({
            jsonrpc: "2.0",
            id,
            result: { outcome: { outcome: "selected", optionId } },
          }));
        } else if (method === "session/update") {
          // session/update can also arrive as a request (with id) — handle and ack
          if (acpNotificationHandler) {
            acpNotificationHandler(method, msg.params as unknown);
          }
          acpStdinWriter?.(JSON.stringify({ jsonrpc: "2.0", id, result: null }));
        } else {
          logErr(`Unhandled ACP request: ${method} (id=${id})`);
          acpStdinWriter?.(JSON.stringify({
            jsonrpc: "2.0",
            id,
            error: { code: -32601, message: `Method not handled: ${method}` },
          }));
        }
      } else if ("id" in msg && msg.id !== null && msg.id !== undefined) {
        // JSON-RPC response (has id but no method)
        const id = msg.id as number;
        const handler = acpResponseHandlers.get(id);
        if (handler) {
          acpResponseHandlers.delete(id);
          if ("error" in msg) {
            const err = msg.error as {
              code: number;
              message: string;
              data?: unknown;
            };
            const error = new AcpError(err.message, err.code, err.data);
            handler.reject(error);
          } else {
            handler.resolve(msg.result);
          }
        }
      } else if ("method" in msg) {
        // JSON-RPC notification (has method but no id)
        if (acpNotificationHandler) {
          acpNotificationHandler(
            msg.method as string,
            msg.params as unknown
          );
        }
      }
    } catch (err) {
      logErr(`Failed to parse ACP message: ${line.slice(0, 200)}`);
    }
  });

  // Read ACP stderr for logging
  acpProcess.stderr.on("data", (data: Buffer) => {
    const text = data.toString().trim();
    if (text) {
      logErr(`ACP stderr: ${text}`);
    }
  });

  acpProcess.on("exit", (code) => {
    logErr(`ACP process exited with code ${code}`);
    acpProcess = null;
    acpStdinWriter = null;
    // All sessions are lost when ACP process dies
    sessions.clear();
    activeSessionId = "";
    isInitialized = false;
    for (const [, handler] of acpResponseHandlers) {
      handler.reject(new Error(`ACP process exited (code ${code})`));
    }
    acpResponseHandlers.clear();
  });
}

class AcpError extends Error {
  code: number;
  data?: unknown;
  constructor(message: string, code: number, data?: unknown) {
    super(message);
    this.code = code;
    this.data = data;
  }
}

// --- State ---

/** Pre-warmed sessions keyed by model name */
const sessions = new Map<string, { sessionId: string; cwd: string }>();
/** The session currently being used by an active query (for interrupt) */
let activeSessionId = "";
let activeAbort: AbortController | null = null;
let interruptRequested = false;
let isInitialized = false;
let authMethods: AuthMethod[] = [];
let authResolve: (() => void) | null = null;
let preWarmPromise: Promise<void> | null = null;
let authRetryCount = 0;
const MAX_AUTH_RETRIES = 2;
let activeAuthPromise: Promise<void> | null = null;
let activeOAuthFlow: OAuthFlowHandle | null = null;

// --- Auth flow (OAuth) ---

/** Restart the ACP subprocess so it picks up freshly-stored credentials */
async function restartAcpProcess(): Promise<void> {
  logErr("Restarting ACP subprocess to pick up new credentials...");
  if (acpProcess) {
    const exitPromise = new Promise<void>((resolve) => {
      acpProcess!.once("exit", () => resolve());
    });
    acpProcess.kill();
    await exitPromise;
  }
  // State is cleaned up by the exit handler (sessions, handlers, etc.)
  startAcpProcess();
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

function buildMcpServers(mode: string, cwd?: string): McpServerConfig[] {
  const servers: McpServerConfig[] = [];

  // omi-tools (stdio, connects back via Unix socket)
  const omiToolsEnv: Array<{ name: string; value: string }> = [
    { name: "OMI_BRIDGE_PIPE", value: omiToolsPipePath },
    { name: "OMI_QUERY_MODE", value: mode },
  ];
  if (cwd) {
    omiToolsEnv.push({ name: "OMI_WORKSPACE", value: cwd });
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

// --- Session pre-warming ---

const DEFAULT_MODEL = "claude-opus-4-6";
const SONNET_MODEL = "claude-sonnet-4-6";

async function preWarmSession(cwd?: string, models?: string[]): Promise<void> {
  const warmCwd = cwd || process.env.HOME || "/";
  const warmModels = models && models.length > 0 ? models : [DEFAULT_MODEL, SONNET_MODEL];

  try {
    await initializeAcp();

    // Pre-warm each model that doesn't already have a session, in parallel
    const toWarm = warmModels.filter((m) => !sessions.has(m));
    if (toWarm.length === 0) {
      logErr("All requested models already have pre-warmed sessions");
      return;
    }

    await Promise.all(
      toWarm.map(async (warmModel) => {
        try {
          const sessionParams: Record<string, unknown> = {
            cwd: warmCwd,
            mcpServers: buildMcpServers("act", warmCwd),
          };

          // Retry once after a short delay if session/new fails
          // (ACP subprocess may not be fully ready immediately after initialize)
          let result: { sessionId: string };
          try {
            result = (await acpRequest("session/new", sessionParams)) as { sessionId: string };
          } catch (firstErr) {
            logErr(`Pre-warm session/new failed for ${warmModel}, retrying in 2s: ${firstErr}`);
            await new Promise((r) => setTimeout(r, 2000));
            result = (await acpRequest("session/new", sessionParams)) as { sessionId: string };
          }

          sessions.set(warmModel, { sessionId: result.sessionId, cwd: warmCwd });
          // Set the model via the proper ACP method (model field is stripped from session/new by schema)
          await acpRequest("session/set_model", { sessionId: result.sessionId, modelId: warmModel });
          logErr(
            `Pre-warmed session: ${result.sessionId} (cwd=${warmCwd}, model=${warmModel})`
          );
        } catch (err) {
          // If pre-warm fails with auth error, start OAuth flow.
          // Only -32000 is AUTH_REQUIRED; -32603 is a generic error (credit balance, API error, etc.)
          if (err instanceof AcpError && err.code === -32000) {
            logErr(`Pre-warm failed with auth error (code=${err.code}), starting OAuth flow`);
            await startAuthFlow();
            return; // After auth, warmup will happen on next query
          }
          logErr(`Pre-warm failed for ${warmModel}: ${err}`);
        }
      })
    );
  } catch (err) {
    logErr(`Pre-warm failed (will create on first query): ${err}`);
  }
}

// --- Handle query from Swift ---

async function handleQuery(msg: QueryMessage): Promise<void> {
  if (activeAbort) {
    activeAbort.abort();
    activeAbort = null;
  }

  const abortController = new AbortController();
  activeAbort = abortController;
  interruptRequested = false;
  authRetryCount = 0;

  let fullText = "";
  let fullPrompt = "";
  let isNewSession = false;
  const pendingTools: string[] = [];

  try {
    const mode = msg.mode ?? "act";
    currentMode = mode;
    logErr(`Query mode: ${mode}`);

    // Wait for pre-warm to finish if in progress
    if (preWarmPromise) {
      logErr("Waiting for pre-warm to complete...");
      await preWarmPromise;
      preWarmPromise = null;
    }

    // Ensure ACP is initialized
    await initializeAcp();

    // Look up a pre-warmed session for the requested model
    const requestedModel = msg.model || DEFAULT_MODEL;
    const requestedCwd = msg.cwd || process.env.HOME || "/";
    let sessionId = "";

    const existing = sessions.get(requestedModel);
    if (existing) {
      // If cwd changed, invalidate this specific session
      if (existing.cwd !== requestedCwd) {
        logErr(`Cwd changed for ${requestedModel} (${existing.cwd} -> ${requestedCwd}), creating new session`);
        sessions.delete(requestedModel);
      } else {
        sessionId = existing.sessionId;
      }
    }

    // Reuse existing session if alive, resume a persisted one, or create a new one
    if (msg.resume && !sessionId) {
      // Resume a persisted session by ID (survives process restarts via ~/.claude/projects/)
      // Fall back to session/new if the session file is gone or resume fails
      try {
        await acpRequest("session/resume", {
          sessionId: msg.resume,
          cwd: requestedCwd,
          mcpServers: buildMcpServers(mode, requestedCwd),
        });
        sessionId = msg.resume;
        sessions.set(requestedModel, { sessionId, cwd: requestedCwd });
        isNewSession = false;
        logErr(`ACP session resumed: ${sessionId}`);
      } catch (resumeErr) {
        logErr(`ACP session resume failed (will create new session): ${resumeErr}`);
        // Fall through to session/new below
      }
    }
    if (!sessionId) {
      const sessionParams: Record<string, unknown> = {
        cwd: requestedCwd,
        mcpServers: buildMcpServers(mode, requestedCwd),
      };
      const sessionResult = (await acpRequest("session/new", sessionParams)) as { sessionId: string };

      sessionId = sessionResult.sessionId;
      sessions.set(requestedModel, { sessionId, cwd: requestedCwd });
      isNewSession = true;
      // Set the model via the proper ACP method (model field is stripped from session/new by schema)
      if (requestedModel) {
        await acpRequest("session/set_model", { sessionId, modelId: requestedModel });
      }
      logErr(`ACP session created: ${sessionId} (model=${requestedModel || "default"}, cwd=${requestedCwd})`);
    } else {
      isNewSession = false;
      logErr(`Reusing existing ACP session: ${sessionId} (model=${requestedModel})`);
    }
    activeSessionId = sessionId;

    // Only prepend system prompt on the first message in a new session.
    // On subsequent messages the session already has the context.
    fullPrompt = isNewSession && msg.systemPrompt
      ? `<system>\n${msg.systemPrompt}\n</system>\n\n${msg.prompt}`
      : msg.prompt;

    // Set up notification handler for this query
    acpNotificationHandler = (method: string, params: unknown) => {
      if (abortController.signal.aborted) return;

      if (method === "session/update") {
        const p = params as Record<string, unknown>;
        handleSessionUpdate(p, pendingTools, (text) => {
          fullText += text;
        });
      }
    };

    // Send the prompt — retry with fresh session if stale
    const sendPrompt = async (): Promise<void> => {
      const promptBlocks: Array<Record<string, unknown>> = [];
      if (msg.imageBase64) {
        promptBlocks.push({ type: "image", data: msg.imageBase64, mimeType: "image/jpeg" });
      }
      promptBlocks.push({ type: "text", text: fullPrompt });

      const promptResult = (await acpRequest("session/prompt", {
        sessionId,
        prompt: promptBlocks,
      })) as {
        stopReason: string;
        // Populated by patched-acp-entry.mjs intercepting SDKResultSuccess
        usage?: { inputTokens: number; outputTokens: number; cachedReadTokens?: number | null; cachedWriteTokens?: number | null; totalTokens: number };
        _meta?: { costUsd?: number };
      };

      logErr(`Prompt completed: stopReason=${promptResult.stopReason}`);

      // Mark any remaining pending tools as completed
      for (const name of pendingTools) {
        send({ type: "tool_activity", name, status: "completed" });
      }
      pendingTools.length = 0;

      const inputTokens = promptResult.usage?.inputTokens ?? Math.ceil(fullPrompt.length / 4);
      const outputTokens = promptResult.usage?.outputTokens ?? Math.ceil(fullText.length / 4);
      const cacheReadTokens = promptResult.usage?.cachedReadTokens ?? 0;
      const cacheWriteTokens = promptResult.usage?.cachedWriteTokens ?? 0;
      const costUsd = promptResult._meta?.costUsd ?? 0;
      send({ type: "result", text: fullText, sessionId, costUsd, inputTokens, outputTokens, cacheReadTokens, cacheWriteTokens });
    };

    try {
      await sendPrompt();
    } catch (err) {
      if (abortController.signal.aborted) {
        if (interruptRequested) {
          for (const name of pendingTools) {
            send({ type: "tool_activity", name, status: "completed" });
          }
          pendingTools.length = 0;
          logErr(
            `Query interrupted by user, sending partial result (${fullText.length} chars)`
          );
          const inputTokens = Math.ceil(fullPrompt.length / 4);
          const outputTokens = Math.ceil(fullText.length / 4);
          send({ type: "result", text: fullText, sessionId, costUsd: 0, inputTokens, outputTokens, cacheReadTokens: 0, cacheWriteTokens: 0 });
        } else {
          logErr("Query aborted (superseded by new query)");
        }
        return;
      }
      // Only -32000 is AUTH_REQUIRED in the new ACP protocol.
      // -32603 is a generic internal error (API error, rate limit, etc.) — do NOT start OAuth for it.
      if (err instanceof AcpError && err.code === -32000) {
        if (authRetryCount >= MAX_AUTH_RETRIES) {
          logErr(`session/prompt auth error but max retries (${MAX_AUTH_RETRIES}) reached, giving up`);
          send({ type: "error", message: "Authentication required. Please disconnect and reconnect your Claude account in Settings." });
          return;
        }
        authRetryCount++;
        logErr(`session/prompt failed with auth error (code=${err.code}), starting OAuth flow (attempt ${authRetryCount})`);
        sessions.delete(requestedModel);
        activeSessionId = "";
        await startAuthFlow();
        return handleQuery(msg);
      }
      // If session/prompt failed while reusing an existing session, retry once with a fresh one.
      // Do NOT retry if we already started fresh (isNewSession) — that would infinite-loop.
      if (!isNewSession && sessionId) {
        logErr(`session/prompt failed with existing session, retrying with fresh session: ${err}`);
        sessions.delete(requestedModel);
        activeSessionId = "";
        return handleQuery(msg);
      }
      throw err;
    }
  } catch (err: unknown) {
    if (abortController.signal.aborted) {
      if (interruptRequested) {
        for (const name of pendingTools) {
          send({ type: "tool_activity", name, status: "completed" });
        }
        pendingTools.length = 0;
        const inputTokens = Math.ceil(fullPrompt.length / 4);
        const outputTokens = Math.ceil(fullText.length / 4);
        send({ type: "result", text: fullText, sessionId: activeSessionId, costUsd: 0, inputTokens, outputTokens });
      }
      return;
    }
    // Only -32000 is AUTH_REQUIRED in the new ACP protocol.
    // -32603 is a generic internal error — surface it as a real error, not auth.
    if (err instanceof AcpError && err.code === -32000) {
      if (authRetryCount >= MAX_AUTH_RETRIES) {
        logErr(`Query auth error but max retries (${MAX_AUTH_RETRIES}) reached, giving up`);
        send({ type: "error", message: "Authentication required. Please disconnect and reconnect your Claude account in Settings." });
        return;
      }
      authRetryCount++;
      logErr(`Query failed with auth error (code=${(err as AcpError).code}), starting OAuth flow (attempt ${authRetryCount})`);
      await startAuthFlow();
      return handleQuery(msg);
    }
    const errMsg = err instanceof Error ? err.message : String(err);
    logErr(`Query error: ${errMsg}`);
    send({ type: "error", message: errMsg });
  } finally {
    if (activeAbort === abortController) {
      activeAbort = null;
    }
    acpNotificationHandler = null;
  }
}

/** Translate ACP session/update notifications into our JSON-lines protocol.
 *
 * ACP uses `params.update.sessionUpdate` as the discriminator field:
 *   - "agent_message_chunk" → text delta (content.text)
 *   - "agent_thought_chunk" → thinking delta (content.text)
 *   - "tool_call" → tool started (title, toolCallId, kind, status)
 *   - "tool_call_update" → tool completed (toolCallId, status, content)
 *   - "plan" → plan entries (entries[].content)
 */
function handleSessionUpdate(
  params: Record<string, unknown>,
  pendingTools: string[],
  onText: (text: string) => void
): void {
  const update = params.update as Record<string, unknown> | undefined;
  if (!update) {
    logErr(`session/update missing 'update' field: ${JSON.stringify(params).slice(0, 200)}`);
    return;
  }

  const sessionUpdate = update.sessionUpdate as string;

  switch (sessionUpdate) {
    case "agent_message_chunk": {
      const content = update.content as { type: string; text?: string } | undefined;
      const text = content?.text ?? "";
      if (text) {
        // If tools were pending, they're now complete
        if (pendingTools.length > 0) {
          for (const name of pendingTools) {
            send({ type: "tool_activity", name, status: "completed" });
          }
          pendingTools.length = 0;
        }
        onText(text);
        send({ type: "text_delta", text });
      }
      break;
    }

    case "agent_thought_chunk": {
      const content = update.content as { type: string; text?: string } | undefined;
      const text = content?.text ?? "";
      if (text) {
        send({ type: "thinking_delta", text });
      }
      break;
    }

    case "tool_call": {
      const toolCallId = (update.toolCallId as string) ?? "";
      let title = (update.title as string) ?? "unknown";
      const kind = (update.kind as string) ?? "";
      const status = (update.status as string) ?? "pending";

      // Fix undefined titles for server-side tools (e.g. WebSearch, WebFetch)
      // where input may not be populated when the notification fires
      if (title.includes("undefined")) {
        const meta = update._meta as { claudeCode?: { toolName?: string } } | undefined;
        const toolName = meta?.claudeCode?.toolName;
        const rawInput = update.rawInput as Record<string, unknown> | undefined;
        if (toolName === "WebSearch" && rawInput?.query) {
          title = `"${rawInput.query}"`;
        } else if (toolName === "WebFetch" && rawInput?.url) {
          title = `Fetch ${rawInput.url}`;
        } else if (toolName) {
          title = toolName;
        }
      }

      if (status === "pending" || status === "in_progress") {
        pendingTools.push(title);
        send({
          type: "tool_activity",
          name: title,
          status: "started",
          toolUseId: toolCallId,
        });

        // Extract input from rawInput if available
        const rawInput = update.rawInput as Record<string, unknown> | undefined;
        if (rawInput && Object.keys(rawInput).length > 0) {
          send({
            type: "tool_activity",
            name: title,
            status: "started",
            toolUseId: toolCallId,
            input: rawInput,
          });
        }

        logErr(`Tool started: ${title} (id=${toolCallId}, kind=${kind})`);
      }
      break;
    }

    case "tool_call_update": {
      const toolCallId = (update.toolCallId as string) ?? "";
      const status = (update.status as string) ?? "";
      const title = (update.title as string) ?? "unknown";

      if (status === "completed" || status === "failed" || status === "cancelled") {
        // Remove from pending
        const idx = pendingTools.indexOf(title);
        if (idx >= 0) pendingTools.splice(idx, 1);

        send({
          type: "tool_activity",
          name: title,
          status: "completed",
          toolUseId: toolCallId,
        });

        // Extract output from content array or rawOutput
        let output = "";
        const contentArr = update.content as
          | Array<{ type: string; text?: string }>
          | undefined;
        if (contentArr && Array.isArray(contentArr)) {
          output = contentArr
            .filter((c) => c.type === "text" && c.text)
            .map((c) => c.text)
            .join("\n");
        }
        if (!output) {
          const rawOutput = update.rawOutput as Record<string, unknown> | undefined;
          if (rawOutput) {
            output = JSON.stringify(rawOutput);
          }
        }

        if (output) {
          const truncated =
            output.length > 2000
              ? output.slice(0, 2000) + "\n... (truncated)"
              : output;
          send({
            type: "tool_result_display",
            toolUseId: toolCallId,
            name: title,
            output: truncated,
          });
        }

        logErr(
          `Tool completed: ${title} (id=${toolCallId}) output=${output ? output.length + " chars" : "none"}`
        );
      }
      break;
    }

    case "plan": {
      const entries = update.entries as
        | Array<{ content: string; status: string }>
        | undefined;
      if (entries && Array.isArray(entries)) {
        for (const entry of entries) {
          if (entry.content) {
            send({ type: "thinking_delta", text: entry.content + "\n" });
          }
        }
      }
      break;
    }

    default:
      logErr(
        `Unknown session update type: ${sessionUpdate} — ${JSON.stringify(update).slice(0, 200)}`
      );
  }
}

// --- Error handling ---

/** Write to /tmp/acp-bridge-crash.log as fallback when stderr might be lost */
function logCrash(msg: string): void {
  try {
    const ts = new Date().toISOString();
    appendFileSync("/tmp/acp-bridge-crash.log", `[${ts}] ${msg}\n`);
  } catch {
    // ignore
  }
}

process.on("unhandledRejection", (reason) => {
  logErr(`Unhandled rejection: ${reason}`);
  logCrash(`Unhandled rejection: ${reason}`);
});

process.on("uncaughtException", (err) => {
  const code = (err as NodeJS.ErrnoException).code;
  if (code === "EPIPE" || code === "ERR_STREAM_DESTROYED") {
    logErr(`Caught ${code} in uncaughtException (subprocess pipe closed)`);
    logCrash(`Caught ${code} (pipe closed)`);
    return;
  }
  logErr(`Uncaught exception: ${err.message}\n${err.stack ?? ""}`);
  logCrash(`Uncaught exception: ${err.message}\n${err.stack ?? ""}`);
  send({ type: "error", message: `Uncaught: ${err.message}` });
  process.exit(1);
});

process.stdout.on("error", (err) => {
  if ((err as NodeJS.ErrnoException).code === "EPIPE") {
    logErr("stdout pipe closed (parent process disconnected)");
    logCrash("stdout EPIPE — parent disconnected");
    process.exit(0);
  }
  logErr(`stdout error: ${err.message}`);
  logCrash(`stdout error: ${err.message}`);
});

// --- Main ---

async function main(): Promise<void> {
  logErr(`Bridge main() starting (pid=${process.pid}, node=${process.version}, execPath=${process.execPath})`);

  // 1. Start Unix socket for omi-tools relay
  omiToolsPipePath = await startOmiToolsRelay();
  logErr("omi-tools relay started");

  // 2. Start the ACP subprocess
  startAcpProcess();
  logErr("ACP subprocess spawned");

  // 3. Signal readiness
  send({ type: "init", sessionId: "" });
  logErr("ACP Bridge started, waiting for queries...");

  // 4. Read JSON lines from Swift
  const rl = createInterface({ input: process.stdin, terminal: false });

  rl.on("line", (line: string) => {
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
        handleQuery(msg).catch((err) => {
          logErr(`Unhandled query error: ${err}`);
          send({ type: "error", message: String(err) });
        });
        break;

      case "warmup": {
        const wm = msg as WarmupMessage;
        // Support both single model (backward compat) and models array
        const models = wm.models ?? (wm.model ? [wm.model] : undefined);
        logErr(`Warmup requested (cwd=${wm.cwd || "default"}, models=${JSON.stringify(models) || "default"})`);
        preWarmPromise = preWarmSession(wm.cwd, models);
        break;
      }

      case "tool_result":
        resolveToolCall(msg);
        break;

      case "interrupt":
        logErr("Interrupt requested by user");
        interruptRequested = true;
        if (activeAbort) activeAbort.abort();
        if (activeSessionId) {
          acpNotify("session/cancel", { sessionId: activeSessionId });
        }
        break;

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
        if (activeAbort) activeAbort.abort();
        if (acpProcess) {
          acpProcess.kill();
        }
        process.exit(0);
        break;

      default:
        logErr(`Unknown message type: ${(msg as any).type}`);
    }
  });

  rl.on("close", () => {
    logErr("stdin closed, exiting");
    logCrash("stdin closed, exiting");
    if (activeAbort) activeAbort.abort();
    if (acpProcess) acpProcess.kill();
    process.exit(0);
  });
}

main().catch((err) => {
  logErr(`Fatal error: ${err}`);
  logCrash(`Fatal error: ${err}`);
  send({ type: "error", message: `Fatal: ${err}` });
  process.exit(1);
});
