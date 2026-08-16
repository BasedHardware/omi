import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it } from "vitest";

import { PROTOCOL_VERSION, type OutboundMessage } from "../src/protocol.js";
import { SqliteAgentStore } from "../src/runtime/sqlite-store.js";
import { readToolInvocation } from "../src/runtime/tool-invocation-ledger.js";

interface CapturedLine {
  stream: "stdout" | "stderr";
  value: string;
}

class RuntimeProcessFixture {
  readonly root = mkdtempSync(join(tmpdir(), "omi-runtime-contract-"));
  readonly child: ChildProcessWithoutNullStreams;
  readonly lines: CapturedLine[] = [];
  private waiters: Array<() => void> = [];

  constructor() {
    const here = dirname(fileURLToPath(import.meta.url));
    this.child = spawn(process.execPath, [join(here, "../dist/index.js")], {
      env: {
        ...process.env,
        HARNESS_MODE: "piMono",
        OMI_AGENT_ALLOW_CONTROL_ONLY: "1",
        OMI_AUTH_TOKEN: "",
        OMI_AGENT_STATE_DIR: join(this.root, "state"),
        OMI_AGENT_ARTIFACTS_DIR: join(this.root, "artifacts"),
      },
      stdio: ["pipe", "pipe", "pipe"],
    });
    this.capture("stdout", this.child.stdout);
    this.capture("stderr", this.child.stderr);
  }

  send(value: Record<string, unknown>): void {
    this.child.stdin.write(`${JSON.stringify(value)}\n`);
  }

  async waitForMessage(
    predicate: (message: OutboundMessage) => boolean,
    timeoutMs = 5_000,
  ): Promise<OutboundMessage> {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      for (const line of this.lines) {
        if (line.stream !== "stdout") continue;
        const message = JSON.parse(line.value) as OutboundMessage;
        if (predicate(message)) return message;
      }
      await new Promise<void>((resolve, reject) => {
        const timeout = setTimeout(
          () => reject(new Error(`runtime message timeout; stderr=${this.stderrSummary()}`)),
          Math.max(1, deadline - Date.now()),
        );
        this.waiters.push(() => {
          clearTimeout(timeout);
          resolve();
        });
      });
    }
    throw new Error(`runtime message timeout; stderr=${this.stderrSummary()}`);
  }

  async stop(): Promise<void> {
    if (!this.child.killed && this.child.exitCode === null) {
      this.send({ type: "stop" });
      await new Promise<void>((resolve) => {
        const timeout = setTimeout(() => {
          this.child.kill("SIGKILL");
          resolve();
        }, 2_000);
        this.child.once("exit", () => {
          clearTimeout(timeout);
          resolve();
        });
      });
    }
  }

  async close(): Promise<void> {
    await this.stop();
    rmSync(this.root, { recursive: true, force: true });
  }

  private capture(stream: CapturedLine["stream"], source: NodeJS.ReadableStream): void {
    let pending = "";
    source.on("data", (chunk: Buffer | string) => {
      pending += chunk.toString();
      const parts = pending.split("\n");
      pending = parts.pop() ?? "";
      for (const value of parts) {
        if (value) this.lines.push({ stream, value });
      }
      for (const wake of this.waiters.splice(0)) wake();
    });
  }

  private stderrSummary(): string {
    return this.lines
      .filter((line) => line.stream === "stderr")
      .map((line) => line.value)
      .slice(-8)
      .join(" | ");
  }
}

