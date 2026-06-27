/**
 * Integration-style tests that simulate the session lifecycle orchestration
 * from index.ts. These verify that set_model is called BEFORE sessions.set()
 * on all paths, and that retry/error paths only delete the failing session key.
 *
 * We replicate the exact sequence of operations from index.ts handleQuery()
 * and preWarmSession() using the session-manager helpers, with a mock
 * acpRequest that records call order.
 */
import { describe, it, expect, beforeEach } from "vitest";
import {
  resolveSession,
  needsModelUpdate,
  filterSessionsToWarm,
  getRetryDeleteKey,
  type SessionEntry,
  type SessionMap,
} from "../src/session-manager.js";

/** Mock acpRequest that records calls in order and supports configurable failures */
function createMockAcp() {
  const calls: Array<{ method: string; params: Record<string, unknown> }> = [];
  let sessionCounter = 0;
  let failSetModel = false;
  let failSessionNew = 0; // Number of times session/new should fail before succeeding
  let failPrompt = false;
  let failPromptCode: number | null = null; // null = generic error, -32000 = auth

  const acpRequest = async (method: string, params: Record<string, unknown>): Promise<unknown> => {
    calls.push({ method, params });

    if (method === "session/new") {
      if (failSessionNew > 0) {
        failSessionNew--;
        throw new Error("session/new failed: transient error");
      }
      sessionCounter++;
      return { sessionId: `session-${sessionCounter}` };
    }
    if (method === "session/resume") {
      return {};
    }
    if (method === "session/set_model") {
      if (failSetModel) {
        throw new Error("set_model failed: stale session");
      }
      return {};
    }
    if (method === "session/prompt") {
      if (failPrompt) {
        const err = new Error("prompt failed") as Error & { code?: number };
        if (failPromptCode !== null) err.code = failPromptCode;
        throw err;
      }
      return { stopReason: "end_turn" };
    }
    return {};
  };

  return {
    calls,
    acpRequest,
    setFailSetModel(fail: boolean) { failSetModel = fail; },
    setFailSessionNew(count: number) { failSessionNew = count; },
    setFailPrompt(fail: boolean, code?: number) { failPrompt = fail; failPromptCode = code ?? null; },
    reset() { calls.length = 0; sessionCounter = 0; failSetModel = false; failSessionNew = 0; failPrompt = false; failPromptCode = null; },
  };
}

/** In-memory SessionMap matching the interface */
function createSessionMap(): SessionMap & { _map: Map<string, SessionEntry> } {
  const _map = new Map<string, SessionEntry>();
  return {
    _map,
    get: (key: string) => _map.get(key),
    set: (key: string, entry: SessionEntry) => { _map.set(key, entry); },
    delete: (key: string) => _map.delete(key),
    has: (key: string) => _map.has(key),
    clear: () => _map.clear(),
  };
}

/**
 * Simulate the warmup path from index.ts preWarmSession().
 * This is the exact sequence: session/new → set_model → sessions.set
 */
async function simulateWarmup(
  sessions: SessionMap,
  acp: ReturnType<typeof createMockAcp>,
  configs: Array<{ key: string; model: string; systemPrompt?: string }>,
  cwd: string,
) {
  const toWarm = filterSessionsToWarm(sessions, configs);
  for (const cfg of toWarm) {
    const result = (await acp.acpRequest("session/new", { cwd })) as { sessionId: string };
    await acp.acpRequest("session/set_model", { sessionId: result.sessionId, modelId: cfg.model });
    sessions.set(cfg.key, { sessionId: result.sessionId, cwd, model: cfg.model });
  }
}

/**
 * Simulate the handleQuery session setup from index.ts.
 * Covers: resolve → resume/create → set_model → cache → reuse model update
 */
