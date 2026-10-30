// @vitest-environment node
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  FakeAuth,
  FakeDocRef,
  FakeFirestore,
  FakeTransaction,
} from "@/lib/__tests__/support/fake-firestore";
import {
  adminRequest,
  decodeTestFirebaseToken,
  firebaseToken,
} from "@/lib/__tests__/support/admin-request";

const state = vi.hoisted(() => ({
  db: null as any,
  auth: null as any,
  sendAdminInviteEmail: vi.fn(),
}));
vi.mock("@/lib/firebase/admin", () => ({
  getDb: () => state.db,
  getAdminAuth: () => state.auth,
  verifyFirebaseToken: async (token: string) => decodeTestFirebaseToken(token),
}));
vi.mock("@/lib/dev-auth", () => ({ DEV_BYPASS_ENABLED: false }));
vi.mock("@/lib/email/invite", () => ({
  sendAdminInviteEmail: state.sendAdminInviteEmail,
}));

import { DELETE, GET, PATCH, POST } from "../route";
import { GET as auditGET } from "../audit/route";
import { LOCK_COLLECTION, lockDigest } from "@/lib/team/roster";
import { SCOPES } from "@/lib/admin-access";

const OWNER = "nik-uid-0001";
const SUPERADMIN = "thinh-uid-0002";
const ARCHIT = "archit-uid-0003";
const DEPUTY = "deputy-uid-0004";
const DEPUTY_2 = "deputy-uid-0005";

const members = () => state.db.table("adminData") as Map<string, any>;
const auditRows = () => state.db.rows("adminAuditLog");

function seedTeam() {
  members().set(OWNER, {
    email: "kodjima33@gmail.com",
    name: "Nik",
    role: "superadmin",
    owner: true,
    createdAt: "2024-01-01T00:00:00.000Z",
  });
  // Legacy docs: a `role` label but no `accessRole`.
  members().set(SUPERADMIN, {
    email: "ngocthinhdp@gmail.com",
    name: "Thinh",
    role: "superadmin",
  });
  members().set(ARCHIT, {
    email: "architdraftid@gmail.com",
    name: "Archit",
    role: "Admin",
  });
  members().set(DEPUTY, {
    email: "deputy@example.com",
    name: "Dee",
    accessRole: "deputy",
  });
  members().set(DEPUTY_2, {
    email: "deputy2@example.com",
    name: "Dee Two",
    accessRole: "deputy",
  });
}

const as = (uid: string, method: string, body?: unknown) =>
  adminRequest(firebaseToken(uid), method, "/api/omi/team-members", body);

beforeEach(() => {
  state.db = new FakeFirestore();
  state.auth = new FakeAuth();
  state.sendAdminInviteEmail.mockReset().mockResolvedValue({ sent: true });
  vi.spyOn(console, "info").mockImplementation(() => {});
  vi.spyOn(console, "log").mockImplementation(() => {});
  vi.spyOn(console, "error").mockImplementation(() => {});
  seedTeam();
});

