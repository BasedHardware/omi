// @vitest-environment node
import { NextResponse } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { FakeAuth, FakeFirestore } from "./support/fake-firestore";
import { adminRequest, firebaseToken } from "./support/admin-request";

const state = vi.hoisted(() => ({
  db: null as any,
  auth: null as any,
  verify: null as any,
}));
// The real isFirebaseTokenError classifies; only token verification itself is
// scripted per test.
vi.mock("@/lib/firebase/admin", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/firebase/admin")>();
  return {
    getDb: () => state.db,
    getAdminAuth: () => state.auth,
    verifyFirebaseToken: (token: string) => state.verify(token),
    isFirebaseTokenError: actual.isFirebaseTokenError,
  };
});
vi.mock("@/lib/dev-auth", () => ({ DEV_BYPASS_ENABLED: false }));

import { SCOPES } from "@/lib/admin-access";
import { requireMember, requireScope } from "@/lib/auth";

const OWNER = "owner-uid";

const tokenError = (code: string) => Object.assign(new Error(code), { code });
const call = () =>
  requireMember(adminRequest(firebaseToken(OWNER), "GET", "/api/omi/access"));

beforeEach(() => {
  state.db = new FakeFirestore();
  state.auth = new FakeAuth();
  state.db.table("adminData").set(OWNER, {
    email: "owner@example.com",
    owner: true,
  });
  state.verify = async () => ({ uid: OWNER });
  vi.spyOn(console, "error").mockImplementation(() => {});
  vi.spyOn(console, "info").mockImplementation(() => {});
});

describe("authenticate: Firebase token verification failures", () => {
  it.each([
    ["a malformed or bad-signature token", "auth/argument-error"],
    ["an invalid token", "auth/invalid-id-token"],
    ["an expired token", "auth/id-token-expired"],
    ["a revoked token", "auth/id-token-revoked"],
  ])("answers %s with 401, not 500", async (_name, code) => {
    state.verify = async () => {
      throw tokenError(code);
    };
    const response = await call();
    expect(response).toBeInstanceOf(NextResponse);
    expect((response as NextResponse).status).toBe(401);
  });
});

describe("authenticate: server faults stay 500", () => {
  it("answers an unexpected verification error with 500", async () => {
    state.verify = async () => {
      throw new Error("credential bus exploded");
    };
    const response = await call();
    expect((response as NextResponse).status).toBe(500);
  });

  it("answers an SDK internal error with 500, not 401", async () => {
    state.verify = async () => {
      throw tokenError("auth/internal-error");
    };
    const response = await call();
    expect((response as NextResponse).status).toBe(500);
  });

  it("answers a Firestore failure after verification with 500", async () => {
    state.db = {
      collection() {
        throw new Error("firestore unavailable");
      },
    };
    const response = await call();
    expect((response as NextResponse).status).toBe(500);
  });
});

describe("authenticate: a valid token still passes", () => {
  it("admits an owner with every scope", async () => {
    const identity = await requireScope(
      adminRequest(firebaseToken(OWNER), "GET", "/api/omi/team-members"),
      "team:manage"
    );
    expect(identity).not.toBeInstanceOf(NextResponse);
    if (!(identity instanceof NextResponse)) {
      expect(identity).toMatchObject({ uid: OWNER, kind: "human" });
      expect(identity.access.scopes).toEqual([...SCOPES]);
    }
  });
});
