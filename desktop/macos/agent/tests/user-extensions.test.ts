import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from "fs";
import { tmpdir } from "os";
import { join } from "path";
import { afterEach, describe, expect, it } from "vitest";

import { loadLocalMcpConfig, userSkillsPluginOptions } from "../src/runtime/user-extensions.js";

const cleanups: string[] = [];

function tempDir(): string {
  const dir = mkdtempSync(join(tmpdir(), "user-ext-"));
  cleanups.push(dir);
  return dir;
}

afterEach(() => {
  while (cleanups.length) rmSync(cleanups.pop()!, { recursive: true, force: true });
});

describe("userSkillsPluginOptions", () => {
  it("returns null for missing dir or dir without plugin manifest", () => {
    expect(userSkillsPluginOptions(undefined)).toBeNull();
    expect(userSkillsPluginOptions("/nonexistent/plugin")).toBeNull();
    expect(userSkillsPluginOptions(tempDir())).toBeNull();
  });

  it("returns plugin config when .claude-plugin/plugin.json exists", () => {
    const dir = tempDir();
    mkdirSync(join(dir, ".claude-plugin"), { recursive: true });
    writeFileSync(join(dir, ".claude-plugin", "plugin.json"), JSON.stringify({ name: "omi-user-skills" }));
    expect(userSkillsPluginOptions(dir)).toEqual({ plugins: [{ type: "local", path: dir }] });
  });
});

describe("loadLocalMcpConfig", () => {
  it("parses standard mcpServers format: stdio and url entries", () => {
    const file = join(tempDir(), "mcp.json");
    writeFileSync(
      file,
      JSON.stringify({
        mcpServers: {
          playwright: { command: "npx", args: ["@playwright/mcp@latest"], env: { DEBUG: "1" } },
          deepwiki: { url: "https://mcp.deepwiki.com/mcp" },
          linear: { url: "https://mcp.linear.app/mcp", token: "sk-x" },
          custom: { url: "https://x.example.com/mcp", headers: { "X-Api-Key": "k" } },
        },
      }),
    );
    const servers = loadLocalMcpConfig(file, new Set());
    expect(servers).toEqual([
      { name: "playwright", command: "npx", args: ["@playwright/mcp@latest"], env: [{ name: "DEBUG", value: "1" }] },
      { name: "deepwiki", type: "http", url: "https://mcp.deepwiki.com/mcp" },
      { name: "linear", type: "http", url: "https://mcp.linear.app/mcp", headers: [{ name: "Authorization", value: "Bearer sk-x" }] },
      { name: "custom", type: "http", url: "https://x.example.com/mcp", headers: [{ name: "X-Api-Key", value: "k" }] },
    ]);
  });

  it("skips reserved names, invalid entries, and malformed files", () => {
    const file = join(tempDir(), "mcp.json");
    writeFileSync(
      file,
      JSON.stringify({
        mcpServers: {
          "omi-tools": { command: "evil" },
          "bad name!": { command: "x" },
          nothing: { note: "no command or url" },
          ok: { command: "echo" },
        },
      }),
    );
    const servers = loadLocalMcpConfig(file, new Set(["omi-tools"]));
    expect(servers.map((s) => s.name)).toEqual(["ok"]);

    const broken = join(tempDir(), "broken.json");
    writeFileSync(broken, "{nope");
    expect(loadLocalMcpConfig(broken, new Set())).toEqual([]);
    expect(loadLocalMcpConfig(undefined, new Set())).toEqual([]);
  });

  it("uses auth.access_token (locally-run OAuth) as the bearer token", () => {
    const file = join(tempDir(), "mcp.json");
    writeFileSync(
      file,
      JSON.stringify({
        mcpServers: {
          linear: { url: "https://mcp.linear.app/mcp", auth: { access_token: "at-1", refresh_token: "rt" } },
        },
      }),
    );
    expect(loadLocalMcpConfig(file, new Set())).toEqual([
      { name: "linear", type: "http", url: "https://mcp.linear.app/mcp", headers: [{ name: "Authorization", value: "Bearer at-1" }] },
    ]);
  });
});

describe("McpStdioClient", () => {
  it("initializes, lists tools, and calls them over stdio", async () => {
    const { McpStdioClient } = await import("../src/runtime/mcp-stdio-client.js");
    const serverScript = `
      const rl = require("readline").createInterface({ input: process.stdin });
      rl.on("line", (line) => {
        const msg = JSON.parse(line);
        if (msg.id === undefined) return;
        const reply = (result) => process.stdout.write(JSON.stringify({ jsonrpc: "2.0", id: msg.id, result }) + "\\n");
        if (msg.method === "initialize") reply({ protocolVersion: "2025-06-18", capabilities: {}, serverInfo: { name: "fake" } });
        else if (msg.method === "tools/list") reply({ tools: [{ name: "ping", description: "pings", inputSchema: { type: "object", properties: {} } }] });
        else if (msg.method === "tools/call") reply({ content: [{ type: "text", text: "pong:" + process.env.FAKE_FLAG }] });
        else reply({});
      });
    `;
    const client = new McpStdioClient(process.execPath, ["-e", serverScript], [{ name: "FAKE_FLAG", value: "on" }]);
    try {
      const tools = await client.listTools();
      expect(tools.map((t) => t.name)).toEqual(["ping"]);
      expect(await client.callTool("ping", {})).toBe("pong:on");
    } finally {
      client.dispose();
    }
  });

  it("rejects cleanly when the command does not exist", async () => {
    const { McpStdioClient } = await import("../src/runtime/mcp-stdio-client.js");
    const client = new McpStdioClient("/nonexistent/definitely-not-a-command", []);
    await expect(client.listTools()).rejects.toThrow();
    client.dispose();
  });
});
