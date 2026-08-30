import { spawn, type ChildProcess } from "child_process";
import { createInterface, type Interface as ReadlineInterface } from "readline";

import { McpClient, MCP_CLIENT_INFO, MCP_PROTOCOL_VERSION } from "./mcp-client.js";

export type { McpRemoteTool } from "./mcp-client.js";

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

  constructor(
    private readonly command: string,
    private readonly args: string[],
    private readonly env?: Array<{ name: string; value: string }>,
  ) {
    super();
  }

  private start(): void {
    if (this.child) return;
    const childEnv: Record<string, string> = { ...(process.env as Record<string, string>) };
    for (const entry of this.env ?? []) childEnv[entry.name] = entry.value;
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
    process.once("exit", () => child.kill("SIGTERM"));
    child.on("error", (err) => this.failAll(new Error(`MCP server failed to start: ${err.message}`)));
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
    this.child = null;
    this.initialized = null;
  }

  override dispose(): void {
    this.readline?.close();
    this.child?.kill("SIGTERM");
    this.failAll(new Error("MCP client disposed"));
  }

  private send(payload: Record<string, unknown>): void {
    this.child?.stdin?.write(`${JSON.stringify(payload)}\n`);
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
      await this.rpc("initialize", {
        protocolVersion: MCP_PROTOCOL_VERSION,
        capabilities: {},
        clientInfo: MCP_CLIENT_INFO,
      });
      this.send({ jsonrpc: "2.0", method: "notifications/initialized", params: {} });
    })();
    return this.initialized;
  }
}
