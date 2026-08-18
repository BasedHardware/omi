import { beforeEach, describe, expect, it, vi } from "vitest";

// The route reaches Firestore through getDb(); faking it here exercises the
// real cohort/pagination/maturity logic without a service account.
const getDb = vi.fn();
vi.mock("@/lib/firebase/admin", () => ({ getDb: () => getDb() }));
vi.mock("@/lib/auth", () => ({ verifyAdmin: vi.fn() }));
vi.mock("@/lib/payload-cache", () => ({
  getPayload: vi.fn(),
  setPayload: vi.fn(),
}));

import { computeActivation } from "@/app/api/omi/stats/activation/route";

const DAY = 86_400_000;

type UserSeed = {
  uid: string;
  signupOs: string;
  signupDaysAgo: number;
  conversationOffsetsDays?: number[];
  throwOnRead?: boolean;
};

function fakeDb(users: UserSeed[]) {
  const now = Date.now();
  const docs = users.map((u) => ({
    id: u.uid,
    seed: u,
    signupAt: new Date(now - u.signupDaysAgo * DAY),
  }));
  docs.sort((a, b) => a.signupAt.getTime() - b.signupAt.getTime());

  // The route's own predicates decide the count. If it filtered the wrong
  // field, or shifted either bound, the returned count changes -- so the
  // 7-day window is a real contract here rather than something the fake
  // re-implements and always agrees with.
  const conversationsFor = (uid: string) => {
    const seed = users.find((u) => u.uid === uid)!;
    const signupAt = new Date(now - seed.signupDaysAgo * DAY);
    const timestamps = (seed.conversationOffsetsDays ?? []).map(
      (off) => signupAt.getTime() + off * DAY,
    );
    const bounds: { field: string; op: string; value: Date }[] = [];
    const api = {
      where(field: string, op: string, value: Date) {
        bounds.push({ field, op, value });
        return api;
      },
      count() {
        return {
          async get() {
            if (seed.throwOnRead) throw new Error("permission denied");
            for (const b of bounds) {
              if (b.field !== "created_at") {
                throw new Error(`unexpected filter field: ${b.field}`);
              }
            }
            const n = timestamps.filter((t) =>
              bounds.every((b) =>
                b.op === ">="
                  ? t >= b.value.getTime()
                  : b.op === "<="
                    ? t <= b.value.getTime()
                    : true,
              ),
            ).length;
            return { data: () => ({ count: n }) };
          },
        };
      },
    };
    return api;
  };

  // Honours the caller's limit(), so the route's own PAGE size drives paging.
  function usersQuery(after = 0, pageSize = docs.length) {
    return {
      where: () => usersQuery(after, pageSize),
      orderBy: () => usersQuery(after, pageSize),
      limit: (n: number) => usersQuery(after, n),
      startAfter(cursorDoc: any) {
        return usersQuery(
          docs.findIndex((d) => d.id === cursorDoc.id) + 1,
          pageSize,
        );
      },
      async get() {
        const slice = docs.slice(after, after + pageSize);
        return {
          empty: slice.length === 0,
          size: slice.length,
          docs: slice.map((d) => ({
            id: d.id,
            data: () => ({
              signup_os: d.seed.signupOs,
              signup_platform_at: { toDate: () => d.signupAt },
            }),
          })),
        };
      },
    };
  }

  return {
    collection(name: string) {
      if (name !== "users") throw new Error("unexpected collection " + name);
      return {
        ...usersQuery(),
        doc: (uid: string) => ({
          collection: (sub: string) => {
            if (sub !== "conversations") throw new Error("unexpected sub " + sub);
            return conversationsFor(uid);
          },
        }),
      };
    },
  };
}

beforeEach(() => getDb.mockReset());