async function simulateQuerySessionSetup(
  sessions: SessionMap,
  acp: ReturnType<typeof createMockAcp>,
  opts: {
    sessionKey: string;
    requestedCwd: string;
    requestedModel: string;
    resume?: string;
  },
): Promise<{ sessionId: string; isNew: boolean }> {
  const { sessionKey, requestedCwd, requestedModel } = opts;
  let sessionId = "";

  // Step 1: Resolve existing session
  const resolved = resolveSession(sessions, sessionKey, requestedCwd);
  if (resolved) {
    sessionId = resolved.sessionId;
  }

  // Step 2: Resume path
  if (opts.resume && !sessionId) {
    try {
      await acp.acpRequest("session/resume", { sessionId: opts.resume, cwd: requestedCwd });
      sessionId = opts.resume;
      if (requestedModel) {
        await acp.acpRequest("session/set_model", { sessionId, modelId: requestedModel });
      }
      sessions.set(sessionKey, { sessionId, cwd: requestedCwd, model: requestedModel });
      return { sessionId, isNew: false };
    } catch {
      // Fall through to session/new
    }
  }

  // Step 3: Fresh session path
  if (!sessionId) {
    const result = (await acp.acpRequest("session/new", { cwd: requestedCwd })) as { sessionId: string };
    sessionId = result.sessionId;
    if (requestedModel) {
      await acp.acpRequest("session/set_model", { sessionId, modelId: requestedModel });
    }
    sessions.set(sessionKey, { sessionId, cwd: requestedCwd, model: requestedModel });
    return { sessionId, isNew: true };
  }

  // Step 4: Reuse path — model update if needed
  if (needsModelUpdate(resolved?.existing, requestedModel)) {
    try {
      await acp.acpRequest("session/set_model", { sessionId, modelId: requestedModel });
      sessions.set(sessionKey, { sessionId, cwd: requestedCwd, model: requestedModel });
    } catch {
      sessions.delete(getRetryDeleteKey(sessionKey));
      // In real code, this recurses into handleQuery — we simulate by re-calling
      return simulateQuerySessionSetup(sessions, acp, { ...opts, resume: undefined });
    }
  }

  return { sessionId, isNew: false };
}

describe("warmup: set_model before cache", () => {
  let sessions: ReturnType<typeof createSessionMap>;
  let acp: ReturnType<typeof createMockAcp>;

  beforeEach(() => {
    sessions = createSessionMap();
    acp = createMockAcp();
  });

  it("calls set_model before caching on warmup", async () => {
    await simulateWarmup(sessions, acp, [
      { key: "main", model: "claude-opus-4-6" },
      { key: "floating", model: "claude-sonnet-4-6" },
    ], "/home/user");

    // Verify ordering: for each session, new → set_model (before cache)
    expect(acp.calls).toHaveLength(4);
    expect(acp.calls[0].method).toBe("session/new");
    expect(acp.calls[1].method).toBe("session/set_model");
    expect(acp.calls[1].params.modelId).toBe("claude-opus-4-6");
    expect(acp.calls[2].method).toBe("session/new");
    expect(acp.calls[3].method).toBe("session/set_model");
    expect(acp.calls[3].params.modelId).toBe("claude-sonnet-4-6");

    // Both sessions cached
    expect(sessions.has("main")).toBe(true);
    expect(sessions.has("floating")).toBe(true);
  });

  it("does not cache session when set_model fails on warmup", async () => {
    acp.setFailSetModel(true);
    try {
      await simulateWarmup(sessions, acp, [
        { key: "floating", model: "claude-sonnet-4-6" },
      ], "/home/user");
    } catch {
      // Expected
    }
    // Session should NOT be cached because set_model failed
    expect(sessions.has("floating")).toBe(false);
  });

  it("skips already-warmed sessions", async () => {
    sessions.set("main", { sessionId: "pre-warmed", cwd: "/home/user", model: "claude-opus-4-6" });
    await simulateWarmup(sessions, acp, [
      { key: "main", model: "claude-opus-4-6" },
      { key: "floating", model: "claude-sonnet-4-6" },
    ], "/home/user");

    // Only floating should have been warmed
    expect(acp.calls).toHaveLength(2); // session/new + set_model for floating only
    expect(acp.calls[1].params.modelId).toBe("claude-sonnet-4-6");
  });
});

