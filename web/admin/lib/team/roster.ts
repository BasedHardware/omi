import { createHash } from "node:crypto";
import type { UserRecord } from "firebase-admin/auth";
import { getAdminAuth, getDb } from "@/lib/firebase/admin";
import { sendAdminInviteEmail } from "@/lib/email/invite";
import {
  ROLES,
  accessFor,
  hasScope,
  scopesForAssignment,
  type MemberAccess,
  type RoleId,
  type Scope,
  type ScopeOverrides,
} from "@/lib/admin-access";

export const ADMIN_COLLECTION = "adminData";
export const AUDIT_COLLECTION = "adminAuditLog";
export const PROPOSAL_COLLECTION = "adminProposals";
/** Lock docs that serialize proposal creation and invites per target. */
export const LOCK_COLLECTION = "adminProposalLocks";

/** Stable doc-id digest for lock docs (proposals, invites). */
export const lockDigest = (value: string) =>
  createHash("sha256").update(value).digest("hex").slice(0, 32);

/**
 * The one lock doc id for a normalized email: direct invites and
 * `add_member` proposals for the same person serialize on it, so whichever
 * commits first forces the other to re-run against its result.
 */
export const inviteLockId = (email: string) => `invite-${lockDigest(email)}`;

/** A person acting in the dashboard; agents never apply changes themselves. */
export interface HumanActor {
  uid: string;
  email: string | null;
  access: MemberAccess;
}

export type AuditActor =
  | { type: "human"; id: string; email: string | null }
  | { type: "agent"; id: string; email: string }
  | { type: "system"; id: string; email: null };

export type AuditAction =
  | "member.added"
  | "member.removed"
  | "member.role_changed"
  | "member.invite_failed"
  | "proposal.created"
  | "proposal.approved"
  | "proposal.rejected"
  | "proposal.expired";

export interface AccessSnapshot {
  accessRole: RoleId | null;
  roleLabel: string;
  scopes: Scope[];
  scopeOverrides: ScopeOverrides;
}

export interface AuditEntry {
  at: string;
  action: AuditAction;
  actor: AuditActor;
  target: { uid: string | null; email: string | null };
  before: AccessSnapshot | null;
  after: AccessSnapshot | null;
  proposalId?: string;
  proposedBy?: string;
  reason?: string;
}

export class TeamError extends Error {
  constructor(readonly status: number, message: string) {
    super(message);
  }
}

type Data = Record<string, unknown>;
type Tx = FirebaseFirestore.Transaction;

export function humanAuditActor(actor: HumanActor): AuditActor {
  return { type: "human", id: actor.uid, email: actor.email };
}

export function snapshot(data: Data | undefined): AccessSnapshot | null {
  if (!data) return null;
  const access = accessFor(data);
  return {
    accessRole: access.role,
    roleLabel: access.roleLabel,
    scopes: access.scopes,
    scopeOverrides: access.overrides,
  };
}

export function assignmentSnapshot(
  role: RoleId,
  overrides: ScopeOverrides
): AccessSnapshot {
  return snapshot({ accessRole: role, scopeOverrides: overrides })!;
}

export function auditRef() {
  return getDb().collection(AUDIT_COLLECTION).doc();
}

export function audit(tx: Tx, entry: Omit<AuditEntry, "at">) {
  const record: AuditEntry = { at: new Date().toISOString(), ...entry };
  // Firestore rejects undefined fields.
  for (const key of Object.keys(record) as (keyof AuditEntry)[]) {
    if (record[key] === undefined) delete record[key];
  }
  tx.set(auditRef(), record);
}

const isOwner = (data: Data | undefined) => data?.owner === true;
const isDeputy = (data: Data | undefined) =>
  !isOwner(data) && data?.accessRole === "deputy";

function assertNoBroaderThanActor(
  actor: HumanActor,
  role: RoleId,
  overrides: ScopeOverrides
) {
  const missing = scopesForAssignment(role, overrides).filter(
    (scope) => !hasScope(actor.access, scope)
  );
  if (missing.length) {
    throw new TeamError(
      403,
      `You cannot grant access you do not have (${missing.join(", ")}).`
    );
  }
  if (role === "deputy" && actor.access.kind !== "owner") {
    throw new TeamError(403, "Only an owner can appoint deputies.");
  }
}

