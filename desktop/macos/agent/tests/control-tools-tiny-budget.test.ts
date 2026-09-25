import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../src/runtime/tool-result-projector.js", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../src/runtime/tool-result-projector.js")>();
  return {
    ...actual,
    toolResultBudgetBytes: () => 32,
  };
});

import {
  handleAgentControlToolCall,
  type AgentControlToolContext,
} from "../src/runtime/control-tools.js";
import { baseRunInput, createKernelHarness } from "./kernel-fakes.js";

const createdDirs: string[] = [];

afterEach(() => {
  for (const dir of createdDirs.splice(0)) {
    rmSync(dir, { recursive: true, force: true });
  }
});

describe("control-tool degenerate provider budgets", () => {
  it("keeps a size-only terminal path successful under a deliberately tiny budget", async () => {
    const dir = mkdtempSync(join(tmpdir(), "omi-control-tiny-budget-"));
    createdDirs.push(dir);
    const { store, kernel } = createKernelHarness(join(dir, "kernel.sqlite3"));
    const run = await kernel.executeRun({
      ...baseRunInput,
      ownerId: "owner",
      prompt: "tiny budget projection",
      requestId: "tiny-budget-request",
    });
    const context: AgentControlToolContext = {
      kernel,
      getOwnerId: () => "owner",
      callerSessionId: run.session.sessionId,
      authorizedToolInvocation: {
        invocationId: "tiny-budget-invocation",
        runId: run.run.runId,
        attemptId: "tiny-budget-attempt",
        toolName: "get_agent_run",
      },
    };

    const raw = await handleAgentControlToolCall(context, "get_agent_run", {});
    const projected = JSON.parse(raw) as {
      ok?: unknown;
      text?: unknown;
      toolResultEnvelope?: Record<string, unknown>;
    };

    expect(projected).toMatchObject({
      ok: true,
      text: "Tool result available via fullOutputRef.",
      toolResultEnvelope: {
        status: "succeeded",
        truncated: true,
        fullOutputRef: expect.stringMatching(/^artifact:/),
      },
    });
    store.close();
  });
});
