import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { SqliteAgentStore } from "../src/runtime/sqlite-store.js";
import { buildSessionRecap } from "../src/runtime/session-recap.js";
import { baseRunInput, createKernelHarness } from "./kernel-fakes.js";

const createdDirs: string[] = [];

function newDatabasePath(): string {
  const dir = mkdtempSync(join(tmpdir(), "session-recap-"));
  createdDirs.push(dir);
  return join(dir, "agent.db");
}

afterEach(() => {
  for (const dir of createdDirs.splice(0)) {
    rmSync(dir, { recursive: true, force: true });
  }
});

/** A session row plus the runs and attempts a recap reads, without the kernel. */
function seedSession(
  store: SqliteAgentStore,
  runs: readonly { runId: string; prompt: string; finalText: string | null; bindingId: string | null; status?: string }[],
): void {
  const now = Date.now();
  store.execute(
    `INSERT INTO sessions(session_id, owner_id, surface_kind, status, default_adapter_id,
       created_at_ms, updated_at_ms, last_activity_at_ms)
     VALUES ('ses-1', 'owner', 'floating_bar', 'open', 'fake', ?, ?, ?)`,
    [now, now, now],
  );
  const bindings = new Set<string>();
  runs.forEach((run, index) => {
    if (run.bindingId && !bindings.has(run.bindingId)) {
      bindings.add(run.bindingId);
      store.execute(
        `INSERT INTO adapter_bindings(binding_id, session_id, adapter_id, binding_generation,
           resume_fidelity, status, created_at_ms, updated_at_ms)
         VALUES (?, 'ses-1', 'fake', ?, 'none', 'stale', ?, ?)`,
        [run.bindingId, bindings.size, now, now],
      );
    }
    store.execute(
      `INSERT INTO runs(run_id, session_id, client_id, request_id, status, mode,
         input_json, final_text, created_at_ms, updated_at_ms)
       VALUES (?, 'ses-1', 'client', ?, ?, 'act', ?, ?, ?, ?)`,
      [
        run.runId,
        `req-${run.runId}`,
        run.status ?? "succeeded",
        JSON.stringify({ prompt: run.prompt }),
        run.finalText,
        now + index,
        now + index,
      ],
    );
    store.execute(
      `INSERT INTO run_attempts(attempt_id, run_id, attempt_no, status, adapter_id,
         adapter_instance_id, binding_id, created_at_ms, updated_at_ms)
       VALUES (?, ?, 1, 'succeeded', 'fake', 'node', ?, ?, ?)`,
      [`att-${run.runId}`, run.runId, run.bindingId, now + index, now + index],
    );
  });
}

describe("buildSessionRecap", () => {
  it("has nothing to say about a session with no earlier runs", () => {
    const store = new SqliteAgentStore({ databasePath: newDatabasePath(), reconcileOnOpen: false });
    seedSession(store, []);

    expect(buildSessionRecap(store, { sessionId: "ses-1", currentRunId: "run-1", currentBindingId: "bind-1" }))
      .toBeUndefined();
    store.close();
  });

  it("stays quiet while the adapter still holds the conversation itself", () => {
    const store = new SqliteAgentStore({ databasePath: newDatabasePath(), reconcileOnOpen: false });
    seedSession(store, [{ runId: "run-1", prompt: "open Safari", finalText: "Safari is open.", bindingId: "bind-1" }]);

    // Same binding: replaying these turns would only duplicate what the model sees.
    expect(buildSessionRecap(store, { sessionId: "ses-1", currentRunId: "run-2", currentBindingId: "bind-1" }))
      .toBeUndefined();
    store.close();
  });

  it("rebuilds the transcript, oldest first, for a binding that did not run it", () => {
    const store = new SqliteAgentStore({ databasePath: newDatabasePath(), reconcileOnOpen: false });
    seedSession(store, [
      { runId: "run-1", prompt: "open Safari and go to wikipedia.org", finalText: "Safari is at wikipedia.org.", bindingId: "bind-1" },
      { runId: "run-2", prompt: "search it for macOS Tahoe", finalText: "Showing results for macOS Tahoe.", bindingId: "bind-1" },
    ]);

    const recap = buildSessionRecap(store, { sessionId: "ses-1", currentRunId: "run-3", currentBindingId: "bind-2" });

    expect(recap).toBeDefined();
    expect(recap!.runCount).toBe(2);
    expect(recap!.priorBindingId).toBe("bind-1");
    expect(recap!.truncated).toBe(false);
    expect(recap!.text.indexOf("open Safari")).toBeLessThan(recap!.text.indexOf("search it"));
    expect(recap!.text).toContain("Safari is at wikipedia.org.");
    store.close();
  });

  it("reports a run that did not succeed as what it was", () => {
    const store = new SqliteAgentStore({ databasePath: newDatabasePath(), reconcileOnOpen: false });
    seedSession(store, [
      { runId: "run-1", prompt: "open Safari", finalText: "Screen Recording is not granted.", bindingId: "bind-1", status: "failed" },
    ]);

    const recap = buildSessionRecap(store, { sessionId: "ses-1", currentRunId: "run-2", currentBindingId: "bind-2" });

    expect(recap!.text).toContain("(failed)");
    expect(recap!.text).toContain("Screen Recording is not granted.");
    store.close();
  });

  it("spends a tight budget on the newest turns, because those are what a follow-up means", () => {
    const store = new SqliteAgentStore({ databasePath: newDatabasePath(), reconcileOnOpen: false });
    seedSession(store, [
      { runId: "run-1", prompt: `the oldest thing ${"x".repeat(350)}`, finalText: "old answer", bindingId: "bind-1" },
      { runId: "run-2", prompt: `the newest thing ${"y".repeat(350)}`, finalText: "new answer", bindingId: "bind-1" },
    ]);

    const recap = buildSessionRecap(store, {
      sessionId: "ses-1",
      currentRunId: "run-3",
      currentBindingId: "bind-2",
      maxChars: 500,
    });

    expect(recap!.runCount).toBe(1);
    expect(recap!.truncated).toBe(true);
    expect(recap!.text).toContain("the newest thing");
    expect(recap!.text).not.toContain("the oldest thing");
    store.close();
  });

  it("recaps what the user said, not the context wrapped around it", () => {
    const store = new SqliteAgentStore({ databasePath: newDatabasePath(), reconcileOnOpen: false });
    seedSession(store, [
      {
        runId: "run-1",
        // Both shapes that reach storage: the Swift chat clock preamble, and a
        // kernel-decorated prompt whose real message sits after the marker.
        prompt: "# Current Time\n2026-08-30T22:40:25-04:00 (America/New_York)\n\nopen Safari",
        finalText: "Safari is open.",
        bindingId: "bind-1",
      },
      {
        runId: "run-2",
        prompt: `# Screen Context\n${"noise ".repeat(200)}\n# User Message\nnow search it`,
        finalText: "Searching.",
        bindingId: "bind-1",
      },
    ]);

    const recap = buildSessionRecap(store, { sessionId: "ses-1", currentRunId: "run-3", currentBindingId: "bind-2" });

    expect(recap!.text).toContain("User: open Safari");
    expect(recap!.text).toContain("User: now search it");
    expect(recap!.text).not.toContain("America/New_York");
    expect(recap!.text).not.toContain("noise");
    store.close();
  });

  it("skips a run whose stored input carries no prompt", () => {
    const store = new SqliteAgentStore({ databasePath: newDatabasePath(), reconcileOnOpen: false });
    seedSession(store, [{ runId: "run-1", prompt: "", finalText: "answer", bindingId: "bind-1" }]);

    expect(buildSessionRecap(store, { sessionId: "ses-1", currentRunId: "run-2", currentBindingId: "bind-2" }))
      .toBeUndefined();
    store.close();
  });
});