describe("POST /api/omi/team-members", () => {
  it("grants dashboard access to an existing Omi user with the chosen role", async () => {
    state.auth.add({
      uid: "new-person",
      email: "new@example.com",
      displayName: "New",
    });

    const response = await POST(
      as(ARCHIT, "POST", { email: " NEW@EXAMPLE.COM ", accessRole: "support" })
    );

    expect(response.status).toBe(201);
    await expect(response.json()).resolves.toEqual({
      teamMember: {
        id: "new-person",
        name: "New",
        role: "Support",
        accessRole: "support",
        email: "new@example.com",
      },
      provisioned: false,
      emailSent: true,
    });
    expect(members().get("new-person")).toMatchObject({
      accessRole: "support",
      role: "Support",
      addedBy: ARCHIT,
    });
  });

  it("defaults to the least-privileged role when a client sends no role", async () => {
    state.auth.add({ uid: "new-person", email: "new@example.com" });
    await POST(as(ARCHIT, "POST", { email: "new@example.com" }));
    expect(members().get("new-person").accessRole).toBe("viewer");
  });

  it("provisions a uid for someone who has never signed in to Omi", async () => {
    const response = await POST(
      as(ARCHIT, "POST", { email: "fresh@example.com" })
    );
    expect(response.status).toBe(201);
    const body = await response.json();
    expect(body.provisioned).toBe(true);
    expect(members().get(body.teamMember.id).email).toBe("fresh@example.com");
  });

  it("reuses the existing uid when provisioning races a first sign-in", async () => {
    let lookups = 0;
    state.auth.getUserByEmail = async () => {
      if (lookups++ === 0)
        throw Object.assign(new Error(), { code: "auth/user-not-found" });
      return { uid: "raced-uid", email: "race@example.com" };
    };
    state.auth.createUser = async () => {
      throw Object.assign(new Error(), { code: "auth/email-already-exists" });
    };
    const response = await POST(
      as(ARCHIT, "POST", { email: "race@example.com" })
    );
    expect(response.status).toBe(201);
    expect(members().has("raced-uid")).toBe(true);
  });

  it("emails the invitee, naming the admin who added them", async () => {
    state.auth.add({ uid: "new-person", email: "new@example.com" });
    await POST(as(ARCHIT, "POST", { email: "new@example.com" }));
    expect(state.sendAdminInviteEmail).toHaveBeenCalledWith({
      email: "new@example.com",
      invitedBy: "architdraftid@gmail.com",
    });
  });

  it("still adds the person when the invite email fails", async () => {
    state.sendAdminInviteEmail.mockResolvedValue({
      sent: false,
      reason: "smtp",
    });
    state.auth.add({ uid: "new-person", email: "new@example.com" });
    const response = await POST(
      as(ARCHIT, "POST", { email: "new@example.com" })
    );
    expect(response.status).toBe(201);
    expect((await response.json()).emailSent).toBe(false);
    expect(members().has("new-person")).toBe(true);
  });

  it("does not email anyone when the person is already an admin", async () => {
    state.auth.add({ uid: ARCHIT, email: "architdraftid@gmail.com" });
    const response = await POST(
      as(SUPERADMIN, "POST", { email: "architdraftid@gmail.com" })
    );
    expect(response.status).toBe(409);
    expect(state.sendAdminInviteEmail).not.toHaveBeenCalled();
  });

  it("does not grant admin access when provisioning fails", async () => {
    state.auth.createUser = async () => {
      throw Object.assign(new Error("boom"), { code: "auth/internal-error" });
    };
    const response = await POST(
      as(ARCHIT, "POST", { email: "fresh@example.com" })
    );
    expect(response.status).toBe(500);
    expect(members().size).toBe(5);
    expect(auditRows()).toEqual([]);
  });

  it("refuses to grant a role broader than the inviter's own", async () => {
    members().set("support", { email: "s@example.com", accessRole: "support" });
    const response = await POST(
      as("support", "POST", { email: "x@example.com" })
    );
    expect(response.status).toBe(403); // support has no team:invite at all

    members().set("inviter", {
      email: "i@example.com",
      accessRole: "support",
      scopeOverrides: { grant: ["team:invite"] },
    });
    state.auth.add({ uid: "x", email: "x@example.com" });
    const broader = await POST(
      as("inviter", "POST", { email: "x@example.com", accessRole: "finance" })
    );
    expect(broader.status).toBe(403);
    expect((await broader.json()).error).toMatch(/finance:read/);
    expect(members().has("x")).toBe(false);
  });

  it("lets only the owner appoint a deputy", async () => {
    state.auth.add({ uid: "x", email: "x@example.com" });
    const byDeputy = await POST(
      as(DEPUTY, "POST", { email: "x@example.com", accessRole: "deputy" })
    );
    expect(byDeputy.status).toBe(403);
    const byOwner = await POST(
      as(OWNER, "POST", { email: "x@example.com", accessRole: "deputy" })
    );
    expect(byOwner.status).toBe(201);
  });

  it("records the addition in the audit log", async () => {
    state.auth.add({ uid: "new-person", email: "new@example.com" });
    await POST(
      as(ARCHIT, "POST", { email: "new@example.com", accessRole: "viewer" })
    );
    expect(auditRows()).toEqual([
      expect.objectContaining({
        action: "member.added",
        actor: { type: "human", id: ARCHIT, email: "architdraftid@gmail.com" },
        target: { uid: "new-person", email: "new@example.com" },
        before: null,
        after: expect.objectContaining({
          accessRole: "viewer",
          scopes: ["analytics:read", "apps:read", "content:read"],
        }),
      }),
    ]);
  });
});

