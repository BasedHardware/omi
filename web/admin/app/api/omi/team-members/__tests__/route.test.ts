import { beforeEach, describe, expect, it, vi } from "vitest";

type AdminDoc = {
  email?: string;
  name?: string;
  role?: string;
  owner?: boolean;
};

const mocks = vi.hoisted(() => ({
  verifyAdmin: vi.fn(),
  getUserByEmail: vi.fn(),
  memberSet: vi.fn(),
  memberDelete: vi.fn(),
  docs: new Map<string, AdminDoc>(),
}));

vi.mock("@/lib/auth", () => ({ verifyAdmin: mocks.verifyAdmin }));
vi.mock("@/lib/firebase/admin", () => ({
  getAdminAuth: () => ({ getUserByEmail: mocks.getUserByEmail }),
  getDb: () => ({
    collection: () => ({
      get: async () => ({
        docs: Array.from(mocks.docs.entries()).map(([id, data]) => ({
          id,
          data: () => data,
        })),
      }),
      doc: (id: string) => ({
        get: async () => ({
          exists: mocks.docs.has(id),
          data: () => mocks.docs.get(id),
        }),
        set: mocks.memberSet,
        delete: async () => {
          mocks.memberDelete(id);
          mocks.docs.delete(id);
        },
      }),
    }),
  }),
}));

import { DELETE, GET, POST } from "../route";

function requestWith(body: unknown) {
  return { json: vi.fn().mockResolvedValue(body) } as never;
}

const OWNER = "nik-uid";
const SUPERADMIN = "thinh-uid";

function seedTeam() {
  mocks.docs.clear();
  mocks.docs.set(OWNER, {
    email: "kodjima33@gmail.com",
    name: "Nik",
    role: "superadmin",
    owner: true,
  });
  mocks.docs.set(SUPERADMIN, {
    email: "ngocthinhdp@gmail.com",
    name: "Thinh",
    role: "superadmin",
  });
  mocks.docs.set("archit-uid", {
    email: "architdraftid@gmail.com",
    name: "Archit",
    role: "Admin",
  });
}

describe("POST /api/omi/team-members", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.docs.clear();
    mocks.verifyAdmin.mockResolvedValue({ uid: "requesting-admin" });
    mocks.memberSet.mockResolvedValue(undefined);
  });

  it("grants dashboard access to an existing Omi user", async () => {
    mocks.getUserByEmail.mockResolvedValue({
      uid: "archit-uid",
      displayName: "Archit",
    });

    const response = await POST(
      requestWith({ email: " ARCHITDRAFTID@GMAIL.COM " })
    );

    expect(response.status).toBe(201);
    await expect(response.json()).resolves.toEqual({
      teamMember: {
        id: "archit-uid",
        name: "Archit",
        role: "Admin",
        email: "architdraftid@gmail.com",
      },
    });
    expect(mocks.getUserByEmail).toHaveBeenCalledWith(
      "architdraftid@gmail.com"
    );
    expect(mocks.memberSet).toHaveBeenCalledWith(
      expect.objectContaining({
        name: "Archit",
        role: "Admin",
        email: "architdraftid@gmail.com",
      })
    );
  });

  it("explains when the person has not signed in to Omi yet", async () => {
    mocks.getUserByEmail.mockRejectedValue({ code: "auth/user-not-found" });

    const response = await POST(
      requestWith({ email: "architdraftid@gmail.com" })
    );

    expect(response.status).toBe(404);
    await expect(response.json()).resolves.toEqual({
      error:
        "No Omi account found for architdraftid@gmail.com. Ask them to sign in to Omi once, then try again.",
    });
    expect(mocks.memberSet).not.toHaveBeenCalled();
  });
});

describe("GET /api/omi/team-members", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    seedTeam();
  });

  it("tells the owner they can remove people and flags the owner card", async () => {
    mocks.verifyAdmin.mockResolvedValue({ uid: OWNER });

    const response = await GET({} as never);
    const body = await response.json();

    expect(body.viewer).toEqual({ uid: OWNER, canRemove: true });
    expect(
      body.teamMembers.find((m: { id: string }) => m.id === OWNER).owner
    ).toBe(true);
    expect(
      body.teamMembers.find((m: { id: string }) => m.id === SUPERADMIN).owner
    ).toBe(false);
  });

  it("tells a superadmin they cannot remove people", async () => {
    mocks.verifyAdmin.mockResolvedValue({ uid: SUPERADMIN });

    const body = await (await GET({} as never)).json();

    expect(body.viewer).toEqual({ uid: SUPERADMIN, canRemove: false });
  });
});

describe("DELETE /api/omi/team-members", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    seedTeam();
  });

  it("lets the owner remove a superadmin", async () => {
    mocks.verifyAdmin.mockResolvedValue({ uid: OWNER });

    const response = await DELETE(requestWith({ uid: SUPERADMIN }));

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({
      removed: {
        id: SUPERADMIN,
        email: "ngocthinhdp@gmail.com",
        role: "superadmin",
      },
    });
    expect(mocks.memberDelete).toHaveBeenCalledWith(SUPERADMIN);
    expect(mocks.docs.has(SUPERADMIN)).toBe(false);
  });

  it("refuses a superadmin who is not the owner", async () => {
    mocks.verifyAdmin.mockResolvedValue({ uid: SUPERADMIN });

    const response = await DELETE(requestWith({ uid: "archit-uid" }));

    expect(response.status).toBe(403);
    expect(mocks.memberDelete).not.toHaveBeenCalled();
    expect(mocks.docs.has("archit-uid")).toBe(true);
  });

  it("refuses to let the owner remove themselves", async () => {
    mocks.verifyAdmin.mockResolvedValue({ uid: OWNER });

    const response = await DELETE(requestWith({ uid: OWNER }));

    expect(response.status).toBe(400);
    expect(mocks.memberDelete).not.toHaveBeenCalled();
  });

  it("reports a person who is already gone", async () => {
    mocks.verifyAdmin.mockResolvedValue({ uid: OWNER });

    const response = await DELETE(requestWith({ uid: "ghost-uid" }));

    expect(response.status).toBe(404);
    expect(mocks.memberDelete).not.toHaveBeenCalled();
  });

  it("rejects a body without a uid", async () => {
    mocks.verifyAdmin.mockResolvedValue({ uid: OWNER });

    const response = await DELETE(requestWith({}));

    expect(response.status).toBe(400);
  });
});