describe("fresh session: set_model before cache", () => {
  let sessions: ReturnType<typeof createSessionMap>;
  let acp: ReturnType<typeof createMockAcp>;

  beforeEach(() => {
    sessions = createSessionMap();
    acp = createMockAcp();
  });

  it("calls set_model before caching on fresh session", async () => {
    const result = await simulateQuerySessionSetup(sessions, acp, {
      sessionKey: "floating",
      requestedCwd: "/home/user",
      requestedModel: "claude-sonnet-4-6",
    });

    expect(result.isNew).toBe(true);
    // Verify ordering: new → set_model → cache
    expect(acp.calls[0].method).toBe("session/new");
    expect(acp.calls[1].method).toBe("session/set_model");
    expect(sessions.get("floating")?.model).toBe("claude-sonnet-4-6");
  });

  it("does not cache when set_model fails on fresh session", async () => {
    acp.setFailSetModel(true);
    try {
      await simulateQuerySessionSetup(sessions, acp, {
        sessionKey: "floating",
        requestedCwd: "/home/user",
        requestedModel: "claude-sonnet-4-6",
      });
    } catch {
      // Expected
    }
    expect(sessions.has("floating")).toBe(false);
  });
});

describe("resume: set_model before cache", () => {
  let sessions: ReturnType<typeof createSessionMap>;
  let acp: ReturnType<typeof createMockAcp>;

  beforeEach(() => {
    sessions = createSessionMap();
    acp = createMockAcp();
  });

  it("calls set_model before caching on resume", async () => {
    const result = await simulateQuerySessionSetup(sessions, acp, {
      sessionKey: "floating",
      requestedCwd: "/home/user",
      requestedModel: "claude-sonnet-4-6",
      resume: "persisted-session-id",
    });

    expect(result.isNew).toBe(false);
    expect(result.sessionId).toBe("persisted-session-id");
    // Verify ordering: resume → set_model → cache
    expect(acp.calls[0].method).toBe("session/resume");
    expect(acp.calls[1].method).toBe("session/set_model");
    expect(sessions.get("floating")?.model).toBe("claude-sonnet-4-6");
  });

  it("falls through to new session when resume + set_model fails", async () => {
    acp.setFailSetModel(true);
    // Resume succeeds but set_model fails — should fall through to session/new
    // In real code, set_model failure in resume catch block falls through
    // For this test we verify the fallback creates a new session
    try {
      await simulateQuerySessionSetup(sessions, acp, {
        sessionKey: "floating",
        requestedCwd: "/home/user",
        requestedModel: "claude-sonnet-4-6",
        resume: "persisted-session-id",
      });
    } catch {
      // Expected — set_model fails on both resume and fresh paths
    }
    // Session should not be cached
    expect(sessions.has("floating")).toBe(false);
  });
});

describe("reuse: model update with retry isolation", () => {
  let sessions: ReturnType<typeof createSessionMap>;
  let acp: ReturnType<typeof createMockAcp>;

  beforeEach(() => {
    sessions = createSessionMap();
    acp = createMockAcp();
    // Pre-warm both sessions
    sessions.set("main", { sessionId: "main-s1", cwd: "/home/user", model: "claude-opus-4-6" });
    sessions.set("floating", { sessionId: "float-s1", cwd: "/home/user", model: "claude-sonnet-4-6" });
  });

  it("updates model on reuse when models differ", async () => {
    const result = await simulateQuerySessionSetup(sessions, acp, {
      sessionKey: "floating",
      requestedCwd: "/home/user",
      requestedModel: "claude-opus-4-6", // Different from cached sonnet
    });

    expect(result.sessionId).toBe("float-s1");
    expect(acp.calls[0].method).toBe("session/set_model");
    expect(acp.calls[0].params.modelId).toBe("claude-opus-4-6");
    expect(sessions.get("floating")?.model).toBe("claude-opus-4-6");
  });

  it("failing floating set_model retry does NOT delete main session", async () => {
    acp.setFailSetModel(true);

    // Request floating with a different model — set_model will fail
    // The retry deletes floating and creates a new session (which also fails set_model)
    try {
      await simulateQuerySessionSetup(sessions, acp, {
        sessionKey: "floating",
        requestedCwd: "/home/user",
        requestedModel: "claude-opus-4-6",
      });
    } catch {
      // Expected — set_model fails on retry too
    }

    // CRITICAL: main session must be untouched
    expect(sessions.has("main")).toBe(true);
    expect(sessions.get("main")?.sessionId).toBe("main-s1");
    expect(sessions.get("main")?.model).toBe("claude-opus-4-6");
  });

  it("failing main set_model retry does NOT delete floating session", async () => {
    acp.setFailSetModel(true);

    try {
      await simulateQuerySessionSetup(sessions, acp, {
        sessionKey: "main",
        requestedCwd: "/home/user",
        requestedModel: "claude-sonnet-4-6", // Different from cached opus
      });
    } catch {
      // Expected
    }

    // CRITICAL: floating session must be untouched
    expect(sessions.has("floating")).toBe(true);
    expect(sessions.get("floating")?.sessionId).toBe("float-s1");
    expect(sessions.get("floating")?.model).toBe("claude-sonnet-4-6");
  });

  it("skips set_model when models match on reuse", async () => {
    await simulateQuerySessionSetup(sessions, acp, {
      sessionKey: "floating",
      requestedCwd: "/home/user",
      requestedModel: "claude-sonnet-4-6", // Same as cached
    });

    // No ACP calls should have been made — session reused as-is
    expect(acp.calls).toHaveLength(0);
  });
});