describe("GET /api/omi/team-members", () => {
  it("shows uid prefix, createdAt, last sign-in and duplicate emails", async () => {
    members().set("dupe-uid-9999", {
      email: "ARCHITDRAFTID@gmail.com",
      name: "Archit again",
    });
    state.auth.add({
      uid: ARCHIT,
      email: "architdraftid@gmail.com",
      lastSignInTime: "Tue, 21 Oct 2026 10:00:00 GMT",
    });

    const body = await (await GET(as(OWNER, "GET"))).json();
    const archit = body.teamMembers.find((m: any) => m.id === ARCHIT);
    expect(archit).toMatchObject({
      uidPrefix: "archit-u",
      lastSignInAt: "2026-10-21T10:00:00.000Z",
      duplicateEmail: true,
      accessKind: "legacy",
      roleLabel: "Admin (legacy, full access)",
    });
    const owner = body.teamMembers.find((m: any) => m.id === OWNER);
    expect(owner).toMatchObject({
      owner: true,
      createdAt: "2024-01-01T00:00:00.000Z",
      duplicateEmail: false,
    });
    expect(body.viewer).toMatchObject({
      uid: OWNER,
      isOwner: true,
      canManage: true,
      canRemove: true,
    });
  });

  it("tells a legacy superadmin they cannot remove people", async () => {
    const body = await (await GET(as(SUPERADMIN, "GET"))).json();
    expect(body.viewer).toMatchObject({
      canManage: false,
      canRemove: false,
      canInvite: true,
    });
  });

  it("is forbidden to a role without team:read", async () => {
    members().set("viewer", { accessRole: "viewer" });
    expect((await GET(as("viewer", "GET"))).status).toBe(403);
  });
});

describe("DELETE /api/omi/team-members", () => {
  it("lets the owner remove a superadmin", async () => {
    const response = await DELETE(as(OWNER, "DELETE", { uid: SUPERADMIN }));
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({
      removed: {
        id: SUPERADMIN,
        email: "ngocthinhdp@gmail.com",
        role: "superadmin (legacy, full access)",
      },
    });
    expect(members().has(SUPERADMIN)).toBe(false);
  });

  it("refuses a superadmin who is not the owner", async () => {
    const response = await DELETE(as(SUPERADMIN, "DELETE", { uid: ARCHIT }));
    expect(response.status).toBe(403);
    expect(members().has(ARCHIT)).toBe(true);
  });

  it("refuses to let the owner remove themselves", async () => {
    const response = await DELETE(as(OWNER, "DELETE", { uid: OWNER }));
    expect(response.status).toBe(400);
    expect(members().has(OWNER)).toBe(true);
  });

  it("reports a person who is already gone", async () => {
    expect((await DELETE(as(OWNER, "DELETE", { uid: "gone" }))).status).toBe(
      404
    );
  });

  it("rejects a body without a uid", async () => {
    expect((await DELETE(as(OWNER, "DELETE", {}))).status).toBe(400);
  });

  it("lets a deputy remove an admin, but not the owner or another deputy", async () => {
    expect((await DELETE(as(DEPUTY, "DELETE", { uid: ARCHIT }))).status).toBe(
      200
    );
    expect((await DELETE(as(DEPUTY, "DELETE", { uid: OWNER }))).status).toBe(
      403
    );
    expect((await DELETE(as(DEPUTY, "DELETE", { uid: DEPUTY_2 }))).status).toBe(
      403
    );
    expect(members().has(OWNER) && members().has(DEPUTY_2)).toBe(true);
  });

  it("lets the owner remove a deputy", async () => {
    expect((await DELETE(as(OWNER, "DELETE", { uid: DEPUTY }))).status).toBe(
      200
    );
  });

  it("audits the removal with the access that was removed", async () => {
    await DELETE(as(OWNER, "DELETE", { uid: SUPERADMIN }));
    expect(auditRows()).toEqual([
      expect.objectContaining({
        action: "member.removed",
        actor: expect.objectContaining({ id: OWNER }),
        target: { uid: SUPERADMIN, email: "ngocthinhdp@gmail.com" },
        before: expect.objectContaining({
          accessRole: null,
          roleLabel: "superadmin (legacy, full access)",
        }),
        after: null,
      }),
    ]);
  });
});

