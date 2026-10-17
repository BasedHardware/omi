import { expect, it, vi } from "vitest";
import { computeWall } from "../wall-metrics";
import { wallPresentation } from "../wall-presentation";
import { formatWallValue } from "../wall-card-svg";
import { queryPosthog } from "../wall-posthog";
const fail = async () => {
  throw new Error("missing");
};
it("formats wall money, percentages and counts for laptop/TV reading", () => {
  expect(formatWallValue(147953.69, "USD")).toBe("$148K");
  expect(formatWallValue(2039.01, "USD/day")).toBe("$2.04K");
  expect(formatWallValue(123.45, "USD")).toBe("$123");
  expect(formatWallValue(39.98, "USD")).toBe("$39.98");
  expect(formatWallValue(0.0041, "USD")).toBe("<$0.01");
  expect(formatWallValue(21.6062, "percent")).toBe("21.6%");
  expect(formatWallValue(4424, "people")).toBe("4,424");
  expect(formatWallValue(null, "people")).toBe("—");
});
it("receives a live HogQL execution timestamp and preserves an upstream cached refresh", async () => {
  vi.stubEnv("POSTHOG_PERSONAL_API_KEY", "fixture-key");
  vi.stubEnv("POSTHOG_PROJECT_ID", "fixture-project");
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce(
      new Response(JSON.stringify({ results: [[0, "macos", 3]] }))
    )
    .mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          results: [[0, "macos", 3]],
          last_refresh: "2026-10-14T00:00:00Z",
          is_cached: true,
        })
      )
    )
    .mockResolvedValueOnce(
      new Response(
        JSON.stringify({ results: [[0, "macos", 3]], is_cached: true })
      )
    );
  vi.stubGlobal("fetch", fetchMock);
  try {
    const before = Date.now();
    const rows = await queryPosthog("SELECT 1");
    expect(Date.parse(rows.sourceRefreshedAt!)).toBeGreaterThanOrEqual(before);
    expect((await queryPosthog("SELECT 1")).sourceRefreshedAt).toBe(
      "2026-10-14T00:00:00Z"
    );
    expect((await queryPosthog("SELECT 1")).sourceRefreshedAt).toBeNull();
  } finally {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
  }
});
it("keeps real healthy counts bright, all fixtures dim, and puts the complete metric in one SVG card", async () => {
  const now = new Date("2026-10-15T12:00Z");
  const data = await computeWall(
    {
      query: async () =>
        Object.assign(
          [
            [0, "macos", 4424],
            [1, "macos", 4082],
          ],
          { sourceRefreshedAt: now.toISOString() }
        ),
      shopify: fail,
      billing: fail,
      stripe: async () => ({
        usd: 39.98,
        partial: false,
        unmappedProducts: 0,
        unsupportedItems: 0,
        fixture: true,
        dataThrough: "2026-10-14",
        sourceRefreshedAt: now.toISOString(),
      }),
    },
    now
  );
  const view = wallPresentation(data, now);
  const count = view.tiles.growth_wau as Record<string, unknown>,
    money = view.tiles.revenue_mrr as Record<string, unknown>;
  expect(count.valueColor).toBe("#f4f7fc");
  expect(money.valueColor).toBe("#8190a6");
  expect(money.state).toBe("FIXTURE");
  const svg = String(count.cardSvg);
  expect(svg).toContain("<rect");
  expect(svg).toContain("Weekly active users");
  expect(svg).toContain("4,424");
  expect(svg).toContain("prior 7 days");
  expect(svg).toContain("macOS");
  expect(svg).toContain("<path");
  expect(svg).toContain("MCP-only");
  expect(svg).toContain("MCP marker not deployed");
  expect(svg).not.toMatch(
    /script|foreignObject|iframe|NO WATERMARK|\[Active\]/
  );
  expect(String(money.cardSvg)).toContain("FIXTURE");
  const cash = data.metrics.find(
    (m) => m.id === "revenue.plan_prepay_usd_week"
  )!;
  Object.assign(cash, {
    value: 41812.82,
    status: "proxy",
    partial: true,
    sourceRefreshedAt: now.toISOString(),
    dataThrough: "2026-10-11",
  });
  expect(
    wallPresentation(data, now).tiles.revenue_plan_prepay_usd_week
  ).toMatchObject({
    valueColor: "#8190a6",
    footnote: "Coverage incomplete · as of Oct 11",
  });
});
it("dims proxies with a material gap without dimming all proxy metrics", async () => {
  const now = new Date("2026-10-15T12:00Z");
  const data = await computeWall(
    {
      query: async () =>
        Object.assign([[0, "macos", 3]], {
          sourceRefreshedAt: now.toISOString(),
        }),
      shopify: fail,
      billing: fail,
      stripe: fail,
    },
    now
  );
  data.metrics[0].materialGap = true;
  expect(wallPresentation(data, now).tiles.growth_wau).toMatchObject({
    value: 3,
    valueColor: "#8190a6",
  });
  expect(wallPresentation(data, now).tiles.engagement_dau).toMatchObject({
    value: 3,
    valueColor: "#f4f7fc",
  });
});
