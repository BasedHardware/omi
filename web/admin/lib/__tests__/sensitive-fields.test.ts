import { describe, expect, it } from "vitest";
import {
  SENSITIVE_FIELD_CLASSES,
  redactSensitiveFields,
  sensitiveClassFor,
} from "@/lib/sensitive-fields";

const ALL_SCOPES = SENSITIVE_FIELD_CLASSES.map((klass) => klass.scope).filter(
  (scope): scope is NonNullable<typeof scope> => scope !== null
);

const scopesWithout = (removed: string) =>
  ALL_SCOPES.filter((scope) => scope !== removed);

describe("sensitiveClassFor", () => {
  it("matches the app monetization, subscription and money-aggregate names", () => {
    for (const field of [
      "money_made",
      "price",
      "payment_link",
      "payment_product_id",
      "payment_price_id",
      "payment_plan",
      "subscription",
      "subscription_plan",
      "stripe_subscription_id",
      "customer_id",
      "revenue",
      "mrr",
      "arr",
      "amount",
      "cost",
      "total_earned",
      "pending_amount",
    ]) {
      expect(sensitiveClassFor(field)?.id, field).toBe("financial");
    }
  });

  it("matches Stripe and payout prefixes anywhere they start a key", () => {
    expect(sensitiveClassFor("stripe_account_id")?.id).toBe("financial");
    expect(sensitiveClassFor("stripe_payment_id")?.id).toBe("financial");
    expect(sensitiveClassFor("payout")?.id).toBe("financial");
    expect(sensitiveClassFor("payouts")?.id).toBe("financial");
    expect(sensitiveClassFor("payout_amount")?.id).toBe("financial");
  });

  it("matches credential and secret names", () => {
    for (const field of [
      "client_secret",
      "code_verifier",
      "mcp_oauth_tokens",
      "access_token",
      "refresh_token",
      "api_key",
      "webhook_secret",
      "private_key",
      "secret",
      "password",
    ]) {
      expect(sensitiveClassFor(field)?.id, field).toBe("credentials");
    }
  });

  it("matches private user-content names", () => {
    for (const field of [
      "comment",
      "transcript",
      "memories",
      "your_questions",
      "all_users_questions",
    ]) {
      expect(sensitiveClassFor(field)?.id, field).toBe("user-content");
    }
  });

  it("lets operational fields through", () => {
    for (const field of [
      "is_paid",
      "name",
      "status",
      "email",
      "capabilities",
      "installed",
      "arrivals", // not arr
      "starred", // not a Stripe prefix
      "token", // TV share links serve tokens by design
      "comments", // affiliate payout notes are finance data, not user content
      "context_type",
    ]) {
      expect(sensitiveClassFor(field), field).toBeNull();
    }
  });

  it("keeps every declared name and prefix matched", () => {
    for (const klass of SENSITIVE_FIELD_CLASSES) {
      for (const field of klass.fields)
        expect(sensitiveClassFor(field)?.id, field).toBe(klass.id);
      for (const prefix of klass.prefixes ?? [])
        expect(sensitiveClassFor(`${prefix}anything`)?.id, prefix).toBe(
          klass.id
        );
    }
  });
});

describe("redactSensitiveFields", () => {
  it("strips every class's fields for a caller holding no unlocking scope", () => {
    const doc = {
      id: "a1",
      name: "App",
      money_made: 99,
      subscription: { plan: "pro", status: "active" },
      external_integration: {
        mcp_server_url: "https://mcp.example",
        mcp_oauth_tokens: { access_token: "x" },
        client_secret: "cs",
      },
      comment: "love it",
      transcript: "we talked about...",
    };
    expect(redactSensitiveFields(doc, { scopes: [] })).toEqual({
      id: "a1",
      name: "App",
      external_integration: { mcp_server_url: "https://mcp.example" },
    });
  });

  it("keeps a class for a caller holding its scope but strips the others", () => {
    const doc = {
      price: 5,
      comment: "love it",
      client_secret: "cs",
    };
    expect(
      redactSensitiveFields(doc, { scopes: scopesWithout("users:read") })
    ).toEqual({ price: 5 });
    expect(
      redactSensitiveFields(doc, { scopes: scopesWithout("finance:read") })
    ).toEqual({ comment: "love it" });
  });

  it("never keeps credentials, even for a caller holding every scope", () => {
    const doc = {
      api_key: "k",
      access_token: "t",
      secret: "s",
      price: 5,
      comment: "ok",
    };
    expect(redactSensitiveFields(doc, { scopes: ALL_SCOPES })).toEqual({
      price: 5,
      comment: "ok",
    });
  });

  it("strips classified fields at any depth, in objects and arrays", () => {
    const doc = {
      id: "a1",
      name: "App",
      money_made: 99,
      price: 5,
      subscription: { plan: "pro", status: "active" },
      reviews: [
        { uid: "u1", rating: 5 },
        { uid: "u2", rating: 1, payout_id: "po_1", comment: "meh" },
      ],
      author: { email: "a@b.c", stripe_customer_id: "cus_1" },
    };
    expect(redactSensitiveFields(doc, { scopes: [] })).toEqual({
      id: "a1",
      name: "App",
      reviews: [
        { uid: "u1", rating: 5 },
        { uid: "u2", rating: 1 },
      ],
      author: { email: "a@b.c" },
    });
  });

  it("does not mutate the input", () => {
    const doc = { price: 5, nested: { mrr: 10 } };
    redactSensitiveFields(doc, { scopes: [] });
    expect(doc).toEqual({ price: 5, nested: { mrr: 10 } });
  });

  it("keeps explicitly allowed fields when a route opts out per field", () => {
    const doc = { price: 5, money_made: 100, name: "App" };
    expect(redactSensitiveFields(doc, { scopes: [], keep: ["price"] })).toEqual(
      { price: 5, name: "App" }
    );
  });

  it("passes scalars and non-plain objects through", () => {
    const date = new Date(0);
    expect(redactSensitiveFields(null, { scopes: [] })).toBeNull();
    expect(redactSensitiveFields(3, { scopes: [] })).toBe(3);
    expect(redactSensitiveFields(date, { scopes: [] })).toBe(date);
  });
});
