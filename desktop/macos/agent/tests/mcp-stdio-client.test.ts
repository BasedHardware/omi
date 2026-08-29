import { execFile } from "child_process";
import { fileURLToPath } from "url";
import { promisify } from "util";

import { describe, expect, it } from "vitest";

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

describe("McpStdioClient", () => {
  // Regression: the client unref'd its child and every stdio stream, so a host
  // with nothing else pending exited mid-RPC and orphaned the reply.
  it("keeps the host process alive until a slow reply arrives", async () => {
    const { stdout } = await run(process.execPath, ["--input-type=module", "-e", DRIVER], {
      cwd: fileURLToPath(new URL("..", import.meta.url)),
    });
    expect(stdout).toContain("TOOLS:1");
  });
});
