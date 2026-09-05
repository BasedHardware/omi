import { spawn, type ChildProcess } from "child_process";
import { homedir, tmpdir } from "os";
import { createInterface, type Interface as ReadlineInterface } from "readline";

import { McpClient, MCP_CLIENT_INFO, MCP_PROTOCOL_VERSION } from "./mcp-client.js";

export type { McpRemoteTool } from "./mcp-client.js";

/**
 * The only runtime env a spawned user server receives. The agent's own
 * environment carries secrets a user server has no business seeing —
 * OMI_AUTH_TOKEN, OMI_BRIDGE_PIPE, BYOK provider keys, Firebase
 * credentials — and inheriting it handed every one of them to any command
 * the user (or a malicious registry entry) pointed at a server.
 */
const STDIO_ENV_ALLOWLIST = ["PATH", "HOME", "TMPDIR", "USER", "LOGNAME", "SHELL", "LANG"] as const;

/**
 * PATH entries appended when the host's own PATH lacks them. A bundled app is
 * launched by launchd with the bare system PATH, and a `command: "npx …"` or
 * `python3 …` server must still resolve its interpreter the way it does from a
 * login shell — the same resolution LocalMcpStore's status probe uses.
 */
const FALLBACK_PATH_ENTRIES = [
  "/opt/homebrew/bin",
  "/usr/local/bin",
  "/usr/bin",
  "/bin",
  "/usr/sbin",
  "/sbin",
];

/**
 * Build the environment handed to a user server: the allowlisted basics, a
 * PATH that can find node/python even from a GUI-spawned host, then the
 * server's own configured entries (a user's `env` block may extend or
 * override any of it — it is their server).
 */
export function stdioChildEnvironment(
  configured: ReadonlyArray<{ name: string; value: string }> = [],
  runtimeEnv: Readonly<Record<string, string | undefined>> = process.env,
): Record<string, string> {
  const env: Record<string, string> = {};
  for (const key of STDIO_ENV_ALLOWLIST) {
    const value = runtimeEnv[key];
    if (value !== undefined && value.length > 0) env[key] = value;
  }
  if (!env.HOME) env.HOME = homedir();
  if (!env.TMPDIR) env.TMPDIR = tmpdir();
  const entries = (env.PATH ?? "").split(":").filter(Boolean);
  for (const entry of FALLBACK_PATH_ENTRIES) {
    if (!entries.includes(entry)) entries.push(entry);
  }
  env.PATH = entries.join(":");
  for (const item of configured) env[item.name] = item.value;
  return env;
}

/**
 * Minimal MCP client over stdio for user-configured local servers
 * (`{"command": "npx", "args": ["@playwright/mcp@latest"]}`). Speaks the same
 * subset as McpHttpClient: initialize, tools/list, tools/call. The child dies
 * with this process; any failure surfaces as an error, never a crash.
 */
export class McpStdioClient extends McpClient {
  private child: ChildProcess | null = null;
  private readline: ReadlineInterface | null = null;
  private readonly pending = new Map<number, { resolve: (v: unknown) => void; reject: (e: Error) => void }>();
  private requestId = 0;
  private initialized: Promise<void> | null = null;
  private exitHookInstalled = false;

  constructor(
    private readonly command: string,
    private readonly args: string[],
    private readonly env?: Array<{ name: string; value: string }>,
  ) {
    super();
  }

  private start(): void {
    if (this.child) return;
    const childEnv = stdioChildEnvironment(this.env);
    const child = spawn(this.command, this.args, {
      stdio: ["pipe", "pipe", "pipe"],
      env: childEnv,
    });
    this.child = child;
    // The child must not keep this process alive, and must die with it.
    for (const stream of [child.stdin, child.stderr]) {
      (stream as unknown as { unref?: () => void } | null)?.unref?.();
    }
    this.holdEventLoop(false);
    // `once` per spawn would stack a listener per respawn; one registration for the
    // client's lifetime kills whichever child is current.
    if (!this.exitHookInstalled) {
      this.exitHookInstalled = true;
      process.once("exit", () => this.child?.kill("SIGTERM"));
    }
    child.on("error", (err) => this.failAll(new Error(`MCP server failed to start: ${err.message}`)));
    // A write to a dead child's stdin emits EPIPE on the stream itself, not on the
    // child. With no listener that is an unhandled 'error' event, which takes down
    // the whole agent process — every chat session with it — over one server that
    // exited mid-call.
    child.stdin?.on("error", (err) =>
      this.failAll(new Error(`MCP server stdin closed: ${err.message}`)),
    );
    child.on("exit", (code) => this.failAll(new Error(`MCP server exited (code ${code})`)));
    child.stderr?.on("data", () => {
      // Server logs are not part of the protocol; discard rather than pollute ours.
    });
    this.readline = createInterface({ input: child.stdout! });
    this.readline.on("line", (line) => {
      let message: { id?: number; result?: unknown; error?: { message?: string; code?: number } };
      try {
        message = JSON.parse(line);
      } catch {
        return; // non-JSON noise on stdout
      }
      if (typeof message.id !== "number") return; // notification
      const waiter = this.pending.get(message.id);
      if (!waiter) return;
      this.pending.delete(message.id);
      if (message.error) {
        waiter.reject(new Error(String(message.error.message ?? message.error.code ?? "MCP error")));
      } else {
        waiter.resolve(message.result);
      }
    });
  }

  /**
   * An idle client must not keep the host process alive, but an in-flight RPC
   * must: everything unref'd lets the loop drain while a reply is still coming,
   * which orphans the pending promise instead of resolving or rejecting it.
   */
  private holdEventLoop(active: boolean): void {
    for (const handle of [this.child, this.child?.stdout] as Array<
      { ref?: () => void; unref?: () => void } | null | undefined
    >) {
      if (active) handle?.ref?.();
      else handle?.unref?.();
    }
  }

  private failAll(error: Error): void {
    for (const waiter of this.pending.values()) waiter.reject(error);
    this.pending.clear();
    // Closing the reader here is what keeps a respawn from stacking: `start()`
    // overwrites `this.readline`, so an unclosed one would keep its dead child's
    // stdout and its line handler reachable for the rest of the session.
    this.readline?.close();
    this.readline = null;
    this.child = null;
    this.initialized = null;
  }

  override dispose(): void {
    this.readline?.close();
    this.child?.kill("SIGTERM");
    this.failAll(new Error("MCP client disposed"));
  }

  private send(payload: Record<string, unknown>): void {
    const stdin = this.child?.stdin;
    if (!stdin?.writable) throw new Error("MCP server is not accepting input");
    stdin.write(`${JSON.stringify(payload)}\n`);
  }

  protected rpc(method: string, params: Record<string, unknown>): Promise<unknown> {
    this.start();
    if (!this.child) return Promise.reject(new Error("MCP server not running"));
    const id = ++this.requestId;
    const promise = new Promise<unknown>((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
    });
    this.holdEventLoop(true);
    this.send({ jsonrpc: "2.0", id, method, params });
    return promise.finally(() => {
      if (this.pending.size === 0) this.holdEventLoop(false);
    });
  }

  protected ensureInitialized(): Promise<void> {
    this.initialized ??= (async () => {
      this.recordCapabilities(
        await this.rpc("initialize", {
          protocolVersion: MCP_PROTOCOL_VERSION,
          capabilities: {},
          clientInfo: MCP_CLIENT_INFO,
        }),
      );
      this.send({ jsonrpc: "2.0", method: "notifications/initialized", params: {} });
    })();
    return this.initialized;
  }
}
