import { describe, expect, it } from "vitest";
import {
  FINANCIAL_FIELDS,
  FINANCIAL_FIELD_PREFIXES,
  isFinancialField,
  redactFinancialFields,
} from "@/lib/financial-fields";

describe("isFinancialField", () => {
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
      expect(isFinancialField(field), field).toBe(true);
    }
  });

  it("matches Stripe and payout prefixes anywhere they start a key", () => {
    expect(isFinancialField("stripe_account_id")).toBe(true);
    expect(isFinancialField("stripe_payment_id")).toBe(true);
    expect(isFinancialField("payout")).toBe(true);
    expect(isFinancialField("payouts")).toBe(true);
    expect(isFinancialField("payout_amount")).toBe(true);
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
    ]) {
      expect(isFinancialField(field), field).toBe(false);
    }
  });

  it("keeps every declared name and prefix matched", () => {
    for (const field of FINANCIAL_FIELDS)
      expect(isFinancialField(field), field).toBe(true);
    for (const prefix of FINANCIAL_FIELD_PREFIXES)
      expect(isFinancialField(`${prefix}anything`), prefix).toBe(true);
  });
});

describe("redactFinancialFields", () => {
  it("strips financial fields at any depth, in objects and arrays", () => {
    const doc = {
      id: "a1",
      name: "App",
      money_made: 99,
      price: 5,
      subscription: { plan: "pro", status: "active" },
      reviews: [
        { uid: "u1", rating: 5 },
        { uid: "u2", rating: 1, payout_id: "po_1" },
      ],
      author: { email: "a@b.c", stripe_customer_id: "cus_1" },
    };
    expect(redactFinancialFields(doc)).toEqual({
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
    redactFinancialFields(doc);
    expect(doc).toEqual({ price: 5, nested: { mrr: 10 } });
  });

  it("keeps explicitly allowed fields when a route opts out per field", () => {
    const doc = { price: 5, money_made: 100, name: "App" };
    expect(redactFinancialFields(doc, { keep: ["price"] })).toEqual({
      price: 5,
      name: "App",
    });
  });

  it("passes scalars and non-plain objects through", () => {
    const date = new Date(0);
    expect(redactFinancialFields(null)).toBeNull();
    expect(redactFinancialFields(3)).toBe(3);
    expect(redactFinancialFields(date)).toBe(date);
  });
});
