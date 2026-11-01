# Team access: roles, scopes and agent proposals

Detail for the **Permissions** and **Team agents** rules in `web/admin/AGENTS.md`.

## Model

Each admin is an `adminData/{uid}` document. Access comes from three fields:

| Field            | Effect                                                                                                             |
| ---------------- | ------------------------------------------------------------------------------------------------------------------ |
| `owner: true`    | Every scope. Set in Firestore only; no API or UI writes it. Any number of admins may be owners (prod carries two). |
| `accessRole`     | One of the roles below. Written by the Team page or an approved proposal.                                          |
| `scopeOverrides` | `{ grant: Scope[], deny: Scope[] }` applied on top of the role. `team:manage` cannot be granted this way.          |

`role` ("superadmin", "Admin", …) is a display label only. It is kept in sync
with `accessRole` when a role is assigned and never grants anything.

A doc with **no `accessRole`** is _legacy_: it keeps the access every admin had
before roles (every scope except `team:manage`) until an owner or a deputy
assigns a role. An `accessRole` this code does not recognise grants nothing
(fail closed).

## Roles

| Role (`accessRole`)               | Scopes                                                                     |
| --------------------------------- | -------------------------------------------------------------------------- |
| Owner (`owner: true`; any number) | all                                                                        |
| `deputy` — Deputy owner           | all, including `team:manage`                                               |
| `admin` — Admin                   | all except `team:manage`                                                   |
| `finance` — Finance               | `analytics:read`, `finance:read`, `finance:write`, `partners:read`         |
| `support` — Support               | `analytics:read`, `users:read`, `users:write`, `apps:read`, `content:read` |
| `viewer` — Viewer (read-only)     | `analytics:read`, `apps:read`, `content:read`                              |
| legacy (no `accessRole`)          | all except `team:manage`                                                   |
| stats reader (machine)            | `analytics:read`, `finance:read`, GET under `/api/omi/stats/` only         |

Scope meanings are in `SCOPE_LABELS` (`lib/admin-access.ts`). The route → scope
inventory is `lib/route-scopes.ts`.

## Team management rules

Enforced server-side in `lib/team/roster.ts`, for direct edits and approvals alike:

- `team:invite` adds a person with a role **no broader than the inviter's own**.
  New people default to `viewer` when no role is sent.
- `team:manage` (owner, deputies) changes roles and removes people.
- Nobody changes or removes themselves. Nobody changes or removes an
  owner — not even another owner.
- Only an owner appoints, changes or removes a deputy.
- Every mutation re-reads the actor's `adminData` doc inside its own
  transaction and re-authorizes from it, so a demotion or removal landing
  mid-flight aborts the in-flight change. Invites additionally re-check
  before provisioning a Firebase Auth account, so a demoted actor
  provisions nothing.
- Two invites for one email serialize on a per-email lock doc in
  `adminProposalLocks`: the loser's transaction re-runs against the
  winner's committed roster doc and refuses with 409. An agent's
  `add_member` proposal for the same email takes the very same lock doc,
  and the membership re-check runs inside the filing transaction, so an
  overlapping invite and proposal cannot both land; while one is pending,
  a direct invite for that email refuses with 409 until it is decided.
- A rejected invite may leave the unverified, credential-less Firebase
  Auth account it provisioned. That orphan is harmless — no `adminData`
  doc means no admin access — and the next invite of the same email
  reuses it, so Auth provisioning is never rolled back.
- Every add, removal, role change and proposal event writes an `adminAuditLog`
  entry (`at`, `action`, `actor`, `target`, `before`, `after`, and the
  proposal and proposer when one was approved) in the same transaction.

## Guard

Every handler calls `requireScope(request, scope)` from `lib/auth.ts` (or
`requireTeamAgent` for agent routes). `lib/__tests__/route-scopes.test.ts`:

- discovers every exported handler under `app/api` and fails if one has no
  entry in `ROUTE_POLICIES`, or an entry has no handler;
