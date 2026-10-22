/**
 * The financial field wall.
 *
 * Scope checks guard routes; this guards fields. Routes under non-finance
 * scopes legitimately read documents that mix operational data with money
 * data (app listings carry `money_made`, user docs carry `subscription`,
 * organization docs carry Stripe billing), so one deep redactor strips every
 * financial field from any JSON body it is handed unless the caller holds
 * finance:read. It is applied at the single response choke point —
 * `AdminIdentity.json` in lib/auth.ts, which every scoped route responds
 * through — so a new route or a newly added Firestore field cannot leak
 * revenue data route by route.
 *
 * The list is derived from the backend REST schema
 * (lib/services/omi-api/omiApi.generated.ts) and the Firestore document
 * shapes the routes read (plugins_data apps, users, organisations). Add a
 * field here when the backend grows one; `lib/__tests__/financial-wall.test.ts`
 * walks every scoped GET handler with fixture data seeded with this whole
 * list and fails if any of these names survives in a response body for a
 * caller without finance:read.
 */

/** Field names that are money data wherever they appear. */
export const FINANCIAL_FIELDS: readonly string[] = [
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
];

/** Key prefixes that are money data (Stripe objects, payout records). */
export const FINANCIAL_FIELD_PREFIXES: readonly string[] = [
  "stripe_",
  "payout",
];

export function isFinancialField(key: string): boolean {
  return (
    FINANCIAL_FIELDS.includes(key) ||
    FINANCIAL_FIELD_PREFIXES.some((prefix) => key.startsWith(prefix))
  );
}

export interface RedactOptions {
  /**
   * Field names this one response may keep despite the wall. Every entry
   * needs a comment at the call site saying why a non-finance caller needs
   * the field, and a test in lib/__tests__/financial-wall.test.ts pinning
   * it. No route uses this today.
   */
  keep?: readonly string[];
}

const isPlainObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" &&
  value !== null &&
  !Array.isArray(value) &&
  Object.getPrototypeOf(value) === Object.prototype;

/**
 * Deep copy of `value` with every financial field removed, at any depth,
 * from plain objects and arrays. Anything JSON-serializable passes through
 * unchanged except for the stripped keys; class instances (Firestore
 * Timestamps and the like, already serialized by the routes) are kept as-is.
 */
export function redactFinancialFields<T>(
  value: T,
  options: RedactOptions = {}
): T {
  const keep = options.keep ?? [];
  const redact = (node: unknown): unknown => {
    if (Array.isArray(node)) return node.map(redact);
    if (!isPlainObject(node)) return node;
    const out: Record<string, unknown> = {};
    for (const [key, child] of Object.entries(node)) {
      if (isFinancialField(key) && !keep.includes(key)) continue;
      out[key] = redact(child);
    }
    return out;
  };
  return redact(value) as T;
}
