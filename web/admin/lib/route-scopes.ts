import type { Scope } from "@/lib/admin-access";

/**
 * Route inventory: every exported API handler and what it requires.
 * `lib/__tests__/route-scopes.test.ts` fails when a handler is missing here,
 * when an entry has no handler, and when a scoped handler admits a member
 * without its scope. Add the entry with the route.
 *
 * - a Scope: `requireScope(request, scope)` with that scope.
 * - "member": any admin (only `/api/omi/access`, which reports your scopes).
 * - "team-agent": `requireTeamAgent` (Google service-account identity).
 * - { open: reason }: not an admin route; the reason says what guards it.
 */
export type RoutePolicy = Scope | "member" | "team-agent" | { open: string };

/**
 * The financial wall: every route that can surface revenue, MRR, cost,
 * subscription, payout or billing data — directly, through a capability
 * (TV share links, the kiosk embed), or mixed into partner data
 * (organization billing fields). The tests in
 * `lib/__tests__/route-scopes.test.ts` walk this list, and fail when a new
 * finance-scoped route is not audited into it.
 *
 * - "policy": the entry's ROUTE_POLICIES scope must be exactly that scope.
 * - "tv-share": an unauthenticated capability route; the share token is
 *   honored only while its issuer still holds finance:read.
 * - "tv-links": link management under analytics:share; minting requires
 *   finance:read and the share tokens are redacted without it.
 * - "partners-with-billing": partner routes; billing fields are redacted
 *   without finance:read and billing mutations require finance:write.
 */
export type FinancialWall =
  | { policy: "finance:read" | "finance:write" }
  | { tvShare: true }
  | { tvLinks: true }
  | { partnersWithBilling: true };

export const FINANCIAL_ROUTES: Record<string, FinancialWall> = {
  // Direct financial data, pinned by policy.
  "GET /api/grafana/embed": { policy: "finance:read" },
  "GET /api/omi/stats/app-subscriptions": { policy: "finance:read" },
  "GET /api/omi/stats/infra-costs": { policy: "finance:read" },
  "GET /api/omi/stats/mrr-trends": { policy: "finance:read" },
  "GET /api/omi/stats/plan-economics": { policy: "finance:read" },
  "GET /api/omi/stats/profitability": { policy: "finance:read" },
  "GET /api/omi/stats/revenue": { policy: "finance:read" },
  "GET /api/omi/stats/subscription-trends": { policy: "finance:read" },
  "GET /api/omi/stats/subscriptions": { policy: "finance:read" },
  "GET /api/omi/stats/wall": { policy: "finance:read" },
  "GET /api/omi/stats/wall/series/[name]": { policy: "finance:read" },
  "GET /api/omi/subscriptions": { policy: "finance:read" },
  "GET /api/omi/payouts": { policy: "finance:read" },
  "GET /api/omi/all-payouts": { policy: "finance:read" },
  "GET /api/omi/users-with-stripe": { policy: "finance:read" },
  "GET /api/omi/affiliates": { policy: "finance:read" },
  "GET /api/omi/affiliate-payouts": { policy: "finance:read" },
  "POST /api/omi/affiliate-payouts": { policy: "finance:write" },

  // The TV capability wall: the omi-tv-v2 Business board (revenue, MRR,
  // Shopify and cost panels) reached without a login.
  "POST /api/grafana/tv-embed": { tvShare: true },
  "GET /api/omi/tv-links": { tvLinks: true },
  "POST /api/omi/tv-links": { tvLinks: true },
  "DELETE /api/omi/tv-links/[id]": { tvLinks: true },

  // Organization documents mix partner metadata with Stripe billing.
  "GET /api/organizations": { partnersWithBilling: true },
  "POST /api/organizations": { partnersWithBilling: true },
  "PATCH /api/organizations/[id]": { partnersWithBilling: true },
};

