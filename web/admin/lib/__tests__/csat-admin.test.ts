import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/auth", () => ({
  verifyAdmin: vi.fn(async () => ({ uid: "t" })),
}));
vi.mock("@/lib/firebase/admin", () => ({ getDb: () => ({}) }));

import { normalizeCsatConfig } from "@/app/api/omi/csat/route";

describe("normalizeCsatConfig", () => {
  it("clamps question_threshold to 1..50 and comment_max_score to 1..5", () => {
    const high = normalizeCsatConfig({
      title: "How would you rate Omi Desktop?",
      question_threshold: 500,
      comment_max_score: 9,
    });
    expect(high.error).toBeUndefined();
    expect(high.doc?.question_threshold).toBe(50);
    expect(high.doc?.comment_max_score).toBe(5);

    const low = normalizeCsatConfig({
      title: "How would you rate Omi Desktop?",
      question_threshold: 0,
      comment_max_score: -2,
    });
    expect(low.doc?.question_threshold).toBe(1);
    expect(low.doc?.comment_max_score).toBe(1);
  });

  it("trims the title and rejects an empty one", () => {
    const { doc, error } = normalizeCsatConfig({
      title: "  How would you rate Omi Desktop?  ",
    });
    expect(error).toBeUndefined();
    expect(doc?.title).toBe("How would you rate Omi Desktop?");
    expect(normalizeCsatConfig({ title: "   " }).error).toContain("title");
    expect(normalizeCsatConfig({}).error).toContain("title");
  });

  it("keeps defaults for omitted optional fields", () => {
    const { doc, error } = normalizeCsatConfig({ title: "Rate us" });
    expect(error).toBeUndefined();
    expect(doc?.enabled).toBe(true);
    expect(doc?.body).toBe("");
    expect(doc?.question_threshold).toBe(3);
    expect(doc?.comment_max_score).toBe(3);
  });
});
