// @vitest-environment node
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { relative, resolve } from "node:path";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { FakeAuth, FakeFirestore } from "./support/fake-firestore";
import {
  adminRequest,
  decodeTestFirebaseToken,
  firebaseToken,
} from "./support/admin-request";

const state = vi.hoisted(() => ({ db: null as any, auth: null as any }));
vi.mock("@/lib/firebase/admin", () => ({
  getDb: () => state.db,
  getAdminAuth: () => state.auth,
  verifyFirebaseToken: async (token: string) => decodeTestFirebaseToken(token),
  default: {},
}));
vi.mock("@/lib/dev-auth", () => ({ DEV_BYPASS_ENABLED: false }));

import {
  ROLES,
  SCOPES,
  STATS_READER_SCOPES,
  isScope,
  type Scope,
} from "@/lib/admin-access";
import { ROUTE_POLICIES } from "@/lib/route-scopes";

const ROOT = resolve(__dirname, "../..");
const METHOD =
  /^export (?:async function|const) (GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)\b/gm;

type Handler = { key: string; file: string; method: string; path: string };

function handlers(): Handler[] {
  const found: Handler[] = [];
  const visit = (dir: string) => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const full = resolve(dir, entry.name);
      if (entry.isDirectory()) visit(full);
      else if (entry.name === "route.ts") {
        const path =
          "/" + relative(resolve(ROOT, "app"), dir).split("\\").join("/");
        for (const [, method] of Array.from(
          readFileSync(full, "utf8").matchAll(METHOD)
        )) {
          found.push({ key: `${method} ${path}`, file: full, method, path });
        }
      }
    }
  };
  visit(resolve(ROOT, "app/api"));
  return found;
}

const ALL = handlers();
const scoped = ALL.filter((h) => isScope(ROUTE_POLICIES[h.key]));

function paramsFor(path: string) {
  const params: Record<string, string> = {};
  for (const [, name] of Array.from(path.matchAll(/\[(\w+)\]/g)))
    params[name] = "x1";
  return { params: Promise.resolve(params) };
}

function concrete(path: string) {
  return path.replace(/\[(\w+)\]/g, "x1");
}

async function call(h: Handler, token: string | null) {
  const mod = await import(/* @vite-ignore */ h.file);
  const body = ["GET", "HEAD", "DELETE", "OPTIONS"].includes(h.method)
    ? undefined
    : {};
  return mod[h.method](
    adminRequest(token, h.method, concrete(h.path), body),
    paramsFor(h.path)
  ) as Promise<Response>;
}

beforeEach(() => {
  state.db = new FakeFirestore();
  state.auth = new FakeAuth();
  vi.spyOn(console, "info").mockImplementation(() => {});
});

describe("route inventory", () => {
  it("declares a policy for every API handler", () => {
    const missing = ALL.filter((h) => !(h.key in ROUTE_POLICIES)).map(
      (h) => h.key
    );
    expect(missing, "add these to lib/route-scopes.ts").toEqual([]);
  });

  it("has no policy without a handler", () => {
    const keys = new Set(ALL.map((h) => h.key));
    expect(Object.keys(ROUTE_POLICIES).filter((k) => !keys.has(k))).toEqual([]);
  });

  it("uses only known scopes", () => {
    for (const [key, policy] of Object.entries(ROUTE_POLICIES)) {
      if (
        typeof policy === "string" &&
        policy !== "member" &&
        policy !== "team-agent"
      ) {
        expect(isScope(policy), key).toBe(true);
      }
    }
  });

  it("has no Pages Router API routes, which this inventory cannot see", () => {
    expect(existsSync(resolve(ROOT, "pages/api"))).toBe(false);
  });

  it("keeps the stats reader's capability unchanged: every stats GET is in its scopes", () => {
    for (const h of ALL.filter(
      (h) => h.method === "GET" && h.path.startsWith("/api/omi/stats/")
    )) {
      expect(STATS_READER_SCOPES, h.key).toContain(ROUTE_POLICIES[h.key]);
    }
  });

  it("gives every scope to at least one role or the owner", () => {
    const granted = new Set(Object.values(ROLES).flatMap((r) => r.scopes));
    expect(SCOPES.filter((s) => !granted.has(s))).toEqual([]);
  });
});

describe.each(scoped.map((h) => [h.key, h] as const))("%s", (_key, h) => {
  const scope = ROUTE_POLICIES[h.key] as Scope;

  it("rejects a caller without a token", async () => {
    expect((await call(h, null)).status).toBe(401);
  });

  it(`forbids a member who has every scope except ${scope}`, async () => {
    state.db.table("adminData").set("member", {
      email: "member@example.com",
      accessRole: "deputy",
      scopeOverrides: { deny: [scope] },
    });
    const response = await call(h, firebaseToken("member"));
    expect(response.status).toBe(403);
    expect((await response.json()).scope).toBe(scope);
  });

  it("forbids a signed-in user who is not an admin", async () => {
    expect((await call(h, firebaseToken("stranger"))).status).toBe(403);
  });
});

describe("special policies", () => {
  it("lets any member read their own access, and nobody else", async () => {
    const access = ALL.find((h) => h.key === "GET /api/omi/access")!;
    state.db.table("adminData").set("viewer", {
      accessRole: "viewer",
      scopeOverrides: { deny: ROLES.viewer.scopes },
    });
    const ok = await call(access, firebaseToken("viewer"));
    expect(ok.status).toBe(200);
    expect(await ok.json()).toMatchObject({ role: "viewer", scopes: [] });
    expect((await call(access, firebaseToken("stranger"))).status).toBe(403);
  });

  it.each(
    ALL.filter((h) => ROUTE_POLICIES[h.key] === "team-agent").map(
      (h) => [h.key, h] as const
    )
  )("%s refuses human tokens, even the owner's", async (_key, h) => {
    state.db.table("adminData").set("owner", { owner: true });
    expect((await call(h, firebaseToken("owner"))).status).toBe(401);
  });
});
