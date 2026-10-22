"use client";

import { useState } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { AddTeamMemberDialog } from "@/components/dashboard/add-team-member-dialog";
import {
  useTeamAudit,
  useTeamMembers,
  useTeamProposals,
  type AuditEntry,
  type Proposal,
  type TeamMember,
  type TeamViewer,
} from "@/hooks/useTeamMembers";
import { useAuthFetch } from "@/hooks/useAuthToken";
import { useToast } from "@/hooks/use-toast";
import { ROLES, ROLE_IDS, type RoleId, type Scope } from "@/lib/admin-access";
import { Check, Loader2, Plus, Trash2, X } from "lucide-react";

// Simple spinner component
const Spinner = () => (
  <div className="mx-auto my-8 h-8 w-8 animate-spin rounded-full border-b-2 border-primary"></div>
);

const LEGACY = "__legacy__";

function when(value: string | null | undefined) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString();
}

function scopeDiff(before: Scope[] = [], after: Scope[] = []) {
  return {
    added: after.filter((s) => !before.includes(s)),
    removed: before.filter((s) => !after.includes(s)),
  };
}

/** Owner/deputy-only actions on a member; mirrors the server's checks for display. */
function manageable(viewer: TeamViewer | null, member: TeamMember) {
  if (!viewer?.canManage || member.owner || member.id === viewer.uid)
    return false;
  return member.accessRole !== "deputy" || viewer.isOwner;
}

const PROPOSAL_LABEL: Record<Proposal["kind"], string> = {
  add_member: "Add person",
  remove_member: "Remove person",
  set_role: "Change role",
};

const AUDIT_LABEL: Record<AuditEntry["action"], string> = {
  "member.added": "Added",
  "member.removed": "Removed",
  "member.role_changed": "Role changed",
  "member.invite_failed": "Invite email failed",
  "proposal.created": "Proposal filed",
  "proposal.approved": "Proposal approved",
  "proposal.rejected": "Proposal rejected",
  "proposal.expired": "Proposal expired",
};

function AccessChange({
  before,
  after,
}: {
  before: Proposal["before"];
  after: Proposal["after"];
}) {
  const { added, removed } = scopeDiff(before?.scopes, after?.scopes);
  return (
    <div className="space-y-1 text-sm">
      <div>
        <span className="text-muted-foreground">
          {before?.roleLabel ?? "No access"}
        </span>
        {" → "}
        <span className="font-medium">{after?.roleLabel ?? "No access"}</span>
      </div>
      {added.length ? (
        <div className="text-green-700 dark:text-green-400">
          + {added.join(", ")}
        </div>
      ) : null}
      {removed.length ? (
        <div className="text-red-700 dark:text-red-400">
          − {removed.join(", ")}
        </div>
      ) : null}
    </div>
  );
}

