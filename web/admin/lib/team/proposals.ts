import { z } from "zod";
import { getDb } from "@/lib/firebase/admin";
import {
  ROLE_IDS,
  SCOPES,
  hasScope,
  type RoleId,
  type ScopeOverrides,
} from "@/lib/admin-access";
import { parseAllowlist } from "@/lib/service-account-token";
import {
  ADMIN_COLLECTION,
  LOCK_COLLECTION,
  PROPOSAL_COLLECTION,
  TeamError,
  addMember,
  assignmentSnapshot,
  audit,
  currentActor,
  humanAuditActor,
  inviteLockId,
  lockDigest,
  removeMember,
  setMemberRole,
  snapshot,
  type AccessSnapshot,
  type ApprovalContext,
  type AuditActor,
  type HumanActor,
} from "@/lib/team/roster";

/** An unapproved proposal stops being approvable after this long. */
export const PROPOSAL_TTL_MS = 72 * 60 * 60 * 1000;
/** Per agent, so a misbehaving agent cannot bury the owner in requests. */
export const MAX_PENDING_PER_AGENT = 20;

const scopeList = z.array(z.enum(SCOPES)).max(SCOPES.length).optional();
const overrides = z
  .object({ grant: scopeList, deny: scopeList })
  .strict()
  .optional();
const reason = z.string().trim().min(1).max(500);
const role = z.enum(ROLE_IDS);

export const proposalInput = z.discriminatedUnion("kind", [
  z
    .object({
      kind: z.literal("add_member"),
      email: z
        .string()
        .trim()
        .email()
        .transform((e) => e.toLowerCase()),
      accessRole: role,
      scopeOverrides: overrides,
      reason,
    })
    .strict(),
  z
    .object({
      kind: z.literal("remove_member"),
      uid: z.string().trim().min(1).max(128),
      reason,
    })
    .strict(),
  z
    .object({
      kind: z.literal("set_role"),
      uid: z.string().trim().min(1).max(128),
      accessRole: role,
      scopeOverrides: overrides,
      reason,
    })
    .strict(),
]);

export type ProposalInput = z.infer<typeof proposalInput>;
export type ProposalStatus = "pending" | "approved" | "rejected" | "expired";

export interface Proposal {
  id: string;
  kind: ProposalInput["kind"];
  status: ProposalStatus;
  proposedBy: { type: "agent"; email: string };
  reason: string;
  createdAt: string;
  expiresAt: string;
  target: { uid: string | null; email: string | null };
  /** Access when proposed, and what approval would set. */
  before: AccessSnapshot | null;
  after: AccessSnapshot | null;
  change: {
    accessRole?: RoleId;
    scopeOverrides?: ScopeOverrides;
  };
  decidedAt?: string;
  decidedBy?: { uid: string; email: string | null };
  /** Approved add_member only: false when the sign-in email could not be sent. */
  emailSent?: boolean;
}

type Data = Record<string, unknown>;

/** Expiry is a lifecycle event, not something the proposing agent did. */
const EXPIRY_ACTOR: AuditActor = {
  type: "system",
  id: "proposal-expiry",
  email: null,
};

function agentActor(email: string): AuditActor {
  return { type: "agent", id: email, email };
}

/**
 * An agent may not propose anything for itself or for any machine identity:
 * the target must be a person. Owner changes are Firestore-only.
 */
function assertTargetIsAPerson(agentEmail: string, email: string | null) {
  const lower = email?.toLowerCase() ?? "";
  const agents = parseAllowlist(process.env.ADMIN_TEAM_AGENT_SAS).map((e) =>
    e.toLowerCase()
  );
  if (
    lower === agentEmail.toLowerCase() ||
    lower.endsWith(".gserviceaccount.com") ||
    agents.includes(lower)
  ) {
    throw new TeamError(
      403,
      "An agent cannot propose access for itself or another machine identity."
    );
  }
}