- for each scoped handler, calls it as a member holding every scope except the
  declared one and expects 403 naming that scope, plus 401 without a token and
  403 for a signed-in non-admin;
- checks agent routes refuse human tokens, and the stats reader keeps its scopes.

The sidebar and the dashboard layout hide pages whose scope the viewer lacks,
and mark a readable page read-only when its edit scope is missing
(`PAGE_SCOPES`, `GET /api/omi/access`, refreshed every minute and on focus so
role changes show without a reload). The server check is the authority.

## Agent API

Agents (Claude Code and similar) run as an allowlisted Google service account.
They read the roster and audit log and **file** proposals. They hold no admin
scope, cannot call any other admin route, and there is no agent route that
approves.

| Method and path                       | Purpose                                                 |
| ------------------------------------- | ------------------------------------------------------- |
| `GET /api/agent/team`                 | Roster: uid, email, role, scopes, created, last sign-in |
| `GET /api/agent/team/audit?limit=100` | Audit log, newest first                                 |
| `GET /api/agent/team/proposals`       | Proposals and their status                              |
| `POST /api/agent/team/proposals`      | File a proposal                                         |

Proposal bodies (`reason` is required, 1–500 characters):

```json
{ "kind": "add_member", "email": "person@example.com", "accessRole": "support", "reason": "joins support" }
{ "kind": "remove_member", "uid": "<uid>", "reason": "left the team" }
{ "kind": "set_role", "uid": "<uid>", "accessRole": "viewer", "scopeOverrides": { "grant": ["finance:read"] }, "reason": "read-only from now" }
```

Refused: targets that are the agent itself, any `*.gserviceaccount.com` email
or other allowlisted agent, an owner, unknown uids or roles, a second pending
proposal for the same target (409), and more than 20 pending per agent (429).
Overlapping requests are serialized by per-agent and per-target lock docs
(`adminProposalLocks`) read and written in the filing transaction. Proposals
expire 72 hours after filing; listing them is a pure read that derives the
`expired` status, while the persisted transition and its audit entry (a
`system` actor `proposal-expiry`, the proposer in `proposedBy`) land on the
next write — deciding an expired proposal refuses with 410 and records the
expiry, and the next filing persists the expiry of any stale proposal it
saw, so the stored pending set stays bounded. An owner or a deputy approves or
rejects on the Team page (`POST /api/omi/team-members/proposals/{id}`, Firebase
session with `team:manage`); approval re-runs the team management rules above,
so a deputy cannot approve a deputy appointment, and every decision re-reads
the approver's `adminData` inside its transaction, so a demotion or removal
that lands mid-flight aborts the change.

### Configuration

Server-only Cloud Run env vars, like the stats reader's (`docs/stats-reader.md`):

| Variable                    | Value                                                |
| --------------------------- | ---------------------------------------------------- |
| `ADMIN_TEAM_AGENT_AUDIENCE` | `https://admin.omi.me/api/agent/team`                |
| `ADMIN_TEAM_AGENT_SAS`      | comma or whitespace separated service-account emails |

Both empty (the default) disables the agent API: every call returns 401. Use a
dedicated service account with no project roles and no keys; grant each agent's
runtime identity `roles/iam.serviceAccountOpenIdTokenCreator` on it. The
audience differs from the stats reader's, so a stats token cannot be replayed here.

### Example

```bash
TOKEN=$(gcloud auth print-identity-token \
  --impersonate-service-account=omi-team-agent@based-hardware.iam.gserviceaccount.com \
  --audiences=https://admin.omi.me/api/agent/team --include-email)
curl -sS -X POST https://admin.omi.me/api/agent/team/proposals \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"kind":"set_role","uid":"<uid>","accessRole":"support","reason":"moved to support"}'
```

Keep the token in memory; never log it. Each decision logs one JSON line,
`event=admin_team_agent_auth` with the decision and route (and the agent email when allowed), never the token.
