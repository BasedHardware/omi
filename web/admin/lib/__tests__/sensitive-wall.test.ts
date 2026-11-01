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

import {
  SENSITIVE_FIELD_CLASSES,
  sensitiveClassFor,
  type SensitiveFieldClass,
} from "@/lib/sensitive-fields";
import { isScope } from "@/lib/admin-access";
import { ROUTE_POLICIES } from "@/lib/route-scopes";

/**
 * The sensitive field wall, end to end. Every document and service the
 * routes read is seeded with every classified field name; then every
 * scoped GET handler runs and no field of a class may appear anywhere in
 * any response body for a caller who lacks that class's scope — including
 * the owner for the classes no scope unlocks (credentials). This is the
 * guard against the next per-route leak: a new route that responds through
 * AdminIdentity.json is covered without writing anything.
 */

const SENTINEL: Record<SensitiveFieldClass["id"], string> = {
  financial: "FINANCIAL-SENTINEL",
  credentials: "CREDENTIAL-SENTINEL",
  "user-content": "USER-CONTENT-SENTINEL",
};

/** An object carrying every classified field of every class, plus prefix matches. */
function sensitiveDocument(extra: Record<string, unknown> = {}) {
  const doc: Record<string, unknown> = { ...extra };
  for (const klass of SENSITIVE_FIELD_CLASSES) {
    for (const field of klass.fields) doc[field] = SENTINEL[klass.id];
  }
  doc.subscription = {
    plan: SENTINEL.financial,
    status: SENTINEL.financial,
    customer_id: SENTINEL.financial,
    subscription_id: SENTINEL.financial,
  };
  doc.stripe_customer_id = SENTINEL.financial;
  doc.payout_id = SENTINEL.financial;
  doc.payouts = [{ amount: SENTINEL.financial }];
  doc.external_integration = {
    mcp_server_url: "https://mcp.example",
    client_secret: SENTINEL.credentials,
    code_verifier: SENTINEL.credentials,
    mcp_oauth_tokens: {
      access_token: SENTINEL.credentials,
      refresh_token: SENTINEL.credentials,
    },
  };
  return doc;
}

/** Every key anywhere in the parsed body whose name belongs to `klass`. */
function classKeys(
  value: unknown,
  klass: SensitiveFieldClass,
  path = "$",
  found: string[] = []
) {
  if (Array.isArray(value)) {
    value.forEach((item, i) => classKeys(item, klass, `${path}[${i}]`, found));
  } else if (value && typeof value === "object") {
    for (const [key, child] of Object.entries(value)) {
      if (sensitiveClassFor(key)?.id === klass.id) found.push(`${path}.${key}`);
      classKeys(child, klass, `${path}.${key}`, found);
    }
  }
  return found;
}

const byId = (id: SensitiveFieldClass["id"]) =>
  SENSITIVE_FIELD_CLASSES.find((klass) => klass.id === id)!;

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

/**
 * One handler, one caller, one class: every scoped GET runs; a handler
 * that throws (Stripe-backed routes have no key in tests) or answers
 * non-JSON serves no body, so there is nothing to leak and it reads clean.
 */
async function leakPaths(h: Handler, uid: string, klass: SensitiveFieldClass) {
  let body: unknown;
  try {
    body = await (await call(h, uid)).json();
  } catch {
    return [];
  }
  return classKeys(body, klass);
}

/** The one route key for `path`, asserted to exist so a typo cannot pass silently. */
function route(path: string) {
  const h = scopedGets.find((h) => h.key === path);
  if (!h) throw new Error(`no scoped GET handler for ${path}`);
  return h;
}

const SAMPLED_QUESTION = "what did we discuss about the acquisition";
const CURATED_QUESTION = "What can Omi do for me today?";