describe("PATCH /api/omi/team-members", () => {
  it("assigns a role to a legacy member, ending their legacy full access", async () => {
    const response = await PATCH(
      as(OWNER, "PATCH", { uid: ARCHIT, accessRole: "support" })
    );
    expect(response.status).toBe(200);
    expect(members().get(ARCHIT)).toMatchObject({
      accessRole: "support",
      role: "Support",
      accessUpdatedBy: OWNER,
    });
    const [entry] = auditRows();
    expect(entry).toMatchObject({
      action: "member.role_changed",
      before: { accessRole: null },
      after: { accessRole: "support" },
    });
    // The new role is enforced on the next request.
    expect((await GET(as(ARCHIT, "GET"))).status).toBe(403);
  });

  it("applies per-member overrides, but never grants team:manage through them", async () => {
    await PATCH(
      as(OWNER, "PATCH", {
        uid: ARCHIT,
        accessRole: "viewer",
        scopeOverrides: { grant: ["finance:read"], deny: ["content:read"] },
      })
    );
    const body = await (await GET(as(OWNER, "GET"))).json();
    expect(body.teamMembers.find((m: any) => m.id === ARCHIT).scopes).toEqual([
      "analytics:read",
      "finance:read",
      "apps:read",
    ]);
    members().set("sneaky", {
      accessRole: "viewer",
      scopeOverrides: { grant: ["team:manage"] },
    });
    expect((await DELETE(as("sneaky", "DELETE", { uid: ARCHIT }))).status).toBe(
      403
    );
  });

  it("refuses non-managers, self-changes, the owner, and deputy changes by a deputy", async () => {
    expect(
      (
        await PATCH(
          as(SUPERADMIN, "PATCH", { uid: ARCHIT, accessRole: "viewer" })
        )
      ).status
    ).toBe(403);
    expect(
      (await PATCH(as(DEPUTY, "PATCH", { uid: DEPUTY, accessRole: "admin" })))
        .status
    ).toBe(400);
    expect(
      (await PATCH(as(DEPUTY, "PATCH", { uid: OWNER, accessRole: "viewer" })))
        .status
    ).toBe(403);
    expect(
      (
        await PATCH(
          as(DEPUTY, "PATCH", { uid: DEPUTY_2, accessRole: "viewer" })
        )
      ).status
    ).toBe(403);
    expect(
      (await PATCH(as(DEPUTY, "PATCH", { uid: ARCHIT, accessRole: "deputy" })))
        .status
    ).toBe(403);
    expect(
      (await PATCH(as(OWNER, "PATCH", { uid: ARCHIT, accessRole: "deputy" })))
        .status
    ).toBe(200);
    expect(auditRows()).toHaveLength(1);
  });

  it("rejects unknown roles", async () => {
    expect(
      (
        await PATCH(
          as(OWNER, "PATCH", { uid: ARCHIT, accessRole: "superadmin" })
        )
      ).status
    ).toBe(400);
  });
});