export async function createProposal(
  agentEmail: string,
  input: ProposalInput
): Promise<Proposal> {
  const db = getDb();
  const members = db.collection(ADMIN_COLLECTION);
  const proposals = db.collection(PROPOSAL_COLLECTION);

  const now = Date.now();

  let target: Proposal["target"];
  let before: AccessSnapshot | null = null;
  let after: AccessSnapshot | null = null;
  if (input.kind === "add_member") {
    assertTargetIsAPerson(agentEmail, input.email);
    // Fast path outside the locks; the authoritative re-check runs inside
    // the transaction below, after the per-email lock is taken. Query
    // chains keep string literals so the Firestore contract test can
    // extract them (imported constants do not resolve across files).
    const existing = await db
      .collection("adminData")
      .where("email", "==", input.email)
      .get();
    if (!existing.empty) {
      throw new TeamError(409, `${input.email} already has admin access.`);
    }
    target = { uid: null, email: input.email };
    after = assignmentSnapshot(input.accessRole, input.scopeOverrides ?? {});
  } else {
    const doc = await members.doc(input.uid).get();
    if (!doc.exists) throw new TeamError(404, "No admin has that uid.");
    const data = doc.data() as Data;
    const email = typeof data.email === "string" ? data.email : null;
    assertTargetIsAPerson(agentEmail, email);
    if (data.owner === true) {
      throw new TeamError(403, "Owners cannot be changed by proposal.");
    }
    target = { uid: input.uid, email };
    before = snapshot(data);
    if (input.kind === "set_role") {
      after = assignmentSnapshot(input.accessRole, input.scopeOverrides ?? {});
    }
  }

  const ref = proposals.doc();
  const proposal: Omit<Proposal, "id"> = {
    kind: input.kind,
    status: "pending",
    proposedBy: { type: "agent", email: agentEmail },
    reason: input.reason,
    createdAt: new Date(now).toISOString(),
    expiresAt: new Date(now + PROPOSAL_TTL_MS).toISOString(),
    target,
    before,
    after,
    change:
      input.kind === "remove_member"
        ? {}
        : {
            accessRole: input.accessRole,
            scopeOverrides: {
              grant: input.scopeOverrides?.grant ?? [],
              deny: input.scopeOverrides?.deny ?? [],
            },
          },
  };
  // The per-agent cap and the one-pending-per-target rule are checked inside
  // a transaction that also writes a lock doc for the agent and one for the
  // target, so overlapping requests conflict and retry instead of both passing.
  // The target identity is the member's uid (or the invitee's email for
  // add_member, which locks the very same doc a direct invite takes): any
  // kind of pending change on one target is the same lock, so two different
  // kinds cannot both be pending.
  const locks = db.collection(LOCK_COLLECTION);
  const agentLock = locks.doc(`agent-${lockDigest(agentEmail.toLowerCase())}`);
  const targetKey = target.uid ?? target.email ?? "";
  const targetLock = locks.doc(
    input.kind === "add_member"
      ? inviteLockId(input.email)
      : `target-${lockDigest(targetKey)}`
  );
  const stale: { id: string; data: Proposal }[] = [];
  await db.runTransaction(async (tx) => {
    await tx.get(agentLock);
    await tx.get(targetLock);
    // Read after taking the locks: a conflicting commit re-runs this callback,
    // so the retry sees the proposal (or roster doc) that won.
    stale.length = 0;
    if (input.kind === "add_member") {
      const existing = await db
        .collection("adminData")
        .where("email", "==", input.email)
        .get();
      if (!existing.empty) {
        throw new TeamError(409, `${input.email} already has admin access.`);
      }
    }
    const pending = await db
      .collection("adminProposals")
      .where("status", "==", "pending")
      .get();
    for (const doc of pending.docs) {
      if (Date.parse((doc.data() as Proposal).expiresAt) <= now) {
        stale.push({ id: doc.id, data: doc.data() as Proposal });
      }
    }
    const live = pending.docs
      .map((doc) => ({ ...(doc.data() as Proposal), id: doc.id }))
      .filter((p) => Date.parse(p.expiresAt) > now);
    if (
      live.filter((p) => p.proposedBy.email === agentEmail).length >=
      MAX_PENDING_PER_AGENT
    ) {
      throw new TeamError(429, "Too many pending proposals from this agent.");
    }
    const duplicate = live.find(
      (p) => (p.target.uid ?? p.target.email ?? "") === targetKey
    );
    if (duplicate) {
      throw new TeamError(
        409,
        `Proposal ${duplicate.id} is already pending for this target.`
      );
    }
    const stamp = { updatedAt: new Date(now).toISOString() };
    tx.set(agentLock, stamp);
    tx.set(targetLock, stamp);
    tx.set(ref, proposal);
    audit(tx, {
      action: "proposal.created",
      actor: agentActor(agentEmail),
      target,
      before,
      after,
      proposalId: ref.id,
      proposedBy: agentEmail,
      reason: input.reason,
    });
  });
  // The filing committed; stale proposals it superseded now persist their
  // expiry (best effort — a cleanup failure never fails the filing, and the
  // derived display already reads them as expired).
  try {
    await expireStale(stale);
  } catch (error) {
    console.error("Could not persist stale proposal expiries:", error);
  }
  return { id: ref.id, ...proposal };
}

