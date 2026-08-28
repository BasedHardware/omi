import { spawn, type ChildProcess } from "child_process";
import { createInterface, type Interface as ReadlineInterface } from "readline";

import type { McpRemoteTool } from "./mcp-http-client.js";

/**
 * Minimal MCP client over stdio for user-configured local servers
 * (`{"command": "npx", "args": ["@playwright/mcp@latest"]}`). Speaks the same
 * subset as McpHttpClient: initialize, tools/list, tools/call. The child dies
 * with this process; any failure surfaces as an error, never a crash.
 */
export class McpStdioClient {
  private child: ChildProcess | null = null;
  private readline: ReadlineInterface | null = null;
  private readonly pending = new Map<number, { resolve: (v: unknown) => void; reject: (e: Error) => void }>();
  private requestId = 0;
  private initialized: Promise<void> | null = null;

  constructor(
    private readonly command: string,
    private readonly args: string[],
    private readonly env?: Array<{ name: string; value: string }>,
  ) {}

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
    child.unref();
    for (const stream of [child.stdin, child.stdout, child.stderr]) {
      (stream as unknown as { unref?: () => void } | null)?.unref?.();
    }
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

  private failAll(error: Error): void {
    for (const waiter of this.pending.values()) waiter.reject(error);
    this.pending.clear();
    this.child = null;
    this.initialized = null;
  }

  dispose(): void {
    this.readline?.close();
    this.child?.kill("SIGTERM");
    this.failAll(new Error("MCP client disposed"));
  }

  private send(payload: Record<string, unknown>): void {
    this.child?.stdin?.write(`${JSON.stringify(payload)}\n`);
  }

  private rpc(method: string, params: Record<string, unknown>): Promise<unknown> {
    this.start();
    if (!this.child) return Promise.reject(new Error("MCP server not running"));
    const id = ++this.requestId;
    const promise = new Promise<unknown>((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
    });
    this.send({ jsonrpc: "2.0", id, method, params });
    return promise;
  }

  private ensureInitialized(): Promise<void> {
    this.initialized ??= (async () => {
      await this.rpc("initialize", {
        protocolVersion: "2025-06-18",
        capabilities: {},
        clientInfo: { name: "omi-desktop", version: "1.0.0" },
      });
      this.send({ jsonrpc: "2.0", method: "notifications/initialized", params: {} });
    })();
    return this.initialized;
  }

  async listTools(): Promise<McpRemoteTool[]> {
    await this.ensureInitialized();
    const result = (await this.rpc("tools/list", {})) as { tools?: unknown };
    if (!Array.isArray(result?.tools)) return [];
    return result.tools.flatMap((tool) => {
      const { name, description, inputSchema } = (tool ?? {}) as Record<string, unknown>;
      if (typeof name !== "string" || !name) return [];
      return [
        {
          name,
          description: typeof description === "string" ? description : "",
          inputSchema:
            inputSchema && typeof inputSchema === "object"
              ? (inputSchema as Record<string, unknown>)
              : { type: "object", properties: {} },
        },
      ];
    });
  }

  async callTool(name: string, args: Record<string, unknown>): Promise<string> {
    await this.ensureInitialized();
    const result = (await this.rpc("tools/call", { name, arguments: args })) as {
      content?: Array<{ type?: string; text?: string }>;
      isError?: boolean;
    };
    const text = (result?.content ?? [])
      .filter((block) => block?.type === "text" && typeof block.text === "string")
      .map((block) => block.text)
      .join("\n");
    if (result?.isError) {
      throw new Error(text || `MCP tool ${name} reported an error`);
    }
    return text || JSON.stringify(result ?? {});
  }
}
