import { NextRequest, NextResponse } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { testIdentity } from "./support/test-identity";

const posthogResults = vi.hoisted(() => vi.fn());
const fetchTelemetryAggregates = vi.hoisted(() => vi.fn());
const requireScope = vi.hoisted(() => vi.fn());

vi.mock("@/lib/auth", () => ({ requireScope }));
vi.mock("@/lib/posthog", () => ({ posthogResults }));
vi.mock("@/lib/telemetry/client", () => ({ fetchTelemetryAggregates }));
vi.mock("@/lib/firebase/admin", () => ({
  default: {
    firestore: { FieldPath: { documentId: () => "__name__" } },
  },
  getDb: () => ({
    collection: () => ({
      where: () => ({
        select: () => ({
          get: async () => ({ docs: [] }),
        }),
      }),
    }),
  }),
}));

describe("response reliability route", () => {
  beforeEach(() => {
    vi.resetModules();
    posthogResults.mockReset();
    fetchTelemetryAggregates.mockReset();
    requireScope.mockResolvedValue(testIdentity(undefined, "admin-1"));
    process.env.POSTHOG_PERSONAL_API_KEY = "ph";
    process.env.POSTHOG_PROJECT_ID = "1";
    delete process.env.RELIABILITY_REPLACEMENT_READER;
    delete process.env.RELIABILITY_REPLACEMENT_CUTOVER;
    posthogResults.mockResolvedValue([]);
    fetchTelemetryAggregates.mockResolvedValue({
      disposition: "unavailable",
      usable: false,
      body: null,
      code: "telemetry_unavailable",
      countThrough: null,
    });
  });

  it("rejects non-admins before reading telemetry", async () => {
    requireScope.mockResolvedValueOnce(
      NextResponse.json({ error: "Unauthorized" }, { status: 401 })
    );
    const { GET } = await import(
      "@/app/api/omi/stats/response-reliability/route"
    );
    const response = await GET(
      new NextRequest("http://local/api/omi/stats/response-reliability")
    );
    expect(response.status).toBe(401);
    expect(posthogResults).not.toHaveBeenCalled();
    expect(fetchTelemetryAggregates).not.toHaveBeenCalled();
  });

  it("does not call the replacement aggregate while the reader flag is off", async () => {
    const { GET } = await import(
      "@/app/api/omi/stats/response-reliability/route"
    );
    const response = await GET(
      new NextRequest("http://local/api/omi/stats/response-reliability?days=7")
    );
    expect(response.status).toBe(200);
    expect(fetchTelemetryAggregates).not.toHaveBeenCalled();
    expect(posthogResults).toHaveBeenCalledTimes(2);
  });

  it("calls the aggregate with the verified admin uid only after an explicit cutover", async () => {
    process.env.RELIABILITY_REPLACEMENT_READER = "on";
    process.env.RELIABILITY_REPLACEMENT_CUTOVER = "2026-10-10";
    const { GET } = await import(
      "@/app/api/omi/stats/response-reliability/route"
    );
    const response = await GET(
      new NextRequest("http://local/api/omi/stats/response-reliability?days=7")
    );
    expect(response.status).toBe(200);
    expect(fetchTelemetryAggregates).toHaveBeenCalledWith({
      adminUid: "admin-1",
      days: 7,
      channel: "all",
    });
    const body = await response.json();
    expect(body.availability.voice).toBe(false);
    expect(body.summary.voice).toBeNull();
    expect(body.partial).toBe(true);
  });
});