export default function TeamPage() {
  const { teamMembers, viewer, isLoading, error, mutate } = useTeamMembers();
  const {
    proposals,
    error: proposalsError,
    mutate: mutateProposals,
  } = useTeamProposals();
  const { entries, error: auditError, mutate: mutateAudit } = useTeamAudit();
  const { fetchWithAuth } = useAuthFetch();
  const { toast } = useToast();
  const [pendingRemoval, setPendingRemoval] = useState<TeamMember | null>(null);
  const [pendingRole, setPendingRole] = useState<{
    member: TeamMember;
    role: RoleId;
  } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const refresh = async () => {
    await Promise.allSettled([mutate(), mutateProposals(), mutateAudit()]);
  };

  const send = async (
    key: string,
    url: string,
    init: RequestInit,
    success:
      | { title: string; description: string }
      | ((data: any) => { title: string; description: string }),
    failure: string
  ) => {
    setBusy(key);
    try {
      const response = await fetchWithAuth(url, init);
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.error || failure);
      }
      const data = await response.json().catch(() => null);
      await refresh();
      toast(typeof success === "function" ? success(data) : success);
      return data ?? true;
    } catch (err) {
      toast({
        title: failure,
        description: err instanceof Error ? err.message : "Unknown error",
        variant: "destructive",
      });
      return false;
    } finally {
      setBusy(null);
    }
  };

  const confirmRemoval = async () => {
    if (!pendingRemoval) return;
    const member = pendingRemoval;
    const ok = await send(
      "remove",
      "/api/omi/team-members",
      { method: "DELETE", body: JSON.stringify({ uid: member.id }) },
      {
        title: "Access removed",
        description: `${member.email} no longer has admin dashboard access.`,
      },
      "Could not remove person"
    );
    if (ok) setPendingRemoval(null);
  };

  const confirmRole = async () => {
    if (!pendingRole) return;
    const { member, role } = pendingRole;
    const ok = await send(
      "role",
      "/api/omi/team-members",
      {
        method: "PATCH",
        body: JSON.stringify({ uid: member.id, accessRole: role }),
      },
      {
        title: "Role changed",
        description: `${member.email} is now ${ROLES[role].label}.`,
      },
      "Could not change role"
    );
    if (ok) setPendingRole(null);
  };

  const decide = (proposal: Proposal, decision: "approve" | "reject") =>
    send(
      `${proposal.id}:${decision}`,
      `/api/omi/team-members/proposals/${encodeURIComponent(proposal.id)}`,
      { method: "POST", body: JSON.stringify({ decision }) },
      (data) => {
        const label = `${PROPOSAL_LABEL[proposal.kind]} for ${
          proposal.target.email ?? proposal.target.uid
        }`;
        if (
          decision === "approve" &&
          proposal.kind === "add_member" &&
          data?.proposal?.emailSent === false
        ) {
          return {
            title: "Approved, but the invite email failed",
            description: `${label} is applied, but the sign-in email could not be sent. Tell them to open https://admin.omi.me and sign in with ${proposal.target.email}.`,
          };
        }
        return {
          title:
            decision === "approve" ? "Proposal approved" : "Proposal rejected",
          description:
            decision === "approve"
              ? `${label} is applied.`
              : "Nothing changed.",
        };
      },
      decision === "approve" ? "Could not approve" : "Could not reject"
    );

  const header = (
    <div className="flex items-center justify-between gap-4">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Team Members</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          People with access to the Omi admin dashboard, and what their role
          lets them do.
        </p>
      </div>
      {viewer === null || viewer.canInvite ? (
        <AddTeamMemberDialog
          isOwner={viewer?.isOwner ?? false}
          onMemberAdded={refresh}
        >
          <Button>
            <Plus className="mr-2 h-4 w-4" />
            Add new person
          </Button>
        </AddTeamMemberDialog>
      ) : null}
    </div>
  );

  if (isLoading) {
    return (
      <div className="space-y-6 p-6">
        {header}
        <div className="flex min-h-[300px] items-center justify-center">
          <Spinner />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6 p-6">
        {header}
        <div className="py-10 text-center text-red-500">
          Error loading team members: {error.message}
        </div>
      </div>
    );
  }

  const pending = proposals.filter((p) => p.status === "pending");
  const legacyCount = teamMembers.filter(
    (m) => m.accessKind === "legacy"
  ).length;

  return (
    <div className="space-y-6 p-6">
      {header}

      {legacyCount > 0 && viewer?.canManage ? (
        <div className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-200">
          {legacyCount} {legacyCount === 1 ? "person has" : "people have"} no
          assigned role and keep full access (everything except team management)
          until you choose one.
        </div>
      ) : null}

      {proposalsError ? (
        <div className="rounded-md border border-red-300 p-3 text-sm text-red-600">
          Could not load agent proposals, so pending approvals may be missing.
          Reload to try again.
        </div>
      ) : null}

      {pending.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>Proposed changes</CardTitle>
            <CardDescription>
              Filed by agents. Nothing changes until an owner or a deputy
              approves. Unapproved proposals expire.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {pending.map((proposal) => (
              <div
                key={proposal.id}
                className="flex flex-col gap-3 rounded-md border p-3 md:flex-row md:items-start md:justify-between"
                data-testid={`proposal-${proposal.id}`}
              >
                <div className="space-y-1">
                  <div className="font-medium">
                    {PROPOSAL_LABEL[proposal.kind]}:{" "}
                    {proposal.target.email ?? proposal.target.uid}
                    {proposal.target.uid ? (
                      <span className="ml-2 font-mono text-xs text-muted-foreground">
                        {proposal.target.uid.slice(0, 8)}
                      </span>
                    ) : null}
                  </div>
                  <AccessChange
                    before={proposal.before}
                    after={proposal.after}
                  />
                  <div className="text-xs text-muted-foreground">
                    Proposed by {proposal.proposedBy.email} ·{" "}
                    {when(proposal.createdAt)} · expires{" "}
                    {when(proposal.expiresAt)}
                  </div>
                  <div className="text-sm">“{proposal.reason}”</div>
                </div>
                {viewer?.canManage ? (
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      onClick={() => void decide(proposal, "approve")}
                      disabled={busy !== null}
                      aria-label={`Approve ${
                        PROPOSAL_LABEL[proposal.kind]
                      } for ${proposal.target.email ?? proposal.target.uid}`}
                    >
                      {busy === `${proposal.id}:approve` ? (
                        <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                      ) : (
                        <Check className="mr-1 h-4 w-4" />
                      )}
                      Approve
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => void decide(proposal, "reject")}
                      disabled={busy !== null}
                    >
                      <X className="mr-1 h-4 w-4" />
                      Reject
                    </Button>
                  </div>
                ) : null}
              </div>
            ))}
          </CardContent>
        </Card>
      ) : null}

      {teamMembers.length === 0 ? (
        <div className="py-10 text-center text-muted-foreground">
          No team members found.
        </div>
      ) : (
        <Card>
          <CardContent className="overflow-x-auto p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Person</TableHead>
                  <TableHead>UID</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead>Added</TableHead>
                  <TableHead>Last sign-in</TableHead>
                  <TableHead className="w-12" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {teamMembers.map((member) => (
                  <TableRow key={member.id}>
                    <TableCell>
                      <div className="font-medium">{member.name}</div>
                      <div className="flex items-center gap-2 text-sm text-muted-foreground">
                        {member.email}
                        {member.duplicateEmail ? (
                          <Badge
                            variant="outline"
                            title="Another admin record has this email"
                          >
                            Duplicate email
                          </Badge>
                        ) : null}
                      </div>
                    </TableCell>
                    <TableCell>
                      <span className="font-mono text-xs" title={member.id}>
                        {member.uidPrefix}
                      </span>
                    </TableCell>
                    <TableCell>
                      {manageable(viewer, member) ? (
                        <select
                          aria-label={`Role for ${member.email}`}
                          className="h-9 rounded-md border bg-background px-2 text-sm"
                          value={member.accessRole ?? LEGACY}
                          disabled={busy !== null}
                          onChange={(event) => {
                            const role = event.target.value;
                            if (role !== LEGACY && role !== member.accessRole) {
                              setPendingRole({ member, role: role as RoleId });
                            }
                          }}
                        >
                          {member.accessRole === null ? (
                            <option value={LEGACY} disabled>
                              {member.roleLabel}
                            </option>
                          ) : null}
                          {ROLE_IDS.filter(
                            (id) => id !== "deputy" || viewer?.isOwner
                          ).map((id) => (
                            <option key={id} value={id}>
                              {ROLES[id].label}
                            </option>
                          ))}
                        </select>
                      ) : (
                        <span className="flex items-center gap-2 text-sm">
                          {member.roleLabel}
                          {member.owner ? (
                            <Badge variant="secondary">Owner</Badge>
                          ) : null}
                        </span>
                      )}
                    </TableCell>
                    <TableCell className="text-sm">
                      {when(member.createdAt)}
                    </TableCell>
                    <TableCell className="text-sm">
                      {when(member.lastSignInAt)}
                    </TableCell>
                    <TableCell>
                      {manageable(viewer, member) ? (
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label={`Remove ${member.name}`}
                          title="Remove admin access"
                          onClick={() => setPendingRemoval(member)}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      ) : null}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Audit log</CardTitle>
          <CardDescription>
            Every roster, role and proposal event, newest first.
          </CardDescription>
        </CardHeader>
        <CardContent className="overflow-x-auto p-0">
          {auditError ? (
            <p className="p-6 text-sm text-red-600">
              Could not load the audit log.
            </p>
          ) : entries.length === 0 ? (
            <p className="p-6 text-sm text-muted-foreground">No events yet.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>When</TableHead>
                  <TableHead>Who</TableHead>
                  <TableHead>What</TableHead>
                  <TableHead>Target</TableHead>
                  <TableHead>Before → after</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {entries.map((entry) => (
                  <TableRow key={entry.id}>
                    <TableCell className="whitespace-nowrap text-sm">
                      {when(entry.at)}
                    </TableCell>
                    <TableCell className="text-sm">
                      {entry.actor.email ?? entry.actor.id}
                      {entry.actor.type !== "human" ? (
                        <Badge variant="outline" className="ml-2">
                          {entry.actor.type}
                        </Badge>
                      ) : null}
                    </TableCell>
                    <TableCell className="text-sm">
                      {AUDIT_LABEL[entry.action] ?? entry.action}
                      {entry.proposedBy && entry.actor.type === "human" ? (
                        <div className="text-xs text-muted-foreground">
                          proposed by {entry.proposedBy}
                        </div>
                      ) : null}
                    </TableCell>
                    <TableCell className="text-sm">
                      {entry.target.email ?? "—"}
                      {entry.target.uid ? (
                        <span className="ml-2 font-mono text-xs text-muted-foreground">
                          {entry.target.uid.slice(0, 8)}
                        </span>
                      ) : null}
                    </TableCell>
                    <TableCell>
                      <AccessChange before={entry.before} after={entry.after} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <AlertDialog
        open={pendingRole !== null}
        onOpenChange={(open) => {
          if (!open && busy === null) setPendingRole(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              Make {pendingRole?.member.email}{" "}
              {pendingRole ? ROLES[pendingRole.role].label : ""}?
            </AlertDialogTitle>
            <AlertDialogDescription asChild>
              <div>
                {pendingRole ? (
                  <AccessChange
                    before={{
                      accessRole: pendingRole.member.accessRole,
                      roleLabel: pendingRole.member.roleLabel,
                      scopes: pendingRole.member.scopes,
                      scopeOverrides: pendingRole.member.scopeOverrides,
                    }}
                    after={{
                      accessRole: pendingRole.role,
                      roleLabel: ROLES[pendingRole.role].label,
                      scopes: [...ROLES[pendingRole.role].scopes],
                      scopeOverrides: {},
                    }}
                  />
                ) : null}
                <p className="mt-2">Takes effect on their next request.</p>
              </div>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={busy !== null}>
              Cancel
            </AlertDialogCancel>
            <AlertDialogAction
              disabled={busy !== null}
              onClick={(event) => {
                event.preventDefault();
                void confirmRole();
              }}
            >
              {busy === "role" ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : null}
              Change role
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog
        open={pendingRemoval !== null}
        onOpenChange={(open) => {
          if (!open && busy === null) setPendingRemoval(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              Remove {pendingRemoval?.name ?? "this person"}?
            </AlertDialogTitle>
            <AlertDialogDescription>
              {pendingRemoval?.email} loses access to the admin dashboard
              immediately. You can add them back later.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={busy !== null}>
              Cancel
            </AlertDialogCancel>
            <AlertDialogAction
              disabled={busy !== null}
              onClick={(event) => {
                event.preventDefault();
                void confirmRemoval();
              }}
            >
              {busy === "remove" ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : null}
              Remove access
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
