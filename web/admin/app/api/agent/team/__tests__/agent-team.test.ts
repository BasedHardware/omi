// @vitest-environment node
import { generateKeyPairSync, sign } from "node:crypto";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { OAuth2Client } from "google-auth-library";
import { CertificateFormat } from "google-auth-library/build/src/auth/oauth2client";
import {
  FakeAuth,
  FakeFirestore,
} from "@/lib/__tests__/support/fake-firestore";
import {
  adminRequest,
  decodeTestFirebaseToken,
  firebaseToken,
} from "@/lib/__tests__/support/admin-request";

const state = vi.hoisted(() => ({ db: null as any, auth: null as any }));
vi.mock("@/lib/firebase/admin", () => ({
  getDb: () => state.db,
  getAdminAuth: () => state.auth,
  verifyFirebaseToken: async (token: string) => decodeTestFirebaseToken(token),
}));
vi.mock("@/lib/dev-auth", () => ({ DEV_BYPASS_ENABLED: false }));
vi.mock("@/lib/email/invite", () => ({
  sendAdminInviteEmail: vi.fn(async () => ({ sent: true })),
}));

import { GET as rosterGET } from "../route";
import { GET as auditGET } from "../audit/route";
import { GET as proposalsGET, POST as proposePOST } from "../proposals/route";
import { POST as decidePOST } from "@/app/api/omi/team-members/proposals/[id]/route";
import { GET as humanProposalsGET } from "@/app/api/omi/team-members/proposals/route";
import { GET as humanRosterGET } from "@/app/api/omi/team-members/route";
import { GET as userDataGET } from "@/app/api/omi/fair-use/flagged/route";
import { sendAdminInviteEmail } from "@/lib/email/invite";
import { MAX_PENDING_PER_AGENT, PROPOSAL_TTL_MS } from "@/lib/team/proposals";

const AUDIENCE = "https://admin.omi.me/api/agent/team";
const AGENT = "omi-team-agent@based-hardware.iam.gserviceaccount.com";
const { privateKey, publicKey } = generateKeyPairSync("rsa", {
  modulusLength: 2048,
});
const pem = publicKey.export({ type: "spki", format: "pem" }).toString();
const encoded = (value: unknown) =>
  Buffer.from(JSON.stringify(value)).toString("base64url");

function agentToken(overrides: Record<string, unknown> = {}) {
  const now = Math.floor(Date.now() / 1000);
  const input = `${encoded({ alg: "RS256", kid: "test-key" })}.${encoded({
    iss: "https://accounts.google.com",
    aud: AUDIENCE,
    sub: "agent-sub",
    email: AGENT,
    email_verified: true,
    iat: now - 10,
    exp: now + 3600,
    ...overrides,
  })}`;
  return `${input}.${sign(
    "RSA-SHA256",
    Buffer.from(input),
    privateKey
  ).toString("base64url")}`;
}

const OWNER = "owner-uid";
const DEPUTY = "deputy-uid";
const ADMIN = "admin-uid";
const members = () => state.db.table("adminData") as Map<string, any>;
const proposals = () => state.db.table("adminProposals") as Map<string, any>;
const actions = () => state.db.rows("adminAuditLog").map((e: any) => e.action);

const agent = (
  method: string,
  path: string,
  body?: unknown,
  token = agentToken()
) => adminRequest(token, method, path, body);
const human = (uid: string, method: string, path: string, body?: unknown) =>
  adminRequest(firebaseToken(uid), method, path, body);
const propose = async (body: unknown) =>
  proposePOST(agent("POST", "/api/agent/team/proposals", body));
const decide = (uid: string, id: string, decision: string) =>
  decidePOST(
    human(uid, "POST", `/api/omi/team-members/proposals/${id}`, { decision }),
    {
      params: Promise.resolve({ id }),
    }
  );