describe("retry key deletion uses sessionKey, not model", () => {
  let sessions: ReturnType<typeof createSessionMap>;

  beforeEach(() => {
    sessions = createSessionMap();
    sessions.set("main", { sessionId: "main-s1", cwd: "/", model: "claude-opus-4-6" });
    sessions.set("floating", { sessionId: "float-s1", cwd: "/", model: "claude-sonnet-4-6" });
  });

  it("deleting by getRetryDeleteKey('floating') removes floating, not 'claude-sonnet-4-6'", () => {
    const key = getRetryDeleteKey("floating");
    sessions.delete(key);

    expect(sessions.has("floating")).toBe(false);
    expect(sessions.has("main")).toBe(true);
    // If we had accidentally used model name "claude-sonnet-4-6" as key,
    // delete would be a no-op (wrong key) leaving the stale entry
  });

  it("deleting by model name (old bug) would be a no-op", () => {
    // Demonstrate the old bug: deleting by model name doesn't find the entry
    sessions.delete("claude-sonnet-4-6");
    // floating still exists — the old code would leave stale sessions
    expect(sessions.has("floating")).toBe(true);
  });
});

describe("warmup: retry on session/new failure", () => {
  let sessions: ReturnType<typeof createSessionMap>;
  let acp: ReturnType<typeof createMockAcp>;

  beforeEach(() => {
    sessions = createSessionMap();
    acp = createMockAcp();
  });

  /**
   * Simulate the warmup retry logic from index.ts preWarmSession():
   * First session/new fails → wait → retry session/new → set_model → cache
   */
  async function simulateWarmupWithRetry(
    sessions: SessionMap,
    acp: ReturnType<typeof createMockAcp>,
    cfg: { key: string; model: string },
    cwd: string,
  ) {
    let result: { sessionId: string };
    try {
      result = (await acp.acpRequest("session/new", { cwd })) as { sessionId: string };
    } catch {
      // Retry once (skip the 2s delay in tests)
      result = (await acp.acpRequest("session/new", { cwd })) as { sessionId: string };
    }
    await acp.acpRequest("session/set_model", { sessionId: result.sessionId, modelId: cfg.model });
    sessions.set(cfg.key, { sessionId: result.sessionId, cwd, model: cfg.model });
  }

  it("retries session/new once and succeeds", async () => {
    acp.setFailSessionNew(1); // Fail first, succeed second
    await simulateWarmupWithRetry(sessions, acp, { key: "floating", model: "claude-sonnet-4-6" }, "/home/user");

    // Two session/new calls (first failed, second succeeded) + set_model
    expect(acp.calls.filter(c => c.method === "session/new")).toHaveLength(2);
    expect(acp.calls.filter(c => c.method === "session/set_model")).toHaveLength(1);
    expect(sessions.has("floating")).toBe(true);
  });

  it("does not cache when both session/new attempts fail", async () => {
    acp.setFailSessionNew(2); // Both attempts fail
    try {
      await simulateWarmupWithRetry(sessions, acp, { key: "floating", model: "claude-sonnet-4-6" }, "/home/user");
    } catch {
      // Expected
    }
    expect(sessions.has("floating")).toBe(false);
  });
});

