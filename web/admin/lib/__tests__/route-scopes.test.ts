// @vitest-environment node
import { existsSync, readFileSync, statSync } from "node:fs";
import { resolve } from "node:path";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { FakeAuth, FakeFirestore } from "./support/fake-firestore";
import {
  adminRequest,
  decodeTestFirebaseToken,
  firebaseToken,
} from "./support/admin-request";
import {
  concrete,
  handlers,
  paramsFor,
  ROOT,
  type Handler,
} from "./support/route-inventory";

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
import { FINANCIAL_ROUTES, ROUTE_POLICIES } from "@/lib/route-scopes";
import { hashTvToken } from "@/lib/tv-links";

const ALL = handlers();
const scoped = ALL.filter((h) => isScope(ROUTE_POLICIES[h.key]));

async function call(h: Handler, token: string | null, body?: unknown) {
  const mod = await import(/* @vite-ignore */ h.file);
  const payload =
    body !== undefined
      ? body
      : ["GET", "HEAD", "DELETE", "OPTIONS"].includes(h.method)
      ? undefined
      : {};
  return mod[h.method](
    adminRequest(token, h.method, concrete(h.path), payload),
    paramsFor(h.path)
  ) as Promise<Response>;
}

beforeEach(() => {
  state.db = new FakeFirestore();
  state.auth = new FakeAuth();
  vi.spyOn(console, "info").mockImplementation(() => {});
});

/** lib/auth.ts is the guard (and the wall) itself, so it is exempt. */
const GUARD_FILE = resolve(ROOT, "lib/auth.ts");

/**
 * NextResponse.json construction of a bare error envelope — no scoped data.
 * The first argument's only keys may be `error` (required) plus `code` or
 * `details`, each value a string literal or a plain message identifier
 * (`error.message`, `fallback` in lib/team/http.ts). Anything else in the
 * object — an extra key like `revenue`, shorthand properties, a nested
 * object, a call — could carry scoped data and is still flagged.
 */
