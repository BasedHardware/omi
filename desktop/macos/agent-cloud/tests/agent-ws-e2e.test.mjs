// Hermetic WS e2e: spawns the real agent server (agent.mjs --serve) with the
// scripted SDK fixture and drives it over a real WebSocket. Asserts the client
// stream contract that experiments showed users depend on: text streams as
// deltas, subagent tool starts surface as progress, subagent internal text
// never leaks, and stopped turns are marked interrupted.
import { spawn } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import Database from "better-sqlite3";
import WebSocket from "ws";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));
const TOKEN = "e2e-token";
let child = null;
let tempDir = null;
let port = null;

function freePort() {
  return new Promise((resolve, reject) => {
    const srv = createServer();
    srv.listen(0, "127.0.0.1", () => {
      const p = srv.address().port;
      srv.close(() => resolve(p));
    });
    srv.on("error", reject);
  });
}

async function waitForServer(p, timeoutMs = 15000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      await fetch(`http://127.0.0.1:${p}/`);
      return;
    } catch {
      await new Promise((r) => setTimeout(r, 100));
    }
  }
  throw new Error("agent server did not become ready");
}

function connect() {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(`ws://127.0.0.1:${port}/ws?token=${TOKEN}`);
    ws.on("open", () => resolve(ws));
    ws.on("error", reject);
  });
}

function collectUntilResult(ws) {
  return new Promise((resolve) => {
    const messages = [];
    const onMsg = (data) => {
      const msg = JSON.parse(data.toString());
      messages.push(msg);
      if (msg.type === "result" || msg.type === "error") {
        ws.off("message", onMsg);
        resolve(messages);
      }
    };
    ws.on("message", onMsg);
  });
}

beforeAll(async () => {
  tempDir = mkdtempSync(join(tmpdir(), "omi-agent-cloud-e2e-"));
  const dbPath = join(tempDir, "omi.db");
  new Database(dbPath).close(); // empty but valid sqlite file
  port = await freePort();
  child = spawn(process.execPath, [join(here, "../agent.mjs"), "--serve"], {
    env: {
      ...process.env,
      PORT: String(port),
      DB_PATH: dbPath,
      AUTH_TOKEN: TOKEN,
      OMI_AGENT_SDK_MODULE: join(here, "fixtures/fake-agent-sdk.mjs"),
      OMI_AGENT_DISABLE_UPDATES: "1",
    },
    stdio: ["ignore", "pipe", "pipe"],
  });
  await waitForServer(port);
}, 30000);

afterAll(() => {
  child?.kill();
  if (tempDir) rmSync(tempDir, { recursive: true, force: true });
});

describe("agent-cloud WS contract (e2e)", () => {
  it("streams text deltas and subagent progress without leaking subagent text", async () => {
    const ws = await connect();
    const done = collectUntilResult(ws);
    ws.send(JSON.stringify({ type: "query", prompt: "analyze my week" }));
    const messages = await done;
    ws.close();

    const result = messages.at(-1);
    expect(result.type).toBe("result");
    expect(result.text).toBe("Part one. Part two.");
    expect(result.interrupted).toBe(false);

    const deltas = messages.filter((m) => m.type === "text_delta");
    expect(deltas.length).toBeGreaterThanOrEqual(2); // streamed, not one final dump
    expect(deltas.map((m) => m.text).join("")).toContain("Part one. ");

    const subProgress = messages.filter(
      (m) => m.type === "tool_activity" && m.name === "subagent:mcp__omi-tools__execute_sql",
    );
    expect(subProgress.length).toBeGreaterThanOrEqual(1);

    // The leak canary must never reach the client in any message.
    expect(JSON.stringify(messages)).not.toContain("SECRET-INTERNAL");
  }, 20000);

  it("marks stopped turns as interrupted partial results", async () => {
    const ws = await connect();
    const done = collectUntilResult(ws);
    const firstDelta = new Promise((resolve) => {
      const onMsg = (data) => {
        const msg = JSON.parse(data.toString());
        if (msg.type === "text_delta") {
          ws.off("message", onMsg);
          resolve();
        }
      };
      ws.on("message", onMsg);
    });
    ws.send(JSON.stringify({ type: "query", prompt: "SLOW deep analysis please" }));
    await firstDelta;
    ws.send(JSON.stringify({ type: "stop" }));
    const messages = await done;
    ws.close();

    const result = messages.at(-1);
    expect(result.type).toBe("result");
    expect(result.interrupted).toBe(true);
    expect(result.text).toBe("Part one. ");
  }, 20000);
});
