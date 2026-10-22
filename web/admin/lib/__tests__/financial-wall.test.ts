// @vitest-environment node
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FakeAuth, FakeFirestore, DOCUMENT_ID } from "./support/fake-firestore";
import {
  adminRequest,
  decodeTestFirebaseToken,
  firebaseToken,
} from "./support/admin-request";
import {
  concrete,
  handlers,
  paramsFor,
  type Handler,
} from "./support/route-inventory";

const state = vi.hoisted(() => ({
  db: null as any,
  auth: null as any,
  apps: [] as Record<string, any>[],
}));
vi.mock("@/lib/firebase/admin", () => ({
  getDb: () => state.db,
  getAdminAuth: () => state.auth,
  verifyFirebaseToken: async (token: string) => decodeTestFirebaseToken(token),
  // summary-apps filters by FieldPath.documentId(); the sentinel is what
  // the fake Firestore matches against document ids.
  default: { firestore: { FieldPath: { documentId: () => DOCUMENT_ID } } },
}));
vi.mock("@/lib/dev-auth", () => ({ DEV_BYPASS_ENABLED: false }));
vi.mock("@/lib/services/omi-api/apps", () => ({
  getApps: async () => state.apps,
  getUnapprovedApps: async () => state.apps,
}));

import { FINANCIAL_FIELDS, isFinancialField } from "@/lib/financial-fields";
import { isScope } from "@/lib/admin-access";
import { ROUTE_POLICIES } from "@/lib/route-scopes";

/**
 * The financial field wall, end to end. One member holds every scope
 * except finance:read; every document and service the routes read is
 * seeded with every financial field name; then every scoped GET handler
 * runs and no financial field may appear anywhere in any response body.
 * This is the guard against the next per-route leak: a new route that
 * responds through AdminIdentity.json is covered without writing anything.
 */

const MONEY = "FINANCIAL-SENTINEL";

/** An object carrying every financial field, plus prefix matches. */
function financialDocument(extra: Record<string, unknown> = {}) {
  const doc: Record<string, unknown> = { ...extra };
  for (const field of FINANCIAL_FIELDS) doc[field] = MONEY;
  doc.subscription = {
    plan: MONEY,
    status: MONEY,
    customer_id: MONEY,
    subscription_id: MONEY,
  };
  doc.stripe_customer_id = MONEY;
  doc.payout_id = MONEY;
  doc.payouts = [{ amount: MONEY }];
  return doc;
}

/** Every key anywhere in the parsed body whose name is a financial field. */
function financialKeys(value: unknown, path = "$", found: string[] = []) {
  if (Array.isArray(value)) {
    value.forEach((item, i) => financialKeys(item, `${path}[${i}]`, found));
  } else if (value && typeof value === "object") {
    for (const [key, child] of Object.entries(value)) {
      if (isFinancialField(key)) found.push(`${path}.${key}`);
      financialKeys(child, `${path}.${key}`, found);
    }
  }
  return found;
}

const ALL = handlers();
const scopedGets = ALL.filter((h) => {
  const policy = ROUTE_POLICIES[h.key];
  return h.method === "GET" && (isScope(policy) || policy === "member");
});

async function call(h: Handler, uid: string) {
  const mod = await import(/* @vite-ignore */ h.file);
  return mod[h.method](
    adminRequest(firebaseToken(uid), "GET", `${concrete(h.path)}?uid=x1`),
    paramsFor(h.path)
  ) as Promise<Response>;
}

function seedEverything() {
  // The caller: deputy minus finance:read — every scope but the wall.
  state.db.table("adminData").set("member", {
    email: "member@example.com",
    accessRole: "deputy",
    scopeOverrides: { deny: ["finance:read"] },
  });
  state.db.table("adminData").set("owner", { owner: true });

  // Omi API app listings (apps, apps/stats, apps/unapproved).
  state.apps = [
    financialDocument({
      id: "x1",
      name: "Sentinel App",
      approved: true,
      is_paid: true,
      private: false,
      deleted: false,
      capabilities: ["chat"],
      category: "productivity",
      status: "approved",
      author: "someone",
      description: "fixture",
      image: "img",
      created_at: "2026-01-01T00:00:00Z",
    }),
  ];

  // Firestore app documents (details, private-apps, summary-apps).
  state.db.table("plugins_data").set(
    "x1",
    financialDocument({
      name: "Sentinel App",
      approved: true,
      is_paid: true,
      private: true,
      deleted: false,
      capabilities: ["chat"],
      uid: "app-owner",
    })
  );

  // A user with billing on their doc, plus fair-use state and events.
  state.db
    .table("users")
    .set("x1", financialDocument({ email: "user@example.com", name: "User" }));
  state.db.table("users/x1/fair_use_state").set(
    "current",
    financialDocument({
      stage: "warning",
      updated_at: "2026-10-01T00:00:00Z",
      created_at: "2026-09-01T00:00:00Z",
    })
  );
  state.db.table("users/x1/fair_use_events").set(
    "e1",
    financialDocument({
      case_ref: "x1",
      event: "throttle",
      created_at: "2026-10-01T00:00:00Z",
    })
  );

  // Organizations mix partner metadata with Stripe billing.
  state.db.table("organisations").set(
    "x1",
    financialDocument({
      organisation_name: "Acme",
      added_on: "2026-01-01T00:00:00.000Z",
      employees: [],
      max_seats: 5,
    })
  );
  state.db.table("distributors").set(
    "x1",
    financialDocument({
      email: "d@example.com",
      name: "Dist",
      createdAt: "2026-01-01T00:00:00.000Z",
    })
  );

  // A fresh precomputed onboarding payload: the mobile onboarding routes
  // serve it verbatim from the cache, so the wall must cover cached
  // payloads too, not just inline computes.
  state.db
    .table("admin_stats_payload_cache")
    .set("onboarding:mobile:v1:first-run:30", {
      payload: JSON.stringify(
        financialDocument({
          days: 30,
          totalUsers: 2,
          methodology: "Completion, not views",
        })
      ),
      freshAt: Date.now(),
    });
}