beforeEach(() => {
  state.db = new FakeFirestore();
  state.auth = new FakeAuth();
  members().set(OWNER, { email: "owner@example.com", owner: true });
  members().set(DEPUTY, { email: "deputy@example.com", accessRole: "deputy" });
  members().set(ADMIN, { email: "admin@example.com", role: "Admin" });
  vi.stubEnv("ADMIN_TEAM_AGENT_SAS", AGENT);
  vi.stubEnv("ADMIN_TEAM_AGENT_AUDIENCE", AUDIENCE);
  vi.stubEnv("ADMIN_STATS_READER_SAS", AGENT);
  vi.stubEnv(
    "ADMIN_STATS_READER_AUDIENCE",
    "https://admin.omi.me/api/omi/stats"
  );
  vi.spyOn(console, "info").mockImplementation(() => {});
  vi.spyOn(console, "log").mockImplementation(() => {});
  vi.spyOn(
    OAuth2Client.prototype,
    "getFederatedSignonCertsAsync"
  ).mockResolvedValue({
    certs: { "test-key": pem },
    format: CertificateFormat.PEM,
  });
});
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllEnvs();
  vi.useRealTimers();
});

describe("team agent authentication", () => {
  it("reads the roster and audit log with an allowlisted service account", async () => {
    const roster = await rosterGET(agent("GET", "/api/agent/team"));
    expect(roster.status).toBe(200);
    expect((await roster.json()).teamMembers).toHaveLength(3);
    expect((await auditGET(agent("GET", "/api/agent/team/audit"))).status).toBe(
      200
    );
  });

  it.each([
    ["disabled", () => vi.stubEnv("ADMIN_TEAM_AGENT_SAS", ""), agentToken],
    [
      "wrong audience (a stats-reader token)",
      () => {},
      () => agentToken({ aud: "https://admin.omi.me/api/omi/stats" }),
    ],
    [
      "not allowlisted",
      () => {},
      () =>
        agentToken({ email: "other@based-hardware.iam.gserviceaccount.com" }),
    ],
    [
      "expired",
      () => {},
      () => agentToken({ exp: Math.floor(Date.now() / 1000) - 1 }),
    ],
    ["a human Firebase token", () => {}, () => firebaseToken(OWNER)],
  ])("rejects %s", async (_name, setup, token) => {
    setup();
    expect(
      (await rosterGET(agent("GET", "/api/agent/team", undefined, token())))
        .status
    ).toBe(401);
  });

  it("rejects every agent route when the Authorization header is missing", async () => {
    const calls: [string, () => Promise<Response>][] = [
      [
        "GET /api/agent/team",
        () => rosterGET(adminRequest(null, "GET", "/api/agent/team")),
      ],
      [
        "GET /api/agent/team/audit",
        () => auditGET(adminRequest(null, "GET", "/api/agent/team/audit")),
      ],
      [
        "GET /api/agent/team/proposals",
        () =>
          proposalsGET(adminRequest(null, "GET", "/api/agent/team/proposals")),
      ],
      [
        "POST /api/agent/team/proposals",
        () =>
          proposePOST(
            adminRequest(null, "POST", "/api/agent/team/proposals", {})
          ),
      ],
    ];
    for (const [name, call] of calls) {
      expect((await call()).status, name).toBe(401);
    }
  });

  it("gets no admin scope: human routes, user data and approval all refuse the agent token", async () => {
    const token = agentToken();
    expect(
      (
        await humanRosterGET(
          adminRequest(token, "GET", "/api/omi/team-members")
        )
      ).status
    ).toBe(401);
    expect(
      (
        await userDataGET(
          adminRequest(token, "GET", "/api/omi/fair-use/flagged")
        )
      ).status
    ).toBe(401);
    const filed = await (
      await propose({ kind: "remove_member", uid: ADMIN, reason: "left" })
    ).json();
    const approve = await decidePOST(
      adminRequest(
        token,
        "POST",
        `/api/omi/team-members/proposals/${filed.proposal.id}`,
        { decision: "approve" }
      ),
      { params: Promise.resolve({ id: filed.proposal.id }) }
    );
    expect(approve.status).toBe(401);
    expect(members().has(ADMIN)).toBe(true);
  });
});

