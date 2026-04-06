import { describe, it, expect, beforeEach } from "vitest";
import {
  resolveSession,
  needsModelUpdate,
  filterSessionsToWarm,
  getRetryDeleteKey,
  type SessionEntry,
  type SessionMap,
} from "../src/session-manager.js";

/** Simple in-memory session map for testing */
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

describe("resolveSession", () => {
  let sessions: ReturnType<typeof createSessionMap>;

  beforeEach(() => {
    sessions = createSessionMap();
  });

  it("returns null when no session exists for the key", () => {
    const result = resolveSession(sessions, "floating", "/home/user");
    expect(result).toBeNull();
  });

  it("returns existing session when key and cwd match", () => {
    sessions.set("floating", { sessionId: "s1", cwd: "/home/user", model: "claude-sonnet-4-6" });
    const result = resolveSession(sessions, "floating", "/home/user");
    expect(result).not.toBeNull();
    expect(result!.sessionId).toBe("s1");
    expect(result!.existing.model).toBe("claude-sonnet-4-6");
  });

  it("invalidates session when cwd changes", () => {
    sessions.set("floating", { sessionId: "s1", cwd: "/home/user", model: "claude-sonnet-4-6" });
    const result = resolveSession(sessions, "floating", "/home/other");
    expect(result).toBeNull();
    expect(sessions.has("floating")).toBe(false);
  });

  it("does not affect other session keys when invalidating", () => {
    sessions.set("main", { sessionId: "s1", cwd: "/home/user", model: "claude-opus-4-6" });
    sessions.set("floating", { sessionId: "s2", cwd: "/old/path", model: "claude-sonnet-4-6" });

    // Invalidate floating (cwd changed), main should survive
    resolveSession(sessions, "floating", "/new/path");
    expect(sessions.has("main")).toBe(true);
    expect(sessions.has("floating")).toBe(false);
  });
});

describe("needsModelUpdate", () => {
  it("returns false when existing is undefined", () => {
    expect(needsModelUpdate(undefined, "claude-sonnet-4-6")).toBe(false);
  });

  it("returns false when requestedModel is undefined", () => {
    const existing: SessionEntry = { sessionId: "s1", cwd: "/", model: "claude-sonnet-4-6" };
    expect(needsModelUpdate(existing, undefined)).toBe(false);
  });

  it("returns false when models match", () => {
    const existing: SessionEntry = { sessionId: "s1", cwd: "/", model: "claude-sonnet-4-6" };
    expect(needsModelUpdate(existing, "claude-sonnet-4-6")).toBe(false);
  });

  it("returns true when models differ", () => {
    const existing: SessionEntry = { sessionId: "s1", cwd: "/", model: "claude-sonnet-4-6" };
    expect(needsModelUpdate(existing, "claude-opus-4-6")).toBe(true);
  });
});

describe("filterSessionsToWarm", () => {
  let sessions: ReturnType<typeof createSessionMap>;

  beforeEach(() => {
    sessions = createSessionMap();
  });

  it("returns all configs when no sessions exist", () => {
    const configs = [
      { key: "main", model: "claude-opus-4-6" },
      { key: "floating", model: "claude-sonnet-4-6" },
    ];
    const result = filterSessionsToWarm(sessions, configs);
    expect(result).toHaveLength(2);
  });

  it("filters out already-warmed sessions", () => {
    sessions.set("main", { sessionId: "s1", cwd: "/", model: "claude-opus-4-6" });
    const configs = [
      { key: "main", model: "claude-opus-4-6" },
      { key: "floating", model: "claude-sonnet-4-6" },
    ];
    const result = filterSessionsToWarm(sessions, configs);
    expect(result).toHaveLength(1);
    expect(result[0].key).toBe("floating");
  });

  it("returns empty when all sessions already warmed", () => {
    sessions.set("main", { sessionId: "s1", cwd: "/", model: "claude-opus-4-6" });
    sessions.set("floating", { sessionId: "s2", cwd: "/", model: "claude-sonnet-4-6" });
    const configs = [
      { key: "main", model: "claude-opus-4-6" },
      { key: "floating", model: "claude-sonnet-4-6" },
    ];
    const result = filterSessionsToWarm(sessions, configs);
    expect(result).toHaveLength(0);
  });
});

describe("getRetryDeleteKey", () => {
  it("returns sessionKey, not model name", () => {
    // This is the bug fix: retry should delete by sessionKey, not requestedModel
    expect(getRetryDeleteKey("floating")).toBe("floating");
    expect(getRetryDeleteKey("main")).toBe("main");
  });

  it("handles legacy model-as-key scenario", () => {
    // When sessionKey falls back to model name (backward compat)
    expect(getRetryDeleteKey("claude-opus-4-6")).toBe("claude-opus-4-6");
  });
});

describe("needsModelUpdate edge cases", () => {
  it("returns true when existing.model is undefined but requestedModel is set", () => {
    // Legacy/partially cached session with no model field
    const existing: SessionEntry = { sessionId: "s1", cwd: "/" };
    expect(needsModelUpdate(existing, "claude-sonnet-4-6")).toBe(true);
  });
});

describe("session isolation: main vs floating", () => {
  let sessions: ReturnType<typeof createSessionMap>;

  beforeEach(() => {
    sessions = createSessionMap();
    // Simulate pre-warmed state
    sessions.set("main", { sessionId: "main-s1", cwd: "/home/user", model: "claude-opus-4-6" });
    sessions.set("floating", { sessionId: "float-s1", cwd: "/home/user", model: "claude-sonnet-4-6" });
  });

  it("resolves correct session for each key", () => {
    const mainResult = resolveSession(sessions, "main", "/home/user");
    const floatResult = resolveSession(sessions, "floating", "/home/user");

    expect(mainResult!.sessionId).toBe("main-s1");
    expect(mainResult!.existing.model).toBe("claude-opus-4-6");
    expect(floatResult!.sessionId).toBe("float-s1");
    expect(floatResult!.existing.model).toBe("claude-sonnet-4-6");
  });

  it("deleting floating does not affect main", () => {
    sessions.delete(getRetryDeleteKey("floating"));
    expect(sessions.has("main")).toBe(true);
    expect(sessions.has("floating")).toBe(false);
  });

  it("model update detected only for mismatched key", () => {
    const mainEntry = sessions.get("main");
    const floatEntry = sessions.get("floating");

    // Main with Opus request — no update needed
    expect(needsModelUpdate(mainEntry, "claude-opus-4-6")).toBe(false);
    // Floating with Opus request — update needed (was Sonnet)
    expect(needsModelUpdate(floatEntry, "claude-opus-4-6")).toBe(true);
    // Floating with Sonnet request — no update needed
    expect(needsModelUpdate(floatEntry, "claude-sonnet-4-6")).toBe(false);
  });
});
