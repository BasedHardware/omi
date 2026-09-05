import { execFile } from "child_process";
import { fileURLToPath } from "url";
import { promisify } from "util";

import { describe, expect, it } from "vitest";

import { stdioChildEnvironment } from "../src/runtime/mcp-stdio-client.js";

const run = promisify(execFile);
const clientUrl = new URL("../dist/runtime/mcp-stdio-client.js", import.meta.url).href;

// Replies on a later tick so the driver has to survive an idle event loop.
const SERVER =
  'const rl = require("readline").createInterface({ input: process.stdin });' +
  'rl.on("line", (line) => { const msg = JSON.parse(line); if (msg.id === undefined) return;' +
  'setTimeout(() => process.stdout.write(JSON.stringify({ jsonrpc: "2.0", id: msg.id,' +
  ' result: msg.method === "tools/list" ? { tools: [{ name: "add" }] } : {} }) + "\\n"), 150); });';

const DRIVER =
  `import { McpStdioClient } from ${JSON.stringify(clientUrl)};` +
  `const client = new McpStdioClient(process.execPath, ["-e", ${JSON.stringify(SERVER)}]);` +
  'const tools = await client.listTools();' +
  'process.stdout.write(`TOOLS:${tools.length}\\n`);' +
  'client.dispose();';

// A server that emits a bare `null` line before its real reply. `JSON.parse`
// answers that with `null`, and the old handler read `.id` straight off it.
const NULL_LINE_SERVER =
  'const rl = require("readline").createInterface({ input: process.stdin });' +
  'rl.on("line", (line) => { const msg = JSON.parse(line); if (msg.id === undefined) return;' +
  ' process.stdout.write("null\\n");' +
  ' process.stdout.write(JSON.stringify({ jsonrpc: "2.0", id: msg.id,' +
  ' result: msg.method === "tools/list" ? { tools: [{ name: "add" }] } : {} }) + "\\n"); });';

const NULL_LINE_DRIVER =
  `import { McpStdioClient } from ${JSON.stringify(clientUrl)};` +
  `const client = new McpStdioClient(process.execPath, ["-e", ${JSON.stringify(NULL_LINE_SERVER)}]);` +
  'const tools = await client.listTools();' +
  'process.stdout.write(`TOOLS:${tools.length}\\n`);' +
  'client.dispose();';

describe("McpStdioClient", () => {
  // Regression: `JSON.parse("null")` is a successful parse, so the try/catch
  // around it did not fire, and reading `.id` off null threw inside the readline
  // callback — where nothing was waiting to catch it.
  it("survives a literal null line from the server", async () => {
    const { stdout } = await run(process.execPath, ["--input-type=module", "-e", NULL_LINE_DRIVER], {
      cwd: fileURLToPath(new URL("..", import.meta.url)),
    });
    expect(stdout).toContain("TOOLS:1");
  });

  // Regression: the client unref'd its child and every stdio stream, so a host
  // with nothing else pending exited mid-RPC and orphaned the reply.
  it("keeps the host process alive until a slow reply arrives", async () => {
    const { stdout } = await run(process.execPath, ["--input-type=module", "-e", DRIVER], {
      cwd: fileURLToPath(new URL("..", import.meta.url)),
    });
    expect(stdout).toContain("TOOLS:1");
  });
});

describe("stdioChildEnvironment", () => {
  const runtimeEnv = {
    PATH: "/usr/bin:/bin",
    HOME: "/Users/tester",
    TMPDIR: "/var/folders/x",
    USER: "tester",
    SHELL: "/bin/zsh",
    OMI_AUTH_TOKEN: "secret-auth-token",
    OMI_BRIDGE_PIPE: "/tmp/secret-pipe",
    OMI_BYOK_OPENAI: "sk-secret",
    GOOGLE_APPLICATION_CREDENTIALS: "/secret/creds.json",
    FIREBASE_TOKEN: "secret-firebase-token",
    NODE_OPTIONS: "--insecure-http-parser",
  };

  it("passes only an allowlist of the runtime env and never the secrets", () => {
    const env = stdioChildEnvironment([], runtimeEnv);
    expect(env.HOME).toBe("/Users/tester");
    expect(env.TMPDIR).toBe("/var/folders/x");
    expect(env.USER).toBe("tester");
    expect(env.SHELL).toBe("/bin/zsh");
    expect(env.OMI_AUTH_TOKEN).toBeUndefined();
    expect(env.OMI_BRIDGE_PIPE).toBeUndefined();
    expect(env.OMI_BYOK_OPENAI).toBeUndefined();
    expect(env.GOOGLE_APPLICATION_CREDENTIALS).toBeUndefined();
    expect(env.FIREBASE_TOKEN).toBeUndefined();
    expect(env.NODE_OPTIONS).toBeUndefined();
  });

  it("keeps toolchain binaries findable even from a bare GUI PATH", () => {
    const env = stdioChildEnvironment([], {});
    for (const entry of ["/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin"]) {
      expect(env.PATH.split(":")).toContain(entry);
    }
    // Existing entries are kept, not reordered or duplicated.
    const kept = stdioChildEnvironment([], runtimeEnv).PATH.split(":");
    expect(kept.indexOf("/usr/bin")).toBeLessThan(kept.indexOf("/opt/homebrew/bin"));
    expect(new Set(kept).size).toBe(kept.length);
  });

  it("lets the server's configured env extend or override the allowlist", () => {
    const env = stdioChildEnvironment(
      [{ name: "CUSTOM_FLAG", value: "on" }, { name: "PATH", value: "/custom/bin" }],
      runtimeEnv,
    );
    expect(env.CUSTOM_FLAG).toBe("on");
    expect(env.PATH).toBe("/custom/bin");
  });
});
