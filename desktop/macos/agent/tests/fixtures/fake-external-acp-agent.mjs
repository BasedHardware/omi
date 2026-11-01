#!/usr/bin/env node
// A minimal external ACP agent (Hermes-style) for runtime contract tests. It
// treats the session's MCP servers the way a real external agent does: it
// launches the "omi-tools" server from the config it was handed, with its own
// (allowlisted) environment plus that server's configured env, and calls one
// Omi tool through it over MCP. It writes the env names each configured server
// was given and the tool call's MCP response to the file named by argv[2].
import { spawn } from "node:child_process";
import { writeFileSync } from "node:fs";
import { createInterface } from "node:readline";

const [outputPath] = process.argv.slice(2);
const report = { servers: [], toolResponse: null, omiToolsStderr: "" };
let omiTools = null;

const reply = (id, result) => process.stdout.write(`${JSON.stringify({ jsonrpc: "2.0", id, result })}\n`);

function startOmiTools(server) {
  const configured = Object.fromEntries((server.env ?? []).map((entry) => [entry.name, entry.value]));
  const child = spawn(server.command, server.args ?? [], {
    env: { ...process.env, ...configured },
    stdio: ["pipe", "pipe", "pipe"],
  });
  child.stderr.on("data", (chunk) => {
    report.omiToolsStderr += chunk.toString();
  });
  const pending = new Map();
  createInterface({ input: child.stdout }).on("line", (line) => {
    const message = JSON.parse(line);
    pending.get(message.id)?.(message);
    pending.delete(message.id);
  });
  let nextId = 1;
  const request = (method, params) => new Promise((resolve) => {
    const id = nextId++;
    pending.set(id, resolve);
    child.stdin.write(`${JSON.stringify({ jsonrpc: "2.0", id, method, params })}\n`);
  });
  return { child, request };
}

async function callOmiTool() {
  if (!omiTools) return { error: "no omi-tools server configured" };
  await omiTools.request("initialize", { protocolVersion: "2024-11-05", capabilities: {}, clientInfo: { name: "fake-external-acp-agent", version: "1" } });
  omiTools.child.stdin.write(`${JSON.stringify({ jsonrpc: "2.0", method: "notifications/initialized" })}\n`);
  return omiTools.request("tools/call", { name: "execute_sql", arguments: { query: "SELECT 1" } });
}

const input = createInterface({ input: process.stdin });
input.on("close", () => {
  omiTools?.child.kill();
  process.exit(0);
});
input.on("line", async (line) => {
  if (!line.trim()) return;
  const request = JSON.parse(line);
  if (request.id === undefined) return;
  switch (request.method) {
    case "initialize":
      reply(request.id, { protocolVersion: 1, agentCapabilities: {}, authMethods: [] });
      break;
    case "session/new":
    case "session/resume":
      for (const server of request.params.mcpServers ?? []) {
        report.servers.push({ name: server.name, envNames: (server.env ?? []).map((entry) => entry.name) });
        if (server.name === "omi-tools" && !omiTools) omiTools = startOmiTools(server);
      }
      reply(request.id, request.method === "session/new" ? { sessionId: "fake-external-session-1" } : {});
      break;
    case "session/prompt":
      report.toolResponse = await callOmiTool();
      writeFileSync(outputPath, JSON.stringify(report));
      reply(request.id, { stopReason: "end_turn" });
      break;
    default:
      reply(request.id, {});
  }
});