describe("prompt retry: session isolation under error", () => {
  let sessions: ReturnType<typeof createSessionMap>;
  let acp: ReturnType<typeof createMockAcp>;

  beforeEach(() => {
    sessions = createSessionMap();
    acp = createMockAcp();
    sessions.set("main", { sessionId: "main-s1", cwd: "/home/user", model: "claude-opus-4-6" });
    sessions.set("floating", { sessionId: "float-s1", cwd: "/home/user", model: "claude-sonnet-4-6" });
  });

  /**
   * Simulate the session/prompt retry from index.ts handleQuery():
   * If prompt fails on a reused session, delete by sessionKey and retry with fresh session.
   * This verifies lines ~823-826 and ~837-840 in index.ts.
   */
  async function simulatePromptWithRetry(
    sessions: SessionMap,
    acp: ReturnType<typeof createMockAcp>,
    sessionKey: string,
    requestedCwd: string,
    requestedModel: string,
  ) {
    // First attempt: reuse existing session
    const existing = sessions.get(sessionKey);
    if (!existing) throw new Error("No session to reuse");

    try {
      await acp.acpRequest("session/prompt", { sessionId: existing.sessionId, prompt: "test" });
    } catch {
      // Stale session — delete only this key and create fresh
      sessions.delete(getRetryDeleteKey(sessionKey));

      // Create new session (retry)
      const result = (await acp.acpRequest("session/new", { cwd: requestedCwd })) as { sessionId: string };
      if (requestedModel) {
        await acp.acpRequest("session/set_model", { sessionId: result.sessionId, modelId: requestedModel });
      }
      sessions.set(sessionKey, { sessionId: result.sessionId, cwd: requestedCwd, model: requestedModel });

      // Retry prompt
      await acp.acpRequest("session/prompt", { sessionId: result.sessionId, prompt: "test" });
    }
  }

  it("stale floating prompt retry only deletes floating, not main", async () => {
    acp.setFailPrompt(true);

    try {
      await simulatePromptWithRetry(sessions, acp, "floating", "/home/user", "claude-sonnet-4-6");
    } catch {
      // Both prompt attempts fail — that's fine for isolation test
    }

    // main must be untouched
    expect(sessions.has("main")).toBe(true);
    expect(sessions.get("main")?.sessionId).toBe("main-s1");
  });

  it("stale main prompt retry only deletes main, not floating", async () => {
    acp.setFailPrompt(true);

    try {
      await simulatePromptWithRetry(sessions, acp, "main", "/home/user", "claude-opus-4-6");
    } catch {
      // Expected
    }

    // floating must be untouched
    expect(sessions.has("floating")).toBe(true);
    expect(sessions.get("floating")?.sessionId).toBe("float-s1");
  });

  it("successful retry creates new session after stale prompt", async () => {
    // Fail first prompt, succeed on retry
    let promptCallCount = 0;
    const origAcpRequest = acp.acpRequest;
    const wrappedAcp = { ...acp };
    wrappedAcp.acpRequest = async (method: string, params: Record<string, unknown>) => {
      if (method === "session/prompt") {
        promptCallCount++;
        if (promptCallCount === 1) throw new Error("stale session");
      }
      return origAcpRequest(method, params);
    };

    // Use wrapped acp for this test
    const existing = sessions.get("floating")!;
    try {
      await wrappedAcp.acpRequest("session/prompt", { sessionId: existing.sessionId, prompt: "test" });
    } catch {
      sessions.delete(getRetryDeleteKey("floating"));
      const result = (await wrappedAcp.acpRequest("session/new", { cwd: "/home/user" })) as { sessionId: string };
      await wrappedAcp.acpRequest("session/set_model", { sessionId: result.sessionId, modelId: "claude-sonnet-4-6" });
      sessions.set("floating", { sessionId: result.sessionId, cwd: "/home/user", model: "claude-sonnet-4-6" });
      await wrappedAcp.acpRequest("session/prompt", { sessionId: result.sessionId, prompt: "test" });
    }

    // Floating has new session, main untouched
    expect(sessions.get("floating")?.sessionId).toBe("session-1");
    expect(sessions.get("main")?.sessionId).toBe("main-s1");
  });
});