describe("runtime stdio contract", () => {
  let fixture: RuntimeProcessFixture | undefined;

  afterEach(async () => {
    await fixture?.close();
    fixture = undefined;
  });

  it("accepts and idempotently projects the Swift legacy remote-turn import", async () => {
    fixture = new RuntimeProcessFixture();
    const init = await fixture.waitForMessage((message) => message.type === "init");
    expect(init).toMatchObject({
      type: "init",
      protocolVersion: PROTOCOL_VERSION,
      runtimeVersion: expect.stringMatching(/^\d+\.\d+\.\d+/),
      runtimeCapabilities: expect.arrayContaining(["journal_import_remote_turn"]),
    });
    fixture.send({ type: "refresh_owner", ownerId: "owner-contract" });

    fixture.send({
      type: "resolve_surface_session",
      protocolVersion: PROTOCOL_VERSION,
      requestId: "resolve-main",
      clientId: "contract-smoke",
      ownerId: "owner-contract",
      surfaceKind: "main_chat",
      externalRefKind: "chat",
      externalRefId: "default",
    });
    await fixture.waitForMessage(
      (message) => message.type === "surface_session_resolved" && message.requestId === "resolve-main",
    );

    const importMessage = {
      type: "journal_import_remote_turn",
      protocolVersion: PROTOCOL_VERSION,
      requestId: "import-one",
      clientId: "contract-smoke",
      ownerId: "owner-contract",
      surfaceKind: "main_chat",
      externalRefKind: "chat",
      externalRefId: "default",
      turn: {
        remoteId: "remote-contract-1",
        canonicalTurnId: "turn-contract-1",
        role: "user",
        content: "contract fixture",
        contentBlocks: [{ type: "text", id: "block-contract-1", text: "contract fixture" }],
        resources: [],
        metadataJson: "{}",
        createdAtMs: 1,
      },
    };
    fixture.send(importMessage);
    const first = await fixture.waitForMessage(
      (message) => message.type === "journal_operation_result" && message.requestId === "import-one",
    );
    expect(first).toMatchObject({
      type: "journal_operation_result",
      operation: "import_remote",
      turn: {
        turnId: "turn-contract-1",
        remoteId: "remote-contract-1",
        surfaceKind: "main_chat",
      },
    });

    fixture.send({ ...importMessage, requestId: "import-two" });
    const second = await fixture.waitForMessage(
      (message) => message.type === "journal_operation_result" && message.requestId === "import-two",
    );
    expect(second).toMatchObject({
      operation: "import_remote",
      conversationId: first.type === "journal_operation_result" ? first.conversationId : "",
      turn: { turnId: "turn-contract-1" },
    });
    expect(fixture.lines.some(
      (line) => line.stream === "stderr" && line.value.includes("Unknown message type"),
    )).toBe(false);
  });

  it("records a Swift oversized tool completion as failed after relay finalization", async () => {
    fixture = new RuntimeProcessFixture();
    await fixture.waitForMessage((message) => message.type === "init");
    fixture.send({ type: "refresh_owner", ownerId: "owner-contract" });

    fixture.send({
      type: "resolve_surface_session",
      protocolVersion: PROTOCOL_VERSION,
      requestId: "resolve-realtime",
      clientId: "contract-smoke",
      ownerId: "owner-contract",
      surfaceKind: "realtime_voice",
      externalRefKind: "chat",
      externalRefId: "contract-realtime",
    });
    const resolved = await fixture.waitForMessage(
      (message) => message.type === "surface_session_resolved" && message.requestId === "resolve-realtime",
    );
    if (resolved.type !== "surface_session_resolved") throw new Error("missing realtime session receipt");

    fixture.send({
      type: "external_surface_run_begin",
      protocolVersion: PROTOCOL_VERSION,
      requestId: "begin-realtime",
      clientId: "contract-smoke",
      ownerId: "owner-contract",
      sessionId: resolved.sessionId,
      turnId: "turn-oversized-relay",
      prompt: "Check Omi's screen-recording permission status.",
      mode: "act",
    });
    const begun = await fixture.waitForMessage(
      (message) => message.type === "external_surface_run_begin_result" && message.requestId === "begin-realtime",
    );
    if (begun.type !== "external_surface_run_begin_result" || !begun.ok || !begun.runId || !begun.attemptId) {
      throw new Error("realtime run admission failed");
    }

    fixture.send({
      type: "external_surface_tool_invoke",
      protocolVersion: PROTOCOL_VERSION,
      requestId: "invoke-swift-permission-tool",
      clientId: "contract-smoke",
      ownerId: "owner-contract",
      sessionId: begun.sessionId,
      runId: begun.runId,
      attemptId: begun.attemptId,
      invocationId: "invocation-swift-oversized-result",
      toolName: "check_permission_status",
      input: { type: "screen_recording" },
    });
    const execution = await fixture.waitForMessage(
      (message) => message.type === "authorized_tool_execution"
        && message.invocationId === "invocation-swift-oversized-result",
    );
    if (execution.type !== "authorized_tool_execution") throw new Error("missing Swift tool execution request");

    fixture.send({
      type: "authorized_tool_execution_result",
      protocolVersion: PROTOCOL_VERSION,
      invocationId: execution.invocationId,
      ownerId: execution.ownerId,
      sessionId: execution.sessionId,
      runId: execution.runId,
      attemptId: execution.attemptId,
      profileGeneration: execution.profileGeneration,
      manifestVersion: execution.manifestVersion,
      manifestDigest: execution.manifestDigest,
      daemonBootEpoch: execution.daemonBootEpoch,
      executionGeneration: execution.executionGeneration,
      inputHash: execution.inputHash,
      outcome: "succeeded",
      // Swift transport marks every ChatToolExecutor return as succeeded;
      // the structured result itself is the semantic failure signal.
      result: JSON.stringify({
        ok: false,
        error: { code: "permission_denied", message: "Screen Recording is not available." },
        snapshot: "x".repeat(9 * 1024),
      }),
    });
    const delivered = await fixture.waitForMessage(
      (message) => message.type === "external_surface_tool_result"
        && message.requestId === "invoke-swift-permission-tool",
    );
    if (delivered.type !== "external_surface_tool_result" || !delivered.ok || !delivered.result) {
      throw new Error("missing bounded external tool result");
    }
    const finalized = JSON.parse(delivered.result) as { ok: boolean; toolResultEnvelope: { status: string; truncated: boolean; fullOutputRef: string | null } };
    expect(finalized).toMatchObject({
      ok: false,
      toolResultEnvelope: {
        status: "failed",
        truncated: true,
        fullOutputRef: expect.stringMatching(/^artifact:/),
      },
    });

    await fixture.stop();
    const store = new SqliteAgentStore({ stateDir: join(fixture.root, "state"), reconcileOnOpen: false });
    expect(readToolInvocation(store, execution.invocationId)).toMatchObject({ status: "failed" });
    store.close();
  });
});
