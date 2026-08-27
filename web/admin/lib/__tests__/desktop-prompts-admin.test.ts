import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/auth", () => ({
  verifyAdmin: vi.fn(async () => ({ uid: "t" })),
}));
vi.mock("@/lib/firebase/admin", () => ({ getDb: () => ({}) }));

import { normalizePrompt } from "@/app/api/omi/desktop-prompts/route";

describe("normalizePrompt", () => {
  it("builds the document the desktop delivery route expects", () => {
    const { doc, error } = normalizePrompt({
      type: "stars",
      question: " How useful was today's summary? ",
      trigger_kind: "question_count",
      trigger_count: 3,
      rollout_pct: 250,
      channels: ["beta", "nightly"],
    });
    expect(error).toBeUndefined();
    expect(doc.question).toBe("How useful was today's summary?");
    expect(doc.trigger).toEqual({ kind: "question_count", count: 3 });
    expect(doc.audience.rollout_pct).toBe(100); // clamped
    expect(doc.audience.channels).toEqual(["beta"]); // unknown channel dropped
    expect(doc.active).toBe(false); // prompts are born inactive
  });

  it("rejects unknown types, empty questions, and 1-option choices", () => {
    expect(normalizePrompt({ type: "modal", question: "x" }).error).toContain(
      "type",
    );
    expect(normalizePrompt({ type: "stars", question: "  " }).error).toContain(
      "question",
    );
    expect(
      normalizePrompt({
        type: "choice",
        question: "Pick",
        options: ["only one"],
      }).error,
    ).toContain("options");
  });

  it("keeps the banner CTA only when both label and url are present", () => {
    const withCta = normalizePrompt({
      type: "banner",
      question: "Try X",
      cta_label: "Open",
      cta_url: "https://omi.me",
    }).doc;
    expect(withCta.cta).toEqual({ label: "Open", url: "https://omi.me" });
    const withoutCta = normalizePrompt({
      type: "banner",
      question: "Try X",
      cta_label: "Open",
    }).doc;
    expect(withoutCta.cta).toBeNull();
  });
});