/** Who may change or remove an existing member. Shared by direct and approved changes. */
export function assertCanChange(
  actor: HumanActor,
  targetUid: string,
  target: Data | undefined,
  verb: "remove" | "change"
) {
  if (!hasScope(actor.access, "team:manage")) {
    throw new TeamError(403, "Only an owner or a deputy can change the team.");
  }
  if (targetUid === actor.uid) {
    throw new TeamError(
      400,
      verb === "remove"
        ? "You cannot remove yourself."
        : "You cannot change your own role."
    );
  }
  if (!target) {
    throw new TeamError(404, "That person no longer has admin access.");
  }
  if (isOwner(target)) {
    throw new TeamError(
      403,
      "Owners are set in Firestore and cannot be changed here."
    );
  }
  if (isDeputy(target) && actor.access.kind !== "owner") {
    throw new TeamError(403, "Only an owner can change a deputy.");
  }
}

function errorCode(error: unknown): string | undefined {
  if (error && typeof error === "object" && "code" in error) {
    const code = (error as { code: unknown }).code;
    if (typeof code === "string") return code;
  }
  return undefined;
}

/**
 * The request's actor snapshot can go stale while the mutation is in
 * flight. Every team mutation re-reads `adminData/{uid}` inside its own
 * transaction and re-derives access from that doc, so a demotion or removal
 * that lands first aborts the in-flight mutation instead of applying it.
 */
export async function currentActor(
  tx: Tx,
  actor: HumanActor
): Promise<HumanActor> {
  const snap = await tx.get(
    getDb().collection(ADMIN_COLLECTION).doc(actor.uid)
  );
  if (!snap.exists) {
    throw new TeamError(403, "Your admin access was removed.");
  }
  return { ...actor, access: accessFor(snap.data() as Data) };
}

/** Applied-change context when a human approves an agent proposal. */
export interface ApprovalContext {
  proposalId: string;
  proposedBy: string;
  reason?: string;
  /** Re-reads the proposal inside the change's transaction (reads come first). */
  check: (tx: Tx) => Promise<void>;
  /** Marks the proposal approved in the same transaction. */
  commit: (tx: Tx) => void;
}

export interface AddMemberInput {
  email: string;
  accessRole: RoleId;
  scopeOverrides?: ScopeOverrides;
}

