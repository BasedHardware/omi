/**
 * Admin dashboard permissions. Pure data and functions: no Firebase, no
 * Next.js, so the server guard, the Team page and tests share one model.
 *
 * A member's access comes from `adminData/{uid}`:
 * - `owner: true` → every scope (set in Firestore only, never through the UI).
 * - `accessRole` → that role's scopes, adjusted by `scopeOverrides`.
 * - no `accessRole` → legacy: the full access every admin had before roles
 *   existed, until the owner or a deputy assigns one. `role` ("superadmin",
 *   "Admin") is only a display label and never grants anything.
 * - an `accessRole` this code does not know → no scopes (fail closed).
 */

export const SCOPES = [
  "analytics:read",
  "analytics:share",
  "finance:read",
  "finance:write",
  "users:read",
  "users:write",
  "apps:read",
  "apps:write",
  "content:read",
  "content:write",
  "partners:read",
  "partners:write",
  "dev:agent",
  "team:read",
  "team:invite",
  "team:manage",
] as const;

export type Scope = (typeof SCOPES)[number];

export const SCOPE_LABELS: Record<Scope, string> = {
  "analytics:read": "Dashboards and product metrics",
  "analytics:share": "Create and revoke TV wall links",
  "finance:read": "Revenue, subscriptions, payouts, affiliates",
  "finance:write": "Affiliate payout actions",
  "users:read": "User support data (fair use, feedback, notifications)",
  "users:write": "Change user state (fair-use resets, regenerate)",
  "apps:read": "App store listings and review queue",
  "apps:write": "Approve, edit and feature apps",
  "content:read": "Announcements, prompts, CSAT, releases, Chat Lab",
  "content:write": "Publish announcements, prompts, CSAT, Chat Lab runs",
  "partners:read": "Distributors and organizations",
  "partners:write": "Edit distributors and organizations",
  "dev:agent": "Run the dashboard coding agent",
  "team:read": "See the admin roster, proposals and audit log",
  "team:invite": "Add people with a role no broader than your own",
  "team:manage": "Change roles, remove people, approve agent proposals",
};

export const ROLE_IDS = [
  "deputy",
  "admin",
  "finance",
  "support",
  "viewer",
] as const;

export type RoleId = (typeof ROLE_IDS)[number];

const ALL: readonly Scope[] = SCOPES;
const without = (...excluded: Scope[]) =>
  ALL.filter((scope) => !excluded.includes(scope));

export const ROLES: Record<
  RoleId,
  { label: string; scopes: readonly Scope[] }
> = {
  deputy: { label: "Deputy owner", scopes: ALL },
  admin: { label: "Admin", scopes: without("team:manage") },
  finance: {
    label: "Finance",
    scopes: [
      "analytics:read",
      "finance:read",
      "finance:write",
      "partners:read",
    ],
  },
  support: {
    label: "Support",
    scopes: [
      "analytics:read",
      "users:read",
      "users:write",
      "apps:read",
      "content:read",
    ],
  },
  viewer: {
    label: "Viewer",
    scopes: ["analytics:read", "apps:read", "content:read"],
  },
};

/** What every admin could do before roles: everything except removal. */
export const LEGACY_SCOPES: readonly Scope[] = without("team:manage");

/**
 * The keyless stats reader (docs/stats-reader.md) keeps exactly what it had:
 * GET under /api/omi/stats/ (that prefix check stays in its verifier).
 */
export const STATS_READER_SCOPES: readonly Scope[] = [
  "analytics:read",
  "finance:read",
];

/** Overrides may never hand out team management: that is the deputy role. */
export const NON_OVERRIDABLE: readonly Scope[] = ["team:manage"];

export type ScopeOverrides = { grant?: Scope[]; deny?: Scope[] };

export type AccessKind = "owner" | "role" | "legacy" | "invalid";

export interface MemberAccess {
  kind: AccessKind;
  role: RoleId | null;
  roleLabel: string;
  scopes: Scope[];
  overrides: ScopeOverrides;
}

export function isScope(value: unknown): value is Scope {
  return (
    typeof value === "string" && (SCOPES as readonly string[]).includes(value)
  );
}