/** Mark pending proposals past their expiry as expired, each with an audit entry. */
async function expireStale(docs: { id: string; data: Proposal }[]) {
  const db = getDb();
  const now = Date.now();
  for (const { id, data } of docs) {
    if (data.status !== "pending" || Date.parse(data.expiresAt) > now) continue;
    const ref = db.collection(PROPOSAL_COLLECTION).doc(id);
    await db.runTransaction(async (tx) => {
      const fresh = await tx.get(ref);
      if ((fresh.data() as Proposal | undefined)?.status !== "pending") return;
      tx.update(ref, { status: "expired" });
      audit(tx, {
        action: "proposal.expired",
        actor: EXPIRY_ACTOR,
        target: data.target,
        before: data.before,
        after: data.after,
        proposalId: id,
        proposedBy: data.proposedBy.email,
      });
    });
    data.status = "expired";
  }
}

/**
 * Derives the displayed status: a pending proposal past its expiry reads as
 * expired whether or not a write has persisted the transition yet. Reads
 * never mutate; the transition (and its audit entry) persists on the next
 * write — deciding, or the next filing (see createProposal).
 */
export function displayedStatus(
  proposal: Pick<Proposal, "status" | "expiresAt">,
  now = Date.now()
): ProposalStatus {
  return proposal.status === "pending" && Date.parse(proposal.expiresAt) <= now
    ? "expired"
    : proposal.status;
}

/**
 * Every pending proposal (so an actionable one never falls off the page),
 * plus the most recent history, newest first. Pure: expiry is derived per
 * response; nothing is written.
 */
export async function listProposals(limit = 100): Promise<Proposal[]> {
  const db = getDb();
  const [pending, recent] = await Promise.all([
    db.collection("adminProposals").where("status", "==", "pending").get(),
    db
      .collection("adminProposals")
      .orderBy("createdAt", "desc")
      .limit(Math.min(Math.max(limit, 1), 200))
      .get(),
  ]);
  const byId = new Map<string, Proposal>();
  for (const doc of [...pending.docs, ...recent.docs]) {
    byId.set(doc.id, doc.data() as Proposal);
  }
  return Array.from(byId, ([id, data]) => ({
    ...data,
    id,
    status: displayedStatus(data),
  })).sort((a, b) => (a.createdAt < b.createdAt ? 1 : -1));
}

/**
 * A human with team:manage approves or rejects. Approval applies the change
 * through the same functions and authority checks as a direct edit, in one
 * transaction with the proposal's status, so a proposal applies at most once.
 */
