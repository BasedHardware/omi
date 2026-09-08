// Minimal MCP stdio server used by the agent tests: it speaks just enough of
// the protocol to answer initialize and tools/list, and reports — as the
// description of its single tool — which environment variables it can see.
// The tests parse that JSON to assert the spawn environment allowlist.
const rl = require("readline").createInterface({ input: process.stdin });

rl.on("line", (line) => {
  let msg;
  try {
    msg = JSON.parse(line);
  } catch {
    return; // non-JSON noise
  }
  if (msg.id === undefined) return;
  const reply = (result) =>
    process.stdout.write(JSON.stringify({ jsonrpc: "2.0", id: msg.id, result }) + "\n");
  if (msg.method === "initialize") {
    reply({
      protocolVersion: "2025-06-18",
      capabilities: {},
      serverInfo: { name: "echo-env", title: "Echo Env" },
    });
  } else if (msg.method === "tools/list") {
    reply({
      tools: [
        {
          name: "report",
          description: JSON.stringify({
            omiAuthToken: process.env.OMI_AUTH_TOKEN ?? null,
            omiBridgePipe: process.env.OMI_BRIDGE_PIPE ?? null,
            omiByokOpenai: process.env.OMI_BYOK_OPENAI ?? null,
            googleCredentials: process.env.GOOGLE_APPLICATION_CREDENTIALS ?? null,
            firebaseToken: process.env.FIREBASE_TOKEN ?? null,
            hasPath: typeof process.env.PATH === "string" && process.env.PATH.length > 0,
            hasHome: typeof process.env.HOME === "string" && process.env.HOME.length > 0,
            hasTmpdir: typeof process.env.TMPDIR === "string" && process.env.TMPDIR.length > 0,
            configuredMarker: process.env.OMI_TEST_MARKER ?? null,
          }),
          inputSchema: { type: "object", properties: {} },
        },
      ],
    });
  } else {
    reply({});
  }
});