const ERROR_ENVELOPE = /NextResponse\.json\(\s*(\{[^{}]*\})/g;
const STRING = `"(?:[^"\\\\]|\\\\.)*"|'(?:[^'\\\\]|\\\\.)*'|\`[^\`$]*\``;
const ENVELOPE_PROPERTY = new RegExp(
  `(?:error|code|details)\\s*:\\s*(?:${STRING}|[A-Za-z$_][\\w$.]*)`,
  "g"
);

/** Bare `{ error: <message> }` (optionally `code`/`details`) and nothing else. */
function isErrorEnvelope(objectSource: string): boolean {
  const properties = objectSource.match(ENVELOPE_PROPERTY) ?? [];
  const other = objectSource
    .replace(ENVELOPE_PROPERTY, "")
    .replace(/[{},\s]/g, "");
  return (
    properties.some((property) => property.trim().startsWith("error")) &&
    other === ""
  );
}

function bypassesGuard(file: string): boolean {
  if (file === GUARD_FILE) return false;
  return readFileSync(file, "utf8")
    .replace(ERROR_ENVELOPE, (envelope, objectSource: string) =>
      isErrorEnvelope(objectSource) ? "" : envelope
    )
    .includes("NextResponse.json(");
}

/** Local lib modules a handler file imports directly (route files use "@/lib/…"). */
function localHelpersOf(file: string): string[] {
  const sources = Array.from(
    readFileSync(file, "utf8").matchAll(/from "(@\/lib\/[^"]+)"/g)
  );
  const found: string[] = [];
  for (const [, specifier] of sources) {
    const base = resolve(ROOT, specifier.replace("@/", ""));
    for (const candidate of [`${base}.ts`, `${base}.tsx`, base]) {
      if (existsSync(candidate) && statSync(candidate).isFile()) {
        found.push(candidate);
        break;
      }
    }
  }
  return found;
}

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

  it("never serializes scoped JSON outside the guard's json()", () => {
    // The sensitive field wall (lib/sensitive-fields.ts) lives in
    // AdminIdentity.json; a scoped route that calls NextResponse.json
    // directly would bypass it. Guard responses (401/403 from requireScope)
    // are returned, not constructed, so they need no wall.
    const files = new Set(
      ALL.filter((h) => {
        const policy = ROUTE_POLICIES[h.key];
        return isScope(policy) || policy === "member";
      }).flatMap((h) => [h.file, ...localHelpersOf(h.file)])
    );
    const offenders = Array.from(files).filter((file) => bypassesGuard(file));
    expect(
      offenders,
      "respond via <identity>.json so financial fields are redacted"
    ).toEqual([]);
  });

  it("exempts only bare error envelopes — an extra key like revenue is flagged", () => {
    expect(
      bypassesGuard(
        resolve(
          ROOT,
          "lib/__tests__/support/error-envelope-with-data.fixture.ts"
        )
      )
    ).toBe(true);
    expect(
      bypassesGuard(
        resolve(ROOT, "lib/__tests__/support/error-envelope.fixture.ts")
      )
    ).toBe(false);
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
  it("pins every FINANCIAL_ROUTES policy entry to its finance scope", () => {
    for (const [key, wall] of Object.entries(FINANCIAL_ROUTES)) {
      expect(
        ROUTE_POLICIES[key],
        `${key} is missing from ROUTE_POLICIES`
      ).toBeDefined();
      if ("policy" in wall) {
        expect(ROUTE_POLICIES[key], key).toBe(wall.policy);
      }
    }
  });

  it("audits every finance-scoped route into FINANCIAL_ROUTES", () => {
    const financeScoped = Object.entries(ROUTE_POLICIES)
      .filter(
        ([, policy]) => policy === "finance:read" || policy === "finance:write"
      )
      .map(([key]) => key);
    expect(
      financeScoped.filter((key) => !(key in FINANCIAL_ROUTES)),
      "a new finance-scoped route must be audited into FINANCIAL_ROUTES"
    ).toEqual([]);
  });

  it("refuses an analytics-only member every finance-scoped route", async () => {
    // The omi-tv-v2 board, the mixed wall aggregate and its series (revenue,
    // health, headline) all expose revenue, MRR or cost data; so do the
    // subscription, payout and affiliate listings.
    state.db.table("adminData").set("viewer", { accessRole: "viewer" });
    for (const [key, wall] of Object.entries(FINANCIAL_ROUTES)) {
      if (!("policy" in wall) || !key.startsWith("GET")) continue;
      const h = ALL.find((entry) => entry.key === key)!;
      const response = await call(h, firebaseToken("viewer"));
      expect(response.status, key).toBe(403);
      expect((await response.json()).scope, key).toBe("finance:read");
    }
  });

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

describe("the financial wall on TV share links", () => {
  const route = (key: string) => ALL.find((entry) => entry.key === key)!;

  /** Deputy minus finance:read: can manage links, must not see the board. */
  const SHARER = {
    accessRole: "deputy" as const,
    scopeOverrides: { deny: ["finance:read" as const] },
  };

  function seedTvLink(createdBy: string) {
    const token = "tv-token".padEnd(43, "x");
    state.db.table("admin_tv_links").set(hashTvToken(token), {
      tokenHash: hashTvToken(token),
      token,
      prefix: token.slice(0, 8),
      label: "Office TV",
      createdBy,
      createdAt: Date.now(),
      expiresAt: null,
      revokedAt: null,
      lastUsedAt: null,
    });
    return token;
  }

  it("refuses to mint a link without finance:read, and writes nothing", async () => {
    state.db.table("adminData").set("sharer", SHARER);
    const response = await call(
      route("POST /api/omi/tv-links"),
      firebaseToken("sharer")
    );
    expect(response.status).toBe(403);
    expect((await response.json()).scope).toBe("finance:read");
    expect(state.db.table("admin_tv_links").size).toBe(0);
  });

  it("lets a finance:read holder mint one", async () => {
    state.db.table("adminData").set("owner", { owner: true });
    const response = await call(
      route("POST /api/omi/tv-links"),
      firebaseToken("owner")
    );
    expect(response.status).toBe(200);
    expect((await response.json()).link.status).toBe("active");
  });

  it("redacts share tokens in the list without finance:read", async () => {
    seedTvLink("owner");
    state.db.table("adminData").set("sharer", SHARER);
    state.db.table("adminData").set("owner", { owner: true });

    const denied = await call(
      route("GET /api/omi/tv-links"),
      firebaseToken("sharer")
    );
    expect(denied.status).toBe(200);
    const deniedLinks = (await denied.json()).links;
    expect(deniedLinks).toHaveLength(1);
    expect(deniedLinks[0]).toMatchObject({
      token: null,
      path: null,
      label: "Office TV",
    });

    const allowed = await call(
      route("GET /api/omi/tv-links"),
      firebaseToken("owner")
    );
    expect((await allowed.json()).links[0].token).toMatch(/^tv-token/);
  });

  it.each([
    ["demoted to viewer", { accessRole: "viewer" }],
    [
      "denied finance:read",
      { accessRole: "deputy", scopeOverrides: { deny: ["finance:read"] } },
    ],
    ["removed from adminData", null],
  ])("stops a kiosk embed whose issuer was %s", async (_name, issuerDoc) => {
    const token = seedTvLink("issuer");
    if (issuerDoc) state.db.table("adminData").set("issuer", issuerDoc);
    const { POST } = await import("@/app/api/grafana/tv-embed/route");
    const dead = await POST(
      adminRequest(null, "POST", "/api/grafana/tv-embed", { token })
    );
    expect(dead.status).toBe(403);
    // The link did not even refresh lastUsedAt.
    expect(
      state.db.table("admin_tv_links").get(hashTvToken(token))!.lastUsedAt
    ).toBeNull();
  });

  it("keeps a kiosk embed working while the issuer holds finance:read", async () => {
    const token = seedTvLink("issuer");
    state.db.table("adminData").set("issuer", { owner: true });
    const { POST } = await import("@/app/api/grafana/tv-embed/route");
    // The embed flag is off in tests: validation passing gets this far and
    // stops, proving the token resolved without minting anything.
    const alive = await POST(
      adminRequest(null, "POST", "/api/grafana/tv-embed", { token })
    );
    expect(alive.status).toBe(200);
    expect(await alive.json()).toEqual({ enabled: false });
  });
});

describe("the financial wall on organization billing", () => {
  const route = (key: string) => ALL.find((entry) => entry.key === key)!;
  const subscription = {
    subscription_id: "pi_secret",
    customer_id: "cus_secret",
    plan: "unlimited",
    status: "active",
    current_period_end: 1735689600,
  };

  function seedOrganisation() {
    // The dynamic [id] params resolve to "x1" (paramsFor), so the PATCH
    // tests can reach this document.
    state.db.table("organisations").set("x1", {
      organisation_name: "Acme",
      added_on: "2026-01-01T00:00:00.000Z",
      subscription,
      employees: [],
    });
  }

  it("redacts subscription for partners:read without finance:read", async () => {
    seedOrganisation();
    state.db.table("adminData").set("partner", {
      accessRole: "deputy",
      scopeOverrides: { deny: ["finance:read"] },
    });
    const response = await call(
      route("GET /api/organizations"),
      firebaseToken("partner")
    );
    expect(response.status).toBe(200);
    const org = (await response.json()).organizations[0];
    expect(org).toMatchObject({ organisation_name: "Acme" });
    // The financial field wall removes the key entirely, it does not
    // null it: nothing billing-shaped survives for a non-finance caller.
    expect("subscription" in org).toBe(false);
  });

  it("shows subscription to finance:read", async () => {
    seedOrganisation();
    state.db.table("adminData").set("owner", { owner: true });
    const response = await call(
      route("GET /api/organizations"),
      firebaseToken("owner")
    );
    expect((await response.json()).organizations[0].subscription).toEqual(
      subscription
    );
  });

  it.each([
    [
      "POST /api/organizations",
      "creating an org with a payment",
      {
        organisation_name: "Beta",
        admin_name: "Bee",
        admin_email: "bee@example.com",
        stripe_payment_id: "pi_abc",
      },
    ],
    [
      "PATCH /api/organizations/[id]",
      "setting an org payment",
      { stripe_payment_id: "pi_abc" },
    ],
    [
      "PATCH /api/organizations/[id]",
      "clearing an org payment",
      { stripe_payment_id: "" },
    ],
  ])("refuses %s without finance:write", async (key, _name, body) => {
    seedOrganisation();
    state.db.table("adminData").set("partner", {
      accessRole: "deputy",
      scopeOverrides: { deny: ["finance:write"] },
    });
    const response = await call(route(key), firebaseToken("partner"), body);
    expect(response.status).toBe(403);
    expect((await response.json()).scope).toBe("finance:write");
    expect(state.db.table("organisations").get("x1")!.subscription).toEqual(
      subscription
    );
    expect(state.db.table("organisations").size).toBe(1);
  });

  it("refuses clearing an org payment for a billing writer who can't read billing", async () => {
    seedOrganisation();
    state.db.table("adminData").set("partner", {
      accessRole: "deputy",
      scopeOverrides: { deny: ["finance:read"] },
    });
    const response = await call(
      route("PATCH /api/organizations/[id]"),
      firebaseToken("partner"),
      { stripe_payment_id: "" }
    );
    expect(response.status).toBe(403);
    expect((await response.json()).scope).toBe("finance:read");
    expect(state.db.table("organisations").get("x1")!.subscription).toEqual(
      subscription
    );
  });

  it("still lets partners:write edit org metadata without billing", async () => {
    seedOrganisation();
    state.db.table("adminData").set("partner", {
      accessRole: "deputy",
      scopeOverrides: { deny: ["finance:read", "finance:write"] },
    });
    const response = await call(
      route("PATCH /api/organizations/[id]"),
      firebaseToken("partner"),
      { organisation_name: "Gamma" }
    );
    expect(response.status).toBe(200);
    const org = (await response.json()).organization;
    expect(org).toMatchObject({ organisation_name: "Gamma" });
    expect("subscription" in org).toBe(false);
    expect(state.db.table("organisations").get("x1")!.organisation_name).toBe(
      "Gamma"
    );
  });
});