export function isRoleId(value: unknown): value is RoleId {
  return (
    typeof value === "string" && (ROLE_IDS as readonly string[]).includes(value)
  );
}

function readOverrides(raw: unknown): ScopeOverrides {
  if (!raw || typeof raw !== "object") return {};
  const { grant, deny } = raw as { grant?: unknown; deny?: unknown };
  const list = (value: unknown) =>
    Array.isArray(value) ? value.filter(isScope) : [];
  return {
    grant: list(grant).filter((scope) => !NON_OVERRIDABLE.includes(scope)),
    deny: list(deny),
  };
}

function sorted(scopes: Iterable<Scope>): Scope[] {
  const set = new Set(scopes);
  return SCOPES.filter((scope) => set.has(scope));
}

/** Effective access for one `adminData/{uid}` document. */
export function accessFor(
  doc: Record<string, unknown> | undefined | null
): MemberAccess {
  const data = doc ?? {};
  if (data.owner === true) {
    return {
      kind: "owner",
      role: null,
      roleLabel: "Owner",
      scopes: [...ALL],
      overrides: {},
    };
  }
  const overrides = readOverrides(data.scopeOverrides);
  const raw = data.accessRole;
  if (raw === undefined || raw === null || raw === "") {
    const label =
      typeof data.role === "string" && data.role ? data.role : "Admin";
    return {
      kind: "legacy",
      role: null,
      roleLabel: `${label} (legacy, full access)`,
      scopes: [...LEGACY_SCOPES],
      overrides: {},
    };
  }
  if (!isRoleId(raw)) {
    return {
      kind: "invalid",
      role: null,
      roleLabel: `Unknown role "${String(raw)}"`,
      scopes: [],
      overrides: {},
    };
  }
  const scopes = new Set<Scope>(ROLES[raw].scopes);
  for (const scope of overrides.grant ?? []) scopes.add(scope);
  for (const scope of overrides.deny ?? []) scopes.delete(scope);
  return {
    kind: "role",
    role: raw,
    roleLabel: ROLES[raw].label,
    scopes: sorted(scopes),
    overrides,
  };
}

/** Scopes a role assignment would produce, for "no broader than you" checks. */
export function scopesForAssignment(
  role: RoleId,
  overrides: ScopeOverrides = {}
): Scope[] {
  return accessFor({ accessRole: role, scopeOverrides: overrides }).scopes;
}

export function hasScope(access: { scopes: readonly Scope[] }, scope: Scope) {
  return access.scopes.includes(scope);
}

/** Dashboard pages and the scope that unlocks each one in the sidebar. */
export const PAGE_SCOPES: { prefix: string; scope: Scope }[] = [
  { prefix: "/dashboard/tv-links", scope: "analytics:share" },
  { prefix: "/dashboard/apps", scope: "apps:read" },
  { prefix: "/dashboard/summary-apps", scope: "apps:read" },
  { prefix: "/dashboard/reviews", scope: "apps:read" },
  { prefix: "/dashboard/subscriptions", scope: "finance:read" },
  { prefix: "/dashboard/payouts", scope: "finance:read" },
  { prefix: "/dashboard/affiliates", scope: "finance:read" },
  { prefix: "/dashboard/organizations", scope: "partners:read" },
  { prefix: "/dashboard/distributors", scope: "partners:read" },
  { prefix: "/dashboard/team", scope: "team:read" },
  { prefix: "/dashboard/announcements", scope: "content:read" },
  { prefix: "/dashboard/prompts", scope: "content:read" },
  { prefix: "/dashboard/csat", scope: "content:read" },
  { prefix: "/dashboard/releases", scope: "content:read" },
  { prefix: "/dashboard/chat-lab", scope: "content:read" },
  { prefix: "/dashboard/notifications", scope: "users:read" },
  { prefix: "/dashboard/fair-use", scope: "users:read" },
  { prefix: "/dashboard/feedback", scope: "users:read" },
  { prefix: "/dashboard", scope: "analytics:read" },
];

export function pageScope(pathname: string): Scope | null {
  const match = PAGE_SCOPES.find(
    ({ prefix }) => pathname === prefix || pathname.startsWith(`${prefix}/`)
  );
  return match?.scope ?? null;
}