describe("session recap in a run", () => {
  it("hands a replacement binding what the session already did", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath());
    // A background leaf: no external surface ref, so nothing replays its turns.
    const leafRunInput = {
      ...baseRunInput,
      surfaceKind: "floating_bar",
      externalRefKind: undefined,
      externalRefId: undefined,
      executionRole: "leaf" as const,
    };

    const first = await kernel.executeRun({ ...leafRunInput, requestId: "request-1", prompt: "open Safari" });
    // The process holding the transcript went away; the follow-up opens a fresh
    // adapter session that never saw the first turn.
    store.execute("UPDATE adapter_bindings SET status = 'stale'");
    await kernel.sendAgentMessage({
      ownerId: leafRunInput.ownerId,
      sessionId: first.session.sessionId,
      clientId: leafRunInput.clientId,
      requestId: "request-2",
      prompt: "now search it for macOS Tahoe",
    });

    const secondPrompt = adapter.executed[1]!.prompt
      .filter((block): block is Extract<(typeof block), { type: "text" }> => block.type === "text")
      .map((block) => block.text)
      .join("\n");
    expect(secondPrompt).toContain("Earlier In This Session");
    expect(secondPrompt).toContain("open Safari");
    expect(secondPrompt).toContain("now search it for macOS Tahoe");

    const seeded = store.allRows("SELECT payload_json FROM events WHERE type = 'binding.recap_seeded'");
    expect(seeded).toHaveLength(1);
    expect(String(seeded[0]!.payload_json)).toContain("\"outcome\":\"recovered\"");
    store.close();
  });

  it("leaves a journal-backed chat surface alone, because its snapshot already replays turns", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath());

    // baseRunInput is a task_chat surface with an external ref, so the kernel
    // gives it a conversation and its snapshot carries recentTurns.
    await kernel.executeRun({ ...baseRunInput, requestId: "request-1", prompt: "remember 8317" });
    expect(store.allRows("SELECT 1 FROM surface_conversations")).not.toHaveLength(0);
    store.execute("UPDATE adapter_bindings SET status = 'stale'");
    await kernel.executeRun({ ...baseRunInput, requestId: "request-2", prompt: "what number?" });

    const secondPrompt = adapter.executed[1]!.prompt
      .filter((block): block is Extract<(typeof block), { type: "text" }> => block.type === "text")
      .map((block) => block.text)
      .join("\n");
    expect(secondPrompt).not.toContain("Earlier In This Session");
    expect(store.allRows("SELECT 1 FROM events WHERE type = 'binding.recap_seeded'")).toHaveLength(0);
    store.close();
  });

  it("says nothing extra while the binding is still warm", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath());

    await kernel.executeRun({ ...baseRunInput, requestId: "request-1", prompt: "open Safari" });
    await kernel.executeRun({ ...baseRunInput, requestId: "request-2", prompt: "now search it" });

    const secondPrompt = adapter.executed[1]!.prompt
      .filter((block): block is Extract<(typeof block), { type: "text" }> => block.type === "text")
      .map((block) => block.text)
      .join("\n");
    expect(secondPrompt).not.toContain("Earlier In This Session");
    expect(store.allRows("SELECT 1 FROM events WHERE type = 'binding.recap_seeded'")).toHaveLength(0);
    store.close();
  });
});
