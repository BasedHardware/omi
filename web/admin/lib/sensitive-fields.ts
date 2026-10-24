/**
 * The sensitive field wall.
 *
 * Scope checks guard routes; this guards fields. Routes legitimately read
 * documents that mix operational data with data the caller's scope does not
 * cover (app listings carry `money_made` and MCP credentials, user docs
 * carry `subscription`, CSAT aggregates carry free-text comments), so one
 * deep redactor strips every classified field from any JSON body it is
 * handed unless the caller holds the scope that unlocks the field's class.
 * It is applied at the single response choke point — `AdminIdentity.json`
 * in lib/auth.ts, which every scoped route responds through — so a new
 * route or a newly added Firestore field cannot leak classified data route
 * by route.
 *
 * The classification table below is the whole policy: one class per kind of
 * sensitive data, the scope that unlocks it (`null` = no scope ever unlocks
 * it), and the field names it covers. Adding a field or a class later is
 * one line here — `lib/__tests__/sensitive-wall.test.ts` then walks every
 * scoped GET handler with fixture data seeded with the whole table and
 * fails if any classified name survives in a response body for a caller
 * who lacks that class's scope.
 *
 * Field names are matched exactly at any depth (plus the class's prefixes),
 * so a name must be specific enough to mean only its class everywhere it
 * appears: `token` is not a credential field (TV share links serve tokens
 * by design) and `email` is not user content (partner and employee emails
 * are business contacts, not end-user data).
 */

import type { Scope } from "@/lib/admin-access";

export interface SensitiveFieldClass {
  /** Stable id, used by the wall test to sweep one class at a time. */
  id: "financial" | "credentials" | "user-content";
  /** What the class protects, for docs and failure messages. */
  label: string;
  /**
   * The scope that unlocks the class. `null` means no scope ever returns
   * these fields to the browser; a route that must surface one (an
   * owner-only edit flow) passes `keep` per response, with a comment and a
   * wall test.
   */
  scope: Scope | null;
  /** Field names that belong to this class wherever they appear. */
  fields: readonly string[];
  /** Key prefixes that belong to this class (Stripe objects, payouts). */
  prefixes?: readonly string[];
}

/** The classification table. Field lists derive from the backend REST
 * schema (lib/services/omi-api/omiApi.generated.ts) and the Firestore
 * document shapes the routes read (plugins_data apps, users,
 * organisations, csat_ratings). */
export const SENSITIVE_FIELD_CLASSES: readonly SensitiveFieldClass[] = [
  {
    id: "financial",
    label: "Money data (revenue, subscriptions, payouts, billing)",
    scope: "finance:read",
    fields: [
      // App/plugin monetization (plugins_data docs and /v1/apps DTOs)
      "money_made",
      "price",
      "prices",
      "price_id",
      "price_string",
      "current_price_id",
      "unit_amount",
      "amount_minor",
      "payment",
      "payment_link",
      "payment_link_id",
      "payment_plan",
      "payment_price_id",
      "payment_product_id",
      "payment_details",
      "payment_method",
      // Subscriptions and billing (user docs, organisation docs, Stripe DTOs)
      "subscription",
      "subscription_plan",
      "subscription_id",
      "stripe_subscription_id",
      "customer_id",
      "next_billing_date",
      "billing",
      // Aggregate money figures (stats, payouts, affiliates)
      "revenue",
      "mrr",
      "arr",
      "amount",
      "cost",
      "cost_usd",
      "total_cost_usd",
      "real_cost_usd",
      "included_cost_usd",
      "chat_cost_usd_per_month",
      "total_earned",
      "pending_amount",
    ],
    prefixes: ["stripe_", "payout"],
  },
  {
    id: "credentials",
    label: "Credentials and secrets (never returned to the browser)",
    scope: null,
    fields: [
      // MCP app integration auth (plugins_data external_integration)
      "mcp_oauth_tokens",
      "client_secret",
      "code_verifier",
      // Integration and API credentials (omiApi.generated.ts DTOs)
      "access_token",
      "refresh_token",
      "api_key",
      // Generic secret material wherever a doc carries it
      "secret",
      "password",
      "webhook_secret",
      "private_key",
    ],
  },
  {
    id: "user-content",
    label: "Private user content (verbatim end-user material)",
    scope: "users:read",
    fields: [
      // CSAT free-text feedback rows
      "comment",
      // Conversation transcripts and memories
      "transcript",
      "memories",
      // Chat Lab sampling of real users' messages
      "your_questions",
      "all_users_questions",
    ],
  },
];

export function sensitiveClassFor(key: string): SensitiveFieldClass | null {
  return (
    SENSITIVE_FIELD_CLASSES.find(
      (klass) =>
        klass.fields.includes(key) ||
        (klass.prefixes ?? []).some((prefix) => key.startsWith(prefix))
    ) ?? null
  );
}

export interface RedactOptions {
  /** The caller's effective scopes; a class is kept when its scope is present. */
  scopes: readonly Scope[];
  /**
   * Field names this one response may keep despite the wall (for a class
   * the caller's scopes do not unlock, including credentials). Every entry
   * needs a comment at the call site saying why, and a test in
   * `lib/__tests__/sensitive-wall.test.ts` pinning it. No route uses this
   * today.
   */
  keep?: readonly string[];
}

const isPlainObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" &&
  value !== null &&
  !Array.isArray(value) &&
  Object.getPrototypeOf(value) === Object.prototype;

/**
 * Deep copy of `value` with every classified field removed, at any depth,
 * from plain objects and arrays. A field survives only when the caller's
 * scopes include its class's scope — or the response opted out via `keep`.
 * Anything JSON-serializable passes through unchanged except for the
 * stripped keys; class instances (Firestore Timestamps and the like,
 * already serialized by the routes) are kept as-is.
 */
export function redactSensitiveFields<T>(value: T, options: RedactOptions): T {
  const keep = options.keep ?? [];
  // A class no scope unlocks is hidden from everyone; a scoped class is
  // hidden from callers whose scopes do not include it.
  const hidden = (klass: SensitiveFieldClass) =>
    klass.scope === null || !options.scopes.includes(klass.scope);
  const redact = (node: unknown): unknown => {
    if (Array.isArray(node)) return node.map(redact);
    if (!isPlainObject(node)) return node;
    const out: Record<string, unknown> = {};
    for (const [key, child] of Object.entries(node)) {
      const klass = sensitiveClassFor(key);
      if (klass && !keep.includes(key) && hidden(klass)) continue;
      out[key] = redact(child);
    }
    return out;
  };
  return redact(value) as T;
}