export async function addMember(
  actor: HumanActor,
  input: AddMemberInput,
  approval?: ApprovalContext
) {
  const overrides = input.scopeOverrides ?? {};
  assertNoBroaderThanActor(actor, input.accessRole, overrides);
  const email = input.email.trim().toLowerCase();

  // Re-authorize from a current read before creating anything: an actor
  // demoted or removed since authenticate() must not get as far as
  // provisioning a Firebase Auth account. The transaction below re-checks
  // and stays the authority; this only narrows the window.
  {
    const snap = await getDb()
      .collection(ADMIN_COLLECTION)
      .doc(actor.uid)
      .get();
    if (!snap.exists) {
      throw new TeamError(403, "Your admin access was removed.");
    }
    const acting = { ...actor, access: accessFor(snap.data() as Data) };
    if (!hasScope(acting.access, "team:invite")) {
      throw new TeamError(
        403,
        "Only an owner, a deputy or an admin can invite."
      );
    }
    assertNoBroaderThanActor(acting, input.accessRole, overrides);
  }

  let firebaseUser: UserRecord;
  let provisioned = false;
  try {
    firebaseUser = await getAdminAuth().getUserByEmail(email);
  } catch (error) {
    if (errorCode(error) !== "auth/user-not-found") throw error;
    // The invitee has never signed in to Omi, so no Firebase Auth user
    // exists to key `adminData/{uid}` on. Reserve the uid now with an
    // unverified, credential-less account: the project keeps Firebase's
    // default one-account-per-email setting, so when they later sign in
    // with Google for this address the provider links into this very uid
    // and the admin grant below is already waiting for them.
    //
    // A rejected invite (the actor was demoted mid-flight, the person
    // already had access) can leave this account behind. That orphan is
    // deliberate and harmless: without an adminData doc it grants no admin
    // access, and the next invite of the same email reuses it. Deleting it
    // outside the transaction raced concurrent invites that had adopted
    // the account, so Auth provisioning is never rolled back
    // (docs/team-access.md).
    try {
      firebaseUser = await getAdminAuth().createUser({
        email,
        emailVerified: false,
      });
      provisioned = true;
    } catch (createError) {
      // Lost a race with a concurrent add (or with their first sign-in).
      if (errorCode(createError) !== "auth/email-already-exists") {
        throw createError;
      }
      firebaseUser = await getAdminAuth().getUserByEmail(email);
    }
  }

  const db = getDb();
  const memberRef = db.collection(ADMIN_COLLECTION).doc(firebaseUser.uid);
  const role = ROLES[input.accessRole];
  const memberDoc = {
    name: firebaseUser.displayName || email,
    role: role.label,
    accessRole: input.accessRole,
    scopeOverrides: {
      grant: overrides.grant ?? [],
      deny: overrides.deny ?? [],
    },
    email,
    createdAt: new Date().toISOString(),
    addedBy: actor.uid,
  };

  // Invites for one normalized email serialize on this lock doc (like the
  // proposal locks — agent add_member proposals for the same email take the
  // very same doc): a concurrent invite's or proposal's transaction
  // conflicts and re-runs against whatever this one committed — including
  // the roster doc that adopted the Auth account this request may have
  // provisioned. Rejected invites deliberately leave any provisioned
  // account in place (see the provisioning note above); nothing below
  // deletes Auth accounts.
  const inviteLock = db.collection(LOCK_COLLECTION).doc(inviteLockId(email));
  await db.runTransaction(async (tx) => {
    await tx.get(inviteLock);
    // Re-authorize from the actor's current doc, not the request snapshot.
    const acting = await currentActor(tx, actor);
    if (!hasScope(acting.access, "team:invite")) {
      throw new TeamError(
        403,
        "Only an owner, a deputy or an admin can invite."
      );
    }
    assertNoBroaderThanActor(acting, input.accessRole, overrides);
    if ((await tx.get(memberRef)).exists) {
      throw new TeamError(409, `${email} already has admin access.`);
    }
    // One pending change per person: a live add-person proposal for this
    // email conflicts with a direct invite, so decide that proposal
    // (approving it runs through here too, its own id excluded) instead of
    // landing a divergent second grant.
    const pending = await db
      .collection(PROPOSAL_COLLECTION)
      .where("status", "==", "pending")
      .get();
    const now = Date.now();
    const conflicting = pending.docs.find((doc) => {
      if (doc.id === approval?.proposalId) return false;
      const data = doc.data() as {
        kind?: string;
        expiresAt?: string;
        target?: { email?: string | null };
      };
      return (
        data.kind === "add_member" &&
        data.target?.email === email &&
        Date.parse(data.expiresAt ?? "") > now
      );
    });
    if (conflicting) {
      throw new TeamError(
        409,
        `${email} already has a pending proposal; approve or reject it instead.`
      );
    }
    await approval?.check(tx);
    approval?.commit(tx);
    tx.set(inviteLock, { updatedAt: new Date().toISOString() });
    tx.set(memberRef, memberDoc);
    audit(tx, {
      action: "member.added",
      actor: humanAuditActor(actor),
      target: { uid: firebaseUser.uid, email },
      before: null,
      after: snapshot(memberDoc),
      proposalId: approval?.proposalId,
      proposedBy: approval?.proposedBy,
      reason: approval?.reason,
    });
  });

  // The grant has landed. Telling them about it is best effort: a mail
  // failure is reported in the response, never rolled back into an error.
  const invite = await sendAdminInviteEmail({ email, invitedBy: actor.email });
  if (!invite.sent) {
    console.error(
      `Admin invite email not sent to ${email} (reason ${
        invite.reason ?? "unknown"
      })`
    );
  }

  return {
    teamMember: {
      id: firebaseUser.uid,
      name: memberDoc.name,
      role: memberDoc.role,
      accessRole: memberDoc.accessRole,
      email,
    },
    provisioned,
    emailSent: invite.sent,
  };
}

export async function removeMember(
  actor: HumanActor,
  uid: string,
  approval?: ApprovalContext
) {
  const db = getDb();
  const memberRef = db.collection(ADMIN_COLLECTION).doc(uid);
  return db.runTransaction(async (tx) => {
    const doc = await tx.get(memberRef);
    const data = doc.exists ? (doc.data() as Data) : undefined;
    // Re-authorize from the actor's current doc, not the request snapshot.
    assertCanChange(await currentActor(tx, actor), uid, data, "remove");
    await approval?.check(tx);
    approval?.commit(tx);
    tx.delete(memberRef);
    const email = typeof data!.email === "string" ? data!.email : null;
    audit(tx, {
      action: "member.removed",
      actor: humanAuditActor(actor),
      target: { uid, email },
      before: snapshot(data),
      after: null,
      proposalId: approval?.proposalId,
      proposedBy: approval?.proposedBy,
      reason: approval?.reason,
    });
    console.log(
      `Admin ${actor.uid} removed admin ${uid} (${email ?? "no email"})`
    );
    return { id: uid, email, role: accessFor(data).roleLabel };
  });
}

