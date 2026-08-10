import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  verifyAdmin: vi.fn(),
  getUserByEmail: vi.fn(),
  memberGet: vi.fn(),
  memberSet: vi.fn(),
}));

vi.mock("@/lib/auth", () => ({ verifyAdmin: mocks.verifyAdmin }));
vi.mock("@/lib/firebase/admin", () => ({
  getAdminAuth: () => ({ getUserByEmail: mocks.getUserByEmail }),
  getDb: () => ({
    collection: () => ({
      doc: () => ({ get: mocks.memberGet, set: mocks.memberSet }),
    }),
  }),
}));

import { POST } from "../route";

function requestWith(body: unknown) {
  return { json: vi.fn().mockResolvedValue(body) } as never;
}

describe("POST /api/omi/team-members", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.verifyAdmin.mockResolvedValue({ uid: "requesting-admin" });
    mocks.memberGet.mockResolvedValue({ exists: false });
    mocks.memberSet.mockResolvedValue(undefined);
  });

  it("grants dashboard access to an existing Omi user", async () => {
    mocks.getUserByEmail.mockResolvedValue({
      uid: "archit-uid",
      displayName: "Archit",
    });

    const response = await POST(
      requestWith({ email: " ARCHITDRAFTID@GMAIL.COM " }),
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
      "architdraftid@gmail.com",
    );
    expect(mocks.memberSet).toHaveBeenCalledWith(
      expect.objectContaining({
        name: "Archit",
        role: "Admin",
        email: "architdraftid@gmail.com",
      }),
    );
  });

  it("explains when the person has not signed in to Omi yet", async () => {
    mocks.getUserByEmail.mockRejectedValue({ code: "auth/user-not-found" });

    const response = await POST(
      requestWith({ email: "architdraftid@gmail.com" }),
    );

    expect(response.status).toBe(404);
    await expect(response.json()).resolves.toEqual({
      error:
        "No Omi account found for architdraftid@gmail.com. Ask them to sign in to Omi once, then try again.",
    });
    expect(mocks.memberSet).not.toHaveBeenCalled();
  });
});