export const ROUTE_POLICIES: Record<string, RoutePolicy> = {
  // Session
  "GET /api/omi/access": "member",

  // Analytics
  "GET /api/omi/stats/activation": "analytics:read",
  "GET /api/omi/stats/conversation-count": "analytics:read",
  "GET /api/omi/stats/crash-rate": "analytics:read",
  "GET /api/omi/stats/daily-new-users": "analytics:read",
  "GET /api/omi/stats/dau-trends": "analytics:read",
  "GET /api/omi/stats/desktop-ratings": "analytics:read",
  "GET /api/omi/stats/device-health": "analytics:read",
  "GET /api/omi/stats/floating-bar-usage": "analytics:read",
  "GET /api/omi/stats/k-factor/posthog": "analytics:read",
  "GET /api/omi/stats/macos-versions": "analytics:read",
  "GET /api/omi/stats/message-ratings": "analytics:read",
  "GET /api/omi/stats/notifications": "analytics:read",
  "GET /api/omi/stats/onboarding/mobile": "analytics:read",
  "GET /api/omi/stats/onboarding/mobile/attach": "analytics:read",
  "GET /api/omi/stats/onboarding/mobile/tutorial": "analytics:read",
  "GET /api/omi/stats/onboarding/posthog": "analytics:read",
  "GET /api/omi/stats/releases": "analytics:read",
  "GET /api/omi/stats/response-reliability": "analytics:read",
  "GET /api/omi/stats/retention/posthog": "analytics:read",
  "GET /api/omi/stats/viral-metrics": "analytics:read",
  // The CSAT page's own feed; its free-text comments are additionally
  // wall-gated on users:read (lib/sensitive-fields.ts).
  "GET /api/omi/csat/stats": "content:read",
  "GET /api/omi/tv-links": "analytics:share",
  "POST /api/omi/tv-links": "analytics:share",
  "DELETE /api/omi/tv-links/[id]": "analytics:share",

  // Finance
  // The omi-tv-v2 Business board exposes revenue, MRR, Shopify and cost
  // panels; the wall aggregate and its series (revenue, health, headline)
  // carry MRR, hardware revenue and all-in cost.
  "GET /api/grafana/embed": "finance:read",
  "GET /api/omi/stats/app-subscriptions": "finance:read",
  "GET /api/omi/stats/infra-costs": "finance:read",
  "GET /api/omi/stats/mrr-trends": "finance:read",
  "GET /api/omi/stats/plan-economics": "finance:read",
  "GET /api/omi/stats/profitability": "finance:read",
  "GET /api/omi/stats/revenue": "finance:read",
  "GET /api/omi/stats/subscription-trends": "finance:read",
  "GET /api/omi/stats/subscriptions": "finance:read",
  "GET /api/omi/stats/wall": "finance:read",
  "GET /api/omi/stats/wall/series/[name]": "finance:read",
  "GET /api/omi/subscriptions": "finance:read",
  "GET /api/omi/payouts": "finance:read",
  "GET /api/omi/all-payouts": "finance:read",
  "GET /api/omi/users-with-stripe": "finance:read",
  "GET /api/omi/affiliates": "finance:read",
  "GET /api/omi/affiliate-payouts": "finance:read",
  "POST /api/omi/affiliate-payouts": "finance:write",

  // Users and support
  "GET /api/omi/fair-use/flagged": "users:read",
  "GET /api/omi/fair-use/case/[caseRef]": "users:read",
  "GET /api/omi/fair-use/user/[uid]": "users:read",
  "POST /api/omi/fair-use/user/[uid]/reset": "users:write",
  "POST /api/omi/fair-use/user/[uid]/set-stage": "users:write",
  "POST /api/omi/fair-use/user/[uid]/resolve-event/[eventId]": "users:write",
  "GET /api/omi/feedback/reports": "users:read",
  "GET /api/omi/feedback/reports/[reportDate]": "users:read",
  "POST /api/omi/feedback/reports/[reportDate]": "users:write",
  "GET /api/omi/feedback/events/[eventId]/context": "users:read",
  "GET /api/omi/notifications/user-notifications": "users:read",
  "POST /api/omi/notifications/regenerate": "users:write",

  // Apps
  "GET /api/omi/apps": "apps:read",
  "GET /api/omi/apps/stats": "apps:read",
  "OPTIONS /api/omi/apps/stats": { open: "CORS preflight; returns no data" },
  "GET /api/omi/apps/unapproved": "apps:read",
  "GET /api/omi/apps/[app_id]/details": "apps:read",
  "GET /api/omi/private-apps": "apps:read",
  "GET /api/omi/summary-apps": "apps:read",
  "POST /api/omi/apps/[app_id]/review": "apps:write",
  "POST /api/omi/apps/[app_id]/update": "apps:write",
  "PATCH /api/omi/apps/[app_id]/popular": "apps:write",
  "POST /api/omi/summary-apps": "apps:write",
  "PATCH /api/omi/summary-apps": "apps:write",
  "DELETE /api/omi/summary-apps": "apps:write",

  // Content
  "GET /api/omi/announcements": "content:read",
  "GET /api/omi/announcements/[id]": "content:read",
  "POST /api/omi/announcements": "content:write",
  "PUT /api/omi/announcements/[id]": "content:write",
  "DELETE /api/omi/announcements/[id]": "content:write",
  "GET /api/omi/desktop-prompts": "content:read",
  "GET /api/omi/desktop-prompts/results": "content:read",
  "POST /api/omi/desktop-prompts": "content:write",
  "PATCH /api/omi/desktop-prompts/[id]": "content:write",
  "DELETE /api/omi/desktop-prompts/[id]": "content:write",
  "GET /api/omi/csat": "content:read",
  "PUT /api/omi/csat": "content:write",
  "GET /api/omi/releases": "content:read",
  "GET /api/omi/chat-lab/prompts": "content:read",
  "GET /api/omi/chat-lab/questions": "content:read",
  "GET /api/omi/chat-lab/ratings": "content:read",
  "POST /api/omi/chat-lab/prompts": "content:write",
  "POST /api/omi/chat-lab/questions": "content:write",
  "POST /api/omi/chat-lab/generate": "content:write",
  "POST /api/omi/chat-lab/evaluate": "content:write",

  // Partners
  "GET /api/distributors": "partners:read",
  "GET /api/distributors/locations": "partners:read",
  "POST /api/distributors": "partners:write",
  "PUT /api/distributors": "partners:write",
  "GET /api/organizations": "partners:read",
  "POST /api/organizations": "partners:write",
  "PATCH /api/organizations/[id]": "partners:write",

  // Development
  // GET only reports whether the local agent endpoint is enabled; the POST
  // spawn is additionally 404 outside local development (lib/local-agent.ts).
  "GET /api/omi/agent/customize": "dev:agent",
  "POST /api/omi/agent/customize": "dev:agent",

  // Team
  "GET /api/omi/team-members": "team:read",
  "GET /api/omi/team-members/audit": "team:read",
  "GET /api/omi/team-members/proposals": "team:read",
  "POST /api/omi/team-members": "team:invite",
  "PATCH /api/omi/team-members": "team:manage",
  "DELETE /api/omi/team-members": "team:manage",
  "POST /api/omi/team-members/proposals/[id]": "team:manage",

  // Team agents: roster/audit reads and proposals only, never applied directly
  "GET /api/agent/team": "team-agent",
  "GET /api/agent/team/audit": "team-agent",
  "GET /api/agent/team/proposals": "team-agent",
  "POST /api/agent/team/proposals": "team-agent",

  // Not admin routes
  "GET /api/grafana/jwks": { open: "public signing keys for Grafana" },
  "POST /api/grafana/tv-embed": {
    open: "TV share-link capability token; issuer's finance:read re-checked",
  },
  "POST /api/internal/precompute": { open: "x-cron-secret scheduler header" },
  "GET /api/public/user-growth": { open: "public aggregate counts only" },
};