export async function decideProposal(
  actor: HumanActor,
  id: string,
  decision: "approve" | "reject"
): Promise<Proposal> {
  const db = getDb();
  const ref = db.collection(PROPOSAL_COLLECTION).doc(id);
  const initial = await ref.get();
  if (!initial.exists) throw new TeamError(404, "No such proposal.");
  const proposal = { ...(initial.data() as Proposal), id };
  if (proposal.status !== "pending") {
    throw new TeamError(409, `This proposal is already ${proposal.status}.`);
  }
  if (Date.parse(proposal.expiresAt) <= Date.now()) {
    await expireStale([{ id, data: proposal }]);
    throw new TeamError(410, "This proposal has expired.");
  }
  const decidedAt = new Date().toISOString();
  const decidedBy = { uid: actor.uid, email: actor.email };

  if (decision === "reject") {
    await db.runTransaction(async (tx) => {
      // The reject decision is a team mutation: re-authorize from the
      // actor's current doc so a mid-flight demotion cannot reject with
      // authority they just lost.
      const acting = await currentActor(tx, actor);
      if (!hasScope(acting.access, "team:manage")) {
        throw new TeamError(
          403,
          "Only an owner or a deputy can decide proposals."
        );
      }
      const fresh = await tx.get(ref);
      if ((fresh.data() as Proposal).status !== "pending") {
        throw new TeamError(409, "This proposal was decided meanwhile.");
      }
      tx.update(ref, { status: "rejected", decidedAt, decidedBy });
      audit(tx, {
        action: "proposal.rejected",
        actor: humanAuditActor(actor),
        target: proposal.target,
        before: proposal.before,
        after: proposal.after,
        proposalId: id,
        proposedBy: proposal.proposedBy.email,
      });
    });
    return { ...proposal, status: "rejected", decidedAt, decidedBy };
  }

  const approval: ApprovalContext = {
    proposalId: id,
    proposedBy: proposal.proposedBy.email,
    reason: proposal.reason,
    check: async (tx) => {
      const fresh = (await tx.get(ref)).data() as Proposal;
      if (
        fresh.status !== "pending" ||
        Date.parse(fresh.expiresAt) <= Date.now()
      ) {
        throw new TeamError(
          409,
          "This proposal was decided or expired meanwhile."
        );
      }
    },
    commit: (tx) => {
      tx.update(ref, { status: "approved", decidedAt, decidedBy });
      audit(tx, {
        action: "proposal.approved",
        actor: humanAuditActor(actor),
        target: proposal.target,
        before: proposal.before,
        after: proposal.after,
        proposalId: id,
        proposedBy: proposal.proposedBy.email,
      });
    },
  };

  if (proposal.kind === "add_member") {
    const applied = await addMember(
      actor,
      {
        email: proposal.target.email!,
        accessRole: proposal.change.accessRole!,
        scopeOverrides: proposal.change.scopeOverrides,
      },
      approval
    );
    if (!applied.emailSent) {
      // The grant landed but the person never heard about it. The approver
      // is told in the response; the audit log records why they had to
      // reach out by hand.
      await db.runTransaction(async (tx) => {
        audit(tx, {
          action: "member.invite_failed",
          actor: humanAuditActor(actor),
          target: {
            uid: applied.teamMember.id,
            email: applied.teamMember.email,
          },
          before: null,
          after: proposal.after,
          proposalId: id,
          proposedBy: proposal.proposedBy.email,
        });
      });
    }
    return {
      ...proposal,
      status: "approved",
      decidedAt,
      decidedBy,
      emailSent: applied.emailSent,
    };
  } else if (proposal.kind === "remove_member") {
    await removeMember(actor, proposal.target.uid!, approval);
  } else {
    // The proposal's "before" was captured when it was filed; the change
    // audit entry records the access actually replaced at approval time.
    await setMemberRole(
      actor,
      proposal.target.uid!,
      proposal.change.accessRole!,
      proposal.change.scopeOverrides,
      approval
    );
  }
  return { ...proposal, status: "approved", decidedAt, decidedBy };
}