function seedEverything() {
  // Callers: deputies denying exactly one class's scope (they hold every
  // other scope, so each sweep proves its class strips on its own), plus
  // an owner, who must still never see credential fields.
  state.db.table("adminData").set("member", {
    email: "member@example.com",
    accessRole: "deputy",
    scopeOverrides: { deny: ["finance:read"] },
  });
  state.db.table("adminData").set("no-user-data", {
    email: "nouser@example.com",
    accessRole: "deputy",
    scopeOverrides: { deny: ["users:read"] },
  });
  state.db.table("adminData").set("owner", { owner: true });

  // Omi API app listings (apps, apps/stats, apps/unapproved).
  state.apps = [
    sensitiveDocument({
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
    sensitiveDocument({
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
    .set("x1", sensitiveDocument({ email: "user@example.com", name: "User" }));
  state.db.table("users/x1/fair_use_state").set(
    "current",
    sensitiveDocument({
      stage: "warning",
      updated_at: "2026-10-01T00:00:00Z",
      created_at: "2026-09-01T00:00:00Z",
    })
  );
  state.db.table("users/x1/fair_use_events").set(
    "e1",
    sensitiveDocument({
      case_ref: "x1",
      event: "throttle",
      created_at: "2026-10-01T00:00:00Z",
    })
  );

  // Real user messages the Chat Lab sampler would read, plus curated ones.
  state.db.table("users/x1/messages").set("m1", {
    text: SAMPLED_QUESTION,
    sender: "human",
    created_at: "2026-10-01T00:00:00Z",
  });
  state.db.table("admin/chat_lab/questions").set("c1", {
    text: CURATED_QUESTION,
    context_type: "conversations",
  });

  // CSAT rows with free-text comments.
  state.db.table("csat_ratings").set("r1", {
    uid: "x1",
    platform: "macos",
    app_version: "0.11.1",
    score: 5,
    comment: "USER-CONTENT-SENTINEL",
    created_at: 1,
    revision: 1,
  });

  // Organizations mix partner metadata with Stripe billing.
  state.db.table("organisations").set(
    "x1",
    sensitiveDocument({
      organisation_name: "Acme",
      added_on: "2026-01-01T00:00:00.000Z",
      employees: [],
      max_seats: 5,
    })
  );
  state.db.table("distributors").set(
    "x1",
    sensitiveDocument({
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
        sensitiveDocument({
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

describe("the sensitive field wall over every scoped GET handler", () => {
  it.each([
    ["financial", "member", "finance:read"],
    ["user-content", "no-user-data", "users:read"],
  ] as const)(
    "leaks no %s field to a member who holds every scope except %s",
    async (classId, uid) => {
      expect(scopedGets.length).toBeGreaterThan(30);
      for (const h of scopedGets) {
        expect(await leakPaths(h, uid, byId(classId)), h.key).toEqual([]);
      }
    },
    30_000
  );

  it("leaks no credential field to anyone, not even an owner", async () => {
    for (const h of scopedGets) {
      expect(await leakPaths(h, "owner", byId("credentials")), h.key).toEqual(
        []
      );
    }
  }, 30_000);

  it(
    "actually served the seeded data, so the scans above are not vacuous",
    { timeout: 30_000 },
    async () => {
      const byKey = (key: string) => scopedGets.find((h) => h.key === key)!;
      // route key -> where the non-sensitive sentinel of the fixture surfaces
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

  it("shows financial fields to a caller who holds finance:read, but never credentials", async () => {
    const apps = route("GET /api/omi/apps");
    const ownerApps = await call(apps, "owner");
    const appList = await ownerApps.json();
    expect(appList).toMatchObject([
      {
        name: "Sentinel App",
        money_made: SENTINEL.financial,
        price: SENTINEL.financial,
      },
    ]);
    expect(classKeys(appList, byId("credentials"))).toEqual([]);

    const fairUse = route("GET /api/omi/fair-use/user/[uid]");
    const ownerDetail = await call(fairUse, "owner");
    expect(await ownerDetail.json()).toMatchObject({
      profile: { subscription_plan: SENTINEL.financial },
    });
  });

  it("redacts the Luna findings specifically", async () => {
    // P1: app earnings under apps:read.
    const memberApps = await (
      await call(route("GET /api/omi/apps"), "member")
    ).json();
    expect(memberApps[0]).toMatchObject({ name: "Sentinel App" });
    expect(classKeys(memberApps, byId("financial"))).toEqual([]);

    // P2: fair-use user detail subscription.plan under users:read.
    const memberDetail = await (
      await call(route("GET /api/omi/fair-use/user/[uid]"), "member")
    ).json();
    expect(memberDetail.profile).toMatchObject({
      email: "user@example.com",
      name: "User",
    });
    expect(memberDetail.profile).not.toHaveProperty("subscription_plan");
    expect(classKeys(memberDetail, byId("financial"))).toEqual([]);
  });

  it("strips integration credentials from app reads under apps:read", async () => {
    // The whole plugins_data document is served; only the credential
    // fields go missing, for a plain apps:read caller and for the owner.
    for (const uid of ["member", "owner"]) {
      const details = await (
        await call(route("GET /api/omi/apps/[app_id]/details"), uid)
      ).json();
      expect(details).toMatchObject({
        name: "Sentinel App",
        external_integration: { mcp_server_url: "https://mcp.example" },
      });
      expect(details).not.toHaveProperty("client_secret");
      expect(details.external_integration).not.toHaveProperty(
        "mcp_oauth_tokens"
      );
      expect(classKeys(details, byId("credentials"))).toEqual([]);
    }
  });

  it("serves CSAT aggregates under content:read but strips comments without users:read", async () => {
    const csat = route("GET /api/omi/csat/stats");
    const withoutUserData = await (await call(csat, "no-user-data")).json();
    expect(withoutUserData).toMatchObject({
      available: true,
      total: 1,
      avg: 5,
    });
    expect(withoutUserData.comments).toHaveLength(1);
    expect(withoutUserData.comments[0]).not.toHaveProperty("comment");

    // A caller who also holds users:read (support) sees the free text.
    const member = await (await call(csat, "member")).json();
    expect(member.comments[0]).toMatchObject({
      comment: "USER-CONTENT-SENTINEL",
    });
  });

  it("samples chat-lab questions only for callers who hold users:read", async () => {
    const questions = route("GET /api/omi/chat-lab/questions");
    const bodyOf = async (uid: string) =>
      JSON.stringify(await (await call(questions, uid)).json());

    // content:read without users:read: curated questions only — no sampled
    // user message appears anywhere in the response.
    const withoutUserData = await bodyOf("no-user-data");
    expect(withoutUserData).toContain(CURATED_QUESTION);
    expect(withoutUserData).not.toContain(SAMPLED_QUESTION);
    expect(JSON.parse(withoutUserData)).toMatchObject({
      questions: [{ text: CURATED_QUESTION }],
    });

    // users:read (support) still sees the sampled questions.
    const member = JSON.parse(await bodyOf("member"));
    const texts = JSON.stringify(member);
    expect(texts).toContain(SAMPLED_QUESTION);
  });

  it("serves no sampled chat-lab questions without users:read even when none are curated", async () => {
    // With no curated questions the route would fold sampled user messages
    // into `questions` under `text` — a field name too generic for the
    // wall — so the sampling itself must not run for a content-only caller.
    state.db.table("admin/chat_lab/questions").delete("c1");
    const questions = route("GET /api/omi/chat-lab/questions");

    const withoutUserData = await (
      await call(questions, "no-user-data")
    ).json();
    expect(withoutUserData.questions).toEqual([]);

    const member = await (await call(questions, "member")).json();
    expect(JSON.stringify(member.questions)).toContain(SAMPLED_QUESTION);
  });
});
