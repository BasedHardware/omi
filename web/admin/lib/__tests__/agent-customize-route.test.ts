// @vitest-environment node
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FakeAuth, FakeFirestore } from "./support/fake-firestore";
import {
  adminRequest,
  decodeTestFirebaseToken,
  firebaseToken,
} from "./support/admin-request";

const state = vi.hoisted(() => ({
  db: null as any,
  auth: null as any,
  spawn: vi.fn(),
}));
vi.mock("@/lib/firebase/admin", () => ({
  getDb: () => state.db,
  getAdminAuth: () => state.auth,
  verifyFirebaseToken: async (token: string) => decodeTestFirebaseToken(token),
}));
vi.mock("@/lib/dev-auth", () => ({ DEV_BYPASS_ENABLED: false }));
vi.mock("node:child_process", () => ({ spawn: state.spawn }));

import { GET, POST } from "@/app/api/omi/agent/customize/route";

/**
 * The endpoint spawns claude/codex with permission-bypass flags: it must not
 * exist outside local development (production or without the explicit
 * ADMIN_LOCAL_AGENT opt-in), and when it does exist the child must inherit
 * only an allowlisted environment — never the server's process.env with its
 * Firebase credentials and secrets.
 */

function fakeChild() {
  return {
    stdout: { on: vi.fn() },
    stderr: { on: vi.fn() },
    on: vi.fn(),
    kill: vi.fn(),
  };
}

beforeEach(() => {
  state.db = new FakeFirestore();
  state.auth = new FakeAuth();
  // An owner holding dev:agent: every gate below fails because of the
  // environment, never because of authority.
  state.db.table("adminData").set("owner", { owner: true });
  state.spawn.mockReset().mockImplementation(() => fakeChild());
  vi.spyOn(console, "info").mockImplementation(() => {});
  delete process.env.ADMIN_LOCAL_AGENT;
  // Vitest runs with NODE_ENV=test (not production), so the opt-in alone
  // decides; a canary proves the spawn env is not process.env.
  vi.stubEnv("ADMIN_TEST_SECRET", "must-not-leak");
});

afterEach(() => {
  vi.unstubAllEnvs();
  delete process.env.ADMIN_LOCAL_AGENT;
});

describe("the local agent endpoint", () => {
  it("does not exist for an owner without the explicit opt-in", async () => {
    const response = await POST(
      adminRequest(firebaseToken("owner"), "POST", "/api/omi/agent/customize", {
        prompt: "hello",
      })
    );
    expect(response.status).toBe(404);
    expect(state.spawn).not.toHaveBeenCalled();
  });

  it("does not exist in production even with the opt-in", async () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("ADMIN_LOCAL_AGENT", "1");
    const response = await POST(
      adminRequest(firebaseToken("owner"), "POST", "/api/omi/agent/customize", {
        prompt: "hello",
      })
    );
    expect(response.status).toBe(404);
    expect(state.spawn).not.toHaveBeenCalled();
  });

  it("spawns with an allowlisted env, never process.env, when enabled", async () => {
    vi.stubEnv("ADMIN_LOCAL_AGENT", "1");
    const response = await POST(
      adminRequest(firebaseToken("owner"), "POST", "/api/omi/agent/customize", {
        prompt: "hello",
      })
    );
    expect(response.status).toBe(200);
    expect(state.spawn).toHaveBeenCalledTimes(1);
    const [bin, args, options] = state.spawn.mock.calls[0];
    expect(bin).toBe("claude");
    expect(args.join(" ")).toContain("hello");
    expect(options.env).not.toBe(process.env);
    expect(options.env.PATH).toBe(process.env.PATH);
    expect(options.env.HOME).toBe(process.env.HOME);
    expect(options.env.ADMIN_TEST_SECRET).toBeUndefined();
  });

  it("reports enabled to the widget, honestly in both states", async () => {
    const disabled = await GET(
      adminRequest(firebaseToken("owner"), "GET", "/api/omi/agent/customize")
    );
    expect(disabled.status).toBe(200);
    expect(await disabled.json()).toEqual({ enabled: false });

    vi.stubEnv("ADMIN_LOCAL_AGENT", "1");
    const enabled = await GET(
      adminRequest(firebaseToken("owner"), "GET", "/api/omi/agent/customize")
    );
    expect(await enabled.json()).toEqual({ enabled: true });
  });
});
