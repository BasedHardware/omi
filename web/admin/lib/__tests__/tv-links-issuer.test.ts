// @vitest-environment node
import { beforeEach, describe, expect, it, vi } from "vitest";
import { FakeAuth, FakeFirestore } from "./support/fake-firestore";

const state = vi.hoisted(() => ({ db: null as any, auth: null as any }));
vi.mock("@/lib/firebase/admin", () => ({
  getDb: () => state.db,
  getAdminAuth: () => state.auth,
  verifyFirebaseToken: async () => null,
  default: {},
}));
vi.mock("@/lib/dev-auth", () => ({ DEV_BYPASS_ENABLED: false }));

import { createTvLink, resolveActiveTvToken } from "@/lib/tv-links";

const ISSUER = "issuer-uid";
const members = () => state.db.table("adminData") as Map<string, any>;

beforeEach(() => {
  state.db = new FakeFirestore();
  state.auth = new FakeAuth();
  vi.spyOn(console, "error").mockImplementation(() => {});
});

async function mintedLink() {
  const created = await createTvLink({
    label: "Office TV",
    createdBy: ISSUER,
  });
  return created.token;
}

describe("TV link issuer re-check", () => {
  it("resolves while the issuer holds finance:read", async () => {
    const token = await mintedLink();
    members().set(ISSUER, { owner: true });
    expect(await resolveActiveTvToken(token)).toEqual({
      id: expect.any(String),
      label: "Office TV",
    });
  });

  it.each([
    [
      "demoted to viewer",
      { email: "issuer@example.com", accessRole: "viewer" },
    ],
    [
      "denied finance:read",
      {
        email: "issuer@example.com",
        accessRole: "deputy",
        scopeOverrides: { deny: ["finance:read"] },
      },
    ],
    ["removed from adminData", null],
  ])("kills the link when the issuer is %s", async (_name, issuerDoc) => {
    const token = await mintedLink();
    if (issuerDoc) members().set(ISSUER, issuerDoc);
    expect(await resolveActiveTvToken(token)).toBeNull();
  });

  it("does not refresh lastUsedAt for a link whose issuer lost access", async () => {
    const token = await mintedLink();
    members().set(ISSUER, { accessRole: "viewer" });
    await resolveActiveTvToken(token);
    const rows = state.db.rows("admin_tv_links");
    expect(rows).toHaveLength(1);
    expect(rows[0].lastUsedAt).toBeNull();
  });
});