export async function setMemberRole(
  actor: HumanActor,
  uid: string,
  accessRole: RoleId,
  scopeOverrides: ScopeOverrides = {},
  approval?: ApprovalContext
) {
  const db = getDb();
  const memberRef = db.collection(ADMIN_COLLECTION).doc(uid);
  return db.runTransaction(async (tx) => {
    const doc = await tx.get(memberRef);
    const data = doc.exists ? (doc.data() as Data) : undefined;
    // Re-authorize from the actor's current doc, not the request snapshot,
    // so a mid-flight demotion cannot appoint or keep broad access flowing.
    const acting = await currentActor(tx, actor);
    assertCanChange(acting, uid, data, "change");
    assertNoBroaderThanActor(acting, accessRole, scopeOverrides);
    const update = {
      accessRole,
      role: ROLES[accessRole].label,
      scopeOverrides: {
        grant: scopeOverrides.grant ?? [],
        deny: scopeOverrides.deny ?? [],
      },
      accessUpdatedAt: new Date().toISOString(),
      accessUpdatedBy: actor.uid,
    };
    await approval?.check(tx);
    approval?.commit(tx);
    tx.update(memberRef, update);
    const after = snapshot({ ...data, ...update });
    audit(tx, {
      action: "member.role_changed",
      actor: humanAuditActor(actor),
      target: {
        uid,
        email: typeof data!.email === "string" ? data!.email : null,
      },
      before: snapshot(data),
      after,
      proposalId: approval?.proposalId,
      proposedBy: approval?.proposedBy,
      reason: approval?.reason,
    });
    return { id: uid, ...after! };
  });
}

export interface RosterMember {
  id: string;
  uidPrefix: string;
  name: string;
  email: string;
  /** Legacy display label, kept in sync with the assigned role. */
  role: string;
  roleLabel: string;
  accessRole: RoleId | null;
  accessKind: MemberAccess["kind"];
  scopes: Scope[];
  scopeOverrides: ScopeOverrides;
  owner: boolean;
  createdAt: string | null;
  lastSignInAt: string | null;
  /** Another adminData doc carries the same email (case-insensitive). */
  duplicateEmail: boolean;
}

function isoOrNull(value: unknown): string | null {
  if (typeof value === "string" && value) return value;
  if (value && typeof value === "object" && "toDate" in value) {
    return (value as { toDate: () => Date }).toDate().toISOString();
  }
  return null;
}

/** Sign-in times from Firebase Auth, best effort (the roster still loads without them). */
async function lastSignIns(uids: string[]): Promise<Map<string, string>> {
  const result = new Map<string, string>();
  try {
    for (let i = 0; i < uids.length; i += 100) {
      const { users } = await getAdminAuth().getUsers(
        uids.slice(i, i + 100).map((uid) => ({ uid }))
      );
      for (const user of users) {
        const time = user.metadata?.lastSignInTime;
        if (time) result.set(user.uid, new Date(time).toISOString());
      }
    }
  } catch {
    console.error("Could not read admin sign-in times from Firebase Auth");
  }
  return result;
}

export async function listRoster(): Promise<RosterMember[]> {
  const snapshot = await getDb().collection(ADMIN_COLLECTION).get();
  const signIns = await lastSignIns(snapshot.docs.map((doc) => doc.id));
  const emailCounts = new Map<string, number>();
  for (const doc of snapshot.docs) {
    const email = String(doc.data().email ?? "").toLowerCase();
    if (email) emailCounts.set(email, (emailCounts.get(email) ?? 0) + 1);
  }
  return snapshot.docs.map((doc) => {
    const data = doc.data();
    const access = accessFor(data);
    const email = typeof data.email === "string" ? data.email : "No email";
    return {
      id: doc.id,
      uidPrefix: doc.id.slice(0, 8),
      name: data.name || "Unknown",
      email,
      role: data.role || "Admin",
      roleLabel: access.roleLabel,
      accessRole: access.role,
      accessKind: access.kind,
      scopes: access.scopes,
      scopeOverrides: access.overrides,
      owner: access.kind === "owner",
      createdAt: isoOrNull(data.createdAt),
      lastSignInAt: signIns.get(doc.id) ?? null,
      duplicateEmail: (emailCounts.get(email.toLowerCase()) ?? 0) > 1,
    };
  });
}

export async function listAudit(
  limit = 100
): Promise<(AuditEntry & { id: string })[]> {
  const snapshot = await getDb()
    .collection(AUDIT_COLLECTION)
    .orderBy("at", "desc")
    .limit(Math.min(Math.max(limit, 1), 500))
    .get();
  return snapshot.docs.map((doc) => ({
    id: doc.id,
    ...(doc.data() as AuditEntry),
  }));
}