describe("computeActivation", () => {
  it("counts a macOS signup as activated only on a conversation inside its 7-day window", async () => {
    getDb.mockReturnValue(
      fakeDb([
        { uid: "in-window", signupOs: "macos", signupDaysAgo: 30, conversationOffsetsDays: [3] },
        { uid: "too-late", signupOs: "macos", signupDaysAgo: 30, conversationOffsetsDays: [9] },
        { uid: "none", signupOs: "macos", signupDaysAgo: 30 },
      ]),
    );

    const result = await computeActivation(60);

    expect(result.signups).toBe(3);
    expect(result.activated).toBe(1);
    expect(result.rate).toBe(33.3);
  });

  it("treats the 7-day window as closed at both ends", async () => {
    getDb.mockReturnValue(
      fakeDb([
        { uid: "at-signup", signupOs: "macos", signupDaysAgo: 30, conversationOffsetsDays: [0] },
        { uid: "at-day-seven", signupOs: "macos", signupDaysAgo: 30, conversationOffsetsDays: [7] },
        { uid: "just-after", signupOs: "macos", signupDaysAgo: 30, conversationOffsetsDays: [7.001] },
        { uid: "just-before", signupOs: "macos", signupDaysAgo: 30, conversationOffsetsDays: [-0.001] },
      ]),
    );

    const result = await computeActivation(60);

    // Inclusive at signup and at signup+7d; anything outside is not activation.
    expect(result.signups).toBe(4);
    expect(result.activated).toBe(2);
  });

  it("excludes non-macOS signups", async () => {
    getDb.mockReturnValue(
      fakeDb([
        { uid: "mac", signupOs: "macos", signupDaysAgo: 20, conversationOffsetsDays: [1] },
        { uid: "ios", signupOs: "ios", signupDaysAgo: 20, conversationOffsetsDays: [1] },
        { uid: "web", signupOs: "web", signupDaysAgo: 20 },
      ]),
    );

    const result = await computeActivation(60);

    expect(result.signups).toBe(1);
    expect(result.activated).toBe(1);
  });

  it("excludes signups whose 7-day window has not elapsed", async () => {
    getDb.mockReturnValue(
      fakeDb([
        { uid: "matured", signupOs: "macos", signupDaysAgo: 10, conversationOffsetsDays: [1] },
        { uid: "yesterday", signupOs: "macos", signupDaysAgo: 1 },
        { uid: "day-six", signupOs: "macos", signupDaysAgo: 6 },
      ]),
    );

    const result = await computeActivation(60);

    expect(result.signups).toBe(1);
    expect(result.rate).toBe(100);
  });

  it("paginates past the 500-doc page instead of stopping at the first page", async () => {
    // 1,200 > 2 full pages, so a missing cursor advance truncates the cohort --
    // the exact shape that would silently undercount a real 10k-signup window.
    const many: UserSeed[] = Array.from({ length: 1200 }, (_, i) => ({
      uid: `u${i}`,
      signupOs: "macos",
      signupDaysAgo: 10 + (i % 40),
      conversationOffsetsDays: i % 2 === 0 ? [1] : [],
    }));
    getDb.mockReturnValue(fakeDb(many));

    const result = await computeActivation(60);

    expect(result.signups).toBe(1200);
    expect(result.activated).toBe(600);
  });

  it("drops unreadable users from the denominator instead of scoring them as not activated", async () => {
    getDb.mockReturnValue(
      fakeDb([
        { uid: "ok", signupOs: "macos", signupDaysAgo: 30, conversationOffsetsDays: [1] },
        { uid: "broken", signupOs: "macos", signupDaysAgo: 30, throwOnRead: true },
      ]),
    );

    const result = await computeActivation(60);

    // Counting the unreadable user would report 50% -- the same "absence of
    // evidence read as evidence of absence" mistake this metric exists to undo.
    expect(result.erroredUsers).toBe(1);
    expect(result.signups).toBe(1);
    expect(result.activated).toBe(1);
    expect(result.rate).toBe(100);
  });

  it("keeps a week's rate honest when only some of its users are unreadable", async () => {
    getDb.mockReturnValue(
      fakeDb([
        { uid: "a", signupOs: "macos", signupDaysAgo: 30, conversationOffsetsDays: [1] },
        { uid: "b", signupOs: "macos", signupDaysAgo: 30 },
        { uid: "c", signupOs: "macos", signupDaysAgo: 30, throwOnRead: true },
        { uid: "d", signupOs: "macos", signupDaysAgo: 30, throwOnRead: true },
      ]),
    );

    const result = await computeActivation(60);

    expect(result.erroredUsers).toBe(2);
    expect(result.weeks).toHaveLength(1);
    expect(result.weeks[0].signups).toBe(2);
    expect(result.weeks[0].rate).toBe(50);
  });
});