beforeEach(() => {
  state.db = new FakeFirestore();
  state.auth = new FakeAuth();
  seedEverything();
  // summary-apps reaches the Omi API for the id list before reading
  // plugins_data; other routes that fetch get an empty array.
  vi.stubEnv("NEXT_PUBLIC_OMI_API_URL", "https://omi.test");
  vi.stubEnv("OMI_API_SECRET_KEY", "secret");
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: unknown) => {
      const url =
        typeof input === "string"
          ? input
          : (input as { url?: string })?.url ?? "";
      const json = url.includes("/v1/summary-app-ids")
        ? { app_ids: ["x1"] }
        : [];
      return { ok: true, json: async () => json };
    })
  );
  vi.spyOn(console, "info").mockImplementation(() => {});
  vi.spyOn(console, "error").mockImplementation(() => {});
  vi.spyOn(console, "log").mockImplementation(() => {});
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("the financial field wall over every scoped GET handler", () => {
  it(
    "leaks no financial field to a member who holds every scope except finance:read",
    { timeout: 30_000 },
    async () => {
      expect(scopedGets.length).toBeGreaterThan(30);
      for (const h of scopedGets) {
        const response = await call(h, "member");
        let body: unknown;
        try {
          body = await response.json();
        } catch {
          continue; // not JSON (nothing to leak)
        }
        expect(financialKeys(body), `${h.key} -> ${response.status}`).toEqual(
          []
        );
      }
    }
  );

  it(
    "actually served the seeded data, so the scan above is not vacuous",
    { timeout: 30_000 },
    async () => {
      const byKey = (key: string) => scopedGets.find((h) => h.key === key)!;
      // route key -> where the non-financial sentinel of the fixture surfaces
      const carried: [string, unknown, (body: any) => unknown][] = [
        ["GET /api/omi/apps", "Sentinel App", (b) => b[0]?.name],
        ["GET /api/omi/apps/unapproved", "Sentinel App", (b) => b[0]?.name],
        ["GET /api/omi/apps/[app_id]/details", "Sentinel App", (b) => b.name],
        ["GET /api/omi/private-apps", "Sentinel App", (b) => b.apps[0]?.name],
        ["GET /api/omi/summary-apps", "Sentinel App", (b) => b[0]?.name],
        [
          "GET /api/omi/fair-use/user/[uid]",
          "user@example.com",
          (b) => b.profile?.email,
        ],
        ["GET /api/omi/fair-use/flagged", "x1", (b) => b.users[0]?.uid],
        ["GET /api/omi/stats/onboarding/mobile", 2, (b) => b.totalUsers],
        [
          "GET /api/organizations",
          "Acme",
          (b) => b.organizations[0]?.organisation_name,
        ],
        ["GET /api/distributors", "Dist", (b) => b.distributors[0]?.name],
      ];
      for (const [key, expected, read] of carried) {
        const response = await call(byKey(key), "member");
        expect(response.status, key).toBe(200);
        expect(read(await response.json()), key).toBe(expected);
      }
    }
  );

  it("shows the same fields to a caller who holds finance:read", async () => {
    const apps = scopedGets.find((h) => h.key === "GET /api/omi/apps")!;
    const ownerApps = await call(apps, "owner");
    expect(await ownerApps.json()).toMatchObject([
      { name: "Sentinel App", money_made: MONEY, price: MONEY },
    ]);

    const fairUse = scopedGets.find(
      (h) => h.key === "GET /api/omi/fair-use/user/[uid]"
    )!;
    const ownerDetail = await call(fairUse, "owner");
    expect(await ownerDetail.json()).toMatchObject({
      profile: { subscription_plan: MONEY },
    });
  });

  it("redacts the Luna findings specifically", async () => {
    // P1: app earnings under apps:read.
    const memberApps = await (
      await call(
        scopedGets.find((h) => h.key === "GET /api/omi/apps")!,
        "member"
      )
    ).json();
    expect(memberApps[0]).toMatchObject({ name: "Sentinel App" });
    expect(financialKeys(memberApps)).toEqual([]);

    // P2: fair-use user detail subscription.plan under users:read.
    const memberDetail = await (
      await call(
        scopedGets.find((h) => h.key === "GET /api/omi/fair-use/user/[uid]")!,
        "member"
      )
    ).json();
    expect(memberDetail.profile).toMatchObject({
      email: "user@example.com",
      name: "User",
    });
    expect(memberDetail.profile).not.toHaveProperty("subscription_plan");
    expect(financialKeys(memberDetail)).toEqual([]);
  });
});