describe("multiple owners", () => {
  // Prod carries two owners (Nik and David); `owner: true` is per-doc.
  const OWNER_2 = "david-uid-0006";

  beforeEach(() => {
    members().set(OWNER_2, {
      email: "david@example.com",
      name: "David",
      owner: true,
    });
  });

  it("gives both owners full access", async () => {
    for (const uid of [OWNER, OWNER_2]) {
      const body = await (await GET(as(uid, "GET"))).json();
      expect(body.viewer).toMatchObject({
        uid,
        isOwner: true,
        canManage: true,
        canInvite: true,
        canRemove: true,
      });
      expect(body.viewer.scopes).toEqual([...SCOPES]);
    }
    // Full access in practice: the second owner manages the team like the first.
    expect((await DELETE(as(OWNER_2, "DELETE", { uid: ARCHIT }))).status).toBe(
      200
    );
    expect(members().has(ARCHIT)).toBe(false);
  });

  it("never lets one owner remove or re-role the other", async () => {
    expect((await DELETE(as(OWNER, "DELETE", { uid: OWNER_2 }))).status).toBe(
      403
    );
    expect((await DELETE(as(OWNER_2, "DELETE", { uid: OWNER }))).status).toBe(
      403
    );
    expect(
      (await PATCH(as(OWNER, "PATCH", { uid: OWNER_2, accessRole: "viewer" })))
        .status
    ).toBe(403);
    expect(
      (await PATCH(as(OWNER_2, "PATCH", { uid: OWNER, accessRole: "viewer" })))
        .status
    ).toBe(403);
    expect(members().get(OWNER).owner).toBe(true);
    expect(members().get(OWNER_2).owner).toBe(true);
    expect(auditRows()).toEqual([]);
  });
});

describe("concurrent invites for the same email", () => {
  /**
   * Invites never roll Auth provisioning back: a rejected invite may leave
   * an unverified, credential-less account behind (harmless — no adminData
   * doc means no admin access — and reused by the next invite of that
   * email), so no code path may delete an account, adopted or not.
   */
  it("never deletes an Auth account a concurrent invite adopted", async () => {
    const deleteUser = vi.spyOn(state.auth, "deleteUser");
    let releaseA!: () => void;
    const stalled = new Promise<void>((resolve) => (releaseA = resolve));
    let aUid: string | null = null;
    const realCreateUser = state.auth.createUser.bind(state.auth);
    state.auth.createUser = async (input: { email: string }) => {
      const user = await realCreateUser(input);
      aUid = user.uid;
      await stalled; // A holds the new account right after creating it
      return user;
    };

    const inviteA = POST(as(ARCHIT, "POST", { email: "shared@example.com" }));
    await vi.waitFor(() => expect(aUid).not.toBeNull());

    // B sees the account A provisioned (never provisions its own) and
    // lands the roster doc while A is still stalled inside createUser.
    const responseB = await POST(
      as(OWNER, "POST", { email: "SHARED@example.com", accessRole: "support" })
    );
    expect(responseB.status).toBe(201);
    expect((await responseB.json()).provisioned).toBe(false);
    expect(members().get(aUid!).accessRole).toBe("support");

    releaseA();
    const responseA = await inviteA;
    expect(responseA.status).toBe(409); // already has admin access

    // The account B adopted survives A's rejected invite — no deleteUser
    // was even attempted.
    expect(deleteUser).not.toHaveBeenCalled();
    expect(state.auth.users.has(aUid!)).toBe(true);
    expect(members().get(aUid!).accessRole).toBe("support");
  });

  it("serializes overlapping invites per email: one commits, the other retries into 409", async () => {
    state.auth.add({ uid: "shared-uid", email: "shared@example.com" });

    // Reading the per-email lock inside the transaction is what makes a
    // concurrent same-email invite conflict and re-run; count those reads so
    // this test fails if the transaction ever stops reading the lock.
    const lockReads: string[] = [];
    const realTxGet = FakeTransaction.prototype.get;
    FakeTransaction.prototype.get = async function (
      this: FakeTransaction,
      target: FakeDocRef | { get: () => Promise<any> }
    ) {
      if (
        target instanceof FakeDocRef &&
        target.collectionName === LOCK_COLLECTION
      ) {
        lockReads.push(target.id);
      }
      return realTxGet.call(this, target);
    };

    // Invite A stalls inside its transaction just after reading the
    // (missing) roster doc; invite B commits underneath it, then A resumes.
    let releaseA!: () => void;
    const stalled = new Promise<void>((resolve) => (releaseA = resolve));
    let aStalled = false;
    const realGet = FakeDocRef.prototype.get;
    let rosterReads = 0;
    FakeDocRef.prototype.get = async function (this: FakeDocRef) {
      const result = await realGet.call(this);
      if (this.collectionName === "adminData" && this.id === "shared-uid") {
        rosterReads += 1;
        if (rosterReads === 1) {
          aStalled = true;
          await stalled;
        }
      }
      return result;
    };

    let responseA!: Response;
    try {
      const inviteA = POST(as(ARCHIT, "POST", { email: "shared@example.com" }));
      await vi.waitFor(() => expect(aStalled).toBe(true));
      const responseB = await POST(
        as(OWNER, "POST", { email: "shared@example.com" })
      );
      expect(responseB.status).toBe(201);
      releaseA();
      responseA = await inviteA;
    } finally {
      FakeDocRef.prototype.get = realGet;
      FakeTransaction.prototype.get = realTxGet;
    }
    expect(responseA.status).toBe(409);

    // Exactly one grant landed …
    expect(members().get("shared-uid")).toMatchObject({
      email: "shared@example.com",
      addedBy: OWNER,
    });
    expect(
      auditRows().filter((row: any) => row.action === "member.added")
    ).toHaveLength(1);
    // … because the losing transaction re-ran against the winner's commit:
    // every attempt read the per-email lock (A twice — its first attempt
    // conflicted and retried — and B once).
    const lockId = `invite-${lockDigest("shared@example.com")}`;
    expect(lockReads.filter((id) => id === lockId)).toHaveLength(3);
  });
});

