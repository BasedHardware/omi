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
      OMI_TURN_HEARTBEAT_MS: "100", // fast heartbeats so the held turn emits them without long waits
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

    // The leak canary must never enter the ANSWER stream (text_delta/result) —
    // ephemeral `status` progress MAY carry subagent text (researcher-progress
    // feature, presentation-only by contract).
    const answerStream = messages.filter((m) => m.type === "text_delta" || m.type === "result");
    expect(JSON.stringify(answerStream)).not.toContain("SECRET-INTERNAL");
    const progress = messages.filter((m) => m.type === "status" && m.message?.startsWith("Researching…"));
    expect(progress.length).toBeGreaterThanOrEqual(1);
  }, 20000);

  it("emits exactly one started/completed pair for a main tool seen on both channels", async () => {
    // The SDK surfaces the same main-level tool_use via stream_event AND the
    // assistant message; the server previously emitted a tool_activity from
    // both, double-counting starts and completions.
    const ws = await connect();
    const done = collectUntilResult(ws);
    ws.send(JSON.stringify({ type: "query", prompt: "MAINTOOL please" }));
    const messages = await done;
    ws.close();
    const acts = messages.filter(
      (m) => m.type === "tool_activity" && m.name === "mcp__omi-tools__execute_sql",
    );
    expect(acts.filter((a) => a.status === "started").length).toBe(1);
    expect(acts.filter((a) => a.status === "completed").length).toBe(1);
  }, 20000);

  it("keeps the session (and its context) alive across reconnects", async () => {
    // First connection: run one turn, then disconnect like a backgrounded app.
    let ws = await connect();
    let done = collectUntilResult(ws);
    ws.send(JSON.stringify({ type: "query", prompt: "COUNT check one" }));
    let messages = await done;
    const firstTurn = Number(messages.at(-1).text.match(/^turn:(\d+)$/)[1]);
    ws.close();
    await new Promise((r) => setTimeout(r, 100)); // let the server observe the close

    // Reconnect: the server must reattach the SAME session, not start fresh.
    ws = await connect();
    const hello = await new Promise((resolve) => {
      const onMsg = (data) => {
        const msg = JSON.parse(data.toString());
        if (msg.type === "session_state") {
          ws.off("message", onMsg);
          resolve(msg);
        }
      };
      ws.on("message", onMsg);
    });
    expect(hello.active).toBe(true);

    done = collectUntilResult(ws);
    ws.send(JSON.stringify({ type: "query", prompt: "COUNT check two" }));
    messages = await done;
    ws.close();
    // turn n+1 proves the same SDK session consumed both queries — a fresh
    // session would restart its count (the reconnect-amnesia regression).
    expect(messages.at(-1).text).toBe(`turn:${firstTurn + 1}`);
  }, 20000);

  it("supersedes an in-flight turn with a queued second query at the turn boundary", async () => {
    const ws = await connect();
    const results = [];
    const collected = new Promise((resolve) => {
      const onMsg = (data) => {
        const msg = JSON.parse(data.toString());
        if (msg.type === "result") {
          results.push(msg);
          if (results.length === 2) {
            ws.off("message", onMsg);
            resolve();
          }
        }
      };
      ws.on("message", onMsg);
    });
    // First query holds (SLOW); the second supersedes it mid-turn.
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
    ws.send(JSON.stringify({ type: "query", prompt: "SLOW analysis one" }));
    await firstDelta;
    ws.send(JSON.stringify({ type: "query", prompt: "quick question two" }));
    await collected;
    ws.close();

    // First turn terminalizes as an interrupted partial; the superseding turn
    // runs to completion afterwards — never interleaved into the first.
    expect(results[0].interrupted).toBe(true);
    expect(results[1].interrupted).toBe(false);
    expect(results[1].text).toBe("Part one. Part two.");
  }, 20000);

  it("emits heartbeats during silent turns and marks stopped turns as interrupted partials", async () => {
    const ws = await connect();
    const done = collectUntilResult(ws);
    // The SLOW turn holds silently after its first delta — wait for a
    // heartbeat (the silent-gap ceiling) before stopping like a user would.
    const sawHeartbeat = new Promise((resolve) => {
      let gotDelta = false;
      const onMsg = (data) => {
        const msg = JSON.parse(data.toString());
        if (msg.type === "text_delta") gotDelta = true;
        if (gotDelta && msg.type === "status" && /Still working/.test(msg.message ?? "")) {
          ws.off("message", onMsg);
          resolve();
        }
      };
      ws.on("message", onMsg);
    });
    ws.send(JSON.stringify({ type: "query", prompt: "SLOW deep analysis please" }));
    await sawHeartbeat;
    ws.send(JSON.stringify({ type: "stop" }));
    const messages = await done;
    ws.close();

    // The real SDK terminalizes interrupts with a non-success subtype — the
    // client must still receive a result marked interrupted, never an error.
    const result = messages.at(-1);
    expect(result.type).toBe("result");
    expect(result.interrupted).toBe(true);
    expect(result.text).toBe("Part one. ");
  }, 20000);

  it("recovers non-destructively after the session dies — reseeds prior context", async () => {
    // Turn 1: establish a turn in history.
    let ws = await connect();
    let done = collectUntilResult(ws);
    ws.send(JSON.stringify({ type: "query", prompt: "remember my project is omi" }));
    await done;
    ws.close();
    await new Promise((r) => setTimeout(r, 100));

    // Turn 2: crash the session (the SDK loop throws → session marked dead).
    ws = await connect();
    done = collectUntilResult(ws);
    ws.send(JSON.stringify({ type: "query", prompt: "CRASH now" }));
    await done; // resolves on the error the dead loop emits
    ws.close();
    await new Promise((r) => setTimeout(r, 100));

    // Turn 3: a fresh session is created — it must be RESEEDED with the prior
    // turn's context, not start amnesiac. The fixture echoes the reseed.
    ws = await connect();
    done = collectUntilResult(ws);
    ws.send(JSON.stringify({ type: "query", prompt: "what is my project" }));
    const messages = await done;
    ws.close();
    const result = messages.at(-1);
    expect(result.type).toBe("result");
    expect(result.text).toMatch(/^RESEEDED:/); // the new session carried a condensed seed
    expect(result.text).toContain("what is my project"); // the raw prompt rides after the seed
  }, 30000);

  it("acks a failed prewarm instead of hanging when the SDK dies before a session id", async () => {
    // Own server: the SDK stream throws before emitting session_id. Before the
    // fix, sessionIdReady never resolved, so the prewarm `.then()` never fired
    // and no prewarm_ack was ever sent — the client hung. Now the loop catch
    // resolves sessionIdReady, so prewarm acks failure within the timeout.
    const localTemp = mkdtempSync(join(tmpdir(), "omi-agent-cloud-preid-"));
    const dbPath = join(localTemp, "omi.db");
    new Database(dbPath).close();
    const p = await freePort();
    const proc = spawn(process.execPath, [join(here, "../agent.mjs"), "--serve"], {
      env: {
        ...process.env,
        PORT: String(p),
        DB_PATH: dbPath,
        AUTH_TOKEN: TOKEN,
        OMI_AGENT_SDK_MODULE: join(here, "fixtures/fake-agent-sdk.mjs"),
        OMI_AGENT_DISABLE_UPDATES: "1",
        OMI_FAKE_SDK_CRASH_BEFORE_ID: "1",
      },
      stdio: ["ignore", "pipe", "pipe"],
    });
    try {
      await waitForServer(p);
      const ws = new WebSocket(`ws://127.0.0.1:${p}/ws?token=${TOKEN}`);
      await new Promise((resolve, reject) => {
        ws.on("open", resolve);
        ws.on("error", reject);
      });
      const ack = await new Promise((resolve) => {
        ws.on("message", (data) => {
          const msg = JSON.parse(data.toString());
          if (msg.type === "prewarm_ack") resolve(msg);
        });
        ws.send(JSON.stringify({ type: "prewarm" }));
      });
      ws.close();
      expect(ack.success).toBe(false);
    } finally {
      proc.kill();
      rmSync(localTemp, { recursive: true, force: true });
    }
  }, 20000);

  it("emits a bounded string category for SDK failures", async () => {
    const ws = await connect();
    const done = collectUntilResult(ws);
    ws.send(JSON.stringify({ type: "query", prompt: "AUTH_FAIL" }));
    const messages = await done;
    ws.close();

    expect(messages.at(-1)).toMatchObject({
      type: "error",
      code: "auth",
      message: "Please reconnect your account in Settings, then try again.",
    });
  });
});
