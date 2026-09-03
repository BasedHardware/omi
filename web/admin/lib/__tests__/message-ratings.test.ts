import { beforeEach, describe, expect, it, vi } from "vitest";

const docsMock = vi.hoisted(() => ({ docs: [] as any[] }));
vi.mock("@/lib/firebase/admin", () => ({
  getDb: () => ({
    collectionGroup: () => ({
      where: () => ({
        where: () => ({ get: async () => ({ docs: docsMock.docs }) }),
      }),
    }),
  }),
}));
vi.mock("@/lib/auth", () => ({ verifyAdmin: vi.fn() }));

import {
  aggregateRatedMessages,
  classifyRatedMessage,
  computeMessageRatings,
} from "@/app/api/omi/stats/message-ratings/route";

// Noon UTC = same NYC calendar day.
const at = (ymd: string) => `${ymd}T12:00:00.000Z`;
const row = (
  ymd: string,
  rating: 1 | -1,
  messageSource: string | null,
  continuityKey: string | null = null
) => ({ createdAt: at(ymd), rating, messageSource, continuityKey });

describe("classifyRatedMessage", () => {
  it("routes notification cards, desktop lanes, and mobile correctly", () => {
    expect(
      classifyRatedMessage(
        row("2026-08-24", 1, "desktop_chat", "notification:memory:abc")
      )
    ).toBe("notification");
    expect(classifyRatedMessage(row("2026-08-24", 1, "desktop_chat"))).toBe(
      "text"
    );
    expect(classifyRatedMessage(row("2026-08-24", 1, "realtime_voice"))).toBe(
      "voice"
    );
    // Mobile ratings have no desktop message_source — they must never count
    // on the macOS board (522 of 633 rated docs in the 28d verification scan
    // were mobile, at a very different positive rate).
    expect(classifyRatedMessage(row("2026-08-24", 1, null))).toBe("mobile");
    expect(
      classifyRatedMessage(row("2026-08-24", 1, "some_future_source"))
    ).toBe("mobile");
  });
});

describe("aggregateRatedMessages (general Omi answers only)", () => {
  it("excludes notification and mobile ratings from every series", () => {
    // Monday 2026-08-24: text 3↑1↓, voice 1↑1↓, plus noise that must move
    // nothing: notification thumbs and mobile thumbs.
    const { daily, weekly, data } = aggregateRatedMessages([
      row("2026-08-24", 1, "desktop_chat"),
      row("2026-08-24", 1, "desktop_chat"),
      row("2026-08-24", 1, "desktop_chat"),
      row("2026-08-24", -1, "desktop_chat"),
      row("2026-08-24", 1, "realtime_voice"),
      row("2026-08-24", -1, "realtime_voice"),
      row("2026-08-24", -1, "desktop_chat", "notification:memory:x"),
      row("2026-08-24", -1, "desktop_chat", "notification:suggestion:y"),
      row("2026-08-24", 1, null),
      row("2026-08-24", 1, null),
      // Tuesday: all-downvote day is a real 0, not null.
      row("2026-08-25", -1, "desktop_chat"),
    ]);

    const monday = daily.find((p) => p.date === "2026-08-24")!;
    expect(monday.text).toBe(75);
    expect(monday.voice).toBe(50);
    expect(monday.all).toBeCloseTo(66.7);
    expect(monday.upAll).toBe(4);
    expect(monday.downAll).toBe(2);

    const tuesday = daily.find((p) => p.date === "2026-08-25")!;
    expect(tuesday.all).toBe(0); // all-down day: real 0
    expect(tuesday.voice).toBeNull(); // no voice ratings: unmeasurable

    // A day with no desktop-answer ratings yields no point at all — absence,
    // never a fake 0 (honesty rule).
    expect(daily).toHaveLength(2);

    // Weekly: both days share the 2026-08-24 NYC Monday bucket.
    expect(weekly).toHaveLength(1);
    expect(weekly[0].week).toBe("2026-08-24");
    expect(weekly[0].all).toBeCloseTo(57.1); // 4↑ / 7 rated
    expect(weekly[0].text).toBe(60);

    // Legacy shape stays for the volumes panel and /dashboard/classic.
    expect(data[0]).toEqual({
      date: "2026-08-24",
      thumbs_up: 4,
      thumbs_down: 2,
      ratio: expect.closeTo(66.7, 1),
    });
  });
});

describe("computeMessageRatings (Firestore join)", () => {
  beforeEach(() => {
    docsMock.docs = [];
  });

  it("decodes Firestore docs: timestamp, message_source, journal continuityKey", async () => {
    docsMock.docs = [
      {
        data: () => ({
          rating: 1,
          created_at: { toDate: () => new Date(at("2026-08-24")) },
          message_source: "desktop_chat",
          metadata: JSON.stringify({ continuityKey: "turn-1" }),
        }),
      },
      {
        data: () => ({
          rating: -1,
          created_at: { toDate: () => new Date(at("2026-08-24")) },
          message_source: "desktop_chat",
          metadata: JSON.stringify({ continuityKey: "notification:insight:z" }),
        }),
      },
      {
        data: () => ({
          rating: -1,
          created_at: { toDate: () => new Date(at("2026-08-24")) },
          message_source: null,
          metadata: "not json {",
        }),
      },
    ];
    const payload = await computeMessageRatings(30);
    expect(payload.days).toBe(30);
    // Only the desktop answer counts: notification and mobile (bad-metadata,
    // no source) rows are excluded.
    expect(payload.daily).toHaveLength(1);
    expect(payload.daily[0]).toMatchObject({
      date: "2026-08-24",
      all: 100,
      text: 100,
      voice: null,
      upAll: 1,
      downAll: 0,
    });
  });
});