describe("GET /api/omi/team-members/audit", () => {
  it("returns events newest first", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-10-22T10:00:00Z"));
    await PATCH(as(OWNER, "PATCH", { uid: ARCHIT, accessRole: "support" }));
    vi.setSystemTime(new Date("2026-10-22T10:00:01Z"));
    await DELETE(as(OWNER, "DELETE", { uid: SUPERADMIN }));
    vi.useRealTimers();
    const response = await auditGET(
      adminRequest(firebaseToken(DEPUTY), "GET", "/api/omi/team-members/audit")
    );
    const { entries } = await response.json();
    expect(entries.map((e: any) => e.action)).toEqual([
      "member.removed",
      "member.role_changed",
    ]);
  });
});

describe("in-flight authority: mutations re-read the actor's doc", () => {
  /**
   * Changes the actor's adminData doc the moment their mutation's Nth read
   * of it happens — after the read, before the commit. The fake's conflict
   * detection retries the transaction, so the retry must re-authorize from
   * the changed doc and abort. Read 1 is authenticate(); later reads depend
   * on the mutation (addMember re-checks before provisioning, then again
   * inside its transaction).
   */
  function changeActorInsideTransaction(
    uid: string,
    doc: Record<string, any> | null,
    atRead = 2
  ) {
    const realGet = FakeDocRef.prototype.get;
    let reads = 0;
    FakeDocRef.prototype.get = async function (this: FakeDocRef) {
      const result = await realGet.call(this);
      if (this.collectionName === "adminData" && this.id === uid) {
        reads += 1;
        if (reads === atRead) {
          if (doc) members().set(uid, doc);
          else members().delete(uid);
          state.db.bump("adminData", uid);
        }
      }
      return result;
    };
    return () => {
      FakeDocRef.prototype.get = realGet;
    };
  }

  it("aborts a role change when the actor is demoted mid-flight", async () => {
    const restore = changeActorInsideTransaction(DEPUTY, {
      email: "deputy@example.com",
      accessRole: "viewer",
    });
    try {
      const response = await PATCH(
        as(DEPUTY, "PATCH", { uid: ARCHIT, accessRole: "viewer" })
      );
      expect(response.status).toBe(403);
    } finally {
      restore();
    }
    expect(members().get(ARCHIT).accessRole).toBeUndefined();
    expect(auditRows()).toEqual([]);
  });

  it("aborts a removal when the actor is demoted mid-flight", async () => {
    const restore = changeActorInsideTransaction(DEPUTY, {
      email: "deputy@example.com",
      accessRole: "viewer",
    });
    try {
      expect((await DELETE(as(DEPUTY, "DELETE", { uid: ARCHIT }))).status).toBe(
        403
      );
    } finally {
      restore();
    }
    expect(members().has(ARCHIT)).toBe(true);
    expect(auditRows()).toEqual([]);
  });

  it("aborts an addition when the actor is demoted mid-flight", async () => {
    state.auth.add({ uid: "x", email: "x@example.com" });
    const restore = changeActorInsideTransaction(ARCHIT, {
      email: "architdraftid@gmail.com",
      accessRole: "viewer",
    });
    try {
      const response = await POST(
        as(ARCHIT, "POST", { email: "x@example.com" })
      );
      expect(response.status).toBe(403);
    } finally {
      restore();
    }
    expect(members().has("x")).toBe(false);
    expect(state.sendAdminInviteEmail).not.toHaveBeenCalled();
    expect(auditRows()).toEqual([]);
  });

  it("provisions no Auth account when the inviter was demoted before the pre-check", async () => {
    // fresh@example.com has never signed in: no Firebase Auth user exists.
    // The demotion lands right after authenticate()'s read (read 1), so
    // addMember's pre-provisioning re-authorization (read 2) sees a viewer.
    const restore = changeActorInsideTransaction(
      ARCHIT,
      { email: "architdraftid@gmail.com", accessRole: "viewer" },
      1
    );
    try {
      const response = await POST(
        as(ARCHIT, "POST", { email: "fresh@example.com" })
      );
      expect(response.status).toBe(403);
    } finally {
      restore();
    }
    expect(
      Array.from(state.auth.users.values()).filter(
        (u: any) => u.email === "fresh@example.com"
      )
    ).toEqual([]);
    expect(state.auth.deleted).toEqual([]);
    expect(auditRows()).toEqual([]);
  });

  it("keeps the Auth account a rejected invite provisioned, and the next invite reuses it", async () => {
    // The demotion lands right after the pre-check's read (read 2), so the
    // pre-check passed with stale authority and a uid was provisioned; the
    // transaction's re-read (read 3) then sees a viewer and aborts. The
    // provisioned account stays: unverified and credential-less, with no
    // adminData doc it grants nothing, and the next invite of the same
    // email reuses it.
    const restore = changeActorInsideTransaction(
      ARCHIT,
      { email: "architdraftid@gmail.com", accessRole: "viewer" },
      2
    );
    let orphanUid: string | null = null;
    const realCreate = state.auth.createUser.bind(state.auth);
    state.auth.createUser = async (input: { email: string }) => {
      const user = await realCreate(input);
      orphanUid = user.uid;
      return user;
    };
    try {
      const response = await POST(
        as(ARCHIT, "POST", { email: "fresh@example.com" })
      );
      expect(response.status).toBe(403);
    } finally {
      restore();
    }
    expect(orphanUid).not.toBeNull();
    expect(state.auth.users.has(orphanUid!)).toBe(true);
    expect(members().has(orphanUid!)).toBe(false);
    expect(auditRows()).toEqual([]);

    // Re-inviting the email adopts the orphan instead of provisioning again.
    const again = await POST(as(OWNER, "POST", { email: "fresh@example.com" }));
    expect(again.status).toBe(201);
    const body = await again.json();
    expect(body.provisioned).toBe(false);
    expect(body.teamMember.id).toBe(orphanUid!);
  });

  it("aborts a deputy appointment when the owner is demoted mid-flight", async () => {
    const restore = changeActorInsideTransaction(OWNER, {
      email: "kodjima33@gmail.com",
      accessRole: "viewer",
    });
    try {
      expect(
        (await PATCH(as(OWNER, "PATCH", { uid: ARCHIT, accessRole: "deputy" })))
          .status
      ).toBe(403);
    } finally {
      restore();
    }
    expect(members().get(ARCHIT).accessRole).toBeUndefined();
    expect(members().get(ARCHIT).role).toBe("Admin");
    expect(auditRows()).toEqual([]);
  });

  it("aborts a removal when the actor's doc is deleted mid-flight", async () => {
    const restore = changeActorInsideTransaction(DEPUTY, null);
    try {
      expect((await DELETE(as(DEPUTY, "DELETE", { uid: ARCHIT }))).status).toBe(
        403
      );
    } finally {
      restore();
    }
    expect(members().has(ARCHIT)).toBe(true);
    expect(auditRows()).toEqual([]);
  });
});
