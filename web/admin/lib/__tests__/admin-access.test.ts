import { describe, expect, it } from "vitest";
import {
  LEGACY_SCOPES,
  ROLES,
  SCOPES,
  accessFor,
  pageScope,
  pageWriteScope,
} from "@/lib/admin-access";

describe("accessFor", () => {
  it("gives the owner every scope, whatever else the doc says", () => {
    expect(accessFor({ owner: true, accessRole: "viewer" }).scopes).toEqual([
      ...SCOPES,
    ]);
  });

  it.each([{}, { role: "superadmin" }, { role: "Admin" }, { accessRole: "" }])(
    "keeps legacy docs at their pre-role access until a role is assigned: %j",
    (doc) => {
      const access = accessFor(doc);
      expect(access.kind).toBe("legacy");
      expect(access.scopes).toEqual([...LEGACY_SCOPES]);
      expect(access.scopes).not.toContain("team:manage");
    }
  );

  it("fails closed on a role this code does not know", () => {
    expect(accessFor({ accessRole: "superadmin" })).toMatchObject({
      kind: "invalid",
      scopes: [],
    });
  });

  it("applies grant and deny overrides, ignoring unknown scopes and team:manage grants", () => {
    const access = accessFor({
      accessRole: "viewer",
      scopeOverrides: {
        grant: ["finance:read", "team:manage", "root"],
        deny: ["apps:read"],
      },
    });
    expect(access.scopes).toEqual([
      "analytics:read",
      "finance:read",
      "content:read",
    ]);
  });

  it("keeps the read-only roles read-only", () => {
    for (const role of [ROLES.viewer]) {
      expect(role.scopes.every((s) => s.endsWith(":read"))).toBe(true);
    }
    expect(ROLES.support.scopes).not.toContain("finance:read");
    expect(ROLES.admin.scopes).not.toContain("team:manage");
    expect(ROLES.deputy.scopes).toContain("team:manage");
  });
});

describe("pageScope", () => {
  it("maps dashboard pages to the scope their sidebar entry needs", () => {
    expect(pageScope("/dashboard")).toBe("analytics:read");
    expect(pageScope("/dashboard/team")).toBe("team:read");
    expect(pageScope("/dashboard/fair-use/abc")).toBe("users:read");
    expect(pageScope("/dashboard/payouts")).toBe("finance:read");
    expect(pageScope("/login")).toBeNull();
  });

  it("names the scope a page's edit controls need", () => {
    expect(pageWriteScope("/dashboard/announcements")).toBe("content:write");
    expect(pageWriteScope("/dashboard/reviews")).toBe("apps:write");
    expect(pageWriteScope("/dashboard/notifications")).toBe("users:write");
    expect(pageWriteScope("/dashboard/subscriptions")).toBeNull();
  });
});