describe("proposals", () => {
  it("files a role change without applying it, and audits the filing", async () => {
    const response = await propose({
      kind: "set_role",
      uid: ADMIN,
      accessRole: "support",
      reason: "moved to support",
    });
    expect(response.status).toBe(201);
    const { proposal } = await response.json();
    expect(proposal).toMatchObject({
      status: "pending",
      proposedBy: { type: "agent", email: AGENT },
      target: { uid: ADMIN, email: "admin@example.com" },
      before: { accessRole: null },
      after: { accessRole: "support" },
    });
    expect(
      Date.parse(proposal.expiresAt) - Date.parse(proposal.createdAt)
    ).toBe(PROPOSAL_TTL_MS);
    expect(members().get(ADMIN).accessRole).toBeUndefined();
    expect(actions()).toEqual(["proposal.created"]);
  });

  it.each([
    [
      { kind: "add_member", email: AGENT, accessRole: "viewer", reason: "me" },
      403,
    ],
    [
      {
        kind: "add_member",
        email: "x@project.iam.gserviceaccount.com",
        accessRole: "viewer",
        reason: "bot",
      },
      403,
    ],
    [
      {
        kind: "add_member",
        email: "admin@example.com",
        accessRole: "viewer",
        reason: "dupe",
      },
      409,
    ],
    [{ kind: "remove_member", uid: OWNER, reason: "coup" }, 403],
    [
      { kind: "set_role", uid: OWNER, accessRole: "viewer", reason: "coup" },
      403,
    ],
    [{ kind: "remove_member", uid: "nobody", reason: "?" }, 404],
    [
      {
        kind: "set_role",
        uid: ADMIN,
        accessRole: "superadmin",
        reason: "bad role",
      },
      400,
    ],
    [{ kind: "remove_member", uid: ADMIN }, 400],
    [{ kind: "approve", id: "anything", reason: "self-approve" }, 400],
  ])("refuses %j with %i", async (body, status) => {
    expect((await propose(body)).status).toBe(status);
    expect(proposals().size).toBe(0);
  });

  it("refuses to grant itself access even when its email is in a member doc", async () => {
    members().set("agent-doc", { email: AGENT, accessRole: "viewer" });
    expect(
      (
        await propose({
          kind: "set_role",
          uid: "agent-doc",
          accessRole: "admin",
          reason: "x",
        })
      ).status
    ).toBe(403);
  });

  it("refuses a duplicate pending proposal for the same target", async () => {
    await propose({ kind: "remove_member", uid: ADMIN, reason: "left" });
    expect(
      (await propose({ kind: "remove_member", uid: ADMIN, reason: "again" }))
        .status
    ).toBe(409);
  });

  it("refuses a pending proposal of another kind for the same target", async () => {
    expect(
      (
        await propose({
          kind: "set_role",
          uid: ADMIN,
          accessRole: "support",
          reason: "to support",
        })
      ).status
    ).toBe(201);
    expect(
      (await propose({ kind: "remove_member", uid: ADMIN, reason: "gone" }))
        .status
    ).toBe(409);
    expect(proposals().size).toBe(1);
  });

  it("files only one of two overlapping proposals of different kinds for the same target", async () => {
    const statuses = (
      await Promise.all([
        propose({
          kind: "set_role",
          uid: ADMIN,
          accessRole: "support",
          reason: "a",
        }),
        propose({ kind: "remove_member", uid: ADMIN, reason: "b" }),
      ])
    ).map((r) => r.status);
    expect(statuses.sort()).toEqual([201, 409]);
    expect(proposals().size).toBe(1);
  });

  it("applies on owner or deputy approval, once, with the approver and proposer audited", async () => {
    state.auth.add({ uid: "new-uid", email: "new@example.com" });
    const { proposal } = await (
      await propose({
        kind: "add_member",
        email: "new@example.com",
        accessRole: "support",
        reason: "new hire",
      })
    ).json();

    expect((await decide(ADMIN, proposal.id, "approve")).status).toBe(403); // legacy admin lacks team:manage
    expect(members().has("new-uid")).toBe(false);

    const approved = await decide(DEPUTY, proposal.id, "approve");
    expect(approved.status).toBe(200);
    expect(members().get("new-uid")).toMatchObject({
      accessRole: "support",
      addedBy: DEPUTY,
    });
    expect(proposals().get(proposal.id)).toMatchObject({
      status: "approved",
      decidedBy: { uid: DEPUTY },
    });
    expect((await decide(OWNER, proposal.id, "approve")).status).toBe(409);

    const log = state.db.rows("adminAuditLog");
    expect(log.map((e: any) => e.action)).toEqual([
      "proposal.created",
      "proposal.approved",
      "member.added",
    ]);
    expect(log.find((e: any) => e.action === "member.added")).toMatchObject({
      actor: { type: "human", id: DEPUTY },
      proposalId: proposal.id,
      proposedBy: AGENT,
      reason: "new hire",
    });
  });

  it("keeps deputy appointments owner-only, even by proposal", async () => {
    const { proposal } = await (
      await propose({
        kind: "set_role",
        uid: ADMIN,
        accessRole: "deputy",
        reason: "backup",
      })
    ).json();
    expect((await decide(DEPUTY, proposal.id, "approve")).status).toBe(403);
    expect(proposals().get(proposal.id).status).toBe("pending");
    expect((await decide(OWNER, proposal.id, "approve")).status).toBe(200);
    expect(members().get(ADMIN).accessRole).toBe("deputy");
  });

  it("tells the approver when an approved add-person invite email fails, and audits it", async () => {
    vi.mocked(sendAdminInviteEmail).mockResolvedValueOnce({
      sent: false,
      reason: "not-configured",
    });
    const failedProposal = (
      await (
        await propose({
          kind: "add_member",
          email: "new@example.com",
          accessRole: "support",
          reason: "new hire",
        })
      ).json()
    ).proposal;
    const approved = await decide(OWNER, failedProposal.id, "approve");
    expect(approved.status).toBe(200);
    expect((await approved.json()).proposal.emailSent).toBe(false);
    expect(members().get("new-uid-1")).toMatchObject({
      accessRole: "support",
      addedBy: OWNER,
    });
    expect(
      state.db
        .rows("adminAuditLog")
        .find((e: any) => e.action === "member.invite_failed")
    ).toMatchObject({
      actor: { type: "human", id: OWNER },
      target: { uid: "new-uid-1", email: "new@example.com" },
      proposalId: failedProposal.id,
      proposedBy: AGENT,
    });

    // A delivered invite reports plain success and writes no such entry.
    const delivered = (
      await (
        await propose({
          kind: "add_member",
          email: "ok@example.com",
          accessRole: "viewer",
          reason: "fine",
        })
      ).json()
    ).proposal;
    const ok = await decide(OWNER, delivered.id, "approve");
    expect((await ok.json()).proposal.emailSent).toBe(true);
    expect(
      state.db
        .rows("adminAuditLog")
        .filter((e: any) => e.action === "member.invite_failed")
    ).toHaveLength(1);
  });

  it("removes on approval and records rejection without change", async () => {
    const remove = (
      await (
        await propose({ kind: "remove_member", uid: ADMIN, reason: "left" })
      ).json()
    ).proposal;
    expect((await decide(OWNER, remove.id, "reject")).status).toBe(200);
    expect(members().has(ADMIN)).toBe(true);
    expect(proposals().get(remove.id).status).toBe("rejected");

    const again = (
      await (
        await propose({
          kind: "remove_member",
          uid: ADMIN,
          reason: "really left",
        })
      ).json()
    ).proposal;
    expect((await decide(OWNER, again.id, "approve")).status).toBe(200);
    expect(members().has(ADMIN)).toBe(false);
    expect(actions()).toEqual([
      "proposal.created",
      "proposal.rejected",
      "proposal.created",
      "proposal.approved",
      "member.removed",
    ]);
  });

  it("expires unapproved proposals and audits the expiry", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-10-22T00:00:00Z"));
    const { proposal } = await (
      await propose({ kind: "remove_member", uid: ADMIN, reason: "left" })
    ).json();
    vi.setSystemTime(
      new Date(Date.parse("2026-10-22T00:00:00Z") + PROPOSAL_TTL_MS + 1000)
    );

    expect((await decide(OWNER, proposal.id, "approve")).status).toBe(410);
    expect(members().has(ADMIN)).toBe(true);
    expect(proposals().get(proposal.id).status).toBe("expired");
    expect(actions()).toEqual(["proposal.created", "proposal.expired"]);
    const expiry = state.db
      .rows("adminAuditLog")
      .find((e: any) => e.action === "proposal.expired");
    // A lifecycle event, not something the agent did; the proposer stays recorded.
    expect(expiry).toMatchObject({
      actor: { type: "system", id: "proposal-expiry" },
      proposedBy: AGENT,
    });
  });

  it("files only one of two overlapping proposals for the same target", async () => {
    const statuses = (
      await Promise.all([
        propose({ kind: "remove_member", uid: ADMIN, reason: "a" }),
        propose({ kind: "remove_member", uid: ADMIN, reason: "b" }),
      ])
    ).map((r) => r.status);
    expect(statuses.sort()).toEqual([201, 409]);
    expect(proposals().size).toBe(1);
  });

  it("holds the per-agent cap under a burst of overlapping proposals", async () => {
    const burst = Array.from({ length: MAX_PENDING_PER_AGENT + 3 }, (_, i) =>
      propose({
        kind: "add_member",
        email: `p${i}@example.com`,
        accessRole: "viewer",
        reason: "burst",
      })
    );
    const statuses = (await Promise.all(burst)).map((r) => r.status);
    expect(statuses.filter((s) => s === 201)).toHaveLength(
      MAX_PENDING_PER_AGENT
    );
    expect(statuses.filter((s) => s === 429)).toHaveLength(3);
    expect(proposals().size).toBe(MAX_PENDING_PER_AGENT);
  });

  it("keeps an older pending proposal listed behind a long decided history", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-10-22T00:00:00Z"));
    const { proposal } = await (
      await propose({ kind: "remove_member", uid: ADMIN, reason: "left" })
    ).json();
    for (let i = 0; i < 120; i++) {
      proposals().set(`old-${i}`, {
        kind: "remove_member",
        status: "rejected",
        proposedBy: { type: "agent", email: AGENT },
        createdAt: new Date(
          Date.parse("2026-10-22T01:00:00Z") + i * 1000
        ).toISOString(),
        expiresAt: "2026-10-25T00:00:00.000Z",
        target: { uid: ADMIN, email: "admin@example.com" },
      });
    }
    const list = await (
      await humanProposalsGET(
        human(OWNER, "GET", "/api/omi/team-members/proposals")
      )
    ).json();
    expect(list.proposals.map((p: any) => p.id)).toContain(proposal.id);
    expect(list.proposals[0].createdAt >= list.proposals[1].createdAt).toBe(
      true
    );
  });

  it("expires stale proposals when the Team page lists them", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-10-22T00:00:00Z"));
    await propose({ kind: "remove_member", uid: ADMIN, reason: "left" });
    vi.setSystemTime(
      new Date(Date.parse("2026-10-22T00:00:00Z") + PROPOSAL_TTL_MS + 1000)
    );

    const list = await (
      await humanProposalsGET(
        human(OWNER, "GET", "/api/omi/team-members/proposals")
      )
    ).json();
    expect(list.proposals[0].status).toBe("expired");
    const agentView = await (
      await proposalsGET(
        agent("GET", "/api/agent/team/proposals", undefined, agentToken())
      )
    ).json();
    expect(agentView.proposals[0].status).toBe("expired");
    expect(
      actions().filter((a: string) => a === "proposal.expired")
    ).toHaveLength(1);
  });
});
